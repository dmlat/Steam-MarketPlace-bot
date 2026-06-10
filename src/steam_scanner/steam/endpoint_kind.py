"""Steam endpoint kinds for per-route rate limits."""

from __future__ import annotations

from enum import Enum


class SteamEndpoint(str, Enum):
    PRICE = "price"
    SEARCH = "search"
    LISTING = "listing"
    ORDERBOOK = "orderbook"
    STORE = "store"
    OTHER = "other"
