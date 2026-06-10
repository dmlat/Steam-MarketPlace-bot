"""Collect price overview snapshots."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import desc, exists, func

from steam_scanner.config import CURRENCIES, MIN_PRICE_USD, MIN_VOLUME, PRIMARY_CURRENCY
from steam_scanner.db.models import MarketItem, PriceSnapshot
from steam_scanner.db.session import get_session
from steam_scanner.steam.endpoint_kind import SteamEndpoint
from steam_scanner.steam.client import STEAM_CLIENT_ABORT_ERRORS, SteamClient
from steam_scanner.steam.parallel import ParallelSteamClient, run_parallel_lanes
from steam_scanner.steam.endpoints import price_overview
from steam_scanner.progress import ProgressTracker, log_budget
from steam_scanner.steam.parsers import parse_price_overview

logger = logging.getLogger(__name__)


class PriceOverviewCollector:
    def __init__(self, client: SteamClient | ParallelSteamClient | None = None):
        self.client = client or SteamClient()

    def _scan_one(self, client: SteamClient, item_id: int, currency_code: str) -> bool:
        with get_session() as session:
            item = session.get(MarketItem, item_id)
            if not item:
                return False
            cfg = CURRENCIES.get(currency_code, PRIMARY_CURRENCY)
            url = price_overview(
                market_hash_name=item.market_hash_name,
                appid=item.market_appid,
                currency=cfg.steam_id,
                country=cfg.country,
            )
            raw = client.get_json(url, endpoint=SteamEndpoint.PRICE)
            parsed = parse_price_overview(raw)
            if not parsed.get("success") and not parsed.get("lowest_price"):
                return False
            snap = PriceSnapshot(
                market_item_id=item.id,
                currency_code=currency_code,
                country_code=cfg.country,
                lowest_price=float(parsed["lowest_price"]) if parsed["lowest_price"] else None,
                median_price=float(parsed["median_price"]) if parsed["median_price"] else None,
                volume=parsed["volume"],
                raw_response=raw,
                captured_at=datetime.utcnow(),
            )
            session.add(snap)
            return True

    @staticmethod
    def _queue_item_ids(
        *,
        limit: int | None,
        currency_code: str,
        skip_already_priced: bool,
        resume_from_id: int | None,
    ) -> tuple[list[int], int]:
        """Build scan queue: first `limit` catalog items minus already priced."""
        with get_session() as session:
            window = session.query(MarketItem.id.label("id")).order_by(MarketItem.id)
            if resume_from_id and not skip_already_priced:
                window = window.filter(MarketItem.id > resume_from_id)
            if limit:
                window = window.limit(limit)
            window_sq = window.subquery()

            q = session.query(window_sq.c.id)
            skipped = 0
            if skip_already_priced:
                has_price = exists().where(
                    PriceSnapshot.market_item_id == window_sq.c.id,
                    PriceSnapshot.currency_code == currency_code,
                )
                skipped = q.filter(has_price).count()
                q = q.filter(~has_price)

            item_ids = [row[0] for row in q.order_by(window_sq.c.id).all()]
            return item_ids, skipped

    def scan_item(
        self,
        market_item: MarketItem,
        currency_code: str = "USD",
    ) -> PriceSnapshot | None:
        cfg = CURRENCIES.get(currency_code, PRIMARY_CURRENCY)
        url = price_overview(
            market_hash_name=market_item.market_hash_name,
            appid=market_item.market_appid,
            currency=cfg.steam_id,
            country=cfg.country,
        )

        raw = self.client.get_json(url, endpoint=SteamEndpoint.PRICE)
        parsed = parse_price_overview(raw)

        if not parsed.get("success") and not parsed.get("lowest_price"):
            return None

        with get_session() as session:
            snap = PriceSnapshot(
                market_item_id=market_item.id,
                currency_code=currency_code,
                country_code=cfg.country,
                lowest_price=float(parsed["lowest_price"]) if parsed["lowest_price"] else None,
                median_price=float(parsed["median_price"]) if parsed["median_price"] else None,
                volume=parsed["volume"],
                raw_response=raw,
                captured_at=datetime.utcnow(),
            )
            session.add(snap)
            session.flush()
            return snap

    def scan_all(
        self,
        limit: int | None = None,
        resume_from_id: int | None = None,
        currency_code: str = "USD",
        batch_size: int = 50,
        skip_already_priced: bool = True,
    ) -> int:
        item_ids, skipped = self._queue_item_ids(
            limit=limit,
            currency_code=currency_code,
            skip_already_priced=skip_already_priced,
            resume_from_id=resume_from_id,
        )

        if not item_ids:
            if skip_already_priced and skipped:
                logger.info(
                    "Price scan: all %d items in scope already priced (%s), nothing to do",
                    skipped,
                    currency_code,
                )
            else:
                logger.info("Price scan: no items queued")
            return 0

        if skip_already_priced and skipped:
            logger.info(
                "Price scan: %d items queued, %d already priced (%s) skipped",
                len(item_ids),
                skipped,
                currency_code,
            )
        else:
            logger.info("Price scan: %d items queued", len(item_ids))

        count = 0
        total = len(item_ids)
        progress = ProgressTracker("Price scan", total, log_every_pct=2.0)

        if isinstance(self.client, ParallelSteamClient):
            return run_parallel_lanes(
                item_ids,
                self.client.lanes,
                lambda c, iid: self._scan_one(c, iid, currency_code),
                label="Price scan",
                log_every_pct=2.0,
                request_cap=self.client.request_cap,
            )

        for i in range(0, len(item_ids), batch_size):
            batch = item_ids[i : i + batch_size]
            with get_session() as session:
                items = session.query(MarketItem).filter(MarketItem.id.in_(batch)).all()
                for item in items:
                    try:
                        if self._scan_one(self.client, item.id, currency_code):
                            count += 1
                    except STEAM_CLIENT_ABORT_ERRORS:
                        raise
                    except Exception as exc:
                        logger.warning("Price scan failed for %s: %s", item.market_hash_name, exc)
            progress.update(
                min(count, total),
                extra=f"batch={i // batch_size + 1}, req={self.client.requests_made}",
            )
            if count and count % 200 == 0:
                log_budget("Price scan", self.client.requests_made, self.client.request_cap)

        progress.finish(extra=f"scanned={count}")
        return count

    @staticmethod
    def get_short_list(
        min_price: Decimal = MIN_PRICE_USD,
        min_volume: int = MIN_VOLUME,
        limit: int = 2000,
        prioritize_cards: bool = True,
    ) -> list[int]:
        """Return market_item IDs eligible for orderbook scan."""
        with get_session() as session:
            subq = (
                session.query(
                    PriceSnapshot.market_item_id,
                    func.max(PriceSnapshot.captured_at).label("max_at"),
                )
                .filter(PriceSnapshot.currency_code == "USD")
                .group_by(PriceSnapshot.market_item_id)
                .subquery()
            )

            q = (
                session.query(MarketItem.id, PriceSnapshot.lowest_price, PriceSnapshot.volume)
                .join(PriceSnapshot, MarketItem.id == PriceSnapshot.market_item_id)
                .join(
                    subq,
                    (PriceSnapshot.market_item_id == subq.c.market_item_id)
                    & (PriceSnapshot.captured_at == subq.c.max_at),
                )
                .filter(PriceSnapshot.currency_code == "USD")
                .filter(PriceSnapshot.lowest_price >= float(min_price))
                .filter(PriceSnapshot.volume >= min_volume)
            )

            if prioritize_cards:
                q = q.order_by(
                    desc(MarketItem.is_card),
                    desc(MarketItem.is_foil),
                    desc(PriceSnapshot.volume),
                )
            else:
                q = q.order_by(desc(PriceSnapshot.volume))

            rows = q.limit(limit).all()
            return [r[0] for r in rows]

    @staticmethod
    def get_latest_price(item_id: int, currency: str = "USD") -> PriceSnapshot | None:
        with get_session() as session:
            return (
                session.query(PriceSnapshot)
                .filter(
                    PriceSnapshot.market_item_id == item_id,
                    PriceSnapshot.currency_code == currency,
                )
                .order_by(desc(PriceSnapshot.captured_at))
                .first()
            )
