"""
JcampFX — Backtester Engine (Phase 3, PRD §9.1)

Custom event-driven bar-level replay loop.

Architecture:
  1. Pre-load Range Bar parquet cache per pair (no tick replay)
  2. Merge all pairs into a chronological priority queue (keyed by end_time)
  3. Pop events in time order:
     a. reset_daily_if_needed
     b. Check exits on open trades for this pair
     c. Build point-in-time DCRD inputs (no lookahead)
     d. Call BrainCore.process() → Signal
     e. Open trade if Signal is valid
  4. Force-close all trades before Friday market close
  5. Build equity curve, drawdown curve, DCRD timeline

Bar-level exit resolution (conservative):
  - SL check:  BUY → bar.low  ≤ sl_price;  SELL → bar.high ≥ sl_price
  - 1.5R check: BUY → bar.high ≥ 1.5R target; SELL → bar.low ≤ 1.5R target
  - When BOTH SL and 1.5R are hit in the same bar → SL wins (conservative)
  - Chandelier check: BUY → bar.low ≤ chandelier_sl; SELL → bar.high ≥ chandelier_sl

DCRD fallback:
  If 4H/1H OHLC not yet downloaded, composite_score defaults to 50.0 (Transitional)
  with a WARNING so the user knows to run fetch_all() for accurate results.
"""

from __future__ import annotations

import heapq
import logging
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd

from backtester.account import BacktestAccount
from backtester.cost_model import apply_entry_slippage
from backtester.results import BacktestResults
from backtester.trade import BacktestTrade
from backtester.walk_forward import _compute_drawdown
from src.brain_core import AccountState, BrainCore
from src.config import (
    BACKTEST_RESULTS_DIR,
    DATA_NEWS_JSON,
    DATA_OHLC_1H_DIR,
    DATA_OHLC_4H_DIR,
    DATA_RANGE_BARS_DIR,
    DAILY_LOSS_CAP_R,
    PIP_SIZE,
    RANGE_BAR_PIPS,
    WEEKEND_CLOSE_MINUTES,
)
from src.dcrd.dcrd_engine import DCRDEngine
from src.exit_manager import calculate_1_5r_price, is_at_1_5r, should_force_close_runner
from src.news_layer import NewsLayer
from src.signal import Signal

log = logging.getLogger(__name__)

_DCRD_FALLBACK_SCORE = 50.0   # Used when 4H/1H data unavailable
_ATR_DEFAULT_PIPS = 15        # Default ATR when insufficient bars
_MIN_BARS_FOR_DCRD = 30       # Minimum range bars before scoring


