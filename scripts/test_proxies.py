#!/usr/bin/env python3
"""Test SOCKS5/HTTP proxies against Steam priceoverview."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx

from steam_scanner.config import STEAM_PROXY_URLS
from steam_scanner.steam.proxy_pool import mask_proxy_url

TEST_URL = (
    "https://steamcommunity.com/market/priceoverview/"
    "?appid=753&currency=1&country=US&market_hash_name=730-Anarchist&format=json"
)


def test_proxy(url: str) -> tuple[bool, str]:
    try:
        with httpx.Client(
            proxy=url,
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
        ) as client:
            r = client.get(TEST_URL)
            if r.status_code == 429:
                return False, "HTTP 429 (proxy IP rate-limited)"
            if r.status_code == 200:
                return True, f"OK {r.status_code}"
            return False, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    if not STEAM_PROXY_URLS:
        print("STEAM_PROXY_URLS is empty. Add proxies to .env first.")
        return 1
    print(f"Testing {len(STEAM_PROXY_URLS)} proxy(s)...")
    ok = 0
    for i, proxy in enumerate(STEAM_PROXY_URLS, 1):
        success, msg = test_proxy(proxy)
        print(f"  [{'PASS' if success else 'FAIL'}] proxy {i}: {mask_proxy_url(proxy)} -> {msg}")
        ok += int(success)
    print(f"Result: {ok}/{len(STEAM_PROXY_URLS)}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())