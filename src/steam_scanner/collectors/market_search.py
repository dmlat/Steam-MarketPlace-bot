"""Collect market items via Steam Market Search."""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urlencode

from sqlalchemy.dialects.postgresql import insert

from steam_scanner.config import EXCLUDED_APPIDS, MARKET_COMMUNITY_APPID
from steam_scanner.db.models import MarketItem
from steam_scanner.db.session import get_session
from steam_scanner.steam.endpoint_kind import SteamEndpoint
from steam_scanner.steam.client import SteamClient
from steam_scanner.steam.endpoints import market_search_for_game, market_search_render
from steam_scanner.steam.parsers import classify_item_type, parse_market_search_response

from steam_scanner.progress import ProgressTracker, log_budget

logger = logging.getLogger(__name__)

ITEM_CLASS_FILTERS = [
    "tag_item_class_2",   # Trading Card
    "tag_item_class_3",   # Emoticon
    "tag_item_class_4",   # Booster Pack
    "tag_item_class_5",   # Profile Background
    "tag_item_class_6",   # Foil Trading Card (variant)
]


class MarketSearchCollector:
    def __init__(self, client: SteamClient | None = None):
        self.client = client or SteamClient()

    def collect_for_game(
        self,
        game_appid: int,
        game_name: str | None = None,
        item_classes: list[str] | None = None,
        max_pages: int | None = None,
    ) -> int:
        if game_appid in EXCLUDED_APPIDS:
            return 0

        saved = 0
        classes = item_classes or ITEM_CLASS_FILTERS

        for item_class in classes:
            saved += self._collect_with_filter(
                game_appid=game_appid,
                game_name=game_name,
                item_class=item_class,
                max_pages=max_pages,
            )

        return saved

    def _collect_with_filter(
        self,
        game_appid: int,
        game_name: str | None,
        item_class: str,
        max_pages: int | None,
    ) -> int:
        saved = 0
        start = 0
        page = 0
        page_size = 100

        while True:
            if max_pages is not None and page >= max_pages:
                break

            extra = {
                f"category_{MARKET_COMMUNITY_APPID}_Game[]": f"tag_app_{game_appid}",
                f"category_{MARKET_COMMUNITY_APPID}_item_class[]": item_class,
            }
            url = market_search_render(
                appid=MARKET_COMMUNITY_APPID,
                start=start,
                count=page_size,
                extra_params=extra,
            )

            data = self.client.get_json_or_html(url, endpoint=SteamEndpoint.SEARCH)
            parsed = parse_market_search_response(data)
            items = parsed["items"]

            if not items:
                break

            saved += self._save_items(items, game_appid, game_name, item_class)

            actual_page_size = parsed.get("pagesize") or len(items) or 10
            total = parsed["total_count"]
            start += actual_page_size
            if start >= total:
                break
            page += 1

        return saved

    def collect_general_market(
        self,
        start_offset: int = 0,
        max_items: int | None = None,
        sort_column: str = "popular",
        progress_label: str = "General market",
    ) -> int:
        """Scan general appid=753 market without game filter."""
        saved = 0
        start = start_offset
        page_size = 100
        page_num = 0
        progress: ProgressTracker | None = None

        while True:
            if max_items is not None and saved >= max_items:
                break

            url = market_search_render(
                appid=MARKET_COMMUNITY_APPID,
                start=start,
                count=page_size,
                sort_column=sort_column,
            )
            data = self.client.get_json_or_html(url, endpoint=SteamEndpoint.SEARCH)
            parsed = parse_market_search_response(data)
            items = parsed["items"]

            if not items:
                break

            batch_saved = self._save_items(items, appid=None, game_name=None, item_class=None)
            saved += batch_saved
            page_num += 1

            actual_page_size = parsed.get("pagesize") or len(items) or 10
            total = parsed["total_count"]
            if progress is None and total > 0:
                est_pages = min(
                    (max_items or total) // max(actual_page_size, 1) + 1,
                    total // max(actual_page_size, 1) + 1,
                )
                progress = ProgressTracker(progress_label, est_pages, log_every_pct=5.0)

            if progress:
                progress.update(
                    page_num,
                    extra=f"start={start}, saved={saved}, req={self.client.requests_made}",
                )

            start += actual_page_size
            if start >= total:
                if progress:
                    progress.finish(extra=f"saved={saved}")
                break

            if page_num % 50 == 0:
                log_budget(progress_label, self.client.requests_made, self.client.request_cap)

        return saved

    def _save_items(
        self,
        items: list[dict],
        appid: int | None,
        game_name: str | None,
        item_class: str | None,
    ) -> int:
        count = 0
        with get_session() as session:
            for item in items:
                mhn = item["market_hash_name"]
                if any(tag in mhn for tag in []):
                    pass

                # Skip items from excluded games based on game name heuristics
                gn = item.get("game_name") or game_name or ""
                classification = classify_item_type(
                    mhn,
                    item_type=item.get("item_type") or item_class,
                    tags=[gn] if gn else [],
                )

                stmt = insert(MarketItem).values(
                    appid=appid,
                    market_appid=item.get("market_appid", MARKET_COMMUNITY_APPID),
                    market_hash_name=mhn,
                    item_name=item.get("item_name"),
                    item_type=item.get("item_type") or item_class,
                    game_name=item.get("game_name") or game_name,
                    category_game_tag=f"tag_app_{appid}" if appid else None,
                    market_url=item.get("market_url"),
                    marketable=item.get("marketable"),
                    tradable=item.get("tradable"),
                    commodity=item.get("commodity"),
                    **classification,
                    updated_at=datetime.utcnow(),
                ).on_conflict_do_update(
                    index_elements=["market_appid", "market_hash_name"],
                    set_={
                        "item_name": item.get("item_name"),
                        "game_name": item.get("game_name") or game_name,
                        "item_type": item.get("item_type") or item_class,
                        "market_url": item.get("market_url"),
                        "marketable": item.get("marketable"),
                        "tradable": item.get("tradable"),
                        "commodity": item.get("commodity"),
                        "updated_at": datetime.utcnow(),
                        **classification,
                    },
                )
                session.execute(stmt)
                count += 1
        return count

    def collect_all_games(
        self,
        appids: list[int],
        resume_from_appid: int | None = None,
        max_pages_per_game: int = 5,
    ) -> int:
        total = 0
        started = resume_from_appid is None
        eligible = [a for a in sorted(appids) if a not in EXCLUDED_APPIDS]
        progress = ProgressTracker("Market search games", len(eligible), log_every_pct=2.0)
        processed = 0

        with get_session() as session:
            from steam_scanner.db.models import App
            app_map = {
                a.appid: a.name
                for a in session.query(App).filter(App.appid.in_(appids)).all()
            }

        for appid in sorted(appids):
            if not started:
                if appid == resume_from_appid:
                    started = True
                else:
                    continue

            if appid in EXCLUDED_APPIDS:
                continue

            name = app_map.get(appid)
            batch = self.collect_for_game(appid, name, max_pages=max_pages_per_game)
            total += batch
            processed += 1
            progress.update(
                processed,
                extra=f"appid={appid}, batch={batch}, total_saved={total}, req={self.client.requests_made}",
            )

        progress.finish(extra=f"total_saved={total}")
        return total
