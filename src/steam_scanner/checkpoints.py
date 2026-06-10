"""Persistent checkpoints for resumable collection."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "checkpoints"


def checkpoint_path(name: str) -> Path:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR / f"{name}.json"


def load_checkpoint(name: str) -> dict[str, Any] | None:
    path = checkpoint_path(name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.info("Checkpoint loaded: %s (updated %s)", name, data.get("updated_at"))
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load checkpoint %s: %s", name, exc)
        return None


def save_checkpoint(name: str, data: dict[str, Any]) -> None:
    path = checkpoint_path(name)
    payload = {**data, "updated_at": datetime.utcnow().isoformat()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_checkpoint(name: str) -> None:
    path = checkpoint_path(name)
    if path.exists():
        path.unlink()
        logger.info("Checkpoint cleared: %s", name)