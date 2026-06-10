#!/usr/bin/env python3
"""Continue MVP collection + analytics (resumable, network-tolerant)."""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func

from steam_scanner.db.models import MarketItem, PriceSnapshot
from steam_scanner.db.session import get_session
from steam_scanner.log_setup import configure_logging
from steam_scanner.pipeline.runner import PipelineRunner
from steam_scanner.progress import pct, pct_remaining
from steam_scanner.steam.client import NetworkOutageError, RateLimitCircuitOpenError

configure_logging()
logger = logging.getLogger(__name__)

TARGET_ITEMS = 10000


def counts() -> dict:
    with get_session() as session:
        return {
            "items": session.query(func.count(MarketItem.id)).scalar() or 0,
            "prices": session.query(func.count(PriceSnapshot.id)).scalar() or 0,
        }


def main():
    request_cap = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    c = counts()
    logger.info(
        "Start continue: items=%d (%.1f%% of target), prices=%d",
        c["items"],
        pct(c["items"], TARGET_ITEMS),
        c["prices"],
    )

    if c["items"] < TARGET_ITEMS:
        logger.info(
            "=== Phase 1: collect (need %d more, %.1f%% remaining) ===",
            TARGET_ITEMS - c["items"],
            pct_remaining(c["items"], TARGET_ITEMS),
        )
        sys.path.insert(0, str(ROOT / "scripts"))
        from run_bulk_collect import run_bulk_collect

        try:
            run_bulk_collect(TARGET_ITEMS, max(1000, request_cap // 2))
        except RateLimitCircuitOpenError as exc:
            logger.warning(
                "Collection paused (Steam rate limit): %s Re-run in a few hours.",
                exc,
            )
            sys.exit(2)
        except SystemExit as exc:
            if exc.code == 2:
                logger.warning(
                    "Collection paused (network). Data saved. Re-run: .\\scripts\\run.ps1 continue"
                )
                sys.exit(2)
            raise

        c = counts()
        logger.info("After collect: items=%d (%.1f%%)", c["items"], pct(c["items"], TARGET_ITEMS))

    logger.info("=== Phase 2: analytics ===")
    runner = PipelineRunner(resume=True, request_cap=request_cap)
    try:
        try:
            runner.run_price_scan(limit=min(c["items"], 10000))
            runner.run_orderbook_scan(limit=500)
            runner.run_currency_scan(limit=200)
            runner.run_fee_calc()
            runner.run_scoring()
            paths = runner.run_export()
            logger.info("Export: %s", paths)
        except NetworkOutageError:
            logger.warning(
                "Analytics paused (network). Re-run to resume from checkpoint."
            )
            sys.exit(2)
        except RateLimitCircuitOpenError as exc:
            logger.warning(
                "Analytics paused (Steam rate limit): %s Re-run in a few hours.",
                exc,
            )
            sys.exit(2)
    finally:
        runner.client.close()

    final = counts()
    logger.info("=== Done: items=%d, prices=%d ===", final["items"], final["prices"])


if __name__ == "__main__":
    main()
