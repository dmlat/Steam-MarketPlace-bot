"""Discover games with Trading Cards via Steam Store Search."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert

from steam_scanner.config import EXCLUDED_APPIDS
from steam_scanner.db.models import App
from steam_scanner.db.session import get_session
from steam_scanner.steam.endpoint_kind import SteamEndpoint
from steam_scanner.steam.client import SteamClient
from steam_scanner.steam.endpoints import store_search_trading_cards
from steam_scanner.steam.parsers import parse_store_search_html

from steam_scanner.progress import ProgressTracker

logger = logging.getLogger(__name__)


class AppDiscovery:
    def __init__(self, client: SteamClient | None = None):
        self.client = client or SteamClient()

    def discover_all(self, page_size: int = 50, max_pages: int | None = None) -> int:
        """Discover games with trading cards and upsert into apps table."""
        total_saved = 0
        start = 0
        page = 0
        progress: ProgressTracker | None = None

        while True:
            if max_pages is not None and page >= max_pages:
                break

            url = store_search_trading_cards(start=start, count=page_size)
            html = self.client.get_text(url, endpoint=SteamEndpoint.STORE)
            games = parse_store_search_html(html)

            if not games:
                break

            if progress is None:
                est = max_pages * page_size if max_pages else page_size * 50
                progress = ProgressTracker("Discovery (Store)", est, log_every_pct=5.0)

            with get_session() as session:
                for game in games:
                    appid = game["appid"]
                    is_excluded = appid in EXCLUDED_APPIDS
                    exclude_reason = None
                    if is_excluded:
                        exclude_reason = f"Excluded appid {appid}"

                    stmt = insert(App).values(
                        appid=appid,
                        name=game.get("name"),
                        has_trading_cards=True,
                        is_excluded=is_excluded,
                        exclude_reason=exclude_reason,
                        source="store_search_category2_29",
                        updated_at=datetime.utcnow(),
                    ).on_conflict_do_update(
                        index_elements=["appid"],
                        set_={
                            "name": game.get("name"),
                            "has_trading_cards": True,
                            "is_excluded": is_excluded,
                            "exclude_reason": exclude_reason,
                            "updated_at": datetime.utcnow(),
                        },
                    )
                    session.execute(stmt)
                    total_saved += 1

            page += 1
            if progress:
                progress.update(
                    total_saved,
                    extra=f"page={page}, start={start}",
                )

            if len(games) < page_size:
                break

            start += page_size

        if progress:
            progress.finish(extra=f"apps={total_saved}")
        logger.info("Discovered %d apps", total_saved)
        return total_saved

    def get_eligible_appids(self) -> list[int]:
        with get_session() as session:
            rows = session.query(App.appid).filter(
                App.has_trading_cards.is_(True),
                App.is_excluded.is_(False),
            ).all()
            return [r[0] for r in rows]
