#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${APP_DIR:-$HOME/Steam-MarketPlace-bot}"
cd "$APP_DIR"
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart steam-scanner
./deploy/status.sh