"""HTML/JSON parsers for Steam Market responses."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, unquote

from bs4 import BeautifulSoup

ITEM_NAMEID_RE = re.compile(r"Market_LoadOrderSpread\s*\(\s*(\d+)\s*\)")
MARKET_HASH_NAME_RE = re.compile(r"market_listing_item_name[^>]*>([^<]+)<")
TAG_APP_RE = re.compile(r"tag_app_(\d+)")


def parse_price_string(value: str | None) -> Decimal | None:
    """Parse Steam price strings like '$0.03', '0,03€', '0,03 руб.'"""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    # Remove currency symbols and text
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned:
        return None
    # US format: 1,234.56 vs European: 1.234,56 or 0,03
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(".") > cleaned.rfind(","):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_volume_string(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    cleaned = re.sub(r"[^\d]", "", str(value))
    if not cleaned:
        return None
    return int(cleaned)


def parse_price_overview(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": data.get("success", False),
        "lowest_price": parse_price_string(data.get("lowest_price")),
        "median_price": parse_price_string(data.get("median_price")),
        "volume": parse_volume_string(data.get("volume")),
    }


def extract_item_nameid(html: str) -> str | None:
    match = ITEM_NAMEID_RE.search(html)
    return match.group(1) if match else None


def parse_listing_page(html: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "item_nameid": extract_item_nameid(html),
        "marketable": None,
        "tradable": None,
        "commodity": None,
        "tags": [],
        "asset_description": None,
    }

    soup = BeautifulSoup(html, "lxml")

    # Extract g_rgAssets or similar JSON blobs
    for script in soup.find_all("script"):
        text = script.string or ""
        if "g_rgAssets" in text or "market_listing_item_name" in text:
            if "marketable" in text:
                m = re.search(r'"marketable"\s*:\s*(true|false)', text, re.I)
                if m:
                    result["marketable"] = m.group(1).lower() == "true"
            if "tradable" in text:
                m = re.search(r'"tradable"\s*:\s*(true|false)', text, re.I)
                if m:
                    result["tradable"] = m.group(1).lower() == "true"
            if "commodity" in text:
                m = re.search(r'"commodity"\s*:\s*(true|false)', text, re.I)
                if m:
                    result["commodity"] = m.group(1).lower() == "true"

    title = soup.select_one(".market_listing_item_name")
    if title:
        result["item_name"] = title.get_text(strip=True)

    tag_elems = soup.select(".market_listing_game_name, .market_listing_item_game")
    for elem in tag_elems:
        result["tags"].append(elem.get_text(strip=True))

    return result


def parse_market_search_response(data: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return {"success": False, "total_count": 0, "results_html": data, "items": []}

    results_html = data.get("results_html", "")
    raw_results = data.get("results")

    if raw_results and isinstance(raw_results, list):
        items = parse_market_search_results_json(raw_results)
    else:
        items = parse_market_search_html(results_html)

    return {
        "success": data.get("success", True),
        "total_count": int(data.get("total_count", 0)),
        "start": int(data.get("start", 0)),
        "pagesize": int(data.get("pagesize", 0)),
        "results_html": results_html,
        "items": items,
    }


def parse_market_search_results_json(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse modern JSON `results` array from market/search/render."""
    items: list[dict[str, Any]] = []
    for row in results:
        asset = row.get("asset_description") or {}
        market_hash_name = (
            asset.get("market_hash_name")
            or row.get("hash_name")
            or row.get("name")
        )
        if not market_hash_name:
            continue

        sell_price = None
        if row.get("sell_price_text"):
            sell_price = parse_price_string(row["sell_price_text"])
        elif row.get("sell_price") is not None:
            sell_price = Decimal(str(row["sell_price"])) / Decimal(100)

        market_appid = asset.get("appid") or 753
        encoded_name = quote(market_hash_name, safe="")

        items.append({
            "market_hash_name": market_hash_name,
            "item_name": row.get("name") or asset.get("name"),
            "game_name": row.get("app_name"),
            "item_type": asset.get("type"),
            "sell_price": sell_price,
            "sell_listings": row.get("sell_listings"),
            "market_appid": market_appid,
            "market_url": f"https://steamcommunity.com/market/listings/{market_appid}/{encoded_name}",
            "marketable": bool(asset.get("marketable", 1)),
            "tradable": bool(asset.get("tradable", 1)),
            "commodity": bool(asset.get("commodity", 0)),
        })

    return items


