"""Tests for skipping already-priced items in price scan queue."""

import os

import pytest

from steam_scanner.collectors.price_overview import PriceOverviewCollector


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
def test_queue_skips_items_with_usd_snapshot():
    item_ids, skipped = PriceOverviewCollector._queue_item_ids(
        limit=10_000,
        currency_code="USD",
        skip_already_priced=True,
        resume_from_id=None,
    )

    assert skipped >= 0
    assert len(item_ids) + skipped <= 10_000
    assert len(item_ids) == len(set(item_ids))

    if skipped > 0:
        assert len(item_ids) < 10_000


def test_scan_all_accepts_skip_flag():
    import inspect

    sig = inspect.signature(PriceOverviewCollector.scan_all)
    assert sig.parameters["skip_already_priced"].default is True
