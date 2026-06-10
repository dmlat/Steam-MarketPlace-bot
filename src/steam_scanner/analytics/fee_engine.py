"""Steam market fee model with brute-force inverse calculation."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple

from steam_scanner.config import (
    DEFAULT_PUBLISHER_FEE_RATE,
    DEFAULT_STEAM_FEE_RATE,
    FEE_PRICE_LEVELS_USD,
)


class FeeResult(NamedTuple):
    buyer_pays: Decimal
    seller_receives: Decimal
    steam_fee: Decimal
    publisher_fee: Decimal
    total_fee: Decimal
    effective_fee_pct: Decimal
    break_even_sell_price: Decimal
    minimum_profitable_sell_price: Decimal


def _to_cents(amount: Decimal | float | int) -> int:
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _from_cents(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)


def buyer_pays_from_receive(
    receive_cents: int,
    steam_fee_rate: Decimal = DEFAULT_STEAM_FEE_RATE,
    publisher_fee_rate: Decimal = DEFAULT_PUBLISHER_FEE_RATE,
    min_fee_cents: int = 1,
) -> int:
    steam_fee = max(min_fee_cents, int(receive_cents * float(steam_fee_rate)))
    publisher_fee = max(min_fee_cents, int(receive_cents * float(publisher_fee_rate)))
    return receive_cents + steam_fee + publisher_fee


def receive_from_buyer_pays(
    buyer_pays_cents: int,
    steam_fee_rate: Decimal = DEFAULT_STEAM_FEE_RATE,
    publisher_fee_rate: Decimal = DEFAULT_PUBLISHER_FEE_RATE,
    min_fee_cents: int = 1,
) -> int | None:
    best = None
    for receive in range(1, buyer_pays_cents + 1):
        total = buyer_pays_from_receive(
            receive, steam_fee_rate, publisher_fee_rate, min_fee_cents
        )
        if total <= buyer_pays_cents:
            best = receive
    return best


def calculate_fee(
    buyer_pays: Decimal,
    steam_fee_rate: Decimal = DEFAULT_STEAM_FEE_RATE,
    publisher_fee_rate: Decimal = DEFAULT_PUBLISHER_FEE_RATE,
    min_fee_cents: int = 1,
    min_profit_pct: Decimal = Decimal("0.01"),
) -> FeeResult:
    buyer_cents = _to_cents(buyer_pays)
    receive_cents = receive_from_buyer_pays(
        buyer_cents, steam_fee_rate, publisher_fee_rate, min_fee_cents
    )
    if receive_cents is None:
        receive_cents = 0

    steam_fee = max(min_fee_cents, int(receive_cents * float(steam_fee_rate)))
    publisher_fee = max(min_fee_cents, int(receive_cents * float(publisher_fee_rate)))
    total_fee = steam_fee + publisher_fee

    seller_receives = _from_cents(receive_cents)
    buyer = _from_cents(buyer_cents)
    total_fee_dec = _from_cents(total_fee)

    eff_pct = (total_fee_dec / buyer * 100) if buyer > 0 else Decimal(0)

    # Break-even: sell price where seller receives what they paid to buy
    break_even_cents = buyer_pays_from_receive(buyer_cents, steam_fee_rate, publisher_fee_rate, min_fee_cents)
    break_even = _from_cents(break_even_cents)

    # Minimum profitable sell (buy price + 1% profit after fees)
    target_receive = int(buyer_cents * (1 + float(min_profit_pct)))
    min_profitable_cents = buyer_pays_from_receive(
        target_receive, steam_fee_rate, publisher_fee_rate, min_fee_cents
    )
    min_profitable = _from_cents(min_profitable_cents)

    return FeeResult(
        buyer_pays=buyer,
        seller_receives=seller_receives,
        steam_fee=_from_cents(steam_fee),
        publisher_fee=_from_cents(publisher_fee),
        total_fee=total_fee_dec,
        effective_fee_pct=eff_pct.quantize(Decimal("0.01")),
        break_even_sell_price=break_even,
        minimum_profitable_sell_price=min_profitable,
    )


def seller_receives_at_buyer_price(buyer_pays: Decimal, **kwargs) -> Decimal:
    return calculate_fee(buyer_pays, **kwargs).seller_receives


def build_fee_table(
    price_levels: list[Decimal] | None = None,
    **kwargs,
) -> list[dict]:
    levels = price_levels or FEE_PRICE_LEVELS_USD
    rows = []
    for price in levels:
        fee = calculate_fee(price, **kwargs)
        required_growth = Decimal(0)
        if fee.seller_receives > 0:
            required_growth = (
                (fee.break_even_sell_price - price) / price * 100
            ).quantize(Decimal("0.01"))

        rows.append({
            "buyer_pays": float(fee.buyer_pays),
            "seller_receives": float(fee.seller_receives),
            "steam_fee": float(fee.steam_fee),
            "publisher_fee": float(fee.publisher_fee),
            "total_fee": float(fee.total_fee),
            "effective_fee_pct": float(fee.effective_fee_pct),
            "break_even_sell_price": float(fee.break_even_sell_price),
            "required_growth_to_break_even_pct": float(required_growth),
        })
    return rows


def net_spread_after_fee(
    buy_price: Decimal,
    sell_price: Decimal,
    **kwargs,
) -> tuple[Decimal, Decimal]:
    """Net profit if bought at buy_price (buy order) and sold at sell_price (listing)."""
    if buy_price <= 0 or sell_price <= 0:
        return Decimal(0), Decimal(0)

    # Cost to acquire at highest buy order level — buyer pays listing price
    # If we buy from listing at sell_price, we pay sell_price
    # If we had buy order filled, we pay buy_price
    acquire_cost = buy_price
    sell_fee = calculate_fee(sell_price, **kwargs)
    net = sell_fee.seller_receives - acquire_cost
    net_pct = (net / acquire_cost * 100) if acquire_cost > 0 else Decimal(0)
    return net.quantize(Decimal("0.0001")), net_pct.quantize(Decimal("0.01"))
