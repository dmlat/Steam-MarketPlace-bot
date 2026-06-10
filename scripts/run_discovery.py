#!/usr/bin/env python3
"""Run app and market item discovery."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from steam_scanner.collectors.app_discovery import AppDiscovery
from steam_scanner.collectors.market_search import MarketSearchCollector
from steam_scanner.steam.client import SteamClient


def main():
    with SteamClient() as client:
        discovery = AppDiscovery(client=client)
        apps = discovery.discover_all()
        print(f"Discovered {apps} apps with trading cards")

        appids = discovery.get_eligible_appids()
        collector = MarketSearchCollector(client=client)
        items = collector.collect_all_games(appids, max_pages_per_game=5)
        general = collector.collect_general_market(max_items=3000)
        print(f"Collected {items} game-specific items, {general} general market items")


if __name__ == "__main__":
    main()
