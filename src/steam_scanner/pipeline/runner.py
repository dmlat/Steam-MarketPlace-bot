"""Pipeline orchestration with checkpoints."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime

from steam_scanner.analytics.fee_engine import build_fee_table, calculate_fee
from steam_scanner.analytics.scoring import ScoringEngine
from steam_scanner.analytics.currency import CurrencyAnalyzer
from steam_scanner.collectors.app_discovery import AppDiscovery
from steam_scanner.collectors.market_search import MarketSearchCollector
from steam_scanner.collectors.orderbook import OrderBookCollector
from steam_scanner.collectors.price_overview import PriceOverviewCollector
from steam_scanner.config import STEAM_NIGHTLY_REQUEST_CAP
from steam_scanner.db.models import FeeCalculation, PipelineRun
from steam_scanner.db.session import get_session
from steam_scanner.export.csv_export import export_all
from steam_scanner.log_setup import configure_logging
from steam_scanner.progress import pct, log_budget
from steam_scanner.steam.client import SteamClient, RequestBudgetExceeded, RateLimitCircuitOpenError

configure_logging()

logger = logging.getLogger(__name__)


STAGES = [
    "discovery",
    "market_search",
    "general_market",
    "price_scan",
    "orderbook_scan",
    "currency_scan",
    "fee_calc",
    "scoring",
    "export",
]


class PipelineRunner:
    def __init__(self, resume: bool = False, request_cap: int | None = None):
        self.resume = resume
        self.client = SteamClient(request_cap=request_cap or STEAM_NIGHTLY_REQUEST_CAP)
        self.run_id: int | None = None

    def _start_stage(self, stage: str) -> PipelineRun:
        with get_session() as session:
            run = PipelineRun(stage=stage, status="running", started_at=datetime.utcnow())
            session.add(run)
            session.flush()
            self.run_id = run.id
            return run

    def _complete_stage(self, metadata: dict | None = None) -> None:
        if not self.run_id:
            return
        with get_session() as session:
            run = session.get(PipelineRun, self.run_id)
            if run:
                run.status = "completed"
                run.completed_at = datetime.utcnow()
                run.requests_made = self.client.requests_made
                run.metadata_ = metadata

    def _get_checkpoint(self, stage: str) -> dict | None:
        if not self.resume:
            return None
        with get_session() as session:
            run = (
                session.query(PipelineRun)
                .filter(PipelineRun.stage == stage, PipelineRun.status == "completed")
                .order_by(PipelineRun.completed_at.desc())
                .first()
            )
            return run.metadata_ if run else None

    def run_discovery(self, max_pages: int | None = None) -> int:
        self._start_stage("discovery")
        discovery = AppDiscovery(client=self.client)
        count = discovery.discover_all(max_pages=max_pages)
        self._complete_stage({"apps_discovered": count})
        return count

    def run_market_search(
        self,
        max_pages_per_game: int = 5,
        max_games: int | None = None,
    ) -> int:
        self._start_stage("market_search")
        checkpoint = self._get_checkpoint("market_search")
        resume_appid = checkpoint.get("last_appid") if checkpoint else None

        discovery = AppDiscovery(client=self.client)
        appids = discovery.get_eligible_appids()
        if max_games:
            appids = appids[:max_games]

        collector = MarketSearchCollector(client=self.client)
        total = collector.collect_all_games(
            appids,
            resume_from_appid=resume_appid,
            max_pages_per_game=max_pages_per_game,
        )
        self._complete_stage({"items_collected": total, "last_appid": appids[-1] if appids else None})
        return total

    def run_general_market(self, max_items: int = 5000) -> int:
        self._start_stage("general_market")
        collector = MarketSearchCollector(client=self.client)
        total = collector.collect_general_market(max_items=max_items)
        self._complete_stage({"general_items": total})
        return total

    def run_price_scan(self, limit: int | None = None) -> int:
        self._start_stage("price_scan")
        collector = PriceOverviewCollector(client=self.client)
        count = collector.scan_all(limit=limit, skip_already_priced=True)
        self._complete_stage({"prices_scanned": count, "skip_already_priced": True})
        return count

    def run_orderbook_scan(self, limit: int = 500) -> int:
        self._start_stage("orderbook_scan")
        short_list = PriceOverviewCollector.get_short_list(limit=limit * 2)
        collector = OrderBookCollector(client=self.client)
        count = collector.collect_batch(short_list, limit=limit)
        self._complete_stage({"orderbooks_collected": count})
        return count

    def run_currency_scan(self, limit: int = 200) -> int:
        self._start_stage("currency_scan")
        short_list = PriceOverviewCollector.get_short_list(limit=limit)
        analyzer = CurrencyAnalyzer(client=self.client)
        count = analyzer.analyze_batch(short_list, limit=limit)
        self._complete_stage({"currency_analyzed": count})
        return count

    def run_fee_calc(self) -> int:
        self._start_stage("fee_calc")
        table = build_fee_table()
        count = 0
        with get_session() as session:
            for row in table:
                fee = calculate_fee(row["buyer_pays"])
                fc = FeeCalculation(
                    market_item_id=None,
                    currency_code="USD",
                    buyer_pays=float(fee.buyer_pays),
                    seller_receives=float(fee.seller_receives),
                    steam_fee=float(fee.steam_fee),
                    publisher_fee=float(fee.publisher_fee),
                    total_fee=float(fee.total_fee),
                    effective_fee_pct=float(fee.effective_fee_pct),
                    break_even_sell_price=float(fee.break_even_sell_price),
                    minimum_profitable_sell_price=float(fee.minimum_profitable_sell_price),
                )
                session.add(fc)
                count += 1
        self._complete_stage({"fee_rows": count})
        return count

    def run_scoring(self) -> int:
        self._start_stage("scoring")
        engine = ScoringEngine()
        count = engine.score_all()
        self._complete_stage({"scored": count})
        return count

    def run_export(self) -> dict:
        self._start_stage("export")
        paths = export_all()
        self._complete_stage({"exports": {k: str(v) for k, v in paths.items()}})
        return paths

    def run_full(
        self,
        discovery_pages: int | None = None,
        max_games: int | None = None,
        max_pages_per_game: int = 5,
        general_market_items: int = 12000,
        price_limit: int | None = 10000,
        orderbook_limit: int = 500,
        currency_limit: int = 200,
        skip_discovery: bool = False,
    ) -> None:
        stage_plan: list[tuple[str, callable]] = []
        if not skip_discovery:
            stage_plan.append(("discovery", lambda: self.run_discovery(max_pages=discovery_pages)))
        stage_plan.extend([
            ("general_market", lambda: self.run_general_market(max_items=general_market_items)),
            ("market_search", lambda: self.run_market_search(max_pages_per_game, max_games)),
            ("price_scan", lambda: self.run_price_scan(limit=price_limit)),
            ("orderbook_scan", lambda: self.run_orderbook_scan(orderbook_limit)),
            ("currency_scan", lambda: self.run_currency_scan(currency_limit)),
            ("fee_calc", lambda: self.run_fee_calc()),
            ("scoring", lambda: self.run_scoring()),
            ("export", lambda: self.run_export()),
        ])
        total_stages = len(stage_plan)

        try:
            for idx, (stage_name, stage_fn) in enumerate(stage_plan, 1):
                done_pct = pct(idx - 1, total_stages)
                remaining_pct = 100.0 - done_pct
                logger.info(
                    "=== Pipeline stage %d/%d: %s | done %.1f%%, remaining %.1f%% ===",
                    idx,
                    total_stages,
                    stage_name,
                    done_pct,
                    remaining_pct,
                )
                log_budget("Pipeline", self.client.requests_made, self.client.request_cap)
                stage_fn()
                logger.info(
                    "=== Stage %s complete (%d/%d, %.1f%% pipeline) ===",
                    stage_name,
                    idx,
                    total_stages,
                    pct(idx, total_stages),
                )

            logger.info("Pipeline complete. Requests used: %d", self.client.requests_made)

        except RequestBudgetExceeded as exc:
            logger.error(
                "Request budget exceeded: %s. Re-run with --resume. Used %d/%d requests.",
                exc,
                self.client.requests_made,
                self.client.request_cap,
            )
        except RateLimitCircuitOpenError as exc:
            logger.error(
                "Steam rate limit circuit open: %s Used %d requests. "
                "Wait a few hours and re-run with --resume.",
                exc,
                self.client.requests_made,
            )
        finally:
            self.client.close()


def main():
    parser = argparse.ArgumentParser(description="Steam Market Research Scanner Pipeline")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoints")
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--discovery-pages", type=int, default=None)
    parser.add_argument("--max-games", type=int, default=None)
    parser.add_argument("--max-pages-per-game", type=int, default=5)
    parser.add_argument("--general-market-items", type=int, default=3000)
    parser.add_argument("--orderbook-limit", type=int, default=500)
    parser.add_argument("--currency-limit", type=int, default=200)
    parser.add_argument("--request-cap", type=int, default=STEAM_NIGHTLY_REQUEST_CAP)
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default=None,
        help="Run single stage only",
    )
    args = parser.parse_args()

    runner = PipelineRunner(resume=args.resume, request_cap=args.request_cap)

    if args.stage:
        stage_map = {
            "discovery": lambda: runner.run_discovery(args.discovery_pages),
            "market_search": lambda: runner.run_market_search(args.max_pages_per_game, args.max_games),
            "general_market": lambda: runner.run_general_market(args.general_market_items),
            "price_scan": lambda: runner.run_price_scan(),
            "orderbook_scan": lambda: runner.run_orderbook_scan(args.orderbook_limit),
            "currency_scan": lambda: runner.run_currency_scan(args.currency_limit),
            "fee_calc": lambda: runner.run_fee_calc(),
            "scoring": lambda: runner.run_scoring(),
            "export": lambda: runner.run_export(),
        }
        stage_map[args.stage]()
    else:
        runner.run_full(
            discovery_pages=args.discovery_pages,
            max_games=args.max_games,
            max_pages_per_game=args.max_pages_per_game,
            general_market_items=args.general_market_items,
            orderbook_limit=args.orderbook_limit,
            currency_limit=args.currency_limit,
            skip_discovery=args.skip_discovery,
        )


if __name__ == "__main__":
    main()
