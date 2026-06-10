"""CSV/Excel export and final report generation."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import desc, func

from steam_scanner.analytics.fee_engine import build_fee_table
from steam_scanner.analytics.scoring import ScoringEngine
from steam_scanner.db.models import (
    App,
    CurrencyAnalysis,
    MarketItem,
    OpportunityScore,
    OrderbookSnapshot,
    PriceSnapshot,
)
from steam_scanner.db.session import get_session
from steam_scanner.steam.endpoints import manual_check_url

logger = logging.getLogger(__name__)

EXPORT_DIR = Path(__file__).resolve().parents[3] / "exports"


def _ensure_export_dir() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR


def export_market_items() -> Path:
    with get_session() as session:
        rows = session.query(MarketItem).all()
        data = [{
            "id": r.id,
            "appid": r.appid,
            "market_appid": r.market_appid,
            "market_hash_name": r.market_hash_name,
            "item_name": r.item_name,
            "item_type": r.item_type,
            "game_name": r.game_name,
            "is_card": r.is_card,
            "is_foil": r.is_foil,
            "is_booster": r.is_booster,
            "is_background": r.is_background,
            "is_emoticon": r.is_emoticon,
            "item_nameid": r.item_nameid,
            "data_quality_status": r.data_quality_status,
            "market_url": r.market_url,
        } for r in rows]
    path = _ensure_export_dir() / "market_items.csv"
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def export_price_snapshots() -> Path:
    with get_session() as session:
        rows = session.query(PriceSnapshot).order_by(desc(PriceSnapshot.captured_at)).limit(50000).all()
        data = [{
            "market_item_id": r.market_item_id,
            "currency_code": r.currency_code,
            "lowest_price": float(r.lowest_price) if r.lowest_price else None,
            "median_price": float(r.median_price) if r.median_price else None,
            "volume": r.volume,
            "captured_at": r.captured_at,
        } for r in rows]
    path = _ensure_export_dir() / "price_snapshots.csv"
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def export_orderbook_snapshots() -> Path:
    with get_session() as session:
        rows = session.query(OrderbookSnapshot).order_by(desc(OrderbookSnapshot.captured_at)).limit(10000).all()
        data = [{
            "market_item_id": r.market_item_id,
            "highest_buy_order": float(r.highest_buy_order) if r.highest_buy_order else None,
            "lowest_sell_order": float(r.lowest_sell_order) if r.lowest_sell_order else None,
            "buy_order_count": r.buy_order_count,
            "sell_order_count": r.sell_order_count,
            "metrics": r.metrics,
            "captured_at": r.captured_at,
        } for r in rows]
    path = _ensure_export_dir() / "orderbook_snapshots.csv"
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def export_currency_analysis() -> Path:
    with get_session() as session:
        rows = session.query(CurrencyAnalysis).all()
        data = [{
            "market_item_id": r.market_item_id,
            "price_usd": r.price_usd,
            "price_eur": r.price_eur,
            "price_rub": r.price_rub,
            "price_gbp": r.price_gbp,
            "price_brl": r.price_brl,
            "price_cny": r.price_cny,
            "implied_usd_eur": r.implied_usd_eur,
            "implied_usd_rub": r.implied_usd_rub,
            "rounding_anomaly": r.rounding_anomaly,
        } for r in rows]
    path = _ensure_export_dir() / "currency_analysis.csv"
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def export_fee_model() -> Path:
    rows = build_fee_table()
    path = _ensure_export_dir() / "fee_model.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def export_opportunities() -> Path:
    """Export final table per §23."""
    with get_session() as session:
        subq = (
            session.query(
                OpportunityScore.market_item_id,
                func.max(OpportunityScore.calculated_at).label("max_at"),
            )
            .group_by(OpportunityScore.market_item_id)
            .subquery()
        )

        latest_price = (
            session.query(
                PriceSnapshot.market_item_id,
                func.max(PriceSnapshot.captured_at).label("max_at"),
            )
            .filter(PriceSnapshot.currency_code == "USD")
            .group_by(PriceSnapshot.market_item_id)
            .subquery()
        )

        rows = (
            session.query(OpportunityScore, MarketItem, PriceSnapshot, OrderbookSnapshot, CurrencyAnalysis)
            .join(MarketItem, OpportunityScore.market_item_id == MarketItem.id)
            .join(subq, (OpportunityScore.market_item_id == subq.c.market_item_id)
                  & (OpportunityScore.calculated_at == subq.c.max_at))
            .outerjoin(PriceSnapshot, MarketItem.id == PriceSnapshot.market_item_id)
            .outerjoin(latest_price, (PriceSnapshot.market_item_id == latest_price.c.market_item_id)
                       & (PriceSnapshot.captured_at == latest_price.c.max_at))
            .outerjoin(
                OrderbookSnapshot,
                MarketItem.id == OrderbookSnapshot.market_item_id,
            )
            .outerjoin(CurrencyAnalysis, MarketItem.id == CurrencyAnalysis.market_item_id)
            .order_by(desc(OpportunityScore.opportunity_score))
            .limit(5000)
            .all()
        )

        data = []
        seen = set()
        for score, item, price, ob, curr in rows:
            if item.id in seen:
                continue
            seen.add(item.id)

            metrics = (ob.metrics or {}) if ob else {}
            data.append({
                "appid": item.appid,
                "game_name": item.game_name,
                "market_appid": item.market_appid,
                "market_hash_name": item.market_hash_name,
                "item_type": item.item_type,
                "is_card": item.is_card,
                "is_foil": item.is_foil,
                "is_booster": item.is_booster,
                "is_background": item.is_background,
                "is_emoticon": item.is_emoticon,
                "lowest_price_usd": float(price.lowest_price) if price and price.lowest_price else None,
                "median_price_usd": float(price.median_price) if price and price.median_price else None,
                "volume": price.volume if price else None,
                "highest_buy_order_usd": score.highest_buy_order,
                "lowest_sell_order_usd": score.lowest_sell_price,
                "net_spread_usd": score.net_spread_abs,
                "net_spread_pct": score.net_spread_pct,
                "buy_order_count": ob.buy_order_count if ob else None,
                "sell_order_count": ob.sell_order_count if ob else None,
                "buy_depth_near_top": metrics.get("buy_depth_within_3_pct"),
                "sell_depth_near_top": metrics.get("sell_depth_within_3_pct"),
                "currency_usd": curr.price_usd if curr else None,
                "currency_eur": curr.price_eur if curr else None,
                "currency_rub": curr.price_rub if curr else None,
                "implied_usd_rub": curr.implied_usd_rub if curr else None,
                "implied_usd_eur": curr.implied_usd_eur if curr else None,
                "opportunity_score": score.opportunity_score,
                "risk_flags": ",".join(score.risk_flags or []),
                "manual_check_url": manual_check_url(item.market_appid, item.market_hash_name),
                "last_checked_at": score.calculated_at,
            })

    path = _ensure_export_dir() / "opportunities.csv"
    pd.DataFrame(data).to_csv(path, index=False)

    xlsx_path = _ensure_export_dir() / "opportunities.xlsx"
    pd.DataFrame(data).to_excel(xlsx_path, index=False)
    return path


def generate_final_report() -> Path:
    with get_session() as session:
        total_apps = session.query(func.count(App.appid)).scalar() or 0
        total_items = session.query(func.count(MarketItem.id)).scalar() or 0
        total_cards = session.query(func.count(MarketItem.id)).filter(MarketItem.is_card.is_(True)).scalar() or 0
        cards_above_1 = (
            session.query(func.count(MarketItem.id))
            .join(PriceSnapshot, MarketItem.id == PriceSnapshot.market_item_id)
            .filter(MarketItem.is_card.is_(True), PriceSnapshot.lowest_price >= 1.0)
            .scalar() or 0
        )
        orderbook_count = session.query(func.count(OrderbookSnapshot.id)).scalar() or 0
        positive_spread = (
            session.query(func.count(OpportunityScore.id))
            .filter(OpportunityScore.net_spread_pct > 0)
            .scalar() or 0
        )
        currency_rows = session.query(func.count(CurrencyAnalysis.id)).scalar() or 0
        anomalies = (
            session.query(func.count(CurrencyAnalysis.id))
            .filter(CurrencyAnalysis.rounding_anomaly.is_(True))
            .scalar() or 0
        )

    top = ScoringEngine.get_top_opportunities(20)

    report = f"""# Steam Market Research Scanner — Final Report

