#!/usr/bin/env python3
"""Run price overview scan."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from steam_scanner.collectors.price_overview import PriceOverviewCollector
from steam_scanner.steam.client import SteamClient


def main():
    with SteamClient() as client:
        collector = PriceOverviewCollector(client=client)
        count = collector.scan_all()
        print(f"Price snapshots collected: {count}")


if __name__ == "__main__":
    main()
