# Steam Market Research Scanner

Read-only research system for analyzing Steam Community Market items (trading cards, foil cards, booster packs, emoticons, backgrounds, and other community items) to identify potential market inefficiencies.

**Excludes:** CS2 (730), TF2 (440), Dota 2 (570), Rust (252490).

This tool does **not** perform automated trading, login, or order placement. See [COMPLIANCE.md](COMPLIANCE.md).

## Requirements

- Python 3.11+
- Docker (for PostgreSQL)
- ~2 GB disk for database and exports

## Quick start

```bash
# 1. Clone and enter project
cd D:\Steam_MarketPlace

# 2. Copy environment
copy .env.example .env

# 3. Start PostgreSQL (port 5433 by default)
docker compose up -d

# 4. Create virtual environment and install
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

# 5. Initialize database
python scripts/init_db.py

# 6. Run full pipeline (resumable, rate-limited)
.\scripts\run.ps1 continue 8000

# Or directly:
python scripts/run_continue.py 8000

# Or run stages individually:
python scripts/run_discovery.py
python scripts/run_price_scan.py
python scripts/run_orderbook_scan.py

# 7. Export CSV reports
python -c "from steam_scanner.export.csv_export import export_all; export_all()"

# Or resume collection + analytics with progress logs:
python scripts/run_continue.py 8000

# After network/VPN outage — just re-run (checkpoint in checkpoints/bulk_collect.json):
python scripts/run_continue.py 8000

# 8. Launch dashboard
streamlit run dashboard/app.py
```

## Project structure

```
src/steam_scanner/     Core library (collectors, analytics, pipeline)
dashboard/             Streamlit UI
scripts/               CLI entry points
sql/                   PostgreSQL schema
tests/                 Unit tests
exports/               Generated CSV/Excel reports
```

## Pipeline stages

1. **Discovery** — games with trading cards + market items (appid 753)
2. **Price scan** — priceoverview snapshots in USD
3. **Order book** — item_nameid + histogram for short-list items
4. **Currency** — multi-currency price comparison
5. **Fee engine** — commission model and break-even
6. **Scoring** — opportunity scores and risk flags
7. **Export** — CSV/Excel + final report

## Configuration

Edit `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | postgresql+psycopg2://... | PostgreSQL connection |
| `POSTGRES_PORT` | 5433 | Host port for Docker Postgres |
| `STEAM_REQUEST_INTERVAL` | 4.0 | Seconds between Steam requests (base; adapts up on 429) |
| `STEAM_429_COOLDOWN_SEC` | 45 | Mandatory pause after 3+ consecutive 429s |
| `STEAM_429_MAX_RETRIES` | 12 | Max retries per URL when rate-limited |
| `STEAM_NETWORK_MAX_WAIT_SEC` | 120 | Max wait per request when VPN/internet drops |
| `STEAM_NIGHTLY_REQUEST_CAP` | 10000 | Max successful requests per pipeline run |

## Tests

```bash
pytest tests/ -v
```

## MVP criteria (§19)

- 10,000+ market items collected
- 3,000+ trading cards
- 500+ order book snapshots
- Fee model, currency analysis, scoring
- Streamlit dashboard with 6 tabs
- CSV exports and compliance documentation

## License

Research use only. Respect Steam Terms of Service and rate limits.