class BacktestEngine:
    """
    Event-driven Range Bar replay engine.

    Parameters
    ----------
    pairs        : List of canonical pair names to backtest
    data_dir     : Root data directory (default: "data")
    news_json    : Path to news events JSON stub
    """

    def __init__(
        self,
        pairs: list[str],
        data_dir: str = "data",
        news_json: str = DATA_NEWS_JSON,
    ) -> None:
        self.pairs = pairs
        self.data_dir = Path(data_dir)

        # Load Range Bar caches (required)
        self._rb_cache: dict[str, pd.DataFrame] = {}
        for pair in pairs:
            self._rb_cache[pair] = self._load_range_bars(pair)

        # Load 4H/1H OHLC (optional — fallback if missing)
        self._ohlc_4h: dict[str, pd.DataFrame] = {}
        self._ohlc_1h: dict[str, pd.DataFrame] = {}
        self._dcrd_available = True
        for pair in pairs:
            h4 = self._load_ohlc(pair, "4h")
            h1 = self._load_ohlc(pair, "1h")
            if h4 is None or h1 is None:
                self._dcrd_available = False
            else:
                self._ohlc_4h[pair] = h4
                self._ohlc_1h[pair] = h1

        if not self._dcrd_available:
            log.warning(
                "4H/1H OHLC not available — DCRD scores will use fallback=%.1f. "
                "Run `python -m src.data_fetcher --dcrd-only` to download.",
                _DCRD_FALLBACK_SCORE,
            )

        # DCRD engine (stateful — maintains anti-flip state per pair)
        self._dcrd = DCRDEngine()

        # News layer
        self._news = NewsLayer()
        news_path = Path(news_json)
        if news_path.exists():
            self._news.load_from_json(str(news_path))
        else:
            log.warning("News JSON not found at %s — no news blocking in backtest", news_json)

        # BrainCore (auto-registers strategies)
        self._brain = BrainCore(news_layer=self._news)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        start: pd.Timestamp,
        end: pd.Timestamp,
        initial_equity: float = 500.0,
    ) -> BacktestResults:
        """
        Replay Range Bar events from [start, end] and return BacktestResults.

        Parameters
        ----------
        start         : Inclusive start timestamp (UTC)
        end           : Inclusive end timestamp (UTC)
        initial_equity: Starting account equity in USD
        """
        log.info("=" * 60)
        log.info("BacktestEngine.run() called with:")
        log.info(f"  start: {start} (type: {type(start)})")
        log.info(f"  end: {end} (type: {type(end)})")
        log.info(f"  pairs: {self.pairs}")
        log.info("=" * 60)

        account = BacktestAccount(initial_equity=initial_equity)
        dcrd_records: list[dict] = []

        # Build event queue: (end_time, pair, bar_index, bar_series)
        heap: list[tuple] = []
        for pair in self.pairs:
            rb = self._rb_cache.get(pair)
            if rb is None or rb.empty:
                log.warning(f"  {pair}: No range bar data loaded")
                continue
            # Filter to window
            mask = (rb["end_time"] >= start) & (rb["end_time"] <= end)
            filtered = rb[mask].reset_index(drop=True)
            log.info(f"  {pair}: {len(rb)} total bars, {len(filtered)} in [{start.date()}, {end.date()}] window")
            if len(filtered) > 0:
                log.info(f"    First bar: {filtered['end_time'].iloc[0]}")
                log.info(f"    Last bar: {filtered['end_time'].iloc[-1]}")
            for idx, row in filtered.iterrows():
                heapq.heappush(heap, (row["end_time"], pair, int(idx), row))

        bar_count = 0
        rb_window_cache: dict[str, list] = {p: [] for p in self.pairs}
        last_close: dict[str, float] = {}  # last known close price per pair

        while heap:
            end_time, pair, bar_idx, bar = heapq.heappop(heap)
            bar_count += 1

            # Append to rolling window for this pair
            rb_window_cache[pair].append(bar)
            if len(rb_window_cache[pair]) > 300:
                rb_window_cache[pair] = rb_window_cache[pair][-300:]

            # Track last known close price for this pair
            last_close[pair] = float(bar["close"])

            # Daily reset
            account.reset_daily_if_needed(end_time)

            # Build DCRD inputs first (needed for regime deterioration in exit checks)
            rb_window_df = pd.DataFrame(rb_window_cache[pair])
            composite_score, regime, dcrd_breakdown = self._compute_dcrd(pair, end_time, rb_window_df)

            # 1. Check exits for all open trades on this pair
            open_ids_before = {t.trade_id for t in account.open_trades}
            open_on_pair = [t for t in list(account.open_trades) if t.pair == pair]
            for trade in open_on_pair:
                self._check_exits_on_bar(trade, bar, account, end_time, composite_score)
            # Feed closed trades back to performance tracker (enables cooldowns)
            self._report_closed_trades(account, open_ids_before, end_time)

            # 2. Daily 2R cap — if hit, force-close remaining positions
            if account.is_daily_cap_hit():
                open_ids_cap = {t.trade_id for t in account.open_trades}
                for trade in list(account.open_trades):
                    # Use the trade's own pair price, not the current bar's pair price
                    close_px = last_close.get(trade.pair, trade.entry_price)
                    account.close_trade(trade, close_px, end_time, "2R_CAP")
                self._report_closed_trades(account, open_ids_cap, end_time)
                continue  # No new entries on same bar as cap hit

            # 3. Weekend close (Friday ≥ 21:40 UTC = 5 min before 22:00 close)
            if _is_near_friday_close(end_time):
                open_ids_wknd = {t.trade_id for t in account.open_trades}
                for trade in list(account.open_trades):
                    # Use the trade's own pair price, not the current bar's pair price
                    close_px = last_close.get(trade.pair, trade.entry_price)
                    account.close_trade(trade, close_px, end_time, "WEEKEND_CLOSE")
                self._report_closed_trades(account, open_ids_wknd, end_time, is_weekend=True)
                continue

            # Record for timeline
            dcrd_records.append({
                "time": end_time,
                "pair": pair,
                "score": composite_score,
                "regime": regime,
            })

            # 5. BrainCore signal generation
            if len(rb_window_cache[pair]) < _MIN_BARS_FOR_DCRD:
                continue  # Not enough data yet

            ohlc_4h = self._get_ohlc_window(pair, "4h", end_time)
            ohlc_1h = self._get_ohlc_window(pair, "1h", end_time)

            signal = self._brain.process(
                pair=pair,
                range_bars=rb_window_df,
                ohlc_4h=ohlc_4h,
                ohlc_1h=ohlc_1h,
                composite_score=composite_score,
                account_state=account.get_account_state(),
                current_time=end_time,
                last_bar=bar,  # v2.2: phantom detection (VP.4)
            )

            # 6. Open trade if signal is valid and unblocked
            if signal is not None and not signal.is_blocked and signal.lot_size > 0:
                self._open_trade(signal, bar, account, end_time, dcrd_breakdown)

        # End of replay: close any remaining open trades at their own pair's last price
        for trade in list(account.open_trades):
            last_price = last_close.get(trade.pair, trade.entry_price)
            account.close_trade(trade, last_price, end, "WEEKEND_CLOSE")

        log.info(
            "Replay complete: %d bars processed | %d trades | equity $%.2f → $%.2f",
            bar_count, len(account.closed_trades),
            initial_equity, account.equity,
        )

        # Build results
        equity_curve = _build_equity_series(account)
        drawdown_curve = _compute_drawdown(equity_curve, initial_equity) if not equity_curve.empty else None
        dcrd_timeline = pd.DataFrame(dcrd_records) if dcrd_records else None

        return BacktestResults(
            all_trades=list(account.closed_trades),
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            dcrd_timeline=dcrd_timeline,
            initial_equity=initial_equity,
        )

    # ------------------------------------------------------------------
    # Exit checking
    # ------------------------------------------------------------------

    def _check_exits_on_bar(
        self,
        trade: BacktestTrade,
        bar: pd.Series,
        account: BacktestAccount,
        timestamp: pd.Timestamp,
        current_composite_score: float = 50.0,
    ) -> None:
        """
        Check all exit conditions for one trade against one Range Bar.

        Conservative rule: if both SL and 1.5R are hit in the same bar → SL wins.

        v2.2 additions:
          - VP.6: Phantom bar exits use tick_boundary_price instead of bar close/SL
          - VD.9/VE.8: Regime deterioration force-close for runner phase
        """
        bar_high = float(bar["high"])
        bar_low = float(bar["low"])
        bar_close = float(bar["close"])

        # v2.2: determine exit fill price — phantom bars fill at tick boundary (VP.6)
        is_phantom_bar = bool(bar.get("is_phantom", False))
        is_gap_adj = bool(bar.get("is_gap_adjacent", False))
        tick_boundary = float(bar.get("tick_boundary_price", bar_close))

        atr14 = _estimate_atr(trade.pair)  # simple estimate; real ATR from OHLC when available

        if trade.phase == "open":
            # Check SL first (conservative)
            sl_hit = (
                bar_low <= trade.sl_price
                if trade.direction.upper() == "BUY"
                else bar_high >= trade.sl_price
            )
            if sl_hit:
                # v2.2 (VP.6): phantom/gap-adj exit fills at tick boundary, not SL price
                fill_price = tick_boundary if (is_phantom_bar or is_gap_adj) else trade.sl_price
                account.close_trade(trade, fill_price, timestamp, "SL_HIT")
                return

            # Check 1.5R partial exit
            target_1_5r = calculate_1_5r_price(trade.entry_price, trade.sl_price, trade.direction)
            at_1_5r = (
                bar_high >= target_1_5r
                if trade.direction.upper() == "BUY"
                else bar_low <= target_1_5r
            )
            if at_1_5r:
                fill_1_5r = tick_boundary if (is_phantom_bar or is_gap_adj) else target_1_5r
                account.apply_partial_exit(trade, fill_1_5r, timestamp, atr14)

        elif trade.phase == "runner":
            # v2.2 (VD.9, VE.8): Regime deterioration force-close
            if should_force_close_runner(trade.composite_score, current_composite_score):
                fill_price = tick_boundary if (is_phantom_bar or is_gap_adj) else bar_close
                account.close_trade(trade, fill_price, timestamp, "REGIME_DETERIORATION")
                return

            # Update Chandelier with bar extreme
            bar_extreme = bar_high if trade.direction.upper() == "BUY" else bar_low
            account.update_chandelier_for_trade(trade, bar_extreme, atr14)

            # Check Chandelier hit
            chandelier_hit = (
                bar_low <= trade.chandelier_sl
                if trade.direction.upper() == "BUY"
                else bar_high >= trade.chandelier_sl
            )
            if chandelier_hit:
                # v2.2 (VP.6): phantom bar chandelier exits fill at tick boundary
                fill_price = tick_boundary if (is_phantom_bar or is_gap_adj) else trade.chandelier_sl
                account.close_trade(trade, fill_price, timestamp, "CHANDELIER_HIT")

    # ------------------------------------------------------------------
    # Performance tracker feedback
    # ------------------------------------------------------------------

    def _report_closed_trades(
        self,
        account: BacktestAccount,
        open_ids_before: set,
        timestamp: pd.Timestamp,
        is_weekend: bool = False,
    ) -> None:
        """
        Report newly-closed trades to BrainCore's performance tracker.
        This enables the strategy cooldown system to function in backtests.
        """
        current_open_ids = {t.trade_id for t in account.open_trades}
        just_closed_ids = open_ids_before - current_open_ids
        if not just_closed_ids:
            return
        for trade in account.closed_trades:
            if trade.trade_id in just_closed_ids:
                self._brain.performance_tracker.add_trade(
                    strategy=trade.strategy,
                    r_result=float(trade.r_multiple_total),
                    timestamp=timestamp,
                    is_weekend_close=is_weekend,
                )

    # ------------------------------------------------------------------
    # Trade opening
    # ------------------------------------------------------------------

    def _open_trade(
        self,
        signal: Signal,
        bar: pd.Series,
        account: BacktestAccount,
        timestamp: pd.Timestamp,
        dcrd_breakdown: dict | None = None,
    ) -> None:
        """Create a BacktestTrade from a Signal and register it with the account."""
        pip = PIP_SIZE.get(signal.pair, 0.0001)
        entry_price = apply_entry_slippage(signal.entry, signal.direction, signal.pair)
        initial_r_pips = abs(entry_price - signal.sl) / pip

        # Extract L1/L2/L3 and regime from DCRD breakdown (if available)
        layer1 = dcrd_breakdown.get("layer1_structural", 0.0) if dcrd_breakdown else 0.0
        layer2 = dcrd_breakdown.get("layer2_modifier", 0.0) if dcrd_breakdown else 0.0
        layer3 = dcrd_breakdown.get("layer3_rb_intelligence", 0.0) if dcrd_breakdown else 0.0
        regime = dcrd_breakdown.get("regime", "transitional") if dcrd_breakdown else "transitional"

        trade = BacktestTrade(
            trade_id=str(uuid.uuid4())[:8],
            pair=signal.pair,
            direction=signal.direction,
            strategy=signal.strategy,
            entry_price=entry_price,
            sl_price=signal.sl,
            entry_time=timestamp,
            lot_size=signal.lot_size,
            initial_r_pips=initial_r_pips,
            composite_score=signal.composite_score,
            regime=regime,
            layer1_structural=layer1,
            layer2_modifier=layer2,
            layer3_rb_intelligence=layer3,
            partial_exit_pct=signal.partial_exit_pct,
            adx_at_entry=signal.adx_at_entry,
            adx_slope_rising=signal.adx_slope_rising,
            staircase_depth=signal.staircase_depth,
            pullback_bar_idx=signal.pullback_bar_idx,
            pullback_depth_pips=signal.pullback_depth_pips,
            entry_bar_idx=signal.entry_bar_idx,
        )
        account.open_trade(trade)

    # ------------------------------------------------------------------
    # DCRD scoring (point-in-time)
    # ------------------------------------------------------------------

    def _compute_dcrd(
        self,
        pair: str,
        up_to_time: pd.Timestamp,
        rb_window: pd.DataFrame,
    ) -> tuple[float, str, dict]:
        """
        Return (composite_score, regime, breakdown_dict) for this pair at up_to_time.
        Falls back to (50.0, 'transitional', {}) if OHLC data unavailable.

        breakdown_dict contains: layer1_structural, layer2_modifier, layer3_rb_intelligence
        """
        if not self._dcrd_available:
            regime = self._dcrd.get_regime(_DCRD_FALLBACK_SCORE)
            return _DCRD_FALLBACK_SCORE, regime, {}

        ohlc_4h = self._get_ohlc_window(pair, "4h", up_to_time)
        ohlc_1h = self._get_ohlc_window(pair, "1h", up_to_time)

        if ohlc_4h is None or len(ohlc_4h) < 30:
            regime = self._dcrd.get_regime(_DCRD_FALLBACK_SCORE)
            return _DCRD_FALLBACK_SCORE, regime, {}

        try:
            # Use score_components() to get full breakdown including L1/L2/L3
            breakdown = self._dcrd.score_components(
                ohlc_4h=ohlc_4h,
                ohlc_1h=ohlc_1h,
                range_bars=rb_window,
                csm_data=None,  # CSM not used in backtest (requires live 9-pair data)
                pair=pair,
            )
            score = breakdown.get("composite_score", _DCRD_FALLBACK_SCORE)
            regime = breakdown.get("regime", "transitional")
            return score, regime, breakdown
        except Exception as exc:
            log.debug("DCRD scoring error for %s at %s: %s", pair, up_to_time, exc)
            score = _DCRD_FALLBACK_SCORE
            regime = self._dcrd.get_regime(score)
            return score, regime, {}

    # ------------------------------------------------------------------
    # Data loading helpers
    # ------------------------------------------------------------------

    def _load_range_bars(self, pair: str) -> Optional[pd.DataFrame]:
        pips = RANGE_BAR_PIPS.get(pair, 10)
        path = self.data_dir / "range_bars" / f"{pair}_RB{pips}.parquet"
        if not path.exists():
            log.warning("Range Bar cache not found: %s", path)
            return None
        df = pd.read_parquet(path)
        df["end_time"] = pd.to_datetime(df["end_time"], utc=True)
        df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
        return df

    def _load_ohlc(self, pair: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load 4H or 1H OHLC. Returns None if file not found."""
        sub = "ohlc_4h" if timeframe == "4h" else "ohlc_1h"
        suffix = "H4" if timeframe == "4h" else "H1"
        path = self.data_dir / sub / f"{pair}_{suffix}.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        return df.sort_values("time").reset_index(drop=True)

    def _get_ohlc_window(
        self,
        pair: str,
        timeframe: str,
        up_to_time: pd.Timestamp,
        n: int = 300,
    ) -> Optional[pd.DataFrame]:
        """Return last N OHLC bars ending at or before up_to_time (no lookahead)."""
        cache = self._ohlc_4h if timeframe == "4h" else self._ohlc_1h
        df = cache.get(pair)
        if df is None or df.empty:
            return None
        mask = df["time"] <= up_to_time
        sliced = df[mask].tail(n)
        return sliced if not sliced.empty else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_atr(pair: str) -> float:
    """
    Simple ATR estimate for Chandelier initialisation when real ATR unavailable.
    Returns pip_size × 15 (15-pip ATR approximation).
    """
    pip = PIP_SIZE.get(pair, 0.0001)
    return pip * _ATR_DEFAULT_PIPS


def _is_near_friday_close(ts: pd.Timestamp) -> bool:
    """
    Return True if timestamp is within WEEKEND_CLOSE_MINUTES of Friday 22:00 UTC.
    Friday = weekday 4.
    """
    if ts.weekday() != 4:  # Not Friday
        return False
    close_hour = 22
    close_minute = 0
    minutes_to_close = (close_hour * 60 + close_minute) - (ts.hour * 60 + ts.minute)
    return 0 <= minutes_to_close <= WEEKEND_CLOSE_MINUTES


def _build_equity_series(account: BacktestAccount) -> pd.Series:
    """Build a Timestamp-indexed equity Series from account history."""
    if not account.equity_history:
        return pd.Series(dtype=float)
    times, equities = zip(*account.equity_history)
    s = pd.Series(equities, index=pd.DatetimeIndex(times), name="equity")
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s
