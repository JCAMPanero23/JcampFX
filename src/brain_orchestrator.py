"""
JcampFX — Brain Orchestrator (Phase 4)

Main live trading coordinator that integrates all components:
- ZMQ Bridge (receives ticks from MT5, sends signals back)
- LiveRangeBarEngine (builds Range Bars in real-time)
- DCRDEngine (calculates CompositeScore on bar close)
- BrainCore (generates entry signals via strategies)
- Exit Manager (manages partial exits, trailing SL, runner protection)

Event Loop:
    1. Receive tick from MT5 via ZMQ
    2. Feed to LiveRangeBarEngine
    3. On Range Bar close:
       a. Update OHLC data (4H, 1H, CSM)
       b. Calculate DCRD CompositeScore
       c. Run BrainCore.process() for entry signal
       d. Check exit conditions for open positions
    4. Send signals to MT5 via ZMQ
    5. Sync position state with MT5
"""

import logging
import signal as signal_module
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.brain_core import AccountState, BrainCore
from src.config import (
    DAILY_LOSS_CAP_R,
    PAIRS,
    PARTIAL_EXIT_R,
    PIP_SIZE,
    RANGE_BAR_PIPS,
    REGIME_DETERIORATION_THRESHOLD,
    WEEKEND_CLOSE_MINUTES,
)
from src.dcrd.dcrd_engine import DCRDEngine
from src.live_range_bar_engine import BarCloseEvent, LiveRangeBarEngine
from src.news_layer import NewsLayer
from src.ohlc_loader import OHLCLoader
from src.performance_tracker import PerformanceTracker
from src.price_level_tracker import PriceLevelTracker
from src.signal import Signal
from src.zmq_bridge import TradingSignal, ZMQBridge

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

# Dashboard import (optional - graceful fallback if Dash not installed)
try:
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from dashboard.live_monitor import LiveDashboard
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False
    log.warning("Dashboard not available (install: pip install dash plotly)")


@dataclass
class Position:
    """Open position tracking."""
    ticket: int
    pair: str
    direction: str  # "BUY" or "SELL"
    entry: float
    sl: float
    tp: Optional[float]
    lot_size: float
    strategy: str
    open_time: datetime
    entry_cs: float  # CompositeScore at entry
    partial_exited: bool = False
    partial_exit_pct: float = 0.0
    initial_risk: float = 0.0  # Initial R in $ (for R-multiple calculation)


