"""Collect order book histograms."""

from __future__ import annotations

import logging
from datetime import datetime

from steam_scanner.analytics.orderbook_metrics import compute_orderbook_metrics
from steam_scanner.config import PRIMARY_CURRENCY
from steam_scanner.db.models import MarketItem, OrderbookSnapshot
from steam_scanner.db.session import get_session
from steam_scanner.collectors.listing_parser import ListingParser
from steam_scanner.steam.endpoint_kind import SteamEndpoint
from steam_scanner.steam.client import STEAM_CLIENT_ABORT_ERRORS, SteamClient
from steam_scanner.steam.endpoints import item_orders_histogram
from steam_scanner.steam.parsers import parse_order_histogram

from steam_scanner.progress import ProgressTracker, log_budget

logger = logging.getLogger(__name__)


class OrderBookCollector:
    def __init__(self, client: SteamClient | None = None):
        self.client = client or SteamClient()
        self.listing_parser = ListingParser(client=self.client)

    def collect_for_item(self, item: MarketItem) -> OrderbookSnapshot | None:
        if not item.item_nameid:
            self.listing_parser.fetch_and_update(item)
            with get_session() as session:
                item = session.get(MarketItem, item.id)
                if not item or not item.item_nameid:
                    return None

        cfg = PRIMARY_CURRENCY
        url = item_orders_histogram(
            item_nameid=item.item_nameid,
            currency=cfg.steam_id,
            country=cfg.country,
        )

        raw = self.client.get_json(url, endpoint=SteamEndpoint.ORDERBOOK)
        parsed = parse_order_histogram(raw)

        if not parsed.get("success"):
            return None

        metrics = compute_orderbook_metrics(
            buy_graph=parsed["buy_order_graph"],
            sell_graph=parsed["sell_order_graph"],
            highest_buy=parsed["highest_buy_order"],
            lowest_sell=parsed["lowest_sell_order"],
        )

        with get_session() as session:
            snap = OrderbookSnapshot(
                market_item_id=item.id,
                currency_code="USD",
                country_code=cfg.country,
                highest_buy_order=float(parsed["highest_buy_order"]) if parsed["highest_buy_order"] else None,
                lowest_sell_order=float(parsed["lowest_sell_order"]) if parsed["lowest_sell_order"] else None,
                buy_order_count=parsed["buy_order_count"],
                sell_order_count=parsed["sell_order_count"],
                buy_order_graph=parsed["buy_order_graph"],
                sell_order_graph=parsed["sell_order_graph"],
                metrics=metrics,
                raw_response=raw,
                captured_at=datetime.utcnow(),
            )
            session.add(snap)
            session.flush()
            return snap

    def collect_batch(self, item_ids: list[int], limit: int | None = None) -> int:
        ids = item_ids[:limit] if limit else item_ids
        count = 0
        total = len(ids)
        progress = ProgressTracker("Orderbook scan", total, log_every_pct=2.0)
        logger.info("Orderbook scan: %d items queued (~2 req/item)", total)

        with get_session() as session:
            items = session.query(MarketItem).filter(MarketItem.id.in_(ids)).all()
            item_refs = list(items)

        for idx, item in enumerate(item_refs, 1):
            try:
                with get_session() as session:
                    db_item = session.get(MarketItem, item.id)
                    if not db_item:
                        continue
                    result = self.collect_for_item(db_item)
                    if result:
                        count += 1
                progress.update(
                    idx,
                    extra=f"ok={count}, req={self.client.requests_made}",
                )
                if idx % 25 == 0:
                    log_budget("Orderbook", self.client.requests_made, self.client.request_cap)
            except STEAM_CLIENT_ABORT_ERRORS:
                raise
            except Exception as exc:
                logger.warning("Orderbook failed for item %d: %s", item.id, exc)

        progress.finish(extra=f"collected={count}")
        return count
