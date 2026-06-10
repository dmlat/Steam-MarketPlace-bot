#!/usr/bin/env python3
"""Initialize database schema."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from steam_scanner.db.session import init_db, init_db_from_sql


def main():
    sql_path = ROOT / "sql" / "schema.sql"
    if sql_path.exists():
        print(f"Applying SQL schema from {sql_path}")
        init_db_from_sql(str(sql_path))
    else:
        print("Creating tables from ORM models")
        init_db()
    print("Database initialized successfully.")


if __name__ == "__main__":
    main()