def parse_market_search_html(html: str) -> list[dict[str, Any]]:
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []

    for row in soup.select(".market_listing_row_link, a.market_listing_row_link"):
        href = row.get("href", "")
        hash_match = re.search(r"/market/listings/\d+/(.+?)(?:\?|$)", href)
        market_hash_name = unquote(hash_match.group(1)) if hash_match else None

        name_elem = row.select_one(".market_listing_item_name") or row
        item_name = name_elem.get_text(strip=True) if name_elem else None

        game_elem = row.select_one(".market_listing_game_name")
        game_name = game_elem.get_text(strip=True) if game_elem else None

        price_elem = row.select_one(".normal_price, .sale_price")
        sell_price = parse_price_string(price_elem.get_text() if price_elem else None)

        qty_elem = row.select_one(".market_listing_num_listings_qty")
        sell_listings = parse_volume_string(qty_elem.get_text() if qty_elem else None)

        appid_match = re.search(r"/market/listings/(\d+)/", href)
        market_appid = int(appid_match.group(1)) if appid_match else 753

        if market_hash_name:
            items.append({
                "market_hash_name": market_hash_name,
                "item_name": item_name,
                "game_name": game_name,
                "sell_price": sell_price,
                "sell_listings": sell_listings,
                "market_appid": market_appid,
                "market_url": href if href.startswith("http") else f"https://steamcommunity.com{href}",
            })

    return items


def parse_store_search_html(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    games: list[dict[str, Any]] = []

    for row in soup.select("#search_resultsRows a, .search_result_row"):
        href = row.get("href", "")
        appid_match = re.search(r"/app/(\d+)/", href)
        if not appid_match:
            ds = row.get("data-ds-appid") or row.get("data-ds-bundleid")
            if ds:
                appid_match = re.match(r"(\d+)", str(ds))

        if not appid_match:
            continue

        appid = int(appid_match.group(1))
        title_elem = row.select_one(".title")
        name = title_elem.get_text(strip=True) if title_elem else None

        games.append({"appid": appid, "name": name, "store_url": href})

    return games


def extract_market_filters(html: str, appid: int = 753) -> list[dict[str, str]]:
    """Extract category filters from market search page HTML."""
    filters: list[dict[str, str]] = []
    soup = BeautifulSoup(html, "lxml")

    prefix = f"category_{appid}_"
    for elem in soup.select(f"[id^='{prefix}'], [data-category^='{prefix}']"):
        elem_id = elem.get("id") or elem.get("data-category") or ""
        if "item_class" in elem_id or "ItemType" in elem_id:
            name = elem.get_text(strip=True) or elem_id
            filters.append({"filter_key": elem_id, "filter_name": name})

    # Also parse from JSON in page
    for script in soup.find_all("script"):
        text = script.string or ""
        if "item_class" in text:
            for match in re.finditer(
                rf'"{prefix}item_class\[\]"\s*:\s*"([^"]+)"', text
            ):
                val = match.group(1)
                filters.append({"filter_key": f"{prefix}item_class[]", "filter_value": val})

    return filters


def classify_item_type(
    market_hash_name: str,
    item_type: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, bool]:
    """Classify item into card/foil/booster/background/emoticon."""
    name_lower = market_hash_name.lower()
    type_lower = (item_type or "").lower()
    tag_text = " ".join(tags or []).lower()
    combined = f"{name_lower} {type_lower} {tag_text}"

    is_foil = "foil" in combined
    is_booster = "booster pack" in combined or "booster" in type_lower
    is_background = "profile background" in combined or "background" in type_lower
    is_emoticon = "emoticon" in combined
    is_card = (
        "trading card" in combined
        or ("card" in type_lower and not is_booster)
        or (name_lower.endswith(")") and "- " in market_hash_name and not is_booster)
    )

    if is_foil:
        is_card = True

    return {
        "is_card": is_card,
        "is_foil": is_foil,
        "is_booster": is_booster,
        "is_background": is_background,
        "is_emoticon": is_emoticon,
    }


def parse_order_histogram(data: dict[str, Any]) -> dict[str, Any]:
    def to_decimal(val: Any) -> Decimal | None:
        if val is None:
            return None
        try:
            return Decimal(str(val)) / 100 if isinstance(val, (int, float)) else parse_price_string(str(val))
        except (InvalidOperation, ValueError):
            return parse_price_string(str(val))

    buy_graph = data.get("buy_order_graph") or []
    sell_graph = data.get("sell_order_graph") or []

    highest_buy = None
    lowest_sell = None
    if buy_graph:
        highest_buy = Decimal(str(buy_graph[0][0]))
    if sell_graph:
        lowest_sell = Decimal(str(sell_graph[0][0]))

    return {
        "success": data.get("success", 0) == 1,
        "highest_buy_order": highest_buy,
        "lowest_sell_order": lowest_sell,
        "buy_order_graph": buy_graph,
        "sell_order_graph": sell_graph,
        "buy_order_summary": data.get("buy_order_summary"),
        "sell_order_summary": data.get("sell_order_summary"),
        "buy_order_count": _count_orders(buy_graph),
        "sell_order_count": _count_orders(sell_graph),
    }


def _count_orders(graph: list) -> int:
    if not graph:
        return 0
    if graph:
        return int(graph[-1][2]) if len(graph[-1]) > 2 else len(graph)
    return 0
