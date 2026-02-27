"""
JcampFX — Brain Core Orchestrator (Phase 2, PRD §2.2 + §8)

The central coordinator that:
  1. Auto-discovers strategy modules from src/strategies/
  2. Applies all risk gates in order before dispatching signals
  3. Runs the correlation filter (max 2 trades per currency)
  4. Attaches risk/lot-size/exit data to signals
  5. Tracks daily trade counts, concurrent positions, daily R usage

Gate execution order (PRD §12):
  1. Gold gate (XAUUSD blocked if equity < $2,000)
  2. Max concurrent positions (2 or 3)
  3. Max daily trades (5)
  4. Daily 2R loss cap
  5. News gating
  6. Post-event cooling CS check
  7. Route to active strategy by CompositeScore
  8. Strategy cooldown
  9. Correlation filter
  10. Risk engine (risk% < 0.8% → skip)
  11. Attach exit parameters

Validation:
  V2.5  — Gold gate blocks XAUUSD < $2,000
  V2.6  — Max concurrent: 2 positions (until equity > $1,000, then 3)
  V2.7  — Correlation filter: max 2 trades with same base/quote currency
  V2.8  — Standardized signal schema
  V2.9  — News layer blocks signals during high-impact windows
  V2.11 — New strategy auto-registers from /strategies/ without Brain Core changes
  V2.12 — Performance tracker disables/re-enables strategies correctly
  V2.13 — Anti-flipping filter prevents regime oscillation
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

import src.strategies as _strategies_pkg
from src.config import (
    DAILY_LOSS_CAP_R,
    EQUITY_UPGRADE_THRESHOLD,
    GOLD_PAIR,
    GOLD_UNLOCK_EQUITY,
    MAX_CONCURRENT_POSITIONS,
    MAX_CONCURRENT_UPGRADED,
    MAX_DAILY_TRADES,
    NEWS_POST_EVENT_MIN_CS,
    PAIRS,
    PHANTOM_DETECTION_ENABLED,
    PIP_SIZE,
    SLIPPAGE_PIPS,
)
from src.exit_manager import get_partial_exit_pct
from src.news_layer import NewsLayer
from src.performance_tracker import PerformanceTracker
from src.price_level_tracker import PriceLevelTracker
from src.risk_engine import compute_trade_risk
from src.session_filter import SessionFilter, get_session_tag
from src.signal import Signal
from src.strategies.base_strategy import BaseStrategy

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Account state (passed in on each process() call)
# ---------------------------------------------------------------------------

@dataclass
class AccountState:
    equity: float
    open_positions: list[dict] = field(default_factory=list)
    # Each position dict: {pair, direction, entry, sl, lot_size, strategy, open_time}
    daily_r_used: float = 0.0       # Cumulative R loss today (negative = loss)
    daily_trade_count: int = 0      # Trades opened today
    daily_reset_time: Optional[datetime] = None  # Last midnight reset

    def get_max_concurrent(self) -> int:
        return MAX_CONCURRENT_UPGRADED if self.equity >= EQUITY_UPGRADE_THRESHOLD else MAX_CONCURRENT_POSITIONS

    def open_position_count(self) -> int:
        return len(self.open_positions)

    def currency_exposure(self) -> dict[str, int]:
        """Count how many open positions involve each currency."""
        exposure: dict[str, int] = {}
        for pos in self.open_positions:
            pair = pos.get("pair", "")
            if len(pair) == 6:
                base, quote = pair[:3], pair[3:]
                exposure[base] = exposure.get(base, 0) + 1
                exposure[quote] = exposure.get(quote, 0) + 1
        return exposure


# ---------------------------------------------------------------------------
# Correlation filter helper
# ---------------------------------------------------------------------------

def _passes_correlation_filter(pair: str, account_state: AccountState) -> tuple[bool, Optional[str]]:
    """
    PRD §8.3: Max 2 open trades sharing the same base or quote currency.

    Returns (passes, reason_if_blocked).
    V2.7: Blocked signals logged as CORRELATION_BLOCKED.
    """
    if len(pair) != 6:
        return True, None

    base, quote = pair[:3], pair[3:]
    exposure = account_state.currency_exposure()

    for currency in (base, quote):
        if exposure.get(currency, 0) >= 2:
            reason = f"CORRELATION_BLOCKED:{currency} already at 2 exposures"
            log.info("Correlation filter: %s blocked — %s", pair, reason)
            return False, reason

    return True, None


# ---------------------------------------------------------------------------
# BrainCore
# ---------------------------------------------------------------------------

class BrainCore:
    """
    Central strategy orchestrator.

    Auto-discovers all BaseStrategy subclasses in src/strategies/ at init.
    Stateless between calls except for the PerformanceTracker reference.
    """

    def __init__(
        self,
        performance_tracker: Optional[PerformanceTracker] = None,
        news_layer: Optional[NewsLayer] = None,
        price_level_tracker: Optional[PriceLevelTracker] = None,
    ) -> None:
        self.performance_tracker = performance_tracker or PerformanceTracker()
        self.news_layer = news_layer or NewsLayer()
        self.session_filter = SessionFilter()
        self.price_level_tracker = price_level_tracker or PriceLevelTracker()
        self._strategies: list[BaseStrategy] = []
        self._auto_register_strategies()

    def _auto_register_strategies(self) -> None:
        """
        V2.11: Auto-discover all BaseStrategy subclasses in src/strategies/.
        New modules dropped into the directory are registered automatically.
        """
        pkg_path = Path(_strategies_pkg.__file__).parent
        for _finder, module_name, _ispkg in pkgutil.iter_modules([str(pkg_path)]):
            if module_name in ("base_strategy",):
                continue
            try:
                mod = importlib.import_module(f"src.strategies.{module_name}")
                for _name, obj in inspect.getmembers(mod, inspect.isclass):
                    if (
                        issubclass(obj, BaseStrategy)
                        and obj is not BaseStrategy
                        and obj not in [s.__class__ for s in self._strategies]
                    ):
                        self._strategies.append(obj())
                        log.info("BrainCore: registered strategy %s", obj.name)
            except Exception as exc:
                log.error("BrainCore: failed to load module %s: %s", module_name, exc)

        log.info("BrainCore: %d strategies registered: %s",
                 len(self._strategies), [s.name for s in self._strategies])

    def get_registered_strategies(self) -> list[str]:
        return [s.name for s in self._strategies]

    def process(
        self,
        pair: str,
        range_bars: pd.DataFrame,
        ohlc_4h: pd.DataFrame,
        ohlc_1h: pd.DataFrame,
        composite_score: float,
        account_state: AccountState,
        current_time: Optional[datetime] = None,
        atr14: float = 0.0,
        sl_pips: float = 0.0,
        pip_value_per_lot: Optional[float] = None,
        last_bar: Optional[pd.Series] = None,  # v2.2: for phantom detection
        dcrd_history: Optional[list[float]] = None,  # Phase 3.1.1: DCRD momentum tracking
        ohlc_m15: Optional[pd.DataFrame] = None,  # Phase 3.4: PivotScalper M15 data
    ) -> Optional[Signal]:
        """
        Run all gates and route to the appropriate strategy.

        Parameters
        ----------
        pair             : Canonical pair name
        range_bars       : Range Bar DataFrame for this pair
        ohlc_4h          : 4H OHLC DataFrame
        ohlc_1h          : 1H OHLC DataFrame
        composite_score  : DCRD CompositeScore for this pair (0–100)
        account_state    : Current account + position state
        current_time     : UTC datetime for news checks (defaults to now)
        atr14            : ATR(14) in price terms (for chandelier, passed through)
        sl_pips          : Estimated SL distance in pips (for lot sizing)
        pip_value_per_lot: USD pip value for lot sizing (None = auto-estimate)
        dcrd_history     : Last N composite scores for momentum calculation (Phase 3.1.1)

        Returns
        -------
        Signal with all fields populated, or None if no valid setup or all blocked.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # --- Gate 1: Gold gate ---
        if pair == GOLD_PAIR and account_state.equity < GOLD_UNLOCK_EQUITY:
            log.debug("Gold gate: XAUUSD blocked — equity $%.2f < $2,000", account_state.equity)
            return None

        # --- Gate 2: Max concurrent positions ---
        max_pos = account_state.get_max_concurrent()
        if account_state.open_position_count() >= max_pos:
            log.debug("Max concurrent: %d/%d — no new trades", account_state.open_position_count(), max_pos)
            return None

        # --- Gate 3: Max daily trades ---
        if account_state.daily_trade_count >= MAX_DAILY_TRADES:
            log.debug("Max daily trades reached (%d)", MAX_DAILY_TRADES)
            return None

        # --- Gate 4: Daily 2R loss cap ---
        if account_state.daily_r_used <= -DAILY_LOSS_CAP_R:
            log.info("Daily 2R loss cap hit (%.2fR) — all trading paused", account_state.daily_r_used)
            return None

        # --- Gate 5: News gating ---
        news_blocked, news_reason = self.news_layer.is_blocked(pair, current_time)
        if news_blocked:
            log.info("NEWS_BLOCKED: %s at %s — %s", pair, current_time, news_reason)
            return _blocked_signal(pair, composite_score, current_time, news_reason)

        # --- Gate 6: Post-event cooling CS check ---
        if self.news_layer.is_post_event_cooling(pair, current_time):
            if composite_score <= NEWS_POST_EVENT_MIN_CS:
                reason = f"POST_EVENT_COOLING:CS={composite_score:.1f}≤{NEWS_POST_EVENT_MIN_CS}"
                log.info("%s: %s", pair, reason)
                return _blocked_signal(pair, composite_score, current_time, reason)

        # --- Gate 6.5: Phantom bar check (v2.2, PRD §8.4, VP.4) ---
        if PHANTOM_DETECTION_ENABLED and last_bar is not None:
            if last_bar.get("is_phantom", False):
                reason = f"PHANTOM_BLOCKED:{pair}:bar is phantom"
                log.info("%s: %s", pair, reason)
                return _blocked_signal(pair, composite_score, current_time, reason)

        # --- Gate 6.6: Session filter (v2.2, PRD §6.3, VS.1–VS.5) ---
        session_tag = get_session_tag(current_time)
        # We check against all registered strategies' preferred sessions
        # The active strategy hasn't been selected yet, so we pre-check per route
        # Actual per-strategy check happens after Gate 7 determines active_strategy

        # --- Gate 7: Route to active strategy by CompositeScore ---
        active_strategy = self._select_strategy(composite_score)
        if active_strategy is None:
            return None

        # --- Gate 7.5: Per-strategy session filter (v2.2) ---
        session_allowed, session_reason = self.session_filter.check(
            active_strategy.name, pair, current_time
        )
        if not session_allowed:
            log.info("%s: %s", pair, session_reason)
            return _blocked_signal(pair, composite_score, current_time, session_reason)

        # --- Gate 7.6: Gap-adjacent bar check (v2.2, PRD §8.4, VP.5) ---
        if last_bar is not None and last_bar.get("is_gap_adjacent", False):
            if not getattr(active_strategy, "allow_gap_adjacent", True):
                reason = f"PHANTOM_BLOCKED:{pair}:gap-adjacent bar ({active_strategy.name} blocks)"
                log.info("%s: %s", pair, reason)
                return _blocked_signal(pair, composite_score, current_time, reason)

        # --- Gate 8: Strategy cooldown ---
        if self.performance_tracker.is_in_cooldown(active_strategy.name, current_time):
            cd_until = self.performance_tracker.get_cooldown_until(active_strategy.name)
            reason = f"STRATEGY_COOLDOWN:{active_strategy.name} until {cd_until}"
            log.info("%s: %s", pair, reason)
            return _blocked_signal(pair, composite_score, current_time, reason)

        # Build news_state dict for strategy analyze()
        news_state = {
            "pair": pair,
            "blocked": False,
            "post_cooling": self.news_layer.is_post_event_cooling(pair, current_time),
            "events": self.news_layer.get_upcoming(pair, current_time, hours_ahead=24),
        }

        # --- Run strategy ---
        signal = active_strategy.analyze(
            range_bars, ohlc_4h, ohlc_1h, composite_score, news_state,
            dcrd_history=dcrd_history,  # Phase 3.1.1: DCRD momentum filter
            ohlc_m15=ohlc_m15,  # Phase 3.4: PivotScalper
        )
        if signal is None:
            return None

        # --- Gate 8.5: Price level cooldown (Phase 3.1.2.5 — revenge trade prevention) ---
        # CRITICAL: Check post-slippage price to match what will be recorded after trade execution
        pip = PIP_SIZE.get(pair, 0.0001)
        slip = SLIPPAGE_PIPS * pip
        slipped_entry = (signal.entry + slip) if signal.direction.upper() == "BUY" else (signal.entry - slip)

        is_blocked, block_reason = self.price_level_tracker.is_blocked(
            pair=pair,
            price=slipped_entry,  # Use post-slippage price (matches recorded entry)
            strategy=active_strategy.name,
            now=current_time,
        )
        if is_blocked:
            signal.blocked_reason = block_reason
            return signal  # Return blocked signal for logging

        # --- Gate 9: Correlation filter ---
        passes_corr, corr_reason = _passes_correlation_filter(pair, account_state)
        if not passes_corr:
            signal.blocked_reason = corr_reason
            return signal  # Return blocked signal for logging (VN.5)

        # --- Gate 10: Risk engine ---
        perf_mult = self.performance_tracker.get_performance_multiplier(active_strategy.name)
        risk_result = compute_trade_risk(
            composite_score=composite_score,
            performance_multiplier=perf_mult,
            account_equity=account_state.equity,
            sl_pips=sl_pips if sl_pips > 0 else signal.risk_pips,
            pair=pair,
            pip_value_per_lot=pip_value_per_lot,
        )

        if risk_result["skip"]:
            signal.blocked_reason = "RISK_TOO_LOW"
            signal.risk_pct = risk_result["risk_pct"]
            return signal  # Return blocked signal for logging

        # --- Gate 11: Attach exit parameters ---
        signal.risk_pct = risk_result["risk_pct"]
        signal.lot_size = risk_result["lot_size"]
        signal.session_tag = session_tag  # v2.2: tag with active session (PRD §6.3)
        # partial_exit_pct already set by strategy using CS at entry (VE.7)
        # If not set, compute it here as fallback
        if signal.partial_exit_pct == 0.0:
            signal.partial_exit_pct = get_partial_exit_pct(composite_score)

        log.info(
            "BrainCore signal approved: %s %s %s @ %.5f "
            "risk=%.2f%% lots=%.2f partial=%.0f%% CS=%.1f",
            signal.strategy, pair, signal.direction, signal.entry,
            signal.risk_pct * 100, signal.lot_size, signal.partial_exit_pct * 100,
            composite_score,
        )
        return signal

    def _select_strategy(self, composite_score: float) -> Optional[BaseStrategy]:
        """Return the first registered strategy whose regime range contains composite_score."""
        for strategy in self._strategies:
            if strategy.is_regime_active(composite_score):
                return strategy
        return None

    def get_all_strategy_status(self) -> dict:
        return {s.name: self.performance_tracker.get_status(s.name) for s in self._strategies}


# ---------------------------------------------------------------------------
# Helper: create a blocked signal (for logging — never silently dropped)
# ---------------------------------------------------------------------------

def _blocked_signal(
    pair: str,
    composite_score: float,
    timestamp: datetime,
    reason: str,
) -> Signal:
    """
    Create a placeholder Signal with blocked_reason set.
    Used to ensure all blocks are logged with the event/reason (VN.5).
    """
    return Signal(
        timestamp=pd.Timestamp(timestamp),
        pair=pair,
        direction="NONE",
        entry=0.0,
        sl=0.0,
        tp_1r=0.0,
        strategy="BLOCKED",
        composite_score=composite_score,
        blocked_reason=reason,
    )
