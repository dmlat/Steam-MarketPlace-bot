"""Optional SOCKS/HTTP proxy pool with round-robin rotation."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def mask_proxy_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "?"
    port = parsed.port or ""
    scheme = parsed.scheme or "proxy"
    port_suffix = f":{port}" if port else ""
    return f"{scheme}://***@{host}{port_suffix}"


class ProxyPool:
    """Round-robin proxy rotation with cooldown after 429."""

    def __init__(
        self,
        urls: list[str],
        *,
        max_429_per_proxy: int = 1,
        cooldown_hours: float = 6.0,
    ):
        if not urls:
            raise ValueError("ProxyPool requires at least one URL")
        self._urls = urls
        self._max_429 = max(1, max_429_per_proxy)
        self._cooldown_sec = max(60.0, cooldown_hours * 3600.0)
        self._index = 0
        self._consecutive_429 = [0] * len(urls)
        self._cooldown_until = [0.0] * len(urls)

    @property
    def size(self) -> int:
        return len(self._urls)

    @property
    def active_count(self) -> int:
        now = time.monotonic()
        return sum(1 for i in range(len(self._urls)) if self._cooldown_until[i] <= now)

    def describe(self) -> str:
        masked = ", ".join(mask_proxy_url(u) for u in self._urls)
        return f"{self.active_count}/{self.size} active [{masked}]"

    def _is_available(self, idx: int, now: float) -> bool:
        return self._cooldown_until[idx] <= now

    def current(self) -> tuple[int, str]:
        now = time.monotonic()
        if self.active_count == 0:
            raise RuntimeError("No active proxies left in pool (all in cooldown)")
        for _ in range(len(self._urls)):
            idx = self._index % len(self._urls)
            self._index += 1
            if self._is_available(idx, now):
                return idx, self._urls[idx]
        raise RuntimeError("No active proxies left in pool (all in cooldown)")

    def rotate(self) -> tuple[int, str]:
        return self.current()

    def record_429(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._urls):
            return
        self._consecutive_429[idx] += 1
        if self._consecutive_429[idx] >= self._max_429:
            self._cooldown_until[idx] = time.monotonic() + self._cooldown_sec
            logger.warning(
                "Proxy %d cooldown %.1fh after %d x429 (%s)",
                idx + 1,
                self._cooldown_sec / 3600.0,
                self._consecutive_429[idx],
                mask_proxy_url(self._urls[idx]),
            )
            self._consecutive_429[idx] = 0

    def record_success(self, idx: int) -> None:
        if 0 <= idx < len(self._urls):
            self._consecutive_429[idx] = 0
