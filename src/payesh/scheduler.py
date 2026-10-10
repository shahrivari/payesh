"""Hourly collection while the local web server is running."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path

from payesh import web_storage as store

logger = logging.getLogger(__name__)


class CollectionScheduler:
    """Run a single collection at each interval, sharing the manual-run lock."""

    def __init__(self, path: Path, execute: Callable[[str], None], interval: float = 3600):
        self.path = path
        self.execute = execute
        self.interval = interval
        self.next_run_at: datetime | None = None
        self.stop = asyncio.Event()

    def status(self) -> dict:
        return {"enabled": self.interval > 0, "interval_seconds": self.interval,
                "next_run_at": self.next_run_at.isoformat(timespec="seconds") if self.next_run_at else None}

    async def run_once(self) -> None:
        run_id = await asyncio.to_thread(store.start_run, self.path, "scheduled")
        if run_id is not None:
            await asyncio.to_thread(self.execute, run_id)

    async def run(self) -> None:
        if self.interval <= 0:
            return
        self.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=self.interval)
        while not self.stop.is_set():
            delay = max(0, (self.next_run_at - datetime.now(timezone.utc)).total_seconds())
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=delay)
                break
            except TimeoutError:
                pass
            self.next_run_at += timedelta(seconds=self.interval)
            try:
                await self.run_once()
            except Exception:
                logger.exception("Scheduled collection could not be executed")
            # Skip missed ticks after a long run or device sleep; never queue catch-up runs.
            if self.next_run_at <= datetime.now(timezone.utc):
                self.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=self.interval)
        self.next_run_at = None
