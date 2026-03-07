#!/usr/bin/env python3
"""
JcampFX — Test Trade CLI Launcher

Command-line interface for firing dummy trades to validate ZMQ pipeline.
No need to wait for Range Bar close - generates synthetic signals on demand.

Usage:
    # Full cycle test (entry → modify → exit in 15s)
    python test_trade.py --pair EURUSD --direction BUY --mode full_cycle

    # Entry only (position stays open)
    python test_trade.py --pair USDJPY --direction SELL --mode entry_only --lots 0.02

    # Exit specific position
    python test_trade.py --ticket 90001 --mode exit_only

    # Modify specific position
    python test_trade.py --ticket 90001 --mode modify_only

Examples:
    # Quick validation test (recommended first test)
    python test_trade.py --pair EURUSD --direction BUY --mode full_cycle

    # Test entry only (manual close later)
    python test_trade.py --pair AUDJPY --direction BUY --mode entry_only

    # Close test trade #90001
    python test_trade.py --ticket 90001 --mode exit_only
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from test_signal_generator import TestSignalGenerator
from zmq_bridge import ZMQBridge, TradingSignal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)


class MockBrainCore:
    """
    Minimal brain core for test signal generation.
    Only needs ZMQ bridge + latest ticks.
    """
    def __init__(self):
        self.zmq_bridge = None
        self.latest_ticks = {}

    def start(self):
        """Start ZMQ bridge."""
        log.info("Starting ZMQ bridge...")
        self.zmq_bridge = ZMQBridge(
            signal_port=5555,
            command_port=5556,
            news_port=5557,
            tick_callback=self._on_tick
        )
        self.zmq_bridge.start()
        log.info("ZMQ bridge started")

        # Wait for connection
        time.sleep(2)

    def stop(self):
        """Stop ZMQ bridge."""
        if self.zmq_bridge:
            log.info("Stopping ZMQ bridge...")
            self.zmq_bridge.stop()
            log.info("ZMQ bridge stopped")

    def _on_tick(self, tick):
        """Store latest tick for each pair."""
        self.latest_ticks[tick.symbol] = tick


def main():
    parser = argparse.ArgumentParser(
        description="JcampFX Test Trade Launcher - Fire dummy trades to validate ZMQ pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full cycle test (entry → modify → exit in 15s)
  python test_trade.py --pair EURUSD --direction BUY --mode full_cycle

  # Entry only (manual close)
  python test_trade.py --pair USDJPY --direction SELL --mode entry_only --lots 0.02

  # Exit by ticket
  python test_trade.py --ticket 90001 --mode exit_only

  # Modify by ticket
  python test_trade.py --ticket 90001 --mode modify_only
        """
    )

    # Mode selection
    parser.add_argument(
        '--mode',
        choices=['entry_only', 'full_cycle', 'exit_only', 'modify_only'],
        default='entry_only',
        help='Test mode (default: entry_only)'
    )

    # Entry parameters
    parser.add_argument('--pair', type=str, help='Trading pair (e.g., EURUSD)')
    parser.add_argument(
        '--direction',
        choices=['BUY', 'SELL'],
        help='Trade direction'
    )
    parser.add_argument(
        '--lots',
        type=float,
        default=0.01,
        help='Lot size (default: 0.01)'
    )

    # Exit/modify parameters
    parser.add_argument(
        '--ticket',
        type=int,
        help='Position ticket (for exit_only/modify_only)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.mode in ['entry_only', 'full_cycle']:
        if not args.pair or not args.direction:
            parser.error("--pair and --direction are required for entry/full_cycle modes")

    if args.mode in ['exit_only', 'modify_only']:
        if not args.ticket:
            parser.error("--ticket is required for exit_only/modify_only modes")

    # Start brain core (minimal)
    log.info("="*60)
    log.info("JcampFX Test Trade Launcher")
    log.info("="*60)

    brain = MockBrainCore()

    try:
        brain.start()

        # Wait for tick data to flow (10 seconds)
        log.info("Waiting 10s for tick data to flow...")
        time.sleep(10)

        # Check if ticks received
        if not brain.latest_ticks:
            log.warning("No tick data received from cBot/EA - signals may use placeholder prices")
        else:
            log.info(f"Tick data received for: {list(brain.latest_ticks.keys())}")

        # Create test signal generator
        generator = TestSignalGenerator(brain)

        # Fire test signal
        log.info("="*60)
        log.info(f"Firing {args.mode} test signal...")
        log.info("="*60)

        if args.mode == 'entry_only':
            ticket = generator.fire_test_signal(
                pair=args.pair,
                direction=args.direction,
                mode='entry_only',
                lots=args.lots
            )
            if ticket:
                log.info(f"✅ Entry signal sent: Ticket #{ticket}")
                log.info(f"Position will stay open - close manually or use:")
                log.info(f"  python test_trade.py --ticket {ticket} --mode exit_only")
            else:
                log.error("❌ Entry signal failed")

        elif args.mode == 'full_cycle':
            log.info("Full cycle test will take 15 seconds (entry → modify → exit)")
            ticket = generator.fire_test_signal(
                pair=args.pair,
                direction=args.direction,
                mode='full_cycle',
                lots=args.lots
            )
            if ticket:
                log.info(f"✅ Full cycle test complete: Ticket #{ticket}")
            else:
                log.error("❌ Full cycle test failed")

        elif args.mode == 'exit_only':
            ticket = generator.fire_test_signal(
                pair=None,  # Not needed for exit
                direction=None,
                mode='exit_only',
                ticket=args.ticket
            )
            if ticket:
                log.info(f"✅ Exit signal sent: Ticket #{ticket}")
            else:
                log.error("❌ Exit signal failed")

        elif args.mode == 'modify_only':
            ticket = generator.fire_test_signal(
                pair=None,  # Not needed for modify
                direction=None,
                mode='modify_only',
                ticket=args.ticket
            )
            if ticket:
                log.info(f"✅ Modify signal sent: Ticket #{ticket}")
            else:
                log.error("❌ Modify signal failed")

        # Wait a bit for execution reports
        log.info("Waiting 5s for execution reports...")
        time.sleep(5)

        log.info("="*60)
        log.info("Test complete")
        log.info("="*60)

    except KeyboardInterrupt:
        log.info("\nInterrupted by user")
    except Exception as e:
        log.error(f"Error: {e}", exc_info=True)
    finally:
        brain.stop()


if __name__ == "__main__":
    main()
