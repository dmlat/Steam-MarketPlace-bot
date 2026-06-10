#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${APP_DIR:-$HOME/Steam-MarketPlace-bot}"
cd "$APP_DIR"

if [[ ! -f .env ]]; then
  echo "Copy deploy/env.prod.example to .env and fill secrets first."
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d
sleep 5
python scripts/init_db.py

sudo cp deploy/steam-scanner.service /etc/systemd/system/steam-scanner.service
sudo sed -i "s|/root/Steam-MarketPlace-bot|$APP_DIR|g" /etc/systemd/system/steam-scanner.service
sudo systemctl daemon-reload
sudo systemctl enable steam-scanner

echo "Deploy ready. Start: sudo systemctl start steam-scanner"