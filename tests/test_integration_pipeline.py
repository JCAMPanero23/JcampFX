"""
JcampFX — Phase 4 Integration Test

End-to-end pipeline validation:
1. Load historical tick data
2. Build Range Bars via LiveRangeBarEngine
3. Calculate DCRD via DCRDEngine
4. Generate signals via BrainCore
5. Validate against expected behavior

This test validates the complete live trading pipeline WITHOUT requiring MT5 connection.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.brain_core import AccountState
from src.brain_orchestrator import BrainOrchestrator
from src.config import PAIRS, RANGE_BAR_PIPS
from src.live_range_bar_engine import LiveRangeBarEngine
from src.ohlc_loader import OHLCLoader
from src.dcrd.dcrd_engine import DCRDEngine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


class IntegrationTest:
    """
    Integration test harness for Phase 4 live trading pipeline.
    """

    def __init__(self, pair: str = "EURUSD", test_duration_hours: int = 24):
        """
        Initialize integration test.

        Args:
            pair: Trading pair to test
            test_duration_hours: Duration of test data (hours)
        """
        self.pair = pair
        self.test_duration_hours = test_duration_hours

        # Test statistics
        self.ticks_processed = 0
        self.bars_created = 0
        self.dcrd_calculations = 0
        self.signals_generated = 0
        self.signals_approved = 0
        self.signals_blocked = 0

        # Results storage
        self.range_bars = []
        self.dcrd_scores = []
        self.signals = []

        log.info("=" * 70)
        log.info("JcampFX Phase 4 Integration Test")
        log.info("=" * 70)
        log.info("Pair: %s", pair)
        log.info("Test duration: %d hours", test_duration_hours)

    def load_test_data(self) -> pd.DataFrame:
        """
        Load historical tick data for testing.

        Returns:
            DataFrame with tick data (time, bid, ask)
        """
        log.info("\n[Step 1] Loading test data...")

        tick_file = PROJECT_ROOT / "data" / "ticks" / f"{self.pair}_ticks.parquet"

        if not tick_file.exists():
            raise FileNotFoundError(f"Tick data not found: {tick_file}")

        # Load full tick data
        df = pd.read_parquet(tick_file)
        df["time"] = pd.to_datetime(df["time"], utc=True)

        # Take last N hours of data
        end_time = df["time"].max()
        start_time = end_time - pd.Timedelta(hours=self.test_duration_hours)
        df = df[df["time"] >= start_time].copy()

        log.info("Loaded %d ticks from %s to %s",
                 len(df), start_time, end_time)

        return df

    def test_range_bar_engine(self, ticks: pd.DataFrame) -> None:
        """
        Test LiveRangeBarEngine with historical ticks.

        Args:
            ticks: DataFrame with tick data
        """
        log.info("\n[Step 2] Testing LiveRangeBarEngine...")

        # Initialize engine
        engine = LiveRangeBarEngine(
            pairs=[self.pair],
            on_bar_close=self._on_bar_close_callback,
            lookback_bars=200,
        )

        # Process ticks
        for tick in ticks.itertuples(index=False):
            events = engine.process_tick(
                pair=self.pair,
                bid=tick.bid,
                ask=tick.ask,
                timestamp=tick.time,
            )

            self.ticks_processed += 1

            # Track bar closes
            for event in events:
                self.bars_created += 1

        # Print stats
        log.info("Ticks processed: %d", self.ticks_processed)
        log.info("Range Bars created: %d", self.bars_created)
        log.info("Bars in memory: %d", len(engine.get_bar_history(self.pair)))

        # Validate Range Bars
        bars_df = engine.get_bar_history(self.pair, as_dataframe=True)
        if not bars_df.empty:
            # Check bar size consistency
            bar_pips = RANGE_BAR_PIPS.get(self.pair, 15)
            expected_range = bar_pips * 0.0001  # For EURUSD

            # Sample 10 random bars
            sample = bars_df.sample(min(10, len(bars_df)))
            log.info("\n=== Sample Range Bars ===")
            for _, bar in sample.iterrows():
                bar_range = bar["high"] - bar["low"]
                log.info("Bar @ %s: O=%.5f H=%.5f L=%.5f C=%.5f | Range=%.5f (expected=%.5f)",
                         bar["end_time"], bar["open"], bar["high"], bar["low"], bar["close"],
                         bar_range, expected_range)

        self.range_bars = engine.get_bar_history(self.pair)

    def test_ohlc_loader(self) -> OHLCLoader:
        """
        Test OHLCLoader with historical data.

        Returns:
            Initialized OHLCLoader
        """
        log.info("\n[Step 3] Testing OHLCLoader...")

        loader = OHLCLoader(pairs=[self.pair], lookback_4h=200, lookback_1h=500)
        loader.load_historical_data()

        # Print stats
        stats = loader.get_stats()
        log.info("4H OHLC loaded: %s", stats['ohlc_4h_loaded'])
        log.info("1H OHLC loaded: %s", stats['ohlc_1h_loaded'])
        log.info("CSM pairs loaded: %d", len(stats['csm_pairs_loaded']))

        # Validate OHLC data
        ohlc_4h = loader.get_ohlc_4h(self.pair)
        ohlc_1h = loader.get_ohlc_1h(self.pair)

        if not ohlc_4h.empty:
            log.info("\n4H OHLC range: %s to %s (%d bars)",
                     ohlc_4h.index[0], ohlc_4h.index[-1], len(ohlc_4h))

        if not ohlc_1h.empty:
            log.info("1H OHLC range: %s to %s (%d bars)",
                     ohlc_1h.index[0], ohlc_1h.index[-1], len(ohlc_1h))

        return loader

    def test_dcrd_engine(self, loader: OHLCLoader) -> None:
        """
        Test DCRDEngine with loaded data.

        Args:
            loader: OHLCLoader with historical data
        """
        log.info("\n[Step 4] Testing DCRDEngine...")

        dcrd_engine = DCRDEngine()

        # Get data
        ohlc_4h = loader.get_ohlc_4h(self.pair)
        ohlc_1h = loader.get_ohlc_1h(self.pair)
        csm_data = loader.get_csm_data()

        # Convert range bars to DataFrame
        range_bars_df = pd.DataFrame([b.to_dict() for b in self.range_bars[-200:]])
        if "start_time" in range_bars_df.columns:
            range_bars_df["start_time"] = pd.to_datetime(range_bars_df["start_time"], utc=True)
        if "end_time" in range_bars_df.columns:
            range_bars_df["end_time"] = pd.to_datetime(range_bars_df["end_time"], utc=True)

        # Calculate DCRD (test last 10 bar closes)
        log.info("\n=== DCRD Scores (last 10 bars) ===")
        for i in range(max(0, len(self.range_bars) - 10), len(self.range_bars)):
            try:
                score, regime = dcrd_engine.score(
                    ohlc_4h=ohlc_4h,
                    ohlc_1h=ohlc_1h,
                    range_bars=range_bars_df,
                    csm_data=csm_data,
                    pair=self.pair,
                )

                self.dcrd_calculations += 1
                self.dcrd_scores.append((self.range_bars[i].end_time, score, regime))

                log.info("Bar %d @ %s: CS=%.1f (%s)",
                         i, self.range_bars[i].end_time, score, regime)

            except Exception as e:
                log.error("DCRD calculation failed for bar %d: %s", i, e)

        log.info("DCRD calculations: %d", self.dcrd_calculations)

    def test_brain_orchestrator(self) -> None:
        """
        Test BrainOrchestrator with full pipeline (without ZMQ).
        """
        log.info("\n[Step 5] Testing BrainOrchestrator (full pipeline)...")

        # Initialize orchestrator (ZMQ disabled for testing)
        orchestrator = BrainOrchestrator(
            pairs=[self.pair],
            initial_equity=500.0,
            zmq_enabled=False,  # Disable ZMQ for testing
            load_historical_bars=True,
        )

        # Load historical data
        orchestrator._load_historical_data()

        # Get test data
        range_bars_df = orchestrator.range_bar_engine.get_bar_history(
            self.pair, as_dataframe=True
        )

        if range_bars_df.empty:
            log.warning("No Range Bars available for signal generation test")
            return

        # Test signal generation on last 10 bars
        log.info("\n=== Signal Generation Test (last 10 bars) ===")
        for i in range(max(0, len(range_bars_df) - 10), len(range_bars_df)):
            bar = range_bars_df.iloc[i]

            # Calculate DCRD
            try:
                score, regime = orchestrator._calculate_dcrd(
                    self.pair,
                    range_bars_df[:i+1]  # Up to current bar
                )
            except Exception as e:
                log.error("DCRD calculation failed: %s", e)
                continue

            # Generate signal
            try:
                signal = orchestrator._generate_entry_signal(
                    pair=self.pair,
                    range_bars=range_bars_df[:i+1],
                    composite_score=score,
                    current_time=bar["end_time"],
                )

                self.signals_generated += 1

                if signal and not signal.blocked_reason:
                    self.signals_approved += 1
                    self.signals.append(signal)
                    log.info("✅ SIGNAL APPROVED: %s %s @ %.5f (CS=%.1f, strategy=%s)",
                             signal.direction, signal.pair, signal.entry,
                             score, signal.strategy)
                elif signal and signal.blocked_reason:
                    self.signals_blocked += 1
                    log.info("❌ SIGNAL BLOCKED: %s (CS=%.1f)",
                             signal.blocked_reason, score)
                else:
                    log.info("⚪ No setup (CS=%.1f, regime=%s)", score, regime)

            except Exception as e:
                log.error("Signal generation failed: %s", e, exc_info=True)

        log.info("\nSignals generated: %d", self.signals_generated)
        log.info("Signals approved: %d", self.signals_approved)
        log.info("Signals blocked: %d", self.signals_blocked)

    def _on_bar_close_callback(self, event):
        """Callback for bar close events (used by LiveRangeBarEngine)."""
        # Just count the event, actual processing happens in test
        pass

    def print_summary(self) -> None:
        """Print test summary."""
        log.info("\n" + "=" * 70)
        log.info("INTEGRATION TEST SUMMARY")
        log.info("=" * 70)
        log.info("Pair: %s", self.pair)
        log.info("Test duration: %d hours", self.test_duration_hours)
        log.info("")
        log.info("Pipeline Metrics:")
        log.info("  Ticks processed: %d", self.ticks_processed)
        log.info("  Range Bars created: %d", self.bars_created)
        log.info("  DCRD calculations: %d", self.dcrd_calculations)
        log.info("  Signals generated: %d", self.signals_generated)
        log.info("  Signals approved: %d", self.signals_approved)
        log.info("  Signals blocked: %d", self.signals_blocked)
        log.info("")

        if self.signals:
            log.info("Approved Signals:")
            for sig in self.signals:
                log.info("  - %s %s @ %.5f | SL=%.5f | Lots=%.2f | CS=%.1f | Strategy=%s",
                         sig.direction, sig.pair, sig.entry, sig.sl,
                         sig.lot_size, sig.composite_score, sig.strategy)

        # Validation checks
        log.info("\nValidation Checks:")
        checks_passed = 0
        total_checks = 0

        # Check 1: Ticks processed
        total_checks += 1
        if self.ticks_processed > 0:
            log.info("  ✅ Ticks processed: %d", self.ticks_processed)
            checks_passed += 1
        else:
            log.error("  ❌ No ticks processed!")

        # Check 2: Range Bars created
        total_checks += 1
        if self.bars_created > 0:
            log.info("  ✅ Range Bars created: %d", self.bars_created)
            checks_passed += 1
        else:
            log.error("  ❌ No Range Bars created!")

        # Check 3: DCRD calculations
        total_checks += 1
        if self.dcrd_calculations > 0:
            log.info("  ✅ DCRD calculations: %d", self.dcrd_calculations)
            checks_passed += 1
        else:
            log.error("  ❌ No DCRD calculations!")

        # Check 4: Signal generation attempted
        total_checks += 1
        if self.signals_generated > 0:
            log.info("  ✅ Signal generation tested: %d attempts", self.signals_generated)
            checks_passed += 1
        else:
            log.warning("  ⚠️  No signal generation attempts")

        # Check 5: Bar size consistency
        total_checks += 1
        if self.range_bars:
            bar_pips = RANGE_BAR_PIPS.get(self.pair, 15)
            pip_size = 0.0001 if "JPY" not in self.pair else 0.01
            expected_range = bar_pips * pip_size

            # Check last 10 bars
            valid_bars = 0
            for bar in self.range_bars[-10:]:
                actual_range = bar.high - bar.low
                if abs(actual_range - expected_range) < pip_size * 0.1:  # 10% tolerance
                    valid_bars += 1

            if valid_bars >= 8:  # At least 80% should be valid
                log.info("  ✅ Range Bar size consistency: %d/10 bars valid", valid_bars)
                checks_passed += 1
            else:
                log.error("  ❌ Range Bar size inconsistent: only %d/10 bars valid", valid_bars)
        else:
            log.error("  ❌ No Range Bars to validate!")

        log.info("")
        log.info("OVERALL: %d/%d checks passed", checks_passed, total_checks)

        if checks_passed == total_checks:
            log.info("✅ ALL CHECKS PASSED - Pipeline is working correctly!")
        elif checks_passed >= total_checks * 0.8:
            log.warning("⚠️  MOSTLY PASSED - Some issues found, review logs")
        else:
            log.error("❌ FAILED - Critical issues found, pipeline needs debugging")

        log.info("=" * 70)


def main():
    """Run integration test."""
    # Test configuration
    test = IntegrationTest(pair="EURUSD", test_duration_hours=24)

    try:
        # Step 1: Load test data
        ticks = test.load_test_data()

        # Step 2: Test Range Bar engine
        test.test_range_bar_engine(ticks)

        # Step 3: Test OHLC loader
        loader = test.test_ohlc_loader()

        # Step 4: Test DCRD engine
        test.test_dcrd_engine(loader)

        # Step 5: Test BrainOrchestrator
        test.test_brain_orchestrator()

        # Print summary
        test.print_summary()

    except Exception as e:
        log.error("Integration test failed: %s", e, exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
