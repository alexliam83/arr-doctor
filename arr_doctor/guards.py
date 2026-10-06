"""Guardrails that keep the MCP server within Sonarr/Radarr good practice.

Sonarr/Radarr are designed to find releases through RSS, not by searching: active
searches query every indexer and count against their API/grab limits, and abusive
use can get an account or IP banned (Servarr wiki: "How does Sonarr find
episodes", Prowlarr "Query Limit" / "Grab Limit"). An LLM can call tools in a loop,
so every operation that hits the indexers goes through :class:`IndexerBudget`.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import UTC, datetime, timedelta

from arr_doctor.clients.base import ArrError
from arr_doctor.i18n import t


class IndexerBudget:
    """Sliding one-hour window of operations that query the indexers.

    ``limit=0`` disables the budget.
    """

    WINDOW = 3600.0

    def __init__(self, limit: int, clock=time.monotonic) -> None:
        self.limit = limit
        self._clock = clock
        self._events: deque[float] = deque()

    def _prune(self) -> None:
        now = self._clock()
        while self._events and now - self._events[0] >= self.WINDOW:
            self._events.popleft()

    @property
    def used(self) -> int:
        self._prune()
        return len(self._events)

    def consume(self, n: int = 1) -> None:
        if self.limit <= 0 or n <= 0:
            return
        self._prune()
        if len(self._events) + n > self.limit:
            wait = self.WINDOW - (self._clock() - self._events[0]) if self._events else 0
            raise ArrError(t("budget_exceeded", limit=self.limit, minutes=max(1, round(wait / 60))))
        now = self._clock()
        self._events.extend([now] * n)


def recently_searched(last_search: str | None, cooldown_minutes: int, now: datetime | None = None) -> bool:
    """True if Sonarr/Radarr searched this item less than ``cooldown_minutes`` ago."""
    if not last_search or cooldown_minutes <= 0:
        return False
    try:
        when = datetime.fromisoformat(last_search.replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - when < timedelta(minutes=cooldown_minutes)
