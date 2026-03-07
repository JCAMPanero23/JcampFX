"""
JcampFX — Phase 4 ZMQ Bridge (Python Side)

Receives tick data from MT5 EA via ZMQ and sends trading signals back.

Architecture:
- Port 5555 (PULL): Receive tick data from MT5
- Port 5556 (PUB): Send trading signals to MT5
- Port 5557 (PULL): Receive news events from MT5

Threading model:
- Main thread: Signal generation + trade management
- Listener threads: ZMQ message reception (non-blocking)
"""

import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable

import zmq

log = logging.getLogger(__name__)


@dataclass
class TickData:
    """Tick data received from MT5."""
    symbol: str
    time: datetime
    bid: float
    ask: float
    last: float
    volume: int
    flags: int


@dataclass
class TradingSignal:
    """Trading signal to send to MT5."""
    type: str  # "entry", "exit", "modify"
    symbol: str
    direction: Optional[str] = None  # "BUY" or "SELL"
    sl: Optional[float] = None
    tp: Optional[float] = None
    lots: Optional[float] = None
    ticket: Optional[int] = None  # For exit/modify


class ZMQBridge:
    """
    ZMQ bridge between Python Brain and MT5 EA.

    Handles bidirectional communication:
    - Receives tick data, bar closes, news events from MT5
    - Sends trading signals (entry/exit/modify) to MT5
    """

    def __init__(
        self,
        signal_port: int = 5555,
        command_port: int = 5556,
        news_port: int = 5557,
        tick_callback: Optional[Callable] = None,
        command_callback: Optional[Callable] = None,
    ):
        """
        Initialize ZMQ bridge.

        Args:
            signal_port: Port for receiving signals from MT5 (PULL)
            command_port: Port for sending commands to MT5 (PUB)
            news_port: Port for receiving news events from MT5 (PULL)
            tick_callback: Function to call on each tick: tick_callback(TickData)
            command_callback: Function to call on each command: command_callback(dict)
        """
        self.signal_port = signal_port
        self.command_port = command_port
        self.news_port = news_port

        self.tick_callback = tick_callback
        self.command_callback = command_callback

        # ZMQ context and sockets
        self.context = None
        self.signal_socket = None  # PULL from MT5 (tick data)
        self.command_socket = None  # PUB to MT5 (trading signals)
        self.news_socket = None  # PULL from MT5 (news events)

        # State
        self.running = False
        self.threads: List[threading.Thread] = []
        self.last_heartbeat = None

        # Statistics
        self.ticks_received = defaultdict(int)
        self.commands_sent = 0
        self.start_time = None

    def start(self):
        """Start ZMQ bridge and listener threads."""
        if self.running:
            log.warning("ZMQ bridge already running")
            return

        log.info("Starting ZMQ bridge...")

        # Create ZMQ context
        self.context = zmq.Context()

        # Signal socket (PULL) - receive tick data from MT5
        self.signal_socket = self.context.socket(zmq.PULL)
        self.signal_socket.bind(f"tcp://*:{self.signal_port}")
        self.signal_socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout
        log.info(f"Signal socket bound to port {self.signal_port} (PULL)")

        # Command socket (PUB) - send trading signals to MT5
        self.command_socket = self.context.socket(zmq.PUB)
        self.command_socket.bind(f"tcp://*:{self.command_port}")
        log.info(f"Command socket bound to port {self.command_port} (PUB)")

        # News socket (PULL) - receive news events from MT5
        self.news_socket = self.context.socket(zmq.PULL)
        self.news_socket.bind(f"tcp://*:{self.news_port}")
        self.news_socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout
        log.info(f"News socket bound to port {self.news_port} (PULL)")

        self.running = True
        self.start_time = datetime.now()

        # Start listener threads
        signal_thread = threading.Thread(target=self._signal_listener, daemon=True, name="ZMQ-Signal")
        news_thread = threading.Thread(target=self._news_listener, daemon=True, name="ZMQ-News")

        signal_thread.start()
        news_thread.start()

        self.threads = [signal_thread, news_thread]

        log.info("ZMQ bridge started successfully")

    def stop(self):
        """Stop ZMQ bridge and close sockets."""
        if not self.running:
            return

        log.info("Stopping ZMQ bridge...")
        self.running = False

        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=2.0)

        # Close sockets
        if self.signal_socket:
            self.signal_socket.close()
        if self.command_socket:
            self.command_socket.close()
        if self.news_socket:
            self.news_socket.close()

        # Terminate context
        if self.context:
            self.context.term()

        log.info("ZMQ bridge stopped")

    def _signal_listener(self):
        """Listen for signals from MT5 (tick data, bar closes, heartbeats)."""
        log.info("Signal listener thread started")

        while self.running:
            try:
                # Non-blocking receive with timeout
                message = self.signal_socket.recv_string()

                # Parse JSON
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "tick":
                    self._handle_tick(data)
                elif msg_type == "bar":
                    self._handle_bar(data)
                elif msg_type == "heartbeat":
                    self._handle_heartbeat(data)
                elif msg_type == "execution_report":
                    self._handle_execution_report(data)
                elif msg_type == "news_event":
                    self._handle_news_event(data)
                elif msg_type == "news_update_complete":
                    self._handle_news_update_complete(data)
                else:
                    log.warning(f"Unknown signal type: {msg_type}")

            except zmq.Again:
                # Timeout, no message available
                continue
            except json.JSONDecodeError as e:
                log.error(f"JSON decode error: {e}")
            except Exception as e:
                log.error(f"Signal listener error: {e}", exc_info=True)

        log.info("Signal listener thread stopped")

    def _news_listener(self):
        """Listen for news events from MT5."""
        log.info("News listener thread started")

        while self.running:
            try:
                # Non-blocking receive with timeout
                message = self.news_socket.recv_string()

                # Parse JSON
                data = json.loads(message)
                log.info(f"News event received: {data}")

                # TODO: Handle news event (add to news gating system)

            except zmq.Again:
                # Timeout, no message available
                continue
            except json.JSONDecodeError as e:
                log.error(f"JSON decode error: {e}")
            except Exception as e:
                log.error(f"News listener error: {e}", exc_info=True)

        log.info("News listener thread stopped")

    def _handle_tick(self, data: dict):
        """Handle incoming tick data."""
        # Import here to avoid circular dependency
        try:
            from .config import strip_broker_suffix
        except ImportError:
            # Fallback for direct script execution
            from config import strip_broker_suffix

        # Strip broker suffix (MT5 ".r" or cTrader suffix)
        symbol_raw = data["symbol"]
        symbol_canonical = strip_broker_suffix(symbol_raw)

        self.ticks_received[symbol_canonical] += 1

        # Convert to TickData object (use canonical name)
        tick = TickData(
            symbol=symbol_canonical,
            time=datetime.fromtimestamp(data["time"]),
            bid=data["bid"],
            ask=data["ask"],
            last=data["last"],
            volume=data["volume"],
            flags=data["flags"],
        )

        # Call user callback if provided
        if self.tick_callback:
            try:
                self.tick_callback(tick)
            except Exception as e:
                log.error(f"Tick callback error: {e}", exc_info=True)

    def _handle_bar(self, data: dict):
        """Handle Range Bar close event."""
        log.info(f"Range Bar close: {data['symbol']} @ {data['close']}")
        # TODO: Trigger strategy analysis on bar close

    def _handle_heartbeat(self, data: dict):
        """Handle heartbeat from MT5."""
        self.last_heartbeat = datetime.fromtimestamp(data["time"])

    def _handle_execution_report(self, data: dict):
        """Handle execution report from MT5."""
        success = data.get("success", False)
        symbol = data.get("symbol", "")
        direction = data.get("direction", "")
        ticket = data.get("ticket", 0)
        price = data.get("price", 0.0)
        retcode = data.get("retcode", 0)

        if success:
            log.info(
                "Execution report: SUCCESS - %s %s Ticket #%d @ %.5f",
                symbol, direction, ticket, price
            )
        else:
            log.error(
                "Execution report: FAILED - %s %s (retcode=%d)",
                symbol, direction, retcode
            )

        # Call user callback if provided
        if self.command_callback:
            try:
                self.command_callback(data)
            except Exception as e:
                log.error(f"Execution report callback error: {e}", exc_info=True)

    def _handle_news_event(self, data: dict):
        """Handle news event from MT5 calendar."""
        currency = data.get("currency", "")
        event_name = data.get("event_name", "")
        time = datetime.fromtimestamp(data.get("time", 0))
        importance = data.get("importance", 0)

        log.info(
            "News event: %s @ %s - %s (importance=%d)",
            currency, time, event_name, importance
        )

        # Store for news layer (via callback)
        if self.command_callback:
            try:
                self.command_callback(data)
            except Exception as e:
                log.error(f"News event callback error: {e}", exc_info=True)

    def _handle_news_update_complete(self, data: dict):
        """Handle news update completion marker."""
        count = data.get("count", 0)
        log.info("News update complete: %d events received", count)

    def send_signal(self, signal: TradingSignal):
        """
        Send trading signal to MT5.

        Args:
            signal: TradingSignal object (entry, exit, or modify)
        """
        if not self.running:
            log.error("Cannot send signal: ZMQ bridge not running")
            return False

        # Convert to JSON
        signal_dict = {
            "type": signal.type,
            "symbol": signal.symbol,
        }

        if signal.direction:
            signal_dict["direction"] = signal.direction
        if signal.sl is not None:
            signal_dict["sl"] = signal.sl
        if signal.tp is not None:
            signal_dict["tp"] = signal.tp
        if signal.lots is not None:
            signal_dict["lots"] = signal.lots
        if signal.ticket is not None:
            signal_dict["ticket"] = signal.ticket

        message = json.dumps(signal_dict)

        try:
            self.command_socket.send_string(message)
            self.commands_sent += 1
            log.info(f"Signal sent: {signal.type} {signal.symbol}")
            return True
        except Exception as e:
            log.error(f"Failed to send signal: {e}")
            return False

    def get_stats(self) -> dict:
        """Get bridge statistics."""
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

        return {
            "running": self.running,
            "uptime_seconds": uptime,
            "ticks_received": dict(self.ticks_received),
            "total_ticks": sum(self.ticks_received.values()),
            "commands_sent": self.commands_sent,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


def main():
    """Test ZMQ bridge standalone."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    def on_tick(tick: TickData):
        print(f"Tick: {tick.symbol} Bid={tick.bid:.5f} Ask={tick.ask:.5f}")

    with ZMQBridge(tick_callback=on_tick) as bridge:
        print("ZMQ Bridge test mode - Press Ctrl+C to exit")
        print(f"Listening on ports: {bridge.signal_port}, {bridge.command_port}, {bridge.news_port}")

        try:
            while True:
                time.sleep(10)
                stats = bridge.get_stats()
                print(f"\nStats: {stats['total_ticks']} ticks received, {stats['commands_sent']} commands sent")
        except KeyboardInterrupt:
            print("\nShutting down...")


if __name__ == "__main__":
    main()
