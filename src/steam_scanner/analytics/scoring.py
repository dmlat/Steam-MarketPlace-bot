"""Opportunity scoring engine."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import desc, func

from steam_scanner.analytics.data_quality import DataQualityStatus
from steam_scanner.analytics.fee_engine import calculate_fee, net_spread_after_fee, seller_receives_at_buyer_price
from steam_scanner.config import MIN_ORDER_COUNT, MIN_VOLUME
from steam_scanner.db.models import MarketItem, OpportunityScore, OrderbookSnapshot, PriceSnapshot
from steam_scanner.db.session import get_session
from steam_scanner.steam.endpoints import manual_check_url

logger = logging.getLogger(__name__)


class ScoringEngine:
    def score_item(
        self,
        item: MarketItem,
        price: PriceSnapshot | None,
        orderbook: OrderbookSnapshot | None,
    ) -> OpportunityScore | None:
        risk_flags: list[str] = []
        status = DataQualityStatus.OK

        if not price or price.lowest_price is None:
            status = DataQualityStatus.NO_PRICE
            risk_flags.append("NO_PRICE")
            return self._save_score(
                item, None, None, 0, 0, 0, 0, 0, 0, 0, risk_flags, status
            )

        lowest = Decimal(str(price.lowest_price))
        volume = price.volume or 0

        if volume < MIN_VOLUME:
            if lowest >= Decimal("1.00"):
                status = DataQualityStatus.HIGH_PRICE_LOW_VOLUME_WATCHLIST
                risk_flags.append("LOW_VOLUME_HIGH_PRICE")
            else:
                status = DataQualityStatus.LOW_LIQUIDITY
                risk_flags.append("LOW_VOLUME")

        highest_buy = None
        lowest_sell = lowest
        buy_count = 0
        sell_count = 0
        metrics = {}

        if orderbook:
            if orderbook.highest_buy_order:
                highest_buy = Decimal(str(orderbook.highest_buy_order))
            if orderbook.lowest_sell_order:
                lowest_sell = Decimal(str(orderbook.lowest_sell_order))
            buy_count = orderbook.buy_order_count or 0
            sell_count = orderbook.sell_order_count or 0
            metrics = orderbook.metrics or {}
        else:
            status = DataQualityStatus.NO_ORDERBOOK
            risk_flags.append("NO_ORDERBOOK")

        if buy_count < MIN_ORDER_COUNT:
            risk_flags.append("LOW_BUY_ORDERS")
        if sell_count < MIN_ORDER_COUNT:
            risk_flags.append("LOW_SELL_LISTINGS")

        net_spread_abs = Decimal(0)
        net_spread_pct = Decimal(0)

        if highest_buy and lowest_sell and highest_buy > 0:
            sell_receive = seller_receives_at_buyer_price(lowest_sell)
            net_spread_abs = sell_receive - highest_buy
            net_spread_pct = (net_spread_abs / highest_buy * 100).quantize(Decimal("0.01"))

            if net_spread_pct > 50 and volume < MIN_VOLUME:
                risk_flags.append("FAKE_SPREAD")
                if status == DataQualityStatus.OK:
                    status = DataQualityStatus.FAKE_SPREAD

        sell_wall = metrics.get("sell_wall_score", 0) or 0
        if sell_wall > 0.7:
            risk_flags.append("SELL_WALL")

        if lowest < Decimal("0.10"):
            risk_flags.append("LOW_PRICE")

        fee = calculate_fee(lowest_sell)
        if fee.effective_fee_pct > 20:
            risk_flags.append("HIGH_FEE")

        volume_score = min(volume / 100, 10.0)
        depth_score = min(
            (metrics.get("buy_depth_within_3_pct", 0) or 0) / 50, 10.0
        )
        competition_score = max(0, 10 - sell_count / 100)
        volatility_score = 0.0
        if price.median_price and price.lowest_price:
            med = Decimal(str(price.median_price))
            if med > 0:
                dev = abs(lowest - med) / med * 100
                volatility_score = float(min(dev, 50))

        price_tier_bonus = 0.0
        if lowest >= Decimal("1.00"):
            price_tier_bonus += 2.0
        if lowest >= Decimal("0.25"):
            price_tier_bonus += 1.0

        buy_depth_bonus = min((metrics.get("buy_depth_within_3_pct", 0) or 0) / 20, 3.0)

        low_volume_penalty = 5.0 if volume < MIN_VOLUME and status != DataQualityStatus.HIGH_PRICE_LOW_VOLUME_WATCHLIST else 0
        sell_wall_penalty = sell_wall * 5
        fee_penalty = float(fee.effective_fee_pct) / 10 if lowest < Decimal("0.25") else 0

        liquidity_score = volume_score + depth_score
        opportunity_score = (
            float(net_spread_pct) * liquidity_score / 10
            + price_tier_bonus
            + buy_depth_bonus
            - low_volume_penalty
            - sell_wall_penalty
            - volatility_score / 10
            - fee_penalty
        )

        if item.is_card and lowest >= Decimal("1.00"):
            opportunity_score += 1.0

        return self._save_score(
            item,
            float(lowest_sell),
            float(highest_buy) if highest_buy else None,
            float(net_spread_abs),
            float(net_spread_pct),
            volume_score,
            depth_score,
            competition_score,
            volatility_score,
            opportunity_score,
            risk_flags,
            status,
        )

    def _save_score(
        self,
        item: MarketItem,
        lowest_sell: float | None,
        highest_buy: float | None,
        net_spread_abs: float,
        net_spread_pct: float,
        volume_score: float,
        depth_score: float,
        competition_score: float,
        volatility_score: float,
        opportunity_score: float,
        risk_flags: list[str],
        status: str,
    ) -> OpportunityScore:
        with get_session() as session:
            score = OpportunityScore(
                market_item_id=item.id,
                currency_code="USD",
                lowest_sell_price=lowest_sell,
                highest_buy_order=highest_buy,
                net_spread_abs=net_spread_abs,
                net_spread_pct=net_spread_pct,
                volume_score=volume_score,
                depth_score=depth_score,
                competition_score=competition_score,
                volatility_score=volatility_score,
                opportunity_score=opportunity_score,
                risk_flags=risk_flags,
                data_quality_status=status,
                calculated_at=datetime.utcnow(),
            )
            session.add(score)

            db_item = session.get(MarketItem, item.id)
            if db_item:
                db_item.data_quality_status = status

            session.flush()
            return score

    def score_all(self, limit: int | None = None) -> int:
        count = 0
        with get_session() as session:
            items = session.query(MarketItem).order_by(MarketItem.id)
            if limit:
                items = items.limit(limit)
            item_ids = [i.id for i in items.all()]

        for item_id in item_ids:
            with get_session() as session:
                item = session.get(MarketItem, item_id)
                if not item:
                    continue

                price = (
                    session.query(PriceSnapshot)
                    .filter(PriceSnapshot.market_item_id == item_id, PriceSnapshot.currency_code == "USD")
                    .order_by(desc(PriceSnapshot.captured_at))
                    .first()
                )

                orderbook = (
                    session.query(OrderbookSnapshot)
                    .filter(OrderbookSnapshot.market_item_id == item_id)
                    .order_by(desc(OrderbookSnapshot.captured_at))
                    .first()
                )

                self.score_item(item, price, orderbook)
                count += 1

        logger.info("Scored %d items", count)
        return count

    @staticmethod
    def get_top_opportunities(limit: int = 100) -> list[dict]:
        with get_session() as session:
            subq = (
                session.query(
                    OpportunityScore.market_item_id,
                    func.max(OpportunityScore.calculated_at).label("max_at"),
                )
                .group_by(OpportunityScore.market_item_id)
                .subquery()
            )

            rows = (
                session.query(OpportunityScore, MarketItem)
                .join(MarketItem, OpportunityScore.market_item_id == MarketItem.id)
                .join(
                    subq,
                    (OpportunityScore.market_item_id == subq.c.market_item_id)
                    & (OpportunityScore.calculated_at == subq.c.max_at),
                )
                .filter(
                    OpportunityScore.data_quality_status.in_(
                        list(DataQualityStatus.VALID_FOR_CONCLUSIONS)
                    )
                )
                .order_by(desc(OpportunityScore.opportunity_score))
                .limit(limit)
                .all()
            )

            results = []
            for score, item in rows:
                results.append({
                    "market_item_id": item.id,
                    "appid": item.appid,
                    "game_name": item.game_name,
                    "market_hash_name": item.market_hash_name,
                    "item_type": item.item_type,
                    "is_card": item.is_card,
                    "is_foil": item.is_foil,
                    "lowest_sell_price": score.lowest_sell_price,
                    "highest_buy_order": score.highest_buy_order,
                    "net_spread_pct": score.net_spread_pct,
                    "opportunity_score": score.opportunity_score,
                    "risk_flags": score.risk_flags,
                    "manual_check_url": manual_check_url(item.market_appid, item.market_hash_name),
                })
            return results
