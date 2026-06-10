"""Parallel HTTP workers — one rate-limited lane per proxy."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from steam_scanner.config import (
    STEAM_INTERVAL_PRICE,
    STEAM_NIGHTLY_REQUEST_CAP,
    STEAM_PROXY_URLS,
    effective_parallel_workers,
)
from steam_scanner.progress import ProgressTracker
from steam_scanner.steam.client import (
    STEAM_CLIENT_ABORT_ERRORS,
    RequestBudgetExceeded,
    SteamClient,
)
from steam_scanner.steam.endpoint_kind import SteamEndpoint
from steam_scanner.steam.proxy_pool import mask_proxy_url

logger = logging.getLogger(__name__)

ScanOneFn = Callable[[SteamClient, int], bool]


def partition_ids(ids: list[int], n: int) -> list[list[int]]:
    """Split ids across n lanes round-robin (equal +/-1 per lane)."""
    if not ids:
        return []
    lane_count = max(1, min(n, len(ids)))
    lanes: list[list[int]] = [[] for _ in range(lane_count)]
    for i, item_id in enumerate(ids):
        lanes[i % lane_count].append(item_id)
    return lanes


def make_http_client(request_cap: int | None = None) -> SteamClient | ParallelSteamClient:
    """Return ParallelSteamClient when multiple workers configured, else SteamClient."""
    cap = request_cap or STEAM_NIGHTLY_REQUEST_CAP
    if effective_parallel_workers() > 1 and STEAM_PROXY_URLS:
        return ParallelSteamClient(request_cap=cap)
    return SteamClient(request_cap=cap)


class ParallelSteamClient:
    """Pool of SteamClient lanes, each pinned to one proxy with its own rate limiter."""

    def __init__(self, request_cap: int | None = None):
        self.request_cap = request_cap or STEAM_NIGHTLY_REQUEST_CAP
        worker_count = effective_parallel_workers()
        proxy_urls = STEAM_PROXY_URLS[:worker_count]
        self.lanes: list[SteamClient] = [
            SteamClient(
                fixed_proxy_url=url,
                lane_id=i,
                request_cap=self.request_cap,
            )
            for i, url in enumerate(proxy_urls)
        ]
        masked = ", ".join(mask_proxy_url(u) for u in proxy_urls)
        logger.info(
            "Parallel workers: %d lanes, ~%.1fs/req per IP [%s]",
            len(self.lanes),
            STEAM_INTERVAL_PRICE,
            masked,
        )

    @property
    def requests_made(self) -> int:
        return sum(lane.requests_made for lane in self.lanes)

    @property
    def throttled_count(self) -> int:
        return sum(lane.throttled_count for lane in self.lanes)

    def close(self) -> None:
        for lane in self.lanes:
            lane.close()

    def __enter__(self) -> ParallelSteamClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def get(
        self,
        url: str,
        *,
        cookies: dict | None = None,
        endpoint: SteamEndpoint = SteamEndpoint.OTHER,
    ) -> httpx.Response:
        return self.lanes[0].get(url, cookies=cookies, endpoint=endpoint)

    def get_json(
        self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.OTHER
    ) -> dict[str, Any]:
        return self.lanes[0].get_json(url, endpoint=endpoint)

    def get_text(self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.OTHER) -> str:
        return self.lanes[0].get_text(url, endpoint=endpoint)

    def get_json_or_html(
        self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.SEARCH
    ) -> dict[str, Any] | str:
        return self.lanes[0].get_json_or_html(url, endpoint=endpoint)


def run_parallel_lanes(
    item_ids: list[int],
    clients: list[SteamClient],
    scan_one: ScanOneFn,
    *,
    label: str,
    log_every_pct: float = 2.0,
    request_cap: int | None = None,
) -> int:
    """Run scan_one(client, item_id) on each lane in parallel; return success count."""
    if not item_ids:
        return 0
    if len(clients) == 1:
        return _run_sequential_lane(
            item_ids, clients[0], scan_one, label, log_every_pct, request_cap
        )

    partitions = partition_ids(item_ids, len(clients))
    total = len(item_ids)
    progress = ProgressTracker(label, total, log_every_pct=log_every_pct)
    lock = threading.Lock()
    state = {"processed": 0, "ok": 0}
    abort_error: list[BaseException | None] = [None]
    cap = request_cap

    def total_requests() -> int:
        return sum(c.requests_made for c in clients)

    def run_lane(lane_idx: int, client: SteamClient, lane_ids: list[int]) -> int:
        local_ok = 0
        for item_id in lane_ids:
            if abort_error[0] is not None:
                break
            if cap is not None and total_requests() >= cap:
                abort_error[0] = RequestBudgetExceeded(
                    f"Request cap of {cap} reached for this run."
                )
                break
            try:
                if scan_one(client, item_id):
                    local_ok += 1
            except STEAM_CLIENT_ABORT_ERRORS as exc:
                abort_error[0] = exc
                break
            except Exception as exc:
                logger.warning("%s failed for item %d: %s", label, item_id, exc)

            with lock:
                state["processed"] += 1
                progress.update(
                    state["processed"],
                    extra=f"lane={lane_idx + 1}, ok={local_ok}, req={total_requests()}",
                )
        return local_ok

    with ThreadPoolExecutor(max_workers=len(clients)) as executor:
        futures = [
            executor.submit(run_lane, i, clients[i], partitions[i])
            for i in range(len(clients))
        ]
        results = [f.result() for f in as_completed(futures)]

    progress.finish(extra=f"ok={sum(results)}, req={total_requests()}")

    if abort_error[0] is not None:
        raise abort_error[0]

    return sum(results)


def _run_sequential_lane(
    item_ids: list[int],
    client: SteamClient,
    scan_one: ScanOneFn,
    label: str,
    log_every_pct: float,
    request_cap: int | None,
) -> int:
    total = len(item_ids)
    progress = ProgressTracker(label, total, log_every_pct=log_every_pct)
    ok = 0
    for idx, item_id in enumerate(item_ids, 1):
        if request_cap is not None and client.requests_made >= request_cap:
            raise RequestBudgetExceeded(
                f"Request cap of {request_cap} reached for this run."
            )
        try:
            if scan_one(client, item_id):
                ok += 1
        except STEAM_CLIENT_ABORT_ERRORS:
            raise
        except Exception as exc:
            logger.warning("%s failed for item %d: %s", label, item_id, exc)
        progress.update(idx, extra=f"ok={ok}, req={client.requests_made}")
    progress.finish(extra=f"ok={ok}")
    return ok