Generated: {datetime.utcnow().isoformat()} UTC

## 1. Markets and items researched

- Apps discovered: {total_apps}
- Market items collected: {total_items}
- Trading cards: {total_cards}
- Cards above $1.00: {cards_above_1}
- Order book snapshots: {orderbook_count}

## 2. Most promising categories

Review top opportunities by item type in `opportunities.csv`. Cards above $1.00 and foil cards
are prioritized in scoring.

## 3. Cards above $1.00

{cards_above_1} cards have lowest price >= $1.00. See Cards Research tab and
`cards_price_1_to_3` / `cards_price_above_5` filters.

## 4. Best net spread by item type

See opportunities export grouped by `item_type`, `is_card`, `is_foil`.

## 5. Fake spreads

Items flagged `FAKE_SPREAD` have high spread but insufficient volume/depth.

## 6. Fee impact on cheap items

See `fee_model.csv` — effective fee exceeds 50% below $0.10 for typical 15% total fee structure.

## 7. Price level where fee stops killing margin

Typically $0.25–$0.50 depending on publisher fee; see fee table `required_growth_to_break_even_pct`.

## 8. Currency discrepancies

- Currency analyses: {currency_rows}
- Rounding anomalies detected: {anomalies}
- Analysis purpose: Steam internal rounding only, not cross-region trading.

## 9. Watchlist candidates

Items with status `HIGH_PRICE_LOW_VOLUME_WATCHLIST` in opportunities export.

## 10. Items to exclude

Excluded appids: 730, 440, 570, 252490. Items with `EXCLUDED_APP`, `PARSING_ERROR`, `FAKE_SPREAD`.

## 11. Next data to collect

- More frequent price snapshots for volume trend estimation (7d/30d)
- Extended order book history for wall detection
- Publisher fee verification per game

## Summary metrics

- Items with positive net spread: {positive_spread}
- Top 20 opportunities listed below

### Top opportunities

"""
    for i, opp in enumerate(top, 1):
        report += (
            f"{i}. **{opp['market_hash_name']}** ({opp['game_name']}) — "
            f"score={opp['opportunity_score']:.2f}, net_spread={opp['net_spread_pct']}%, "
            f"[check]({opp['manual_check_url']})\n"
        )

    path = _ensure_export_dir() / "final_report.md"
    path.write_text(report, encoding="utf-8")
    return path


def export_all() -> dict[str, Path]:
    paths = {
        "market_items": export_market_items(),
        "price_snapshots": export_price_snapshots(),
        "orderbook_snapshots": export_orderbook_snapshots(),
        "currency_analysis": export_currency_analysis(),
        "fee_model": export_fee_model(),
        "opportunities": export_opportunities(),
        "final_report": generate_final_report(),
    }
    logger.info("Exported to %s", EXPORT_DIR)
    return paths
