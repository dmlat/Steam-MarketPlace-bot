"""Tests for compliance guard."""

import pytest

from steam_scanner.compliance import ComplianceError, ComplianceGuard


def test_validate_allowed_url():
    ComplianceGuard.validate_url(
        "https://steamcommunity.com/market/priceoverview/?appid=753&format=json"
    )


def test_reject_post():
    with pytest.raises(ComplianceError):
        ComplianceGuard.validate_url(
            "https://steamcommunity.com/market/createbuyorder/",
            method="POST",
        )


def test_reject_forbidden_path():
    with pytest.raises(ComplianceError):
        ComplianceGuard.validate_url(
            "https://steamcommunity.com/market/createbuyorder/?",
        )


def test_reject_session_cookies():
    with pytest.raises(ComplianceError):
        ComplianceGuard.validate_cookies({"sessionid": "abc123"})
