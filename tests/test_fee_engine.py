"""Tests for Steam fee engine."""

from decimal import Decimal

from steam_scanner.analytics.fee_engine import (
    build_fee_table,
    buyer_pays_from_receive,
    calculate_fee,
    receive_from_buyer_pays,
)


def test_buyer_pays_from_receive_min_fee():
    # $0.01 receive -> fees min 1 cent each -> buyer pays 3 cents
    assert buyer_pays_from_receive(1) == 3


def test_receive_from_buyer_pays_three_cents():
    # Classic Steam: buyer pays $0.03, seller receives $0.01
    receive = receive_from_buyer_pays(3)
    assert receive == 1


def test_calculate_fee_effective_pct():
    fee = calculate_fee(Decimal("0.03"))
    assert fee.seller_receives == Decimal("0.01")
    assert fee.buyer_pays == Decimal("0.03")


def test_build_fee_table_has_levels():
    table = build_fee_table()
    assert len(table) >= 10
    assert table[0]["buyer_pays"] == 0.03


def test_higher_price_lower_fee_pct():
    cheap = calculate_fee(Decimal("0.05"))
    expensive = calculate_fee(Decimal("5.00"))
    assert expensive.effective_fee_pct < cheap.effective_fee_pct
