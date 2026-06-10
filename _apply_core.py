from pathlib import Path
ROOT = Path(r"D:\Steam_MarketPlace")

# config
cfg_path = ROOT / "src/steam_scanner/config.py"
cfg = cfg_path.read_text(encoding="utf-8")
marker = "EXCLUDED_APPIDS"
insert = '''from steam_scanner.steam.endpoint_kind import SteamEndpoint

'''
if "endpoint_kind" not in cfg:
    cfg = cfg.replace("EXCLUDED_APPIDS", insert + "EXCLUDED_APPIDS")
replacements = {
    'STEAM_REQUEST_INTERVAL = float(os.getenv("STEAM_REQUEST_INTERVAL", "4.0"))':
    'STEAM_REQUEST_INTERVAL = float(os.getenv("STEAM_REQUEST_INTERVAL", "8.0"))',
    'STEAM_429_MAX_RETRIES = int(os.getenv("STEAM_429_MAX_RETRIES", "12"))':
    'STEAM_429_MAX_RETRIES = int(os.getenv("STEAM_429_MAX_RETRIES", "2"))',
    'STEAM_429_COOLDOWN_SEC = float(os.getenv("STEAM_429_COOLDOWN_SEC", "45"))':
    'STEAM_429_COOLDOWN_SEC = float(os.getenv("STEAM_429_COOLDOWN_SEC", "120"))',
    'STEAM_429_CIRCUIT_THRESHOLD = int(os.getenv("STEAM_429_CIRCUIT_THRESHOLD", "25"))':
    'STEAM_429_CIRCUIT_THRESHOLD = int(os.getenv("STEAM_429_CIRCUIT_THRESHOLD", "3"))',
    'STEAM_PROXY_MAX_429 = int(os.getenv("STEAM_PROXY_MAX_429", "8"))':
    'STEAM_PROXY_MAX_429 = int(os.getenv("STEAM_PROXY_MAX_429", "1"))',
}
for a,b in replacements.items():
    cfg = cfg.replace(a,b)
if "STEAM_INTERVAL_PRICE" not in cfg:
    cfg = cfg.replace(
        'STEAM_REQUEST_INTERVAL = float(os.getenv("STEAM_REQUEST_INTERVAL", "8.0"))',
        '''STEAM_REQUEST_INTERVAL = float(os.getenv("STEAM_REQUEST_INTERVAL", "8.0"))
STEAM_INTERVAL_PRICE = float(os.getenv("STEAM_INTERVAL_PRICE", "10.0"))
STEAM_INTERVAL_SEARCH = float(os.getenv("STEAM_INTERVAL_SEARCH", "15.0"))
STEAM_INTERVAL_LISTING = float(os.getenv("STEAM_INTERVAL_LISTING", "25.0"))
STEAM_INTERVAL_ORDERBOOK = float(os.getenv("STEAM_INTERVAL_ORDERBOOK", "35.0"))
STEAM_INTERVAL_STORE = float(os.getenv("STEAM_INTERVAL_STORE", "15.0"))''')
if "STEAM_PROXY_COOLDOWN_HOURS" not in cfg:
    cfg = cfg.replace(
        'STEAM_PROXY_MAX_429 = int(os.getenv("STEAM_PROXY_MAX_429", "1"))',
        '''STEAM_PROXY_MAX_429 = int(os.getenv("STEAM_PROXY_MAX_429", "1"))
STEAM_PROXY_COOLDOWN_HOURS = float(os.getenv("STEAM_PROXY_COOLDOWN_HOURS", "6"))''')
if "def interval_for_endpoint" not in cfg:
    cfg = cfg.replace(
        "STEAM_PROXY_URLS: list[str] = _parse_proxy_urls(os.getenv(\"STEAM_PROXY_URLS\", \"\"))",
        '''STEAM_PROXY_URLS: list[str] = _parse_proxy_urls(os.getenv("STEAM_PROXY_URLS", ""))


def interval_for_endpoint(endpoint: SteamEndpoint) -> float:
    return {
        SteamEndpoint.PRICE: STEAM_INTERVAL_PRICE,
        SteamEndpoint.SEARCH: STEAM_INTERVAL_SEARCH,
        SteamEndpoint.LISTING: STEAM_INTERVAL_LISTING,
        SteamEndpoint.ORDERBOOK: STEAM_INTERVAL_ORDERBOOK,
        SteamEndpoint.STORE: STEAM_INTERVAL_STORE,
        SteamEndpoint.OTHER: STEAM_REQUEST_INTERVAL,
    }.get(endpoint, STEAM_REQUEST_INTERVAL)''')
cfg_path.write_text(cfg, encoding="utf-8")
print("config OK")

