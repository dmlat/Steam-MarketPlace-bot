"""Steam API URL builders."""

from __future__ import annotations

from urllib.parse import quote, urlencode

STORE_BASE = "https://store.steampowered.com"
MARKET_BASE = "https://steamcommunity.com/market"


def store_search_trading_cards(start: int = 0, count: int = 50) -> str:
    params = {
        "category2": "29",
        "ignore_preferences": "1",
        "ndl": "1",
        "start": str(start),
        "count": str(count),
    }
    return f"{STORE_BASE}/search/results/?{urlencode(params)}"


def market_search_render(
    appid: int = 753,
    start: int = 0,
    count: int = 100,
    query: str = "",
    sort_column: str = "popular",
    sort_dir: str = "desc",
    extra_params: dict | None = None,
) -> str:
    params: dict[str, str | int] = {
        "appid": appid,
        "start": start,
        "count": count,
        "query": query,
        "sort_column": sort_column,
        "sort_dir": sort_dir,
        "search_descriptions": 0,
        "norender": 1,
    }
    if extra_params:
        params.update(extra_params)
    return f"{MARKET_BASE}/search/render/?{urlencode(params, doseq=True)}"


def market_search_for_game(appid: int, game_appid: int, start: int = 0, count: int = 100) -> str:
    return market_search_render(
        appid=appid,
        start=start,
        count=count,
        extra_params={f"category_{appid}_Game[]": f"tag_app_{game_appid}"},
    )


def price_overview(
    market_hash_name: str,
    appid: int = 753,
    currency: int = 1,
    country: str = "US",
) -> str:
    params = {
        "appid": appid,
        "currency": currency,
        "country": country,
        "market_hash_name": market_hash_name,
        "format": "json",
    }
    return f"{MARKET_BASE}/priceoverview/?{urlencode(params)}"


def listing_page(appid: int, market_hash_name: str) -> str:
    encoded = quote(market_hash_name, safe="")
    return f"{MARKET_BASE}/listings/{appid}/{encoded}"


def item_orders_histogram(
    item_nameid: str,
    currency: int = 1,
    country: str = "US",
    language: str = "english",
) -> str:
    params = {
        "country": country,
        "language": language,
        "currency": currency,
        "item_nameid": item_nameid,
        "two_factor": 0,
    }
    return f"{MARKET_BASE}/itemordershistogram?{urlencode(params)}"


def manual_check_url(appid: int, market_hash_name: str) -> str:
    return listing_page(appid, market_hash_name)
