"""Tests for parallel proxy worker partitioning and client pool."""

from unittest.mock import patch

from steam_scanner.steam.parallel import ParallelSteamClient, partition_ids


def test_partition_ids_empty():
    assert partition_ids([], 3) == []


def test_partition_ids_single_lane():
    assert partition_ids([1, 2, 3], 1) == [[1, 2, 3]]


def test_partition_ids_round_robin_balanced():
    ids = list(range(6001))
    lanes = partition_ids(ids, 3)
    assert len(lanes) == 3
    assert len(lanes[0]) == 2001
    assert len(lanes[1]) == 2000
    assert len(lanes[2]) == 2000
    assert lanes[0][0] == 0 and lanes[1][0] == 1 and lanes[2][0] == 2
    assert sum(len(l) for l in lanes) == 6001


def test_parallel_steam_client_lane_count():
    urls = [
        "socks5://u:p@1.1.1.1:1080",
        "socks5://u:p@2.2.2.2:1080",
        "socks5://u:p@3.3.3.3:1080",
    ]
    with patch("steam_scanner.steam.parallel.STEAM_PROXY_URLS", urls), patch(
        "steam_scanner.steam.parallel.effective_parallel_workers", return_value=3
    ):
        pool = ParallelSteamClient(request_cap=9000)
    try:
        assert len(pool.lanes) == 3
        assert pool.lanes[0].fixed_proxy_url == urls[0]
        assert pool.lanes[1].lane_id == 1
        assert pool.request_cap == 9000
        assert pool.requests_made == 0
    finally:
        pool.close()


@patch("steam_scanner.config.STEAM_PROXY_URLS", [])
@patch("steam_scanner.config.STEAM_PARALLEL_WORKERS", 3)
def test_effective_parallel_workers_no_proxies():
    from steam_scanner.config import effective_parallel_workers

    assert effective_parallel_workers() == 1


@patch("steam_scanner.config.STEAM_PROXY_URLS", ["socks5://a", "socks5://b", "socks5://c"])
@patch("steam_scanner.config.STEAM_PARALLEL_WORKERS", 0)
def test_effective_parallel_workers_auto():
    from steam_scanner.config import effective_parallel_workers

    assert effective_parallel_workers() == 3
