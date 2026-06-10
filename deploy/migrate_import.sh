#!/usr/bin/env bash
set -euo pipefail
DUMP="${1:?Usage: migrate_import.sh dumpfile}"
APP_DIR="${APP_DIR:-$HOME/Steam-MarketPlace-bot}"
cd "$APP_DIR"
set -a; source .env; set +a
docker exec -i steam_scanner_db pg_restore -U scanner -d steam_scanner --clean --if-exists < "$DUMP"
echo "Restore complete."