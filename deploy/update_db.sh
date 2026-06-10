#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${APP_DIR:-$HOME/Steam-MarketPlace-bot}"
cd "$APP_DIR"
docker compose -f deploy/docker-compose.prod.yml --env-file .env restart postgres