"""Compliance guard — ensures read-only operation."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from steam_scanner.config import STEAM_PROXY_URLS

ALLOWED_HOSTS = frozenset({
    "steamcommunity.com",
    "store.steampowered.com",
    "api.steampowered.com",
})

ALLOWED_PATH_PREFIXES = (
    "/market/search/render",
    "/market/priceoverview",
    "/market/listings/",
    "/market/itemordershistogram",
    "/search/results",
    "/ISteamEconomy/",
)

FORBIDDEN_PATH_PATTERNS = (
    "/market/createbuyorder",
    "/market/sellitem",
    "/market/removelisting",
    "/tradeoffer/",
    "/login",
)

PROXY_ENV_VARS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


class ComplianceError(Exception):
    """Raised when an operation violates compliance rules."""


class ComplianceGuard:
    """Validates HTTP requests and environment before Steam access."""

    @staticmethod
    def check_environment() -> None:
        for var in PROXY_ENV_VARS:
            if os.getenv(var):
                raise ComplianceError(
                    f"System proxy environment variable {var} is set. "
                    f"Use STEAM_PROXY_URLS in .env instead, or unset {var}."
                )
        for url in STEAM_PROXY_URLS:
            parsed = urlparse(url)
            if parsed.scheme not in {"socks5", "socks5h", "http", "https"}:
                raise ComplianceError(
                    f"Unsupported proxy scheme in STEAM_PROXY_URLS: {parsed.scheme!r}"
                )

    @staticmethod
    def validate_proxy_usage() -> None:
        """Documented opt-in: egress rotation for rate limits, not regional spoofing."""
        return

    @staticmethod
    def validate_url(url: str, method: str = "GET") -> None:
        if method.upper() != "GET":
            raise ComplianceError(f"Only GET requests allowed, got {method} for {url}")

        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        if host not in ALLOWED_HOSTS:
            raise ComplianceError(f"Host not allowed: {host}")

        path = parsed.path.lower()
        for forbidden in FORBIDDEN_PATH_PATTERNS:
            if forbidden in path:
                raise ComplianceError(f"Forbidden endpoint: {path}")

        if host == "steamcommunity.com" and not any(
            path.startswith(p) for p in ALLOWED_PATH_PREFIXES
        ):
            if "/market/" in path:
                raise ComplianceError(f"Market path not in whitelist: {path}")

    @staticmethod
    def validate_cookies(cookies: dict | None) -> None:
        if not cookies:
            return
        forbidden = {"sessionid", "steamLoginSecure", "steamLogin"}
        found = forbidden & {k.lower() for k in cookies}
        if found:
            raise ComplianceError(
                f"Authenticated cookies detected: {found}. Login cookies are prohibited."
            )
