"""
JcampFX — Test Signal Generator (Phase 4.3)

Generate synthetic trading signals independent of Range Bar close events.
Used to validate ZMQ pipeline (cBot/EA → Python) without waiting hours for real signals.

Architecture:
- Decouple signal generation from bar close
- Generate entry/exit/modify signals on demand
- Track test trades with ticket numbers
- Support full-cycle test (entry → modify → exit in 15s)

Usage:
    generator = TestSignalGenerator(brain_core)
    generator.fire_test_signal("EURUSD", "BUY", mode="full_cycle")
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal

log = logging.getLogger(__name__)


@dataclass
class TestTrade:
    """Track test trade state for full-cycle tests."""
    pair: str
    direction: str
    ticket: Optional[int] = None
    entry_price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    status: str = "pending"  # pending, entered, modified, exited


class TestSignalGenerator:
    """
    Generate synthetic trading signals for testing ZMQ pipeline.

    Does NOT interact with real Range Bar data or DCRD calculations.
    Uses current live price to generate realistic signals.
    """

    def __init__(self, brain_core):
        """
        Initialize test signal generator.

        Args:
            brain_core: BrainCore instance (for sending signals + accessing live prices)
        """
        self.brain = brain_core
        self.test_trades = {}  # ticket → TestTrade mapping
        self.next_test_id = 90000  # Test tickets start at 90000 (avoid conflict with real trades)

    def fire_test_signal(
        self,
        pair: str,
        direction: Literal["BUY", "SELL"],
        mode: Literal["entry_only", "full_cycle", "exit_only", "modify_only"] = "entry_only",
        lots: float = 0.01,
        ticket: Optional[int] = None,
    ) -> Optional[int]:
        """
        Fire a test signal to cBot/EA via ZMQ.

        Args:
            pair: Canonical pair name (e.g., "EURUSD")
            direction: "BUY" or "SELL"
            mode: Test mode:
                - "entry_only": Send entry signal only (position stays open)
                - "full_cycle": Entry → wait 5s → modify SL → wait 5s → exit (15s total)
                - "exit_only": Close existing position by ticket
                - "modify_only": Update SL/TP on existing position
            lots: Lot size (default 0.01)
            ticket: Position ticket (required for exit_only/modify_only)

        Returns:
            Test ticket number (for tracking), or None if failed
        """
        log.info(f"[TEST] Firing {mode} signal: {pair} {direction} {lots} lots")

        if mode == "entry_only":
            return self._fire_entry(pair, direction, lots)

        elif mode == "full_cycle":
            return self._fire_full_cycle(pair, direction, lots)

        elif mode == "exit_only":
            if ticket is None:
                log.error("[TEST] exit_only requires ticket parameter")
                return None
            return self._fire_exit(ticket)

        elif mode == "modify_only":
            if ticket is None:
                log.error("[TEST] modify_only requires ticket parameter")
                return None
            return self._fire_modify(ticket)

        else:
            log.error(f"[TEST] Unknown mode: {mode}")
            return None

    def _fire_entry(self, pair: str, direction: str, lots: float) -> Optional[int]:
        """Fire entry signal only."""
        # Get current live price
        tick = self._get_current_tick(pair)
        if tick is None:
            log.error(f"[TEST] No tick data available for {pair}")
            return None

        # Calculate SL/TP (simple 50-pip SL, no TP)
        pip_size = self._get_pip_size(pair)
        sl_distance = 50 * pip_size

        if direction == "BUY":
            entry_price = tick.ask
            sl = entry_price - sl_distance
        else:  # SELL
            entry_price = tick.bid
            sl = entry_price + sl_distance

        # Generate test ticket
        test_ticket = self.next_test_id
        self.next_test_id += 1

        # Create test trade record
        test_trade = TestTrade(
            pair=pair,
            direction=direction,
            ticket=test_ticket,
            entry_price=entry_price,
            sl=sl,
            tp=None,
            status="pending"
        )
        self.test_trades[test_ticket] = test_trade

        # Send entry signal via ZMQ
        log.info(f"[TEST] Sending entry: {pair} {direction} @ {entry_price:.5f} SL={sl:.5f} Ticket={test_ticket}")

        # Call brain's signal sender
        try:
            from .zmq_bridge import TradingSignal
            signal = TradingSignal(
                type="entry",
                symbol=pair,
                direction=direction,
                sl=sl,
                tp=None,
                lots=lots
            )
            self.brain.zmq_bridge.send_signal(signal)
            test_trade.status = "entered"
            log.info(f"[TEST] Entry signal sent successfully: Ticket {test_ticket}")
            return test_ticket
        except Exception as e:
            log.error(f"[TEST] Failed to send entry signal: {e}")
            return None

    def _fire_full_cycle(self, pair: str, direction: str, lots: float) -> Optional[int]:
        """Fire full cycle: entry → modify SL → exit (15s total)."""
        # Step 1: Entry
        test_ticket = self._fire_entry(pair, direction, lots)
        if test_ticket is None:
            return None

        # Step 2: Wait 5 seconds
        log.info("[TEST] Full cycle: waiting 5s before modifying SL...")
        time.sleep(5)

        # Step 3: Modify SL to breakeven
        test_trade = self.test_trades.get(test_ticket)
        if test_trade is None:
            log.error(f"[TEST] Test trade {test_ticket} not found")
            return test_ticket

        # Move SL to breakeven (entry price)
        new_sl = test_trade.entry_price
        log.info(f"[TEST] Modifying SL to breakeven: Ticket {test_ticket} SL={new_sl:.5f}")

        try:
            from .zmq_bridge import TradingSignal
            signal = TradingSignal(
                type="modify",
                symbol=test_trade.pair,
                ticket=test_ticket,
                sl=new_sl,
                tp=None
            )
            self.brain.zmq_bridge.send_signal(signal)
            test_trade.sl = new_sl
            test_trade.status = "modified"
            log.info(f"[TEST] Modify signal sent successfully: Ticket {test_ticket}")
        except Exception as e:
            log.error(f"[TEST] Failed to send modify signal: {e}")

        # Step 4: Wait 5 seconds
        log.info("[TEST] Full cycle: waiting 5s before exit...")
        time.sleep(5)

        # Step 5: Exit
        log.info(f"[TEST] Closing position: Ticket {test_ticket}")
        self._fire_exit(test_ticket)

        log.info(f"[TEST] Full cycle complete: Ticket {test_ticket}")
        return test_ticket

    def _fire_exit(self, ticket: int) -> Optional[int]:
        """Fire exit signal to close position."""
        test_trade = self.test_trades.get(ticket)
        if test_trade is None:
            log.error(f"[TEST] Test trade {ticket} not found")
            return None

        log.info(f"[TEST] Sending exit: Ticket {ticket}")

        try:
            from .zmq_bridge import TradingSignal
            signal = TradingSignal(
                type="exit",
                symbol=test_trade.pair,
                ticket=ticket
            )
            self.brain.zmq_bridge.send_signal(signal)
            test_trade.status = "exited"
            log.info(f"[TEST] Exit signal sent successfully: Ticket {ticket}")
            return ticket
        except Exception as e:
            log.error(f"[TEST] Failed to send exit signal: {e}")
            return None

    def _fire_modify(self, ticket: int) -> Optional[int]:
        """Fire modify signal to update SL/TP."""
        test_trade = self.test_trades.get(ticket)
        if test_trade is None:
            log.error(f"[TEST] Test trade {ticket} not found")
            return None

        # Move SL to breakeven as example
        new_sl = test_trade.entry_price
        log.info(f"[TEST] Sending modify: Ticket {ticket} SL={new_sl:.5f}")

        try:
            from .zmq_bridge import TradingSignal
            signal = TradingSignal(
                type="modify",
                symbol=test_trade.pair,
                ticket=ticket,
                sl=new_sl,
                tp=None
            )
            self.brain.zmq_bridge.send_signal(signal)
            test_trade.sl = new_sl
            test_trade.status = "modified"
            log.info(f"[TEST] Modify signal sent successfully: Ticket {ticket}")
            return ticket
        except Exception as e:
            log.error(f"[TEST] Failed to send modify signal: {e}")
            return None

    def _get_current_tick(self, pair: str):
        """Get current tick data from brain (if available)."""
        # Assumes brain stores latest ticks in a dict
        # Adjust based on actual brain implementation
        if hasattr(self.brain, 'latest_ticks'):
            return self.brain.latest_ticks.get(pair)
        else:
            log.warning(f"[TEST] Brain has no latest_ticks attribute - using placeholder price")
            # Return dummy tick for testing
            from .zmq_bridge import TickData
            return TickData(
                symbol=pair,
                time=datetime.now(),
                bid=1.08500,
                ask=1.08503,
                last=1.08501,
                volume=0,
                flags=0
            )

    def _get_pip_size(self, pair: str) -> float:
        """Get pip size for pair."""
        from .config import PIP_SIZE
        return PIP_SIZE.get(pair, 0.0001)

    def get_test_trade_status(self, ticket: int) -> Optional[str]:
        """Get status of test trade."""
        test_trade = self.test_trades.get(ticket)
        if test_trade is None:
            return None
        return test_trade.status

    def list_active_test_trades(self):
        """List all active test trades."""
        active = [t for t in self.test_trades.values() if t.status != "exited"]
        log.info(f"[TEST] Active test trades: {len(active)}")
        for trade in active:
            log.info(f"  Ticket {trade.ticket}: {trade.pair} {trade.direction} @ {trade.entry_price:.5f} ({trade.status})")
        return active
