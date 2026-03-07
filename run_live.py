"""
JcampFX — Run Live Trading System (Phase 4)

Starts the complete live trading pipeline with ZMQ bridge enabled.

Usage:
    python run_live.py

Requirements:
    - MT5 EA attached to chart with EnableTrading configured
    - FP Markets demo account active
"""

import logging
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.brain_orchestrator import BrainOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
log = logging.getLogger(__name__)


def main():
    """Run live trading system."""
    log.info("=" * 70)
    log.info("JcampFX Phase 4 Live Trading System")
    log.info("=" * 70)

    # Initialize orchestrator with ALL features enabled
    orchestrator = BrainOrchestrator(
        pairs=["EURUSD", "USDJPY", "AUDJPY", "USDCHF"],  # Phase 3.6 validated portfolio
        initial_equity=500.0,
        zmq_enabled=True,           # Enable ZMQ bridge
        load_historical_bars=True,  # Load historical data for DCRD
        dashboard_enabled=True,     # Enable web dashboard
        dashboard_port=8050,
    )

    try:
        # Start orchestrator
        orchestrator.start()

        log.info("\n" + "=" * 70)
        log.info("✅ System Running!")
        log.info("=" * 70)
        log.info("📊 Dashboard: http://localhost:8050")
        log.info("🔌 ZMQ Ports: 5555 (signals), 5556 (commands), 5557 (news)")
        log.info("=" * 70)
        log.info("\nWaiting for ticks from MT5...")
        log.info("Press Ctrl+C to stop\n")

        # Keep running (ZMQ threads handle everything)
        import time
        while True:
            time.sleep(60)  # Wake up every minute to check

    except KeyboardInterrupt:
        log.info("\nShutting down gracefully...")
        orchestrator.stop()
        log.info("System stopped")


if __name__ == "__main__":
    main()
