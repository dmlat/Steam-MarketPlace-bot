"""Progress logging helpers with percentage and ETA-style hints."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def pct(current: int | float, total: int | float) -> float:
    if total <= 0:
        return 100.0
    return min(100.0, max(0.0, current / total * 100))


def pct_remaining(current: int | float, total: int | float) -> float:
    return max(0.0, 100.0 - pct(current, total))


@dataclass
class ProgressTracker:
    """Log progress at configurable intervals."""

    label: str
    total: int
    log_every_pct: float = 5.0
    _last_logged_pct: float = field(default=-1.0, init=False)
    _started_at: float = field(default_factory=time.monotonic, init=False)
    _last_current: int = field(default=0, init=False)

    def update(
        self,
        current: int,
        *,
        force: bool = False,
        extra: str = "",
        total: int | None = None,
    ) -> None:
        effective_total = total if total is not None else self.total
        if effective_total <= 0:
            return

        self._last_current = current
        done = pct(current, effective_total)
        remaining = pct_remaining(current, effective_total)

        should_log = force
        if not should_log and done >= 100:
            should_log = self._last_logged_pct < 100
        elif not should_log:
            if self._last_logged_pct < 0:
                should_log = True
            elif done - self._last_logged_pct >= self.log_every_pct:
                should_log = True

        if not should_log:
            return

        self._last_logged_pct = done
        elapsed = time.monotonic() - self._started_at
        rate = current / elapsed if elapsed > 0 and current > 0 else 0
        eta_sec = (effective_total - current) / rate if rate > 0 else 0

        msg = (
            f"[{self.label}] {current}/{effective_total} ({done:.1f}%) "
            f"| remaining {remaining:.1f}%"
        )
        if rate > 0:
            msg += f" | ~{eta_sec / 60:.1f} min"
        if extra:
            msg += f" | {extra}"
        logger.info(msg)

    def finish(self, extra: str = "") -> None:
        self.update(self.total, force=True, extra=extra or "done")


def log_budget(label: str, used: int, cap: int) -> None:
    remaining = max(0, cap - used)
    logger.info(
        "[%s] requests: %d/%d (%.1f%%) | %d left (%.1f%% of cap)",
        label,
        used,
        cap,
        pct(used, cap),
        remaining,
        pct_remaining(used, cap),
    )
