"""Tests for adaptive rate limiting on 429 responses."""

from unittest.mock import patch

import httpx
import pytest

from steam_scanner.steam.client import RateLimitCircuitOpenError, SteamClient


def _mock_response(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return httpx.Response(status, headers=headers, request=httpx.Request("GET", "https://example.com"))


@patch("steam_scanner.steam.client.STEAM_PROXY_URLS", [])
def test_429_not_counted_as_successful_request():
    client = SteamClient(interval=0.01, max_retries=1, request_cap=100)
    ok = _mock_response(200)
    blocked = _mock_response(429)

    with patch.object(client._client, "get", side_effect=[blocked, ok]):
        with patch("steam_scanner.steam.client.time.sleep"):
            client.get("https://steamcommunity.com/market/priceoverview/?appid=753")

    assert client.requests_made == 1
    assert client.throttled_count == 1


@patch("steam_scanner.steam.client.STEAM_PROXY_URLS", [])
def test_circuit_breaker_opens_after_consecutive_429():
    client = SteamClient(interval=0.01, max_retries=1, request_cap=100)
    blocked = _mock_response(429)
    threshold = 5

    with patch("steam_scanner.steam.client.STEAM_429_CIRCUIT_THRESHOLD", threshold):
        with patch.object(client._client, "get", return_value=blocked):
            with patch("steam_scanner.steam.client.time.sleep"):
                with pytest.raises(RateLimitCircuitOpenError, match="consecutive 429"):
                    client.get("https://steamcommunity.com/market/priceoverview/?appid=753")

    assert client.throttled_count == threshold
    assert client.requests_made == 0


@patch("steam_scanner.steam.client.STEAM_PROXY_URLS", [])
def test_circuit_breaker_resets_after_success():
    client = SteamClient(interval=0.01, max_retries=1, request_cap=100)
    blocked = _mock_response(429)
    ok = _mock_response(200)
    threshold = 5

    with patch("steam_scanner.steam.client.STEAM_429_CIRCUIT_THRESHOLD", threshold):
        with patch.object(
            client._client,
            "get",
            side_effect=[blocked, ok, blocked, blocked, blocked, blocked, blocked],
        ):
            with patch("steam_scanner.steam.client.time.sleep"):
                client.get("https://steamcommunity.com/market/priceoverview/?appid=753")
                with pytest.raises(RateLimitCircuitOpenError):
                    client.get("https://steamcommunity.com/market/priceoverview/?appid=753")

    assert client.requests_made == 1
