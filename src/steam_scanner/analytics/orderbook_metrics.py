"""Order book depth and wall metrics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def compute_orderbook_metrics(
    buy_graph: list | None,
    sell_graph: list | None,
    highest_buy: Decimal | None,
    lowest_sell: Decimal | None,
) -> dict[str, Any]:
    buy_graph = buy_graph or []
    sell_graph = sell_graph or []

    metrics: dict[str, Any] = {
        "highest_buy_order": float(highest_buy) if highest_buy else None,
        "lowest_sell_price": float(lowest_sell) if lowest_sell else None,
        "quantity_at_highest_buy": 0,
        "quantity_at_lowest_sell": 0,
        "buy_depth_within_1_pct": 0,
        "buy_depth_within_3_pct": 0,
        "buy_depth_within_5_pct": 0,
        "sell_depth_within_1_pct": 0,
        "sell_depth_within_3_pct": 0,
        "sell_depth_within_5_pct": 0,
        "buy_wall_score": 0.0,
        "sell_wall_score": 0.0,
        "raw_spread": None,
        "raw_spread_pct": None,
        "depth_ratio": None,
        "liquidity_pressure_score": 0.0,
    }

    if highest_buy and lowest_sell and highest_buy > 0:
        raw_spread = lowest_sell - highest_buy
        metrics["raw_spread"] = float(raw_spread)
        metrics["raw_spread_pct"] = float(raw_spread / highest_buy * 100)

    if sell_graph:
        metrics["quantity_at_lowest_sell"] = _qty_at_price(sell_graph, sell_graph[0][0])
        ref = Decimal(str(sell_graph[0][0]))
        metrics["sell_depth_within_1_pct"] = _depth_within_pct(sell_graph, ref, 1.0)
        metrics["sell_depth_within_3_pct"] = _depth_within_pct(sell_graph, ref, 3.0)
        metrics["sell_depth_within_5_pct"] = _depth_within_pct(sell_graph, ref, 5.0)
        metrics["sell_wall_score"] = _wall_score(sell_graph)

    if buy_graph:
        metrics["quantity_at_highest_buy"] = _qty_at_price(buy_graph, buy_graph[0][0])
        ref = Decimal(str(buy_graph[0][0]))
        metrics["buy_depth_within_1_pct"] = _depth_within_pct(buy_graph, ref, 1.0, is_buy=True)
        metrics["buy_depth_within_3_pct"] = _depth_within_pct(buy_graph, ref, 3.0, is_buy=True)
        metrics["buy_depth_within_5_pct"] = _depth_within_pct(buy_graph, ref, 5.0, is_buy=True)
        metrics["buy_wall_score"] = _wall_score(buy_graph)

    buy_depth = metrics["buy_depth_within_3_pct"]
    sell_depth = metrics["sell_depth_within_3_pct"]
    if sell_depth > 0:
        metrics["depth_ratio"] = buy_depth / sell_depth

    if metrics["raw_spread_pct"] is not None:
        spread_factor = max(0, metrics["raw_spread_pct"])
        depth_factor = min(buy_depth, sell_depth) / max(buy_depth + sell_depth, 1)
        metrics["liquidity_pressure_score"] = round(spread_factor * depth_factor, 4)

    return metrics


def _qty_at_price(graph: list, price: float) -> int:
    for entry in graph:
        if len(entry) >= 2 and entry[0] == price:
            return int(entry[1])
    return int(graph[0][1]) if graph and len(graph[0]) >= 2 else 0


def _depth_within_pct(
    graph: list,
    ref_price: Decimal,
    pct: float,
    is_buy: bool = False,
) -> int:
    total = 0
    if ref_price <= 0:
        return 0

    for entry in graph:
        if len(entry) < 2:
            continue
        price = Decimal(str(entry[0]))
        qty = int(entry[1])
        diff_pct = abs(price - ref_price) / ref_price * 100
        if diff_pct <= pct:
            total += qty

    return total


def _wall_score(graph: list) -> float:
    """Higher score = more concentration at top of book (potential wall)."""
    if not graph or len(graph) < 2:
        return 0.0

    top_qty = int(graph[0][1]) if len(graph[0]) >= 2 else 0
    total_qty = sum(int(e[1]) for e in graph if len(e) >= 2)
    if total_qty == 0:
        return 0.0
    return round(top_qty / total_qty, 4)
