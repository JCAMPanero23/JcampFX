"""
JcampFX — Dashboard Test

Quick test to verify the live dashboard works without MT5 connection.
"""

import logging
import time
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.brain_orchestrator import BrainOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
log = logging.getLogger(__name__)


def main():
    """Test dashboard functionality."""
    log.info("=" * 70)
    log.info("JcampFX Dashboard Test")
    log.info("=" * 70)

    # Initialize orchestrator with ZMQ disabled (test mode)
    orchestrator = BrainOrchestrator(
        pairs=["EURUSD", "USDJPY"],
        initial_equity=500.0,
        zmq_enabled=False,  # No MT5 connection needed
        load_historical_bars=False,  # Skip historical loading for quick test
        dashboard_enabled=True,
        dashboard_port=8050,
    )

    try:
        # Start orchestrator (will start dashboard)
        orchestrator.start()

        log.info("\n" + "=" * 70)
        log.info("✅ Dashboard is running!")
        log.info("=" * 70)
        log.info("🌐 Open your browser to: http://localhost:8050")
        log.info("=" * 70)
        log.info("\nPress Ctrl+C to stop...\n")

        # Keep running for dashboard testing
        while True:
            time.sleep(10)

            # Simulate some activity (for testing dashboard updates)
            log.info("Dashboard uptime: %.0f seconds",
                    (time.time() - orchestrator.start_time.timestamp()))

    except KeyboardInterrupt:
        log.info("\nShutting down...")
        orchestrator.stop()
        log.info("Dashboard test complete")


if __name__ == "__main__":
    main()
