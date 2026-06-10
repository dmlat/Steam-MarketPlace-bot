#!/usr/bin/env python3
"""Health snapshot for collector (default: last 30 minutes)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func

from steam_scanner.config import STEAM_PROXY_URLS
from steam_scanner.db.models import MarketItem, PipelineRun, PriceSnapshot
from steam_scanner.db.session import get_session
from steam_scanner.steam.proxy_pool import mask_proxy_url


def _collector_running() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "run_continue.py"],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(r.stdout.strip())
    except FileNotFoundError:
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Steam scanner status")
    p.add_argument("--minutes", type=int, default=30)
    args = p.parse_args()
    since = datetime.utcnow() - timedelta(minutes=args.minutes)

    with get_session() as s:
        items = s.query(func.count(MarketItem.id)).scalar() or 0
        prices = s.query(func.count(PriceSnapshot.id)).scalar() or 0
        priced = s.query(func.count(func.distinct(PriceSnapshot.market_item_id))).scalar() or 0
        recent = (
            s.query(func.count(PriceSnapshot.id))
            .filter(PriceSnapshot.captured_at >= since)
            .scalar()
            or 0
        )
        last_snap = s.query(func.max(PriceSnapshot.captured_at)).scalar()
        run = (
            s.query(PipelineRun)
            .filter(PipelineRun.status == "running")
            .order_by(PipelineRun.id.desc())
            .first()
        )

    log_path = ROOT / "logs" / "continue.log"
    last_log = ""
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        last_log = lines[-1] if lines else ""

    print(f"=== Steam Scanner Status (last {args.minutes} min) ===")
    print(f"Time UTC: {datetime.utcnow().isoformat(timespec='seconds')}")
    print(f"Collector: {'running' if _collector_running() else 'stopped'}")
    print(f"Items: {items} | Price snapshots: {prices} | Unique priced: {priced}")
    print(f"New snapshots ({args.minutes}m): {recent}")
    print(f"Last snapshot: {last_snap}")
    if run:
        print(f"Pipeline stage: {run.stage} (running since {run.started_at})")
    print(f"Proxies configured: {len(STEAM_PROXY_URLS)}")
    for i, u in enumerate(STEAM_PROXY_URLS, 1):
        print(f"  proxy {i}: {mask_proxy_url(u)}")
    if last_log:
        print(f"Last log: {last_log[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())