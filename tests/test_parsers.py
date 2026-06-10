"""Tests for Steam response parsers."""

from decimal import Decimal
from pathlib import Path

from steam_scanner.steam.parsers import (
    classify_item_type,
    extract_item_nameid,
    parse_listing_page,
    parse_market_search_html,
    parse_order_histogram,
    parse_price_overview,
    parse_price_string,
    parse_volume_string,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_price_string_usd():
    assert parse_price_string("$0.03") == Decimal("0.03")
    assert parse_price_string("$1,234.56") == Decimal("1234.56")


def test_parse_price_string_eur():
    assert parse_price_string("0,03€") == Decimal("0.03")


def test_parse_volume_string():
    assert parse_volume_string("1,234") == 1234
    assert parse_volume_string(100) == 100


def test_parse_price_overview_fixture():
    import json
    data = json.loads((FIXTURES / "price_overview_usd.json").read_text())
    result = parse_price_overview(data)
    assert result["lowest_price"] == Decimal("0.05")
    assert result["volume"] == 1234


def test_parse_market_search_json_results():
    import json
    results = json.loads((FIXTURES / "market_search_results.json").read_text())
    from steam_scanner.steam.parsers import parse_market_search_results_json
    items = parse_market_search_results_json(results)
    assert len(items) == 1
    assert items[0]["market_hash_name"] == "753-Sack of Gems"
    assert items[0]["sell_price"] == Decimal("0.73")


def test_parse_market_search_html():
    html = (FIXTURES / "market_search_row.html").read_text()
    items = parse_market_search_html(html)
    assert len(items) == 1
    assert items[0]["market_hash_name"] == "TestGame - TestCard"
    assert items[0]["sell_price"] == Decimal("0.15")


def test_extract_item_nameid():
    html = (FIXTURES / "listing_page.html").read_text()
    assert extract_item_nameid(html) == "176139123"


def test_parse_listing_page():
    html = (FIXTURES / "listing_page.html").read_text()
    result = parse_listing_page(html)
    assert result["item_nameid"] == "176139123"
    assert result["marketable"] is True


def test_parse_order_histogram():
    import json
    data = json.loads((FIXTURES / "order_histogram.json").read_text())
    result = parse_order_histogram(data)
    assert result["success"] is True
    assert result["highest_buy_order"] == Decimal("0.14")
    assert result["lowest_sell_order"] == Decimal("0.16")


def test_classify_item_type():
    c = classify_item_type("Game - Card Name (Trading Card)", tags=["Trading Card"])
    assert c["is_card"] is True
    f = classify_item_type("Game - Foil Card (Foil Trading Card)", tags=["Foil"])
    assert f["is_foil"] is True
    assert f["is_card"] is True
