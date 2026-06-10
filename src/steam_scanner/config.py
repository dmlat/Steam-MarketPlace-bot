"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

from steam_scanner.steam.endpoint_kind import SteamEndpoint

EXCLUDED_APPIDS: frozenset[int] = frozenset({730, 440, 570, 252490})
MARKET_COMMUNITY_APPID = 753

STEAM_REQUEST_INTERVAL = float(os.getenv("STEAM_REQUEST_INTERVAL", "8.0"))
STEAM_INTERVAL_PRICE = float(os.getenv("STEAM_INTERVAL_PRICE", "10.0"))
STEAM_INTERVAL_SEARCH = float(os.getenv("STEAM_INTERVAL_SEARCH", "15.0"))
STEAM_INTERVAL_LISTING = float(os.getenv("STEAM_INTERVAL_LISTING", "25.0"))
STEAM_INTERVAL_ORDERBOOK = float(os.getenv("STEAM_INTERVAL_ORDERBOOK", "35.0"))
STEAM_INTERVAL_STORE = float(os.getenv("STEAM_INTERVAL_STORE", "15.0"))
STEAM_MAX_RETRIES = int(os.getenv("STEAM_MAX_RETRIES", "5"))
STEAM_429_MAX_RETRIES = int(os.getenv("STEAM_429_MAX_RETRIES", "2"))
STEAM_429_COOLDOWN_SEC = float(os.getenv("STEAM_429_COOLDOWN_SEC", "120"))
STEAM_429_CIRCUIT_THRESHOLD = int(os.getenv("STEAM_429_CIRCUIT_THRESHOLD", "3"))
STEAM_NETWORK_MAX_WAIT_SEC = float(os.getenv("STEAM_NETWORK_MAX_WAIT_SEC", "120"))
STEAM_NETWORK_RETRY_BASE_SEC = float(os.getenv("STEAM_NETWORK_RETRY_BASE_SEC", "5"))
STEAM_NIGHTLY_REQUEST_CAP = int(os.getenv("STEAM_NIGHTLY_REQUEST_CAP", "10000"))
STEAM_PROXY_MAX_429 = int(os.getenv("STEAM_PROXY_MAX_429", "1"))
STEAM_PROXY_COOLDOWN_HOURS = float(os.getenv("STEAM_PROXY_COOLDOWN_HOURS", "6"))


def _parse_proxy_urls(raw: str) -> list[str]:
    urls: list[str] = []
    for part in raw.replace("\n", ",").split(","):
        part = part.strip()
        if part:
            urls.append(part)
    return urls


STEAM_PROXY_URLS: list[str] = _parse_proxy_urls(os.getenv("STEAM_PROXY_URLS", ""))
STEAM_PARALLEL_WORKERS = int(os.getenv("STEAM_PARALLEL_WORKERS", "0"))


def effective_parallel_workers() -> int:
    """Parallel lanes: 1 without proxies, else clamp STEAM_PARALLEL_WORKERS to proxy count."""
    if not STEAM_PROXY_URLS:
        return 1
    raw = STEAM_PARALLEL_WORKERS if STEAM_PARALLEL_WORKERS > 0 else len(STEAM_PROXY_URLS)
    return max(1, min(raw, len(STEAM_PROXY_URLS)))


def interval_for_endpoint(endpoint: SteamEndpoint) -> float:
    return {
        SteamEndpoint.PRICE: STEAM_INTERVAL_PRICE,
        SteamEndpoint.SEARCH: STEAM_INTERVAL_SEARCH,
        SteamEndpoint.LISTING: STEAM_INTERVAL_LISTING,
        SteamEndpoint.ORDERBOOK: STEAM_INTERVAL_ORDERBOOK,
        SteamEndpoint.STORE: STEAM_INTERVAL_STORE,
        SteamEndpoint.OTHER: STEAM_REQUEST_INTERVAL,
    }.get(endpoint, STEAM_REQUEST_INTERVAL)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://scanner:scanner_dev_password@localhost:5433/steam_scanner",
)
STEAM_WEB_API_KEY = os.getenv("STEAM_WEB_API_KEY", "")

USER_AGENT = (
    "SteamMarketResearchScanner/0.1 (+research; read-only; "
    "https://github.com/local/steam-scanner)"
)


@dataclass(frozen=True)
class CurrencyConfig:
    code: str
    steam_id: int
    country: str
    symbol: str


CURRENCIES: dict[str, CurrencyConfig] = {
    "USD": CurrencyConfig("USD", 1, "US", "$"),
    "EUR": CurrencyConfig("EUR", 3, "DE", "€"),
    "GBP": CurrencyConfig("GBP", 2, "GB", "£"),
    "RUB": CurrencyConfig("RUB", 5, "RU", "₽"),
    "BRL": CurrencyConfig("BRL", 7, "BR", "R$"),
    "CNY": CurrencyConfig("CNY", 23, "CN", "¥"),
}

PRIMARY_CURRENCY = CURRENCIES["USD"]

# Hard filters for short-list (§11.1)
MIN_PRICE_USD = Decimal("0.10")
MIN_VOLUME = 10
MIN_ORDER_COUNT = 10

# Card price tiers (§11.2)
CARD_PRICE_TIERS: list[tuple[str, Decimal | None, Decimal | None]] = [
    ("cards_price_0_10_to_0_25", Decimal("0.10"), Decimal("0.25")),
    ("cards_price_0_25_to_0_50", Decimal("0.25"), Decimal("0.50")),
    ("cards_price_0_50_to_1", Decimal("0.50"), Decimal("1.00")),
    ("cards_price_1_to_3", Decimal("1.00"), Decimal("3.00")),
    ("cards_price_3_to_5", Decimal("3.00"), Decimal("5.00")),
    ("cards_price_above_5", Decimal("5.00"), None),
]

# Fee model price levels (§7.4)
FEE_PRICE_LEVELS_USD = [
    Decimal("0.03"), Decimal("0.04"), Decimal("0.05"), Decimal("0.10"),
    Decimal("0.25"), Decimal("0.50"), Decimal("1.00"), Decimal("2.00"),
    Decimal("5.00"), Decimal("10.00"), Decimal("25.00"),
]

DEFAULT_STEAM_FEE_RATE = Decimal("0.05")
DEFAULT_PUBLISHER_FEE_RATE = Decimal("0.10")