# client patches
client_path = ROOT / "src/steam_scanner/steam/client.py"
c = client_path.read_text(encoding="utf-8")
if "STEAM_PROXY_COOLDOWN_HOURS" not in c:
    c = c.replace("    STEAM_PROXY_URLS,\n    STEAM_REQUEST_INTERVAL,", "    STEAM_PROXY_COOLDOWN_HOURS,\n    STEAM_PROXY_URLS,\n    interval_for_endpoint,\n    STEAM_REQUEST_INTERVAL,")
    c = c.replace("from steam_scanner.config import (", "from steam_scanner.config import (\n")
    c = c.replace("from steam_scanner.steam.proxy_pool import", "from steam_scanner.steam.endpoint_kind import SteamEndpoint\nfrom steam_scanner.steam.proxy_pool import")
    c = c.replace(
        "self._proxy_pool = ProxyPool(STEAM_PROXY_URLS, max_429_per_proxy=STEAM_PROXY_MAX_429)",
        "self._proxy_pool = ProxyPool(\n                STEAM_PROXY_URLS,\n                max_429_per_proxy=STEAM_PROXY_MAX_429,\n                cooldown_hours=STEAM_PROXY_COOLDOWN_HOURS,\n            )",
    )
    c = c.replace(
        "if self._proxy_pool and self._proxy_pool.active_count > 1:",
        "if self._proxy_pool:",
    )
    c = c.replace(
        "    def _wait_rate_limit(self) -> None:\n        elapsed = time.monotonic() - self._last_request_at\n        wait = self.interval * self._backoff_multiplier - elapsed",
        "    def _wait_rate_limit(self, endpoint: SteamEndpoint = SteamEndpoint.OTHER) -> None:\n        self.interval = interval_for_endpoint(endpoint)\n        elapsed = time.monotonic() - self._last_request_at\n        wait = self.interval * self._backoff_multiplier - elapsed",
    )
    c = c.replace(
        "    def get(self, url: str, *, cookies: dict | None = None) -> httpx.Response:",
        "    def get(\n        self,\n        url: str,\n        *,\n        cookies: dict | None = None,\n        endpoint: SteamEndpoint = SteamEndpoint.OTHER,\n    ) -> httpx.Response:",
    )
    c = c.replace(
        "            self._wait_rate_limit()\n            self._pick_proxy()",
        "            self._wait_rate_limit(endpoint)\n            self._pick_proxy()",
    )
    c = c.replace(
        "    def get_json(self, url: str) -> dict[str, Any]:\n        response = self.get(url)",
        "    def get_json(self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.OTHER) -> dict[str, Any]:\n        response = self.get(url, endpoint=endpoint)",
    )
    c = c.replace(
        "    def get_text(self, url: str) -> str:\n        return self.get(url).text",
        "    def get_text(self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.OTHER) -> str:\n        return self.get(url, endpoint=endpoint).text",
    )
    c = c.replace(
        "    def get_json_or_html(self, url: str) -> dict[str, Any] | str:\n        response = self.get(url)",
        "    def get_json_or_html(self, url: str, *, endpoint: SteamEndpoint = SteamEndpoint.SEARCH) -> dict[str, Any] | str:\n        response = self.get(url, endpoint=endpoint)",
    )
client_path.write_text(c, encoding="utf-8")
print("client OK")

# collectors
po = ROOT / "src/steam_scanner/collectors/price_overview.py"
t = po.read_text(encoding="utf-8")
if "SteamEndpoint.PRICE" not in t:
    t = t.replace("from steam_scanner.steam.client import", "from steam_scanner.steam.endpoint_kind import SteamEndpoint\nfrom steam_scanner.steam.client import")
    t = t.replace("self.client.get_json(url)", "self.client.get_json(url, endpoint=SteamEndpoint.PRICE)")
    po.write_text(t, encoding="utf-8")
print("price_overview OK")

ms = ROOT / "src/steam_scanner/collectors/market_search.py"
t = ms.read_text(encoding="utf-8")
if "SteamEndpoint.SEARCH" not in t:
    t = t.replace("from steam_scanner.steam.client import", "from steam_scanner.steam.endpoint_kind import SteamEndpoint\nfrom steam_scanner.steam.client import")
    t = t.replace("get_json_or_html(url)", "get_json_or_html(url, endpoint=SteamEndpoint.SEARCH)")
    ms.write_text(t, encoding="utf-8")
print("market_search OK")

lp = ROOT / "src/steam_scanner/collectors/listing_parser.py"
t = lp.read_text(encoding="utf-8")
if "SteamEndpoint.LISTING" not in t:
    t = t.replace("from steam_scanner.steam.client import", "from steam_scanner.steam.endpoint_kind import SteamEndpoint\nfrom steam_scanner.steam.client import")
    t = t.replace("self.client.get_text(url)", "self.client.get_text(url, endpoint=SteamEndpoint.LISTING)")
    lp.write_text(t, encoding="utf-8")
print("listing OK")

ob = ROOT / "src/steam_scanner/collectors/orderbook.py"
t = ob.read_text(encoding="utf-8")
if "SteamEndpoint.ORDERBOOK" not in t:
    t = t.replace("from steam_scanner.steam.client import", "from steam_scanner.steam.endpoint_kind import SteamEndpoint\nfrom steam_scanner.steam.client import")
    t = t.replace("self.client.get_json(url)", "self.client.get_json(url, endpoint=SteamEndpoint.ORDERBOOK)")
    ob.write_text(t, encoding="utf-8")
print("orderbook OK")

ad = ROOT / "src/steam_scanner/collectors/app_discovery.py"
t = ad.read_text(encoding="utf-8")
if "SteamEndpoint.STORE" not in t:
    t = t.replace("from steam_scanner.steam.client import", "from steam_scanner.steam.endpoint_kind import SteamEndpoint\nfrom steam_scanner.steam.client import")
    t = t.replace("self.client.get_text(url)", "self.client.get_text(url, endpoint=SteamEndpoint.STORE)")
    ad.write_text(t, encoding="utf-8")
print("app_discovery OK")