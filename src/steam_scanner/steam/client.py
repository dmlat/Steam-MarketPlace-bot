"""Rate-limited HTTP client for Steam public endpoints."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import httpx

from steam_scanner.compliance import ComplianceGuard
from steam_scanner.config import (

    STEAM_429_CIRCUIT_THRESHOLD,
    STEAM_429_COOLDOWN_SEC,
    STEAM_429_MAX_RETRIES,
    STEAM_MAX_RETRIES,
    STEAM_NETWORK_MAX_WAIT_SEC,
    STEAM_NETWORK_RETRY_BASE_SEC,
    STEAM_NIGHTLY_REQUEST_CAP,
    STEAM_PROXY_MAX_429,
    STEAM_PROXY_COOLDOWN_HOURS,
    STEAM_PROXY_URLS,
    interval_for_endpoint,
    STEAM_REQUEST_INTERVAL,
    USER_AGENT,
)
from steam_scanner.steam.endpoint_kind import SteamEndpoint
from steam_scanner.steam.proxy_pool import ProxyPool, mask_proxy_url

logger = logging.getLogger(__name__)

# Errors typical when VPN toggles or internet drops.
NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    ConnectionError,
    TimeoutError,
    OSError,
)


class RequestBudgetExceeded(Exception):
    """Raised when nightly request cap is reached."""


class NetworkOutageError(Exception):
    """Raised when network is unavailable longer than max wait budget."""


class RateLimitCircuitOpenError(Exception):
    """Raised when Steam returns too many consecutive 429 responses without success."""


# Errors that should abort the current pipeline run (not be swallowed per-item).
STEAM_CLIENT_ABORT_ERRORS = (
    NetworkOutageError,
    RateLimitCircuitOpenError,
    RequestBudgetExceeded,
)


class SteamClient:
    """Synchronous read-only Steam HTTP client with adaptive rate limiting."""

    def __init__(
        self,
        interval: float | None = None,
        max_retries: int | None = None,
        request_cap: int | None = None,
        fixed_proxy_url: str | None = None,
        lane_id: int | None = None,
    ):
        ComplianceGuard.check_environment()
        self.base_interval = interval or STEAM_REQUEST_INTERVAL
        self.interval = self.base_interval
        self.max_retries = max_retries or STEAM_MAX_RETRIES
        self.request_cap = request_cap or STEAM_NIGHTLY_REQUEST_CAP
        self.fixed_proxy_url = fixed_proxy_url
        self.lane_id = lane_id
        self.requests_made = 0
        self.throttled_count = 0
        self.network_retries = 0
        self._last_request_at = 0.0
        self._backoff_multiplier = 1.0
        self._consecutive_429 = 0
        self._success_streak = 0
        self._proxy_pool: ProxyPool | None = None
        self._proxy_idx: int | None = None
        self._proxy_url: str | None = None
        if fixed_proxy_url:
            self._proxy_url = fixed_proxy_url
            self._proxy_idx = lane_id if lane_id is not None else 0
        elif STEAM_PROXY_URLS:
            self._proxy_pool = ProxyPool(
                STEAM_PROXY_URLS,
                max_429_per_proxy=STEAM_PROXY_MAX_429,
                cooldown_hours=STEAM_PROXY_COOLDOWN_HOURS,
            )
            logger.info(
                "Proxy pool enabled (%s); ~%.1fs between hits per IP at %.1fs interval",
                self._proxy_pool.describe(),
                self.base_interval * self._proxy_pool.size,
                self.base_interval,
            )
        self._client = self._make_http_client()

    def _make_http_client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {
            "headers": {"User-Agent": USER_AGENT},
            "timeout": httpx.Timeout(30.0, connect=15.0),
            "follow_redirects": True,
        }
        if self._proxy_url:
            kwargs["proxy"] = self._proxy_url
        return httpx.Client(**kwargs)

    def _pick_proxy(self) -> None:
        if self._proxy_pool:
            idx, url = self._proxy_pool.current()
            if url != self._proxy_url or idx != self._proxy_idx:
                self._proxy_idx, self._proxy_url = idx, url
                self._reset_http_client()

    def _rotate_proxy(self, reason: str) -> float:
        assert self._proxy_pool is not None
        if self._proxy_idx is not None:
            self._proxy_pool.record_429(self._proxy_idx)
        if self._proxy_pool.active_count == 0:
            raise RateLimitCircuitOpenError(
                f"All {self._proxy_pool.size} proxies rate-limited. "
                "Wait and retry later."
            )
        prev = self._proxy_idx
        self._proxy_idx, self._proxy_url = self._proxy_pool.rotate()
        self._reset_http_client()
        self._consecutive_429 = 0
        self._backoff_multiplier = 1.0
        self.interval = self.base_interval
        logger.warning(
            "HTTP 429 on proxy %s — %s, switching to proxy %s (%s)",
            (prev or 0) + 1,
            reason,
            self._proxy_idx + 1,
            mask_proxy_url(self._proxy_url),
        )
        return random.uniform(1.0, 3.0)

    def _reset_http_client(self) -> None:
        """Recreate client after VPN/network interface change."""
        try:
            self._client.close()
        except Exception:
            pass
        self._client = self._make_http_client()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SteamClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _wait_rate_limit(self, endpoint: SteamEndpoint = SteamEndpoint.OTHER) -> None:
        self.interval = interval_for_endpoint(endpoint)
        elapsed = time.monotonic() - self._last_request_at
        wait = self.interval * self._backoff_multiplier - elapsed
        if wait > 0:
            time.sleep(wait + random.uniform(0.3, 1.2))

    def _parse_retry_after(self, response: httpx.Response) -> float | None:
        raw = response.headers.get("Retry-After")
        if not raw:
            return None
        try:
            return max(1.0, float(raw))
        except ValueError:
            return None

    def _handle_429(self, response: httpx.Response) -> float:
        self.throttled_count += 1
        self._consecutive_429 += 1
        self._success_streak = 0

        if self._proxy_pool:
            retry_after = self._parse_retry_after(response)
            reason = f"Retry-After {retry_after:.0f}s" if retry_after else f"#{self._consecutive_429}"
            return self._rotate_proxy(reason)

        retry_after = self._parse_retry_after(response)
        if retry_after is not None:
            wait = retry_after
            logger.warning(
                "HTTP 429 (#%d) — Retry-After: %.0fs",
                self._consecutive_429,
                wait,
            )
        else:
            self._backoff_multiplier = min(self._backoff_multiplier * 1.5, 12.0)
            self.interval = min(
                self.base_interval * (1 + self._consecutive_429 * 0.35),
                self.base_interval * 4,
            )
            wait = self.interval * self._backoff_multiplier
            if self._consecutive_429 >= 3:
                wait = max(wait, STEAM_429_COOLDOWN_SEC)
            logger.warning(
                "HTTP 429 (#%d) — pause %.1fs (interval=%.1fs, backoff=%.1fx)",
                self._consecutive_429,
                wait,
                self.interval,
                self._backoff_multiplier,
            )

        if (
            STEAM_429_CIRCUIT_THRESHOLD > 0
            and self._consecutive_429 >= STEAM_429_CIRCUIT_THRESHOLD
        ):
            raise RateLimitCircuitOpenError(
                f"Steam API returned {self._consecutive_429} consecutive 429 responses "
                f"(threshold={STEAM_429_CIRCUIT_THRESHOLD}). "
                "Stop and retry later with a higher STEAM_REQUEST_INTERVAL."
            )

        return wait + random.uniform(0.5, 2.0)

    def _wait_for_network(self, exc: Exception, waited_so_far: float) -> float:
        """Wait and return sleep duration. Raises if budget exceeded."""
        attempt = self.network_retries + 1
        sleep_for = min(
            STEAM_NETWORK_RETRY_BASE_SEC * (1.5 ** min(attempt - 1, 5)),
            30.0,
        )
        if waited_so_far + sleep_for > STEAM_NETWORK_MAX_WAIT_SEC:
            raise NetworkOutageError(
                f"Network unavailable for >{STEAM_NETWORK_MAX_WAIT_SEC:.0f}s "
                f"(last error: {exc})"
            ) from exc

        logger.warning(
            "Network unavailable (VPN/internet?) — waiting %.0fs, elapsed %.0f/%.0fs: %s",
            sleep_for,
            waited_so_far,
            STEAM_NETWORK_MAX_WAIT_SEC,
            type(exc).__name__,
        )
        time.sleep(sleep_for)
        self.network_retries += 1
        self._reset_http_client()
        return sleep_for

    def _handle_success(self) -> None:
        prev_429 = self._consecutive_429
        had_network_issues = self.network_retries > 0
        self._consecutive_429 = 0
        self._success_streak += 1
        self.network_retries = 0

        if self._backoff_multiplier > 1.0:
            self._backoff_multiplier = max(1.0, self._backoff_multiplier * 0.8)

        if self.interval > self.base_interval and self._success_streak >= 10:
            self.interval = max(self.base_interval, self.interval * 0.92)

        if had_network_issues:
            logger.info("Network restored, resuming collection")
        elif prev_429 > 0 and self._success_streak == 1:
            logger.info(
                "Steam API recovered after %d x 429 (interval=%.1fs)",
                prev_429,
                self.interval,
            )
        elif self._success_streak > 0 and self._success_streak % 50 == 0:
            proxy_note = ""
            if self.fixed_proxy_url and self.lane_id is not None:
                proxy_note = f", lane={self.lane_id + 1}"
            elif self._proxy_pool and self._proxy_idx is not None:
                proxy_note = f", proxy={self._proxy_idx + 1}/{self._proxy_pool.size}"
            logger.info(
                "Rate limit OK: %d requests, interval=%.1fs, throttled=%d%s",
                self.requests_made,
                self.interval,
                self.throttled_count,
                proxy_note,
            )

    def _request_once(self, url: str, cookies: dict | None) -> httpx.Response:
        """Single GET with up to 120s total wait on network errors."""
        network_waited = 0.0

        while True:
            try:
                response = self._client.get(url, cookies=cookies)
                self._last_request_at = time.monotonic()
                return response
            except NETWORK_ERRORS as exc:
                network_waited += self._wait_for_network(exc, network_waited)

    def get(
        self,
        url: str,
        *,
        cookies: dict | None = None,
        endpoint: SteamEndpoint = SteamEndpoint.OTHER,
    ) -> httpx.Response:
        ComplianceGuard.validate_url(url, "GET")
        ComplianceGuard.validate_cookies(cookies)

        if self.requests_made >= self.request_cap:
            raise RequestBudgetExceeded(
                f"Request cap of {self.request_cap} reached for this run."
            )

        last_error: Exception | None = None
        max_attempts = max(self.max_retries, STEAM_429_MAX_RETRIES)

        for attempt in range(max_attempts):
            self._wait_rate_limit(endpoint)
            self._pick_proxy()
            try:
                response = self._request_once(url, cookies)

                if response.status_code == 429:
                    time.sleep(self._handle_429(response))
                    continue

                response.raise_for_status()
                self.requests_made += 1
                if self._proxy_pool and self._proxy_idx is not None:
                    self._proxy_pool.record_success(self._proxy_idx)
                self._handle_success()
                return response

            except RateLimitCircuitOpenError:
                raise

            except NetworkOutageError:
                raise

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    time.sleep(self._handle_429(exc.response))
                    continue
                last_error = exc
                backoff = self.interval * (2 ** attempt)
                logger.warning(
                    "HTTP %s (attempt %d/%d): %s",
                    exc.response.status_code,
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                time.sleep(backoff + random.uniform(0, 1.0))

            except httpx.HTTPError as exc:
                last_error = exc
                backoff = self.interval * (2 ** attempt)
                logger.warning(
                    "Request failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                time.sleep(backoff + random.uniform(0, 1.0))

        raise last_error or RuntimeError(
            f"Failed to GET {url} after {max_attempts} attempts "
            f"(throttled {self.throttled_count} times)"
        )

    def get_json(self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.OTHER) -> dict[str, Any]:
        response = self.get(url, endpoint=endpoint)
        return response.json()

    def get_text(self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.OTHER) -> str:
        return self.get(url, endpoint=endpoint).text

    def get_json_or_html(self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.SEARCH) -> dict[str, Any] | str:
        response = self.get(url, endpoint=endpoint)
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return response.json()
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            return response.text
