"""Parse listing pages for item_nameid and metadata."""

from __future__ import annotations

import logging
from datetime import datetime

from steam_scanner.analytics.data_quality import DataQualityStatus
from steam_scanner.db.models import MarketItem
from steam_scanner.db.session import get_session
from steam_scanner.steam.endpoint_kind import SteamEndpoint
from steam_scanner.steam.client import STEAM_CLIENT_ABORT_ERRORS, SteamClient
from steam_scanner.steam.endpoints import listing_page
from steam_scanner.steam.parsers import parse_listing_page

logger = logging.getLogger(__name__)


class ListingParser:
    def __init__(self, client: SteamClient | None = None):
        self.client = client or SteamClient()

    def fetch_and_update(self, item: MarketItem) -> dict | None:
        url = listing_page(item.market_appid, item.market_hash_name)
        html = self.client.get_text(url, endpoint=SteamEndpoint.LISTING)
        parsed = parse_listing_page(html)

        with get_session() as session:
            db_item = session.get(MarketItem, item.id)
            if not db_item:
                return None

            db_item.item_nameid = parsed.get("item_nameid")
            db_item.marketable = parsed.get("marketable")
            db_item.tradable = parsed.get("tradable")
            db_item.commodity = parsed.get("commodity")
            db_item.market_url = url
            db_item.updated_at = datetime.utcnow()

            if not db_item.item_nameid:
                db_item.data_quality_status = DataQualityStatus.NO_ITEM_NAMEID
            else:
                db_item.data_quality_status = DataQualityStatus.OK

            session.flush()

        return parsed

    def fetch_batch(self, item_ids: list[int]) -> int:
        success = 0
        with get_session() as session:
            items = session.query(MarketItem).filter(MarketItem.id.in_(item_ids)).all()
            item_refs = [(i.id, i.market_appid, i.market_hash_name) for i in items]

        for item_id, market_appid, mhn in item_refs:
            with get_session() as session:
                item = session.get(MarketItem, item_id)
                if not item:
                    continue
                try:
                    result = self.fetch_and_update(item)
                    if result and result.get("item_nameid"):
                        success += 1
                except STEAM_CLIENT_ABORT_ERRORS:
                    raise
                except Exception as exc:
                    logger.warning("Listing parse failed for %s: %s", mhn, exc)
                    item.data_quality_status = DataQualityStatus.PARSING_ERROR

        return success