class BrainOrchestrator:
    """
    Main live trading coordinator.

    Integrates all components and manages the live trading event loop.
    """

    def __init__(
        self,
        pairs: list[str],
        initial_equity: float = 500.0,
        zmq_enabled: bool = True,
        load_historical_bars: bool = True,
        dashboard_enabled: bool = True,
        dashboard_port: int = 8050,
    ):
        """
        Initialize BrainOrchestrator.

        Args:
            pairs: List of trading pairs (e.g. ["EURUSD", "USDJPY"])
            initial_equity: Starting equity for demo account
            zmq_enabled: Enable ZMQ bridge (disable for testing)
            load_historical_bars: Load historical bars from cache on startup
            dashboard_enabled: Enable live web dashboard
            dashboard_port: Port for dashboard web server
        """
        self.pairs = pairs
        self.zmq_enabled = zmq_enabled
        self.dashboard_enabled = dashboard_enabled and DASHBOARD_AVAILABLE
        self.dashboard_port = dashboard_port
        self.running = False

        # Account state
        self.account_state = AccountState(
            equity=initial_equity,
            open_positions=[],
            daily_r_used=0.0,
            daily_trade_count=0,
            peak_equity=initial_equity,
        )

        # Position tracking
        self.positions: Dict[int, Position] = {}  # ticket → Position
        self.next_ticket = 1  # Simulated ticket counter for demo

        # Components
        self.zmq_bridge: Optional[ZMQBridge] = None
        self.range_bar_engine: Optional[LiveRangeBarEngine] = None
        self.ohlc_loader: OHLCLoader = OHLCLoader(pairs=pairs, lookback_4h=200, lookback_1h=500)
        self.dcrd_engine: DCRDEngine = DCRDEngine()
        self.brain_core: BrainCore = BrainCore(
            performance_tracker=PerformanceTracker(),
            news_layer=NewsLayer(),
            price_level_tracker=PriceLevelTracker(),
        )
        self.dashboard: Optional = None

        # DCRD scores (cache latest scores per pair)
        self.dcrd_scores: Dict[str, float] = {}
        self.dcrd_regimes: Dict[str, str] = {}

        # Statistics
        self.ticks_received = 0
        self.signals_generated = 0
        self.signals_approved = 0
        self.signals_sent = 0
        self.signals_blocked = 0
        self.start_time: Optional[datetime] = None

        # Strategy-specific statistics
        self.strategy_stats: Dict[str, Dict[str, int]] = {
            'TrendRider': {'generated': 0, 'approved': 0, 'blocked': 0, 'active': 0},
            'RangeRider': {'generated': 0, 'approved': 0, 'blocked': 0, 'active': 0},
            'SwingRider': {'generated': 0, 'approved': 0, 'blocked': 0, 'active': 0},
            'BreakoutRider': {'generated': 0, 'approved': 0, 'blocked': 0, 'active': 0},
        }

        # Signal evaluation history (for dashboard transparency)
        self.signal_evaluations: list[dict] = []  # Last 50 evaluations
        self.max_evaluations = 50

        # Initialize components
        self._initialize()

        # Load historical data
        if load_historical_bars:
            self._load_historical_data()

    def _initialize(self) -> None:
        """Initialize all components."""
        log.info("=" * 60)
        log.info("JcampFX BrainOrchestrator — Phase 4 Live Trading")
        log.info("=" * 60)

        # Initialize LiveRangeBarEngine
        self.range_bar_engine = LiveRangeBarEngine(
            pairs=self.pairs,
            on_bar_close=self._on_bar_close,
            lookback_bars=200,  # Keep 200 bars in memory for DCRD
        )
        log.info("LiveRangeBarEngine initialized for %d pairs", len(self.pairs))

        # Initialize ZMQ Bridge
        if self.zmq_enabled:
            self.zmq_bridge = ZMQBridge(
                tick_callback=self._on_tick_received,
                command_callback=self._on_execution_report,
            )
            log.info("ZMQ Bridge initialized (ports 5555/5556/5557)")
        else:
            log.info("ZMQ Bridge disabled (test mode)")

        log.info("BrainCore initialized (%s strategies)", self.brain_core.get_registered_strategies())

        # Initialize Dashboard
        if self.dashboard_enabled:
            if DASHBOARD_AVAILABLE:
                from dashboard.live_monitor import LiveDashboard
                self.dashboard = LiveDashboard(self, port=self.dashboard_port)
                log.info("Dashboard initialized (will start on orchestrator.start())")
            else:
                log.warning("Dashboard disabled - install: pip install dash plotly")
        else:
            log.info("Dashboard disabled")

        log.info("=" * 60)

    def _load_historical_data(self) -> None:
        """
        Load historical OHLC and Range Bar data from cache.

        Loads:
        1. Historical Range Bars from Parquet cache (last 200 bars)
        2. Historical 4H OHLC for DCRD structural score
        3. Historical 1H OHLC for DCRD dynamic modifier
        4. CSM data (4H OHLC for all CSM pairs)
        """
        log.info("Loading historical data from cache...")

        # Load historical Range Bars for each pair
        for pair in self.pairs:
            try:
                self.range_bar_engine.load_historical_bars(pair, lookback=200)
            except Exception as e:
                log.warning("Failed to load historical bars for %s: %s", pair, e)

        # Load OHLC data (4H, 1H, CSM)
        self.ohlc_loader.load_historical_data()

        # Print OHLC stats
        stats = self.ohlc_loader.get_stats()
        log.info("OHLC data loaded: 4H=%s, 1H=%s, CSM=%d pairs",
                 stats['ohlc_4h_loaded'], stats['ohlc_1h_loaded'],
                 len(stats['csm_pairs_loaded']))

        # Calculate initial DCRD scores for all pairs
        log.info("Calculating initial DCRD CompositeScores...")
        for pair in self.pairs:
            try:
                range_bars_df = self.range_bar_engine.get_bar_history(pair, n_bars=200, as_dataframe=True)
                if len(range_bars_df) > 0:
                    composite_score, regime = self._calculate_dcrd(pair, range_bars_df)
                    self.dcrd_scores[pair] = composite_score
                    self.dcrd_regimes[pair] = regime
                    log.info("DCRD initial: %s = %.1f (%s)", pair, composite_score, regime)
                else:
                    log.warning("No range bars available for %s, DCRD will calculate on first bar close", pair)
            except Exception as e:
                log.error("Failed to calculate initial DCRD for %s: %s", pair, e)

        log.info("Historical data loaded successfully")

    def start(self) -> None:
        """Start the BrainOrchestrator event loop."""
        if self.running:
            log.warning("BrainOrchestrator already running")
            return

        log.info("Starting BrainOrchestrator...")
        self.running = True
        self.start_time = datetime.now(timezone.utc)

        # Start ZMQ bridge
        if self.zmq_bridge:
            self.zmq_bridge.start()

        # Start Dashboard
        if self.dashboard:
            self.dashboard.start()
            log.info("📊 Dashboard available at: http://localhost:%d",
                    self.dashboard.port if hasattr(self.dashboard, 'port') else 8050)

        # Register signal handlers for graceful shutdown
        signal_module.signal(signal_module.SIGINT, self._signal_handler)
        signal_module.signal(signal_module.SIGTERM, self._signal_handler)

        log.info("BrainOrchestrator started successfully")
        log.info("Waiting for ticks from MT5... (Press Ctrl+C to stop)")

        # Main event loop (if not using ZMQ threads)
        if not self.zmq_enabled:
            self._run_test_loop()

    def stop(self) -> None:
        """Stop the BrainOrchestrator and cleanup."""
        if not self.running:
            return

        log.info("Stopping BrainOrchestrator...")
        self.running = False

        # Stop ZMQ bridge
        if self.zmq_bridge:
            self.zmq_bridge.stop()

        # Print final statistics
        self._print_stats()

        log.info("BrainOrchestrator stopped")

    def _signal_handler(self, signum, frame) -> None:
        """Handle Ctrl+C and termination signals."""
        log.info("\nReceived signal %d, shutting down gracefully...", signum)
        self.stop()
        sys.exit(0)

    def _on_tick_received(self, tick) -> None:
        """
        Callback from ZMQ bridge on each tick.

        Args:
            tick: TickData object from ZMQ bridge
        """
        self.ticks_received += 1

        # Strip broker suffix (.r for FP Markets ECN)
        clean_symbol = tick.symbol.replace('.r', '').replace('.', '')

        # Feed to Range Bar engine
        events = self.range_bar_engine.process_tick(
            pair=clean_symbol,
            bid=tick.bid,
            ask=tick.ask,
            timestamp=tick.time,
        )

        # Bar close events are handled via on_bar_close callback
        # (no need to process here, engine will call _on_bar_close)

        # Check exit conditions on every tick (for partial exits)
        self._check_exits_on_tick(clean_symbol, tick.bid, tick.ask, tick.time)

    def _on_bar_close(self, event: BarCloseEvent) -> None:
        """
        Callback from LiveRangeBarEngine on each Range Bar close.

        This is where we:
        1. Update OHLC data (4H, 1H)
        2. Calculate DCRD CompositeScore
        3. Run BrainCore.process() for entry signals
        4. Check exit conditions

        Args:
            event: BarCloseEvent from LiveRangeBarEngine
        """
        pair = event.pair
        bar = event.bar

        log.info("=" * 60)
        log.info("Bar Close Event: %s #%d", pair, event.bar_index)
        log.info("OHLC: %.5f / %.5f / %.5f / %.5f | Vol=%d",
                 bar.open, bar.high, bar.low, bar.close, bar.tick_volume)

        # Skip phantom bars for DCRD calculation (use tick boundary price for exits only)
        if bar.is_phantom:
            log.info("Skipping DCRD calculation for phantom bar")
            return

        # Get recent bars for DCRD
        range_bars_df = self.range_bar_engine.get_bar_history(pair, n_bars=200, as_dataframe=True)

        # Calculate DCRD CompositeScore
        try:
            composite_score, regime = self._calculate_dcrd(pair, range_bars_df)
            self.dcrd_scores[pair] = composite_score
            self.dcrd_regimes[pair] = regime
            log.info("DCRD: CS=%.1f (%s)", composite_score, regime)
        except Exception as e:
            log.error("DCRD calculation failed for %s: %s", pair, e, exc_info=True)
            # Fall back to default score if DCRD fails
            composite_score = 50.0
            regime = "transitional"
            self.dcrd_scores[pair] = composite_score
            self.dcrd_regimes[pair] = regime
            log.warning("Using fallback DCRD score: CS=%.1f (%s)", composite_score, regime)

        # Run BrainCore for entry signal
        signal = self._generate_entry_signal(
            pair=pair,
            range_bars=range_bars_df,
            composite_score=composite_score,
            current_time=bar.end_time,
        )

        if signal and not signal.blocked_reason:
            # Signal approved - send to MT5
            self._execute_signal(signal)
            # Track strategy statistics
            if signal.strategy in self.strategy_stats:
                self.strategy_stats[signal.strategy]['generated'] += 1
                self.strategy_stats[signal.strategy]['approved'] += 1
            # Log evaluation for dashboard
            self._log_signal_evaluation(pair, signal, "APPROVED", composite_score, bar.end_time)
        elif signal and signal.blocked_reason:
            self.signals_blocked += 1
            # Track strategy statistics
            if signal.strategy in self.strategy_stats:
                self.strategy_stats[signal.strategy]['generated'] += 1
                self.strategy_stats[signal.strategy]['blocked'] += 1
            log.info("Signal blocked: %s", signal.blocked_reason)
            # Log evaluation for dashboard
            self._log_signal_evaluation(pair, signal, "BLOCKED", composite_score, bar.end_time)
        else:
            # No signal generated (pattern not formed)
            self._log_signal_evaluation(pair, None, "NO_PATTERN", composite_score, bar.end_time)

        # Check exit conditions on bar close
        self._check_exits_on_bar_close(pair, bar, bar.end_time)

        log.info("=" * 60)

    def _calculate_dcrd(self, pair: str, range_bars: pd.DataFrame) -> tuple[float, str]:
        """
        Calculate DCRD CompositeScore for a pair.

        Args:
            pair: Trading pair
            range_bars: DataFrame with Range Bar history

        Returns:
            Tuple of (composite_score, regime)
        """
        # Get OHLC data
        ohlc_4h = self.ohlc_loader.get_ohlc_4h(pair)
        ohlc_1h = self.ohlc_loader.get_ohlc_1h(pair)
        csm_data = self.ohlc_loader.get_csm_data()

        # Validate data availability
        if ohlc_4h.empty or ohlc_1h.empty or not csm_data:
            log.warning("Insufficient OHLC data for DCRD calculation (%s)", pair)
            return 50.0, "transitional"  # Default fallback

        # Calculate DCRD
        score, regime = self.dcrd_engine.score(
            ohlc_4h=ohlc_4h,
            ohlc_1h=ohlc_1h,
            range_bars=range_bars,
            csm_data=csm_data,
            pair=pair,
        )

        return score, regime

    def _log_signal_evaluation(
        self,
        pair: str,
        signal: Optional[Signal],
        result: str,
        composite_score: float,
        timestamp: datetime,
    ) -> None:
        """
        Log signal evaluation for dashboard transparency.

        Args:
            pair: Trading pair
            signal: Generated signal (or None if no pattern)
            result: "APPROVED", "BLOCKED", or "NO_PATTERN"
            composite_score: Current DCRD score
            timestamp: Evaluation time
        """
        evaluation = {
            'timestamp': timestamp,
            'pair': pair,
            'strategy': signal.strategy if signal else "N/A",
            'direction': signal.direction if signal else "N/A",
            'result': result,
            'reason': signal.blocked_reason if signal and signal.blocked_reason else "",
            'cs': round(composite_score, 1),
            'regime': self.dcrd_regimes.get(pair, "unknown"),
        }

        # Add to history (keep last 50)
        self.signal_evaluations.append(evaluation)
        if len(self.signal_evaluations) > self.max_evaluations:
            self.signal_evaluations.pop(0)

    def _generate_entry_signal(
        self,
        pair: str,
        range_bars: pd.DataFrame,
        composite_score: float,
        current_time: datetime,
    ) -> Optional[Signal]:
        """
        Generate entry signal via BrainCore.

        Args:
            pair: Trading pair
            range_bars: Range Bar DataFrame
            composite_score: DCRD CompositeScore
            current_time: Current timestamp

        Returns:
            Signal object or None if no setup
        """
        # Get OHLC data
        ohlc_4h = self.ohlc_loader.get_ohlc_4h(pair)
        ohlc_1h = self.ohlc_loader.get_ohlc_1h(pair)

        # Validate data
        if range_bars.empty or ohlc_4h.empty or ohlc_1h.empty:
            log.warning("Insufficient data for signal generation (%s)", pair)
            return None

        # Get last bar for phantom detection
        last_bar = range_bars.iloc[-1] if not range_bars.empty else None

        # Calculate ATR(14) for chandelier (from 4H data)
        atr14 = self._calculate_atr14(ohlc_4h)

        # Call BrainCore
        try:
            signal = self.brain_core.process(
                pair=pair,
                range_bars=range_bars,
                ohlc_4h=ohlc_4h,
                ohlc_1h=ohlc_1h,
                composite_score=composite_score,
                account_state=self.account_state,
                current_time=current_time,
                atr14=atr14,
                sl_pips=0.0,  # Will be calculated by strategy
                pip_value_per_lot=None,  # Auto-estimate
                last_bar=last_bar,
                dcrd_history=None,  # TODO: Track DCRD history
                ohlc_m15=None,  # Not needed for TrendRider/RangeRider
                ohlc_daily=None,  # Not needed unless SwingRider is active
            )

            return signal

        except Exception as e:
            log.error("Signal generation failed for %s: %s", pair, e, exc_info=True)
            return None

    def _calculate_atr14(self, ohlc: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate ATR(14) from OHLC data.

        Args:
            ohlc: OHLC DataFrame
            period: ATR period (default 14)

        Returns:
            ATR value in price terms
        """
        if ohlc.empty or len(ohlc) < period:
            return 0.0

        try:
            # True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
            df = ohlc.copy()
            df["prev_close"] = df["close"].shift(1)
            df["tr1"] = df["high"] - df["low"]
            df["tr2"] = abs(df["high"] - df["prev_close"])
            df["tr3"] = abs(df["low"] - df["prev_close"])
            df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)

            # ATR = EMA of True Range
            atr = df["tr"].ewm(span=period, adjust=False).mean().iloc[-1]
            return float(atr)

        except Exception as e:
            log.error("ATR calculation failed: %s", e)
            return 0.0

    def _execute_signal(self, signal: Signal) -> None:
        """
        Execute approved signal by sending to MT5 via ZMQ.

        Args:
            signal: Approved Signal from BrainCore
        """
        self.signals_generated += 1

        # Create trading signal for MT5
        zmq_signal = TradingSignal(
            type="entry",
            symbol=signal.pair,
            direction=signal.direction.upper(),
            sl=signal.sl,
            tp=None,  # Managed by Python
            lots=signal.lot_size,
        )

        # Send to MT5
        if self.zmq_bridge:
            success = self.zmq_bridge.send_signal(zmq_signal)
            if success:
                self.signals_sent += 1
                log.info("Signal sent to MT5: %s %s @ %.5f lots=%.2f",
                         signal.direction, signal.pair, signal.entry, signal.lot_size)

                # Track position (simulated for now - actual position sync from MT5 needed)
                self._add_position(signal)
            else:
                log.error("Failed to send signal to MT5")
        else:
            log.info("ZMQ disabled - signal not sent (test mode)")

    def _on_execution_report(self, report: dict) -> None:
        """
        Handle execution report and news events from MT5.

        Args:
            report: Message dictionary from MT5
        """
        msg_type = report.get("type")

        if msg_type == "news_event":
            self._handle_news_event(report)
            return
        elif msg_type == "news_update_complete":
            self._handle_news_update_complete(report)
            return
        elif msg_type != "execution_report":
            return

        success = report.get("success", False)
        symbol = report.get("symbol", "").replace(".r", "")  # Remove broker suffix
        direction = report.get("direction", "")
        ticket = report.get("ticket", 0)
        price = report.get("price", 0.0)
        retcode = report.get("retcode", 0)

        if success and ticket > 0:
            log.info(
                "Position opened: Ticket #%d %s %s @ %.5f",
                ticket, direction, symbol, price
            )

            # Find the pending signal that triggered this execution
            # For now, we'll track it as a new position
            # TODO: Match with pending signals for full state sync

            # Update position tracking with real ticket from MT5
            # (for now, positions are added in _execute_signal, this confirms execution)

        else:
            log.error(
                "Position open failed: %s %s (retcode=%d)",
                direction, symbol, retcode
            )

    def _handle_news_event(self, event: dict) -> None:
        """
        Handle news event from MT5 calendar.

        Args:
            event: News event dictionary from MT5
        """
        currency = event.get("currency", "")
        event_name = event.get("event_name", "")
        time = datetime.fromtimestamp(event.get("time", 0), tz=timezone.utc)
        importance = event.get("importance", 0)

        # Map MT5 importance to our system
        # CALENDAR_IMPORTANCE_HIGH = 3, MEDIUM = 2, LOW = 1
        if importance >= 3:
            impact = "HIGH"
        elif importance >= 2:
            impact = "MEDIUM"
        else:
            impact = "LOW"

        log.info("News event received: %s @ %s - %s (impact=%s)",
                 currency, time, event_name, impact)

        # Add to news layer
        # Note: NewsLayer expects events in a specific format
        # For now, we log them. Full integration would require updating NewsLayer
        # to accept live events from MT5 calendar

        # TODO: Update NewsLayer to accept live calendar events
        # self.brain_core.news_layer.add_event(currency, event_name, time, impact)

    def _handle_news_update_complete(self, data: dict) -> None:
        """
        Handle news update completion marker.

        Args:
            data: Update completion data
        """
        count = data.get("count", 0)
        log.info("News calendar update complete: %d events loaded", count)

    def _add_position(self, signal: Signal, ticket: int = 0) -> None:
        """
        Add position to tracking.

        Args:
            signal: Signal that triggered the position
            ticket: MT5 ticket number (0 if not yet assigned)
        """
        if ticket == 0:
            ticket = self.next_ticket
            self.next_ticket += 1

        # Calculate initial risk in dollars
        sl_distance = abs(signal.entry - signal.sl)
        pip = PIP_SIZE.get(signal.pair, 0.0001)
        sl_distance_pips = sl_distance / pip
        # Approximate initial risk (will be updated with actual account equity)
        initial_risk = signal.risk_pct * self.account_state.equity if hasattr(signal, 'risk_pct') else 0.0

        pos = Position(
            ticket=ticket,
            pair=signal.pair,
            direction=signal.direction.upper(),
            entry=signal.entry,
            sl=signal.sl,
            tp=signal.tp_1r if hasattr(signal, 'tp_1r') else None,
            lot_size=signal.lot_size,
            strategy=signal.strategy,
            open_time=signal.timestamp,
            entry_cs=signal.composite_score,
            partial_exited=False,
            partial_exit_pct=signal.partial_exit_pct,
            initial_risk=initial_risk,
        )

        self.positions[ticket] = pos

        # Track active positions per strategy
        if pos.strategy in self.strategy_stats:
            self.strategy_stats[pos.strategy]['active'] += 1

        # Update AccountState
        self.account_state.open_positions.append({
            "pair": pos.pair,
            "direction": pos.direction,
            "entry": pos.entry,
            "sl": pos.sl,
            "lot_size": pos.lot_size,
            "strategy": pos.strategy,
            "open_time": pos.open_time,
        })
        self.account_state.daily_trade_count += 1

        log.info("Position tracked: Ticket #%d %s %s @ %.5f (SL %.5f)",
                 ticket, pos.direction, pos.pair, pos.entry, pos.sl)

    def _check_exits_on_tick(self, pair: str, bid: float, ask: float, timestamp: datetime) -> None:
        """
        Check exit conditions on each tick (for partial exits).

        Args:
            pair: Trading pair
            bid: Current bid price
            ask: Current ask price
            timestamp: Current timestamp
        """
        if not self.positions:
            return

        # Check partial exits for positions on this pair
        for ticket, pos in list(self.positions.items()):
            if pos.pair != pair:
                continue

            # Get current price for this position
            current_price = bid if pos.direction == "BUY" else ask

            # Calculate R-multiple
            r_multiple = self._calculate_r_multiple(pos, current_price)

            # Check partial exit at 1.5R
            if not pos.partial_exited and r_multiple >= PARTIAL_EXIT_R:
                self._execute_partial_exit(pos, current_price)

    def _check_exits_on_bar_close(self, pair: str, bar, timestamp: datetime) -> None:
        """
        Check exit conditions on Range Bar close (for trailing SL, regime deterioration).

        Args:
            pair: Trading pair
            bar: Closed Range Bar
            timestamp: Bar close timestamp
        """
        if not self.positions:
            return

        # Get current DCRD score
        current_cs = self.dcrd_scores.get(pair, 50.0)

        # Check exits for all positions on this pair
        for ticket, pos in list(self.positions.items()):
            if pos.pair != pair:
                continue

            # Get current price
            current_price = bar.close

            # Calculate R-multiple
            r_multiple = self._calculate_r_multiple(pos, current_price)

            # Check regime deterioration (CS drop >40 pts from entry)
            cs_drop = pos.entry_cs - current_cs
            if cs_drop > REGIME_DETERIORATION_THRESHOLD:
                log.info("Regime deterioration detected for ticket #%d: CS dropped %.1f pts (%.1f → %.1f)",
                         ticket, cs_drop, pos.entry_cs, current_cs)
                self._close_position(pos, current_price, "REGIME_DETERIORATION")
                continue

            # Update trailing SL (Range Bar extremes + 5-pip buffer)
            self._update_trailing_sl(pos, bar)

            # Check weekend close (Friday 20:40 UTC = 20 mins before close)
            if self._is_weekend_close_time(timestamp):
                # Runner protection: only close deep losers (R < -0.5)
                if r_multiple < -0.5:
                    log.info("Weekend close for ticket #%d (deep loser: R=%.2f)", ticket, r_multiple)
                    self._close_position(pos, current_price, "WEEKEND_CLOSE")
                else:
                    log.info("Weekend close skipped for ticket #%d (runner protection: R=%.2f >= -0.5)",
                             ticket, r_multiple)

        # Check 2R daily loss cap
        self._check_daily_loss_cap()

    def _calculate_r_multiple(self, pos: Position, current_price: float) -> float:
        """
        Calculate R-multiple for a position.

        Args:
            pos: Position object
            current_price: Current market price

        Returns:
            R-multiple (e.g., +1.5R or -0.8R)
        """
        if pos.initial_risk == 0.0:
            # Fallback: calculate from SL distance
            sl_distance = abs(pos.entry - pos.sl)
            if sl_distance == 0.0:
                return 0.0
            pos.initial_risk = sl_distance * pos.lot_size * 100000  # Approximate

        # Calculate current P&L in pips
        if pos.direction == "BUY":
            pnl_pips = (current_price - pos.entry) / PIP_SIZE.get(pos.pair, 0.0001)
        else:
            pnl_pips = (pos.entry - current_price) / PIP_SIZE.get(pos.pair, 0.0001)

        # Calculate SL distance in pips
        sl_distance_pips = abs(pos.entry - pos.sl) / PIP_SIZE.get(pos.pair, 0.0001)

        if sl_distance_pips == 0.0:
            return 0.0

        # R-multiple = P&L pips / SL distance pips
        return pnl_pips / sl_distance_pips

    def _execute_partial_exit(self, pos: Position, current_price: float) -> None:
        """
        Execute partial exit at 1.5R.

        Args:
            pos: Position object
            current_price: Current price
        """
        if pos.partial_exited:
            return

        # Mark as partially exited
        pos.partial_exited = True

        # Calculate partial exit volume (60-80% based on entry CS)
        exit_pct = pos.partial_exit_pct
        exit_volume = pos.lot_size * exit_pct

        log.info("Partial exit triggered for ticket #%d: %.0f%% (%.2f lots) at 1.5R (price=%.5f)",
                 pos.ticket, exit_pct * 100, exit_volume, current_price)

        # Send partial close signal to MT5
        # Note: MT5 doesn't support partial closes directly, so we need to:
        # 1. Close the full position
        # 2. Reopen a smaller position (runner)
        # For now, we'll send a modify signal to reduce volume (if MT5 supports it)
        # Otherwise, we track it internally and handle it differently

        # TODO: Implement partial exit via MT5 (may require close + reopen)
        # For now, just log it
        log.info("Partial exit: Close %.2f lots, keep %.2f lots as runner",
                 exit_volume, pos.lot_size - exit_volume)

        # Move SL to breakeven after partial exit (Phase 3 validated behavior)
        new_sl = pos.entry
        log.info("Moving SL to breakeven: %.5f", new_sl)
        self._send_modify_signal(pos.ticket, new_sl, None)
        pos.sl = new_sl

    def _update_trailing_sl(self, pos: Position, bar) -> None:
        """
        Update trailing SL based on Range Bar extremes + 5-pip buffer.

        Args:
            pos: Position object
            bar: Latest closed Range Bar
        """
        pip = PIP_SIZE.get(pos.pair, 0.0001)
        buffer = 5 * pip

        if pos.direction == "BUY":
            # Long position: SL = bar low - 5 pips
            new_sl = bar.low - buffer

            # Only move SL up (never down)
            if new_sl > pos.sl:
                log.info("Trailing SL update for ticket #%d: %.5f → %.5f (bar low - 5 pips)",
                         pos.ticket, pos.sl, new_sl)
                self._send_modify_signal(pos.ticket, new_sl, None)
                pos.sl = new_sl
        else:
            # Short position: SL = bar high + 5 pips
            new_sl = bar.high + buffer

            # Only move SL down (never up)
            if new_sl < pos.sl:
                log.info("Trailing SL update for ticket #%d: %.5f → %.5f (bar high + 5 pips)",
                         pos.ticket, pos.sl, new_sl)
                self._send_modify_signal(pos.ticket, new_sl, None)
                pos.sl = new_sl

    def _close_position(self, pos: Position, current_price: float, reason: str) -> None:
        """
        Close a position.

        Args:
            pos: Position object
            current_price: Current price
            reason: Close reason (for logging)
        """
        log.info("Closing position ticket #%d @ %.5f (reason: %s)",
                 pos.ticket, current_price, reason)

        # Send close signal to MT5
        self._send_close_signal(pos.ticket)

        # Remove from tracking
        if pos.ticket in self.positions:
            # Track active positions per strategy
            if pos.strategy in self.strategy_stats:
                self.strategy_stats[pos.strategy]['active'] = max(0, self.strategy_stats[pos.strategy]['active'] - 1)
            del self.positions[pos.ticket]

        # Update account state
        self.account_state.open_positions = [
            p for p in self.account_state.open_positions
            if p.get("pair") != pos.pair or p.get("open_time") != pos.open_time
        ]

    def _check_daily_loss_cap(self) -> None:
        """
        Check 2R daily loss cap and close deep losers.

        Runner protection: Only close positions with R < -0.5
        """
        if self.account_state.daily_r_used <= -DAILY_LOSS_CAP_R:
            log.warning("Daily 2R loss cap hit (%.2fR) - closing deep losers (R < -0.5)",
                        self.account_state.daily_r_used)

            for ticket, pos in list(self.positions.items()):
                # Get current price
                current_price = 0.0  # TODO: Get from latest tick

                # Calculate R-multiple
                r_multiple = self._calculate_r_multiple(pos, current_price)

                # Runner protection: only close R < -0.5
                if r_multiple < -0.5:
                    log.info("Closing deep loser ticket #%d (R=%.2f < -0.5)", ticket, r_multiple)
                    self._close_position(pos, current_price, "DAILY_2R_CAP")
                else:
                    log.info("Protecting runner ticket #%d (R=%.2f >= -0.5)", ticket, r_multiple)

    def _is_weekend_close_time(self, timestamp: datetime) -> bool:
        """
        Check if it's time to close positions for the weekend.

        Args:
            timestamp: Current timestamp (UTC)

        Returns:
            True if it's Friday 20:40 UTC or later
        """
        # Friday = weekday 4
        if timestamp.weekday() != 4:
            return False

        # Check if time >= 20:40 UTC (20 minutes before market close at 21:00)
        close_time = timestamp.replace(hour=21, minute=0, second=0, microsecond=0)
        warning_time = close_time - pd.Timedelta(minutes=WEEKEND_CLOSE_MINUTES)

        return timestamp >= warning_time

    def _send_modify_signal(self, ticket: int, new_sl: float, new_tp: Optional[float]) -> None:
        """
        Send modify signal to MT5 (update SL/TP).

        Args:
            ticket: Position ticket
            new_sl: New stop loss
            new_tp: New take profit (optional)
        """
        if not self.zmq_bridge:
            log.debug("ZMQ disabled - modify signal not sent (ticket #%d)", ticket)
            return

        signal = TradingSignal(
            type="modify",
            symbol="",  # Not needed for modify
            ticket=ticket,
            sl=new_sl,
            tp=new_tp,
        )

        success = self.zmq_bridge.send_signal(signal)
        if success:
            log.info("Modify signal sent for ticket #%d: SL=%.5f TP=%s",
                     ticket, new_sl, new_tp if new_tp else "None")
        else:
            log.error("Failed to send modify signal for ticket #%d", ticket)

    def _send_close_signal(self, ticket: int) -> None:
        """
        Send close signal to MT5.

        Args:
            ticket: Position ticket
        """
        if not self.zmq_bridge:
            log.debug("ZMQ disabled - close signal not sent (ticket #%d)", ticket)
            return

        signal = TradingSignal(
            type="exit",
            symbol="",  # Not needed for exit
            ticket=ticket,
        )

        success = self.zmq_bridge.send_signal(signal)
        if success:
            log.info("Close signal sent for ticket #%d", ticket)
        else:
            log.error("Failed to send close signal for ticket #%d", ticket)

    def _print_stats(self) -> None:
        """Print orchestrator statistics."""
        uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds() if self.start_time else 0

        log.info("=" * 60)
        log.info("BrainOrchestrator Statistics")
        log.info("=" * 60)
        log.info("Uptime: %.1f seconds", uptime)
        log.info("Ticks received: %d", self.ticks_received)
        log.info("Signals generated: %d", self.signals_generated)
        log.info("Signals sent: %d", self.signals_sent)
        log.info("Signals blocked: %d", self.signals_blocked)
        log.info("Open positions: %d", len(self.positions))
        log.info("Account equity: $%.2f", self.account_state.equity)
        log.info("Daily R used: %.2fR", self.account_state.daily_r_used)
        log.info("Daily trade count: %d", self.account_state.daily_trade_count)

        # Range Bar engine stats
        if self.range_bar_engine:
            rb_stats = self.range_bar_engine.get_stats()
            log.info("Range Bars produced: %s", rb_stats['bars_produced'])

        # ZMQ bridge stats
        if self.zmq_bridge:
            zmq_stats = self.zmq_bridge.get_stats()
            log.info("ZMQ total ticks: %d", zmq_stats['total_ticks'])
            log.info("ZMQ commands sent: %d", zmq_stats['commands_sent'])

        log.info("=" * 60)

    def _run_test_loop(self) -> None:
        """Test loop when ZMQ is disabled (for testing)."""
        log.info("Running in test mode (no ZMQ)...")
        log.info("Simulating ticks... (Press Ctrl+C to stop)")

        try:
            while self.running:
                time.sleep(1)
                # In test mode, user can manually call process_tick()
        except KeyboardInterrupt:
            log.info("\nTest loop interrupted")
            self.stop()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Run BrainOrchestrator standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # Initialize with all active pairs
    orchestrator = BrainOrchestrator(
        pairs=PAIRS,
        initial_equity=500.0,
        zmq_enabled=True,  # Enable ZMQ for live connection
        load_historical_bars=True,
    )

    # Start event loop
    orchestrator.start()

    # Keep running until interrupted
    try:
        while orchestrator.running:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("\nShutting down...")
        orchestrator.stop()


if __name__ == "__main__":
    main()
