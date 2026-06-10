#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${APP_DIR:-$HOME/Steam-MarketPlace-bot}"
cd "$APP_DIR"
source .venv/bin/activate
python scripts/status.py --minutes "${1:-30}"
echo "--- last 15 log lines ---"
tail -n 15 logs/continue.log 2>/dev/null || true