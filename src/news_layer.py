"""
JcampFX — News & Events Awareness Layer (Phase 2, PRD §4)

Provides currency-specific trade blocking around high/medium-impact economic events.

Phase 2 stub: Events loaded from a JSON file (data/news_events.json).
Phase 4 upgrade: Call load_from_zmq() to replace file data with live MQL5 calendar
                 piped via ZMQ port 5557.

Event format (JSON):
    [
      {
        "event_id": "NFP_2024_12_06",
        "name": "Non-Farm Payrolls",
        "currency": "USD",
        "impact": "HIGH",
        "time_utc": "2024-12-06T13:30:00",
        "actual": null,
        "forecast": "220K",
        "previous": "205K"
      },
      ...
    ]

Impact levels (PRD §4.2):
    HIGH   — block −30 to +15 min, tighten SL to 0.5R on open trades
    MEDIUM — block −15 to +10 min, no change to open trades
    LOW    — no block, dashboard flag only

Currency-specific gating (PRD §4.3):
    Events block only pairs containing the affected currency.
    USD NFP blocks: EURUSD, GBPUSD, USDJPY, USDCHF
    USD NFP does NOT block: AUDJPY (no USD leg)

Post-event cooling (PRD §4.4):
    15 minutes after HIGH events: only CompositeScore > 80 signals allowed.

Validation:
    VN.3 — High-impact events block affected pairs −30 to +15 min
    VN.4 — Non-affected pairs remain tradeable
    VN.5 — Blocked signals logged with event name, not silently dropped
    VN.6 — Post-event cooling: 15 min allows only CS > 80 signals
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.config import (
    NEWS_HIGH_BLOCK_AFTER,
    NEWS_HIGH_BLOCK_BEFORE,
    NEWS_MEDIUM_BLOCK_AFTER,
    NEWS_MEDIUM_BLOCK_BEFORE,
    NEWS_POST_EVENT_COOL_MIN,
    NEWS_POST_EVENT_MIN_CS,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NewsEvent dataclass
# ---------------------------------------------------------------------------

@dataclass
class NewsEvent:
    event_id: str
    name: str
    currency: str           # Affected currency (e.g. "USD", "EUR")
    impact: str             # "HIGH" | "MEDIUM" | "LOW"
    time_utc: datetime      # UTC event time
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "NewsEvent":
        time_utc = d["time_utc"]
        if isinstance(time_utc, str):
            # Parse ISO format, ensure UTC
            dt = datetime.fromisoformat(time_utc.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            time_utc = dt
        return cls(
            event_id=str(d["event_id"]),
            name=str(d["name"]),
            currency=str(d["currency"]).upper(),
            impact=str(d["impact"]).upper(),
            time_utc=time_utc,
            actual=d.get("actual"),
            forecast=d.get("forecast"),
            previous=d.get("previous"),
        )


# ---------------------------------------------------------------------------
# NewsLayer
# ---------------------------------------------------------------------------

class NewsLayer:
    """
    Manages economic event data and provides trade gating logic.

    Phase 2: load events from JSON file.
    Phase 4: call load_from_zmq() to replace with live MQL5 calendar data.
    """

    def __init__(self) -> None:
        self._events: list[NewsEvent] = []

    # --- Data loading ---

    def load_from_json(self, path: str | Path) -> None:
        """Load events from a JSON file (Phase 2 stub)."""
        p = Path(path)
        if not p.exists():
            log.warning("News events file not found: %s — news gating disabled", p)
            return

        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)

        self._events = [NewsEvent.from_dict(d) for d in raw]
        log.info("NewsLayer: loaded %d events from %s", len(self._events), p)

    def load_from_zmq(self, data: list[dict]) -> None:
        """
        Phase 4 hook — replace events with live MQL5 calendar data from ZMQ.
        Called by the ZMQ bridge after receiving event payload on port 5557.
        """
        self._events = [NewsEvent.from_dict(d) for d in data]
        log.info("NewsLayer: loaded %d events from ZMQ", len(self._events))

    def add_event(self, event: NewsEvent) -> None:
        """Add a single event (useful for testing)."""
        self._events.append(event)

    def clear(self) -> None:
        self._events.clear()

    # --- Currency extraction helpers ---

    @staticmethod
    def _pair_currencies(pair: str) -> set[str]:
        """Return the two currency codes from a 6-character pair string."""
        if len(pair) != 6:
            return set()
        return {pair[:3].upper(), pair[3:].upper()}

    @staticmethod
    def _event_affects_pair(event: NewsEvent, pair: str) -> bool:
        """Return True if the event's currency is in the pair's legs."""
        return event.currency in NewsLayer._pair_currencies(pair)

    # --- Block window logic ---

    def _block_window(self, event: NewsEvent) -> tuple[timedelta, timedelta]:
        """Return (before_delta, after_delta) for the event's impact level."""
        if event.impact == "HIGH":
            return (
                timedelta(minutes=NEWS_HIGH_BLOCK_BEFORE),
                timedelta(minutes=NEWS_HIGH_BLOCK_AFTER),
            )
        if event.impact == "MEDIUM":
            return (
                timedelta(minutes=NEWS_MEDIUM_BLOCK_BEFORE),
                timedelta(minutes=NEWS_MEDIUM_BLOCK_AFTER),
            )
        return timedelta(0), timedelta(0)  # LOW — no block

    def is_blocked(
        self,
        pair: str,
        dt: datetime,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a new trade signal should be blocked for `pair` at time `dt`.

        Returns
        -------
        (blocked, reason_string)
        blocked = True if within a HIGH or MEDIUM impact window for a currency in `pair`.
        reason_string includes the event name (VN.5 — never silently dropped).

        VN.3: HIGH events block −30 to +15 min
        VN.4: Only pairs containing the affected currency are blocked
        """
        if not self._events:
            return False, None

        # Ensure dt is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        for event in self._events:
            if event.impact == "LOW":
                continue
            if not self._event_affects_pair(event, pair):
                continue  # VN.4: currency-specific gating

            event_time = event.time_utc
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            before_delta, after_delta = self._block_window(event)
            block_start = event_time - before_delta
            block_end = event_time + after_delta

            if block_start <= dt <= block_end:
                reason = f"NEWS_BLOCKED:{event.impact}:{event.name}({event.currency})"
                log.info(
                    "Signal BLOCKED — %s at %s within %s window [%s → %s]",
                    pair, dt, event.impact, block_start, block_end,
                )
                return True, reason

        return False, None

    def is_post_event_cooling(self, pair: str, dt: datetime) -> bool:
        """
        PRD §4.4: 15-minute cooling after HIGH events.
        Returns True if pair is in cooling period (only CS > 80 signals allowed).
        The Brain Core checks CompositeScore separately.

        VN.6: only CS > NEWS_POST_EVENT_MIN_CS (80) allowed during cooling.
        """
        if not self._events:
            return False

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        for event in self._events:
            if event.impact != "HIGH":
                continue
            if not self._event_affects_pair(event, pair):
                continue

            event_time = event.time_utc
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            # After-event cooling window: event_end → event_end + 15 min
            after_delta = timedelta(minutes=NEWS_HIGH_BLOCK_AFTER)
            cool_start = event_time + after_delta
            cool_end = cool_start + timedelta(minutes=NEWS_POST_EVENT_COOL_MIN)

            if cool_start <= dt <= cool_end:
                return True

        return False

    def get_upcoming(
        self,
        pair: str,
        dt: datetime,
        hours_ahead: int = 24,
    ) -> list[NewsEvent]:
        """
        Return upcoming events affecting `pair` within the next `hours_ahead` hours.
        Used by the dashboard to display countdown timers (VN.7).
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        cutoff = dt + timedelta(hours=hours_ahead)
        result = []
        for event in self._events:
            event_time = event.time_utc
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            if dt <= event_time <= cutoff and self._event_affects_pair(event, pair):
                result.append(event)

        return sorted(result, key=lambda e: e.time_utc)

    def get_all_upcoming(self, dt: datetime, hours_ahead: int = 24) -> list[NewsEvent]:
        """Return all upcoming events (any currency) within `hours_ahead`."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        cutoff = dt + timedelta(hours=hours_ahead)
        result = [
            e for e in self._events
            if dt <= (e.time_utc.replace(tzinfo=timezone.utc) if e.time_utc.tzinfo is None else e.time_utc) <= cutoff
        ]
        return sorted(result, key=lambda e: e.time_utc)
