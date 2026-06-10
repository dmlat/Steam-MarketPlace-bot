#!/usr/bin/env python3
"""Bulk item collection until target count or request cap (resumable)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func

from steam_scanner.checkpoints import clear_checkpoint, load_checkpoint, save_checkpoint
from steam_scanner.collectors.app_discovery import AppDiscovery
from steam_scanner.collectors.market_search import MarketSearchCollector
from steam_scanner.config import STEAM_NETWORK_MAX_WAIT_SEC
from steam_scanner.db.models import MarketItem
from steam_scanner.db.session import get_session
from steam_scanner.log_setup import configure_logging
from steam_scanner.progress import ProgressTracker, log_budget, pct
from steam_scanner.steam.client import NetworkOutageError, RateLimitCircuitOpenError, SteamClient

configure_logging()
logger = logging.getLogger(__name__)

CHECKPOINT_NAME = "bulk_collect"


def item_count() -> int:
    with get_session() as session:
        return session.query(func.count(MarketItem.id)).scalar() or 0


def card_count() -> int:
    with get_session() as session:
        return (
            session.query(func.count(MarketItem.id))
            .filter(MarketItem.is_card.is_(True))
            .scalar()
            or 0
        )


def run_bulk_collect(target: int, request_cap: int) -> None:
    cp = load_checkpoint(CHECKPOINT_NAME) or {}
    start_index = int(cp.get("game_index", 0))
    phase = cp.get("phase", "games")

    logger.info("=== Bulk collect: target=%d, request_cap=%d ===", target, request_cap)
    logger.info(
        "Start: items=%d, cards=%d, resume_index=%d, phase=%s",
        item_count(),
        card_count(),
        start_index,
        phase,
    )

    with SteamClient(request_cap=request_cap) as client:
        collector = MarketSearchCollector(client=client)
        discovery = AppDiscovery(client=client)
        appids = discovery.get_eligible_appids()
        logger.info("Games to scan: %d", len(appids))

        games_progress = ProgressTracker("Games", len(appids), log_every_pct=2.0)
        items_progress = ProgressTracker("Items->target", target, log_every_pct=2.0)

        if phase == "games":
            for i in range(start_index, len(appids)):
                if item_count() >= target:
                    logger.info("Item target reached: %d", item_count())
                    break
                if client.requests_made >= request_cap - 50:
                    logger.warning("Request cap almost exhausted")
                    save_checkpoint(CHECKPOINT_NAME, {
                        "phase": "games",
                        "game_index": i,
                        "target": target,
                        "request_cap": request_cap,
                    })
                    break

                appid = appids[i]
                try:
                    collector.collect_for_game(
                        appid,
                        item_classes=["tag_item_class_2", "tag_item_class_6"],
                        max_pages=3,
                    )
                except NetworkOutageError as exc:
                    logger.error(
                        "Network down >%.0fs. Checkpoint saved at game %d/%d. Re-run later.",
                        STEAM_NETWORK_MAX_WAIT_SEC,
                        i,
                        len(appids),
                    )
                    save_checkpoint(CHECKPOINT_NAME, {
                        "phase": "games",
                        "game_index": i,
                        "last_appid": appid,
                        "target": target,
                        "request_cap": request_cap,
                    })
                    raise SystemExit(2) from exc
                except RateLimitCircuitOpenError as exc:
                    logger.error(
                        "Steam rate limit circuit open at game %d/%d. Checkpoint saved.",
                        i,
                        len(appids),
                    )
                    save_checkpoint(CHECKPOINT_NAME, {
                        "phase": "games",
                        "game_index": i,
                        "last_appid": appid,
                        "target": target,
                        "request_cap": request_cap,
                    })
                    raise SystemExit(2) from exc

                save_checkpoint(CHECKPOINT_NAME, {
                    "phase": "games",
                    "game_index": i + 1,
                    "last_appid": appid,
                    "target": target,
                    "request_cap": request_cap,
                })

                games_progress.update(
                    i + 1,
                    extra=f"appid={appid}, items={item_count()}, cards={card_count()}",
                )
                items_progress.update(
                    min(item_count(), target),
                    extra=f"requests={client.requests_made}/{request_cap}",
                )
                if (i + 1) % 25 == 0:
                    log_budget("Steam API", client.requests_made, request_cap)

            games_progress.finish(extra=f"items={item_count()}")
            phase = "general_market"
            save_checkpoint(CHECKPOINT_NAME, {
                "phase": phase,
                "game_index": len(appids),
                "target": target,
                "request_cap": request_cap,
            })

        if phase == "general_market" and item_count() < target and client.requests_made < request_cap:
            remaining = target - item_count()
            logger.info(
                "=== Phase 2: general market (~%d to target, %.1f%% remaining) ===",
                remaining,
                pct(item_count(), target),
            )
            try:
                collector.collect_general_market(
                    max_items=remaining * 3,
                    progress_label="General market",
                )
            except NetworkOutageError:
                save_checkpoint(CHECKPOINT_NAME, {
                    "phase": "general_market",
                    "target": target,
                    "request_cap": request_cap,
                })
                raise
            except RateLimitCircuitOpenError:
                save_checkpoint(CHECKPOINT_NAME, {
                    "phase": "general_market",
                    "target": target,
                    "request_cap": request_cap,
                })
                raise SystemExit(2)

        final_items = item_count()
        items_progress.update(min(final_items, target), force=True)
        log_budget("Steam API total", client.requests_made, request_cap)
        logger.info(
            "=== Done: items=%d (%.1f%%), cards=%d, requests=%d ===",
            final_items,
            pct(final_items, target),
            card_count(),
            client.requests_made,
        )
        if final_items >= target:
            clear_checkpoint(CHECKPOINT_NAME)


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    request_cap = int(sys.argv[2]) if len(sys.argv) > 2 else 7000
    run_bulk_collect(target, request_cap)


if __name__ == "__main__":
    main()
