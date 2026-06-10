"""Multi-currency price analysis."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from steam_scanner.config import CURRENCIES
from steam_scanner.collectors.price_overview import PriceOverviewCollector
from steam_scanner.db.models import CurrencyAnalysis, MarketItem
from steam_scanner.db.session import get_session
from steam_scanner.steam.client import STEAM_CLIENT_ABORT_ERRORS, SteamClient

logger = logging.getLogger(__name__)

# Reference FX rates for anomaly detection (approximate, analysis only)
REFERENCE_FX_TO_USD = {
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "RUB": Decimal("0.011"),
    "BRL": Decimal("0.20"),
    "CNY": Decimal("0.14"),
}

ANOMALY_THRESHOLD_PCT = Decimal("15")


class CurrencyAnalyzer:
    def __init__(self, client: SteamClient | None = None):
        self.client = client or SteamClient()
        self.price_collector = PriceOverviewCollector(client=self.client)

    def analyze_item(self, item: MarketItem) -> CurrencyAnalysis | None:
        prices: dict[str, Decimal | None] = {}

        for code in CURRENCIES:
            snap = self.price_collector.scan_item(item, currency_code=code)
            if snap and snap.lowest_price:
                prices[code] = Decimal(str(snap.lowest_price))
            else:
                prices[code] = None

        usd = prices.get("USD")
        if not usd or usd <= 0:
            return None

        implied = {}
        anomalies = {}
        for code, price in prices.items():
            if code == "USD" or not price or price <= 0:
                continue
            implied_key = f"implied_usd_{code.lower()}"
            implied[implied_key] = price / usd

            ref = REFERENCE_FX_TO_USD.get(code)
            if ref and ref > 0:
                dev_pct = abs(implied[implied_key] - ref) / ref * 100
                if dev_pct > ANOMALY_THRESHOLD_PCT:
                    anomalies[code] = float(dev_pct)

        with get_session() as session:
            row = CurrencyAnalysis(
                market_item_id=item.id,
                price_usd=float(prices["USD"]) if prices.get("USD") else None,
                price_eur=float(prices["EUR"]) if prices.get("EUR") else None,
                price_rub=float(prices["RUB"]) if prices.get("RUB") else None,
                price_gbp=float(prices["GBP"]) if prices.get("GBP") else None,
                price_brl=float(prices["BRL"]) if prices.get("BRL") else None,
                price_cny=float(prices["CNY"]) if prices.get("CNY") else None,
                implied_usd_eur=float(implied.get("implied_usd_eur")) if implied.get("implied_usd_eur") else None,
                implied_usd_rub=float(implied.get("implied_usd_rub")) if implied.get("implied_usd_rub") else None,
                implied_usd_gbp=float(implied.get("implied_usd_gbp")) if implied.get("implied_usd_gbp") else None,
                implied_usd_brl=float(implied.get("implied_usd_brl")) if implied.get("implied_usd_brl") else None,
                implied_usd_cny=float(implied.get("implied_usd_cny")) if implied.get("implied_usd_cny") else None,
                rounding_anomaly=bool(anomalies),
                anomaly_details=anomalies if anomalies else None,
                calculated_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            return row

    def analyze_batch(self, item_ids: list[int], limit: int = 500) -> int:
        count = 0
        ids = item_ids[:limit]
        from steam_scanner.progress import ProgressTracker, log_budget

        progress = ProgressTracker("Currency scan", len(ids), log_every_pct=5.0)
        logger.info("Currency scan: %d items x %d currencies", len(ids), len(CURRENCIES))

        for idx, item_id in enumerate(ids, 1):
            try:
                with get_session() as session:
                    db_item = session.get(MarketItem, item_id)
                    if db_item:
                        result = self.analyze_item(db_item)
                        if result:
                            count += 1
                progress.update(idx, extra=f"ok={count}, req={self.client.requests_made}")
                if idx % 10 == 0:
                    log_budget("Currency", self.client.requests_made, self.client.request_cap)
            except STEAM_CLIENT_ABORT_ERRORS:
                raise
            except Exception as exc:
                logger.warning("Currency analysis failed for %d: %s", item_id, exc)

        progress.finish(extra=f"analyzed={count}")
        return count
