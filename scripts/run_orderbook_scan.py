#!/usr/bin/env python3
"""Run order book scan for short-list items."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from steam_scanner.collectors.orderbook import OrderBookCollector
from steam_scanner.collectors.price_overview import PriceOverviewCollector
from steam_scanner.steam.client import SteamClient


def main():
    short_list = PriceOverviewCollector.get_short_list(limit=1000)
    print(f"Short-list: {len(short_list)} items")

    with SteamClient() as client:
        collector = OrderBookCollector(client=client)
        count = collector.collect_batch(short_list, limit=500)
        print(f"Order book snapshots collected: {count}")


if __name__ == "__main__":
    main()
