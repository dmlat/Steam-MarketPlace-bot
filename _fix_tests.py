from pathlib import Path
p = Path(r"D:\Steam_MarketPlace\tests\test_client_429.py")
t = p.read_text(encoding="utf-8")
if "STEAM_PROXY_URLS" not in t:
    t = t.replace(
        "def test_429_not_counted_as_successful_request():",
        "@patch(\"steam_scanner.steam.client.STEAM_PROXY_URLS\", [])\ndef test_429_not_counted_as_successful_request():",
    )
    t = t.replace(
        "def test_circuit_breaker_opens_after_consecutive_429():",
        "@patch(\"steam_scanner.steam.client.STEAM_PROXY_URLS\", [])\ndef test_circuit_breaker_opens_after_consecutive_429():",
    )
    t = t.replace(
        "def test_circuit_breaker_resets_after_success():",
        "@patch(\"steam_scanner.steam.client.STEAM_PROXY_URLS\", [])\ndef test_circuit_breaker_resets_after_success():",
    )
    if "from unittest.mock import patch" in t and ", patch" not in t.split("import")[1][:30]:
        t = t.replace("from unittest.mock import patch", "from unittest.mock import patch")
    p.write_text(t, encoding="utf-8")
print("tests patched")