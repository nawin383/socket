"""
Kite WebSocket Client Implementation
"""

import struct
import json
import logging
import time
from threading import Thread, Event
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional

import websocket
from six.moves.urllib.parse import urljoin

from .exceptions import (
    KiteWebSocketException,
    KiteConnectionError,
    KiteAuthenticationError,
    KiteSubscriptionError,
    KiteDataError
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KiteWebSocket:
    """
    Kite WebSocket client for streaming real-time market data.

    Attributes:
        ROOT_URI: WebSocket server URI
        MODE_LTP: Last traded price mode
        MODE_QUOTE: Market depth quote mode
        MODE_FULL: Full market data mode
    """

    # WebSocket endpoint
    ROOT_URI = "wss://ws.kite.trade/"

    # Subscription modes
    MODE_LTP = "ltp"
    MODE_QUOTE = "quote"
    MODE_FULL = "full"

    # Message types
    _MESSAGE_CONNECT = "connect"
    _MESSAGE_SUBSCRIBE = "subscribe"
    _MESSAGE_UNSUBSCRIBE = "unsubscribe"
    _MESSAGE_SETMODE = "mode"

    def __init__(
        self,
        api_key: str,
        access_token: str,
        debug: bool = False,
        reconnect: bool = True,
        reconnect_max_tries: int = 30,
        reconnect_max_delay: int = 60,
        connect_timeout: int = 30,
    ):
        """
        Initialize Kite WebSocket client.

        Args:
            api_key: Kite API key
            access_token: User access token
            debug: Enable debug logging
            reconnect: Enable auto-reconnection
            reconnect_max_tries: Maximum reconnection attempts
            reconnect_max_delay: Maximum delay between reconnections (seconds)
            connect_timeout: Connection timeout (seconds)
        """
        self.api_key = api_key
        self.access_token = access_token
        self.debug = debug
        self.reconnect = reconnect
        self.reconnect_max_tries = reconnect_max_tries
        self.reconnect_max_delay = reconnect_max_delay
        self.connect_timeout = connect_timeout

        # WebSocket instance
        self.ws: Optional[websocket.WebSocketApp] = None

        # Connection state
        self._is_connected = False
        self._reconnect_count = 0
        self._stop_event = Event()

        # Subscribed instruments
        self._subscribed_tokens: set = set()
        self._mode_map: Dict[int, str] = {}

        # Callbacks
        self.on_ticks: Optional[Callable] = None
        self.on_connect: Optional[Callable] = None
        self.on_close: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_reconnect: Optional[Callable] = None
        self.on_noreconnect: Optional[Callable] = None
        self.on_message: Optional[Callable] = None
        self.on_order_update: Optional[Callable] = None

        # Set logging level
        if debug:
            logger.setLevel(logging.DEBUG)
            websocket.enableTrace(True)

    def connect(self, threaded: bool = False, disable_ssl_verification: bool = False):
        """
        Establish WebSocket connection.

        Args:
            threaded: Run in background thread
            disable_ssl_verification: Disable SSL certificate verification
        """
        # Build WebSocket URL
        url = self._get_ws_url()

        # Create WebSocket app
        self.ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_close=self._on_close,
            on_error=self._on_error,
            on_ping=self._on_ping,
            on_pong=self._on_pong,
        )

        # SSL options
        ssl_opts = {}
        if disable_ssl_verification:
            ssl_opts = {"cert_reqs": 0}

        # Run connection
        if threaded:
            self._ws_thread = Thread(target=self._run_forever, args=(ssl_opts,))
            self._ws_thread.daemon = True
            self._ws_thread.start()
        else:
            self._run_forever(ssl_opts)

    def _run_forever(self, ssl_opts: dict):
        """Run WebSocket connection loop."""
        while not self._stop_event.is_set():
            try:
                self.ws.run_forever(
                    ping_interval=3,
                    ping_timeout=2,
                    sslopt=ssl_opts
                )

                # If we get here, connection closed
                if not self._stop_event.is_set() and self.reconnect:
                    self._attempt_reconnect()
                else:
                    break

            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                if not self._stop_event.is_set() and self.reconnect:
                    self._attempt_reconnect()
                else:
                    break

    def _attempt_reconnect(self):
        """Attempt to reconnect with exponential backoff."""
        self._reconnect_count += 1

        if self._reconnect_count > self.reconnect_max_tries:
            logger.error("Max reconnection attempts reached")
            if self.on_noreconnect:
                try:
                    self.on_noreconnect(self)
                except Exception as e:
                    logger.error(f"Error in on_noreconnect callback: {e}")
            return

        # Calculate backoff delay
        delay = min(
            2 ** self._reconnect_count,
            self.reconnect_max_delay
        )

        logger.info(f"Reconnecting in {delay} seconds (attempt {self._reconnect_count})")

        if self.on_reconnect:
            try:
                self.on_reconnect(self, self._reconnect_count)
            except Exception as e:
                logger.error(f"Error in on_reconnect callback: {e}")

        time.sleep(delay)

    def _get_ws_url(self) -> str:
        """Build WebSocket URL with authentication."""
        return f"{self.ROOT_URI}?api_key={self.api_key}&access_token={self.access_token}"

    def _on_open(self, ws):
        """Handle WebSocket connection open."""
        logger.info("WebSocket connection established")
        self._is_connected = True
        self._reconnect_count = 0

        if self.on_connect:
            try:
                self.on_connect(self, None)
            except Exception as e:
                logger.error(f"Error in on_connect callback: {e}")

        # Resubscribe to instruments if reconnecting
        if self._subscribed_tokens:
            logger.info(f"Resubscribing to {len(self._subscribed_tokens)} instruments")
            self.subscribe(list(self._subscribed_tokens))

            # Restore modes
            for mode in [self.MODE_LTP, self.MODE_QUOTE, self.MODE_FULL]:
                tokens = [t for t, m in self._mode_map.items() if m == mode]
                if tokens:
                    self.set_mode(mode, tokens)

    def _on_message(self, ws, message):
        """Handle incoming WebSocket message."""
        try:
            if self.on_message:
                self.on_message(self, message)

            # Parse binary message
            if isinstance(message, bytes):
                ticks = self._parse_binary(message)
                if ticks and self.on_ticks:
                    self.on_ticks(self, ticks)

            # Parse text message
            elif isinstance(message, str):
                data = json.loads(message)

                # Handle order updates
                if data.get("type") == "order":
                    if self.on_order_update:
                        self.on_order_update(self, data.get("data"))

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if self.on_error:
                self.on_error(self, None, str(e))

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection close."""
        logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
        self._is_connected = False

        if self.on_close:
            try:
                self.on_close(self, close_status_code, close_msg)
            except Exception as e:
                logger.error(f"Error in on_close callback: {e}")

    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        logger.error(f"WebSocket error: {error}")

        if self.on_error:
            try:
                self.on_error(self, None, str(error))
            except Exception as e:
                logger.error(f"Error in on_error callback: {e}")

    def _on_ping(self, ws, message):
        """Handle ping from server."""
        logger.debug("Received ping")

    def _on_pong(self, ws, message):
        """Handle pong from server."""
        logger.debug("Received pong")

    def subscribe(self, instrument_tokens: List[int]):
        """
        Subscribe to instruments.

        Args:
            instrument_tokens: List of instrument tokens to subscribe
        """
        if not self._is_connected:
            raise KiteConnectionError("Not connected to WebSocket")

        if not instrument_tokens:
            return

        # Update subscribed tokens
        self._subscribed_tokens.update(instrument_tokens)

        # Send subscribe message
        message = {
            "a": self._MESSAGE_SUBSCRIBE,
            "v": instrument_tokens
        }

        try:
            self.ws.send(json.dumps(message))
            logger.info(f"Subscribed to {len(instrument_tokens)} instruments")
        except Exception as e:
            raise KiteSubscriptionError(f"Failed to subscribe: {e}")

    def unsubscribe(self, instrument_tokens: List[int]):
        """
        Unsubscribe from instruments.

        Args:
            instrument_tokens: List of instrument tokens to unsubscribe
        """
        if not self._is_connected:
            raise KiteConnectionError("Not connected to WebSocket")

        if not instrument_tokens:
            return

        # Update subscribed tokens
        self._subscribed_tokens.difference_update(instrument_tokens)

        # Remove from mode map
        for token in instrument_tokens:
            self._mode_map.pop(token, None)

        # Send unsubscribe message
        message = {
            "a": self._MESSAGE_UNSUBSCRIBE,
            "v": instrument_tokens
        }

        try:
            self.ws.send(json.dumps(message))
            logger.info(f"Unsubscribed from {len(instrument_tokens)} instruments")
        except Exception as e:
            raise KiteSubscriptionError(f"Failed to unsubscribe: {e}")

    def set_mode(self, mode: str, instrument_tokens: List[int]):
        """
        Set streaming mode for instruments.

        Args:
            mode: Subscription mode (MODE_LTP, MODE_QUOTE, MODE_FULL)
            instrument_tokens: List of instrument tokens
        """
        if not self._is_connected:
            raise KiteConnectionError("Not connected to WebSocket")

        if mode not in [self.MODE_LTP, self.MODE_QUOTE, self.MODE_FULL]:
            raise KiteSubscriptionError(f"Invalid mode: {mode}")

        if not instrument_tokens:
            return

        # Update mode map
        for token in instrument_tokens:
            self._mode_map[token] = mode

        # Send mode change message
        message = {
            "a": self._MESSAGE_SETMODE,
            "v": [mode, instrument_tokens]
        }

        try:
            self.ws.send(json.dumps(message))
            logger.info(f"Set mode {mode} for {len(instrument_tokens)} instruments")
        except Exception as e:
            raise KiteSubscriptionError(f"Failed to set mode: {e}")

    def resubscribe(self):
        """Resubscribe to all instruments."""
        if self._subscribed_tokens:
            self.subscribe(list(self._subscribed_tokens))

    def close(self, code: int = 1000, reason: str = ""):
        """
        Close WebSocket connection.

        Args:
            code: Close status code
            reason: Close reason
        """
        if self.ws:
            logger.info("Closing WebSocket connection")
            self.ws.close()
            self._is_connected = False

    def stop(self):
        """Stop WebSocket connection and cleanup."""
        logger.info("Stopping WebSocket client")
        self._stop_event.set()
        self.close()

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._is_connected

    def _parse_binary(self, data: bytes) -> List[Dict[str, Any]]:
        """
        Parse binary tick data.

        Args:
            data: Binary data from WebSocket

        Returns:
            List of parsed tick dictionaries
        """
        ticks = []

        try:
            # Number of packets
            count = struct.unpack(">H", data[:2])[0]
            offset = 2

            for _ in range(count):
                if offset >= len(data):
                    break

                # Parse instrument token
                instrument_token = struct.unpack(">I", data[offset:offset + 4])[0]
                offset += 4

                # Determine packet size based on mode
                mode = self._mode_map.get(instrument_token, self.MODE_FULL)

                tick = {"instrument_token": instrument_token, "mode": mode}

                # Parse based on mode
                if mode == self.MODE_LTP:
                    # LTP: 8 bytes
                    tick["last_price"] = struct.unpack(">I", data[offset:offset + 4])[0] / 100.0
                    offset += 8

                elif mode == self.MODE_QUOTE:
                    # Quote: 44 bytes
                    tick["last_price"] = struct.unpack(">I", data[offset:offset + 4])[0] / 100.0
                    tick["last_quantity"] = struct.unpack(">I", data[offset + 4:offset + 8])[0]
                    tick["average_price"] = struct.unpack(">I", data[offset + 8:offset + 12])[0] / 100.0
                    tick["volume"] = struct.unpack(">I", data[offset + 12:offset + 16])[0]
                    tick["buy_quantity"] = struct.unpack(">I", data[offset + 16:offset + 20])[0]
                    tick["sell_quantity"] = struct.unpack(">I", data[offset + 20:offset + 24])[0]

                    # OHLC
                    tick["ohlc"] = {
                        "open": struct.unpack(">I", data[offset + 24:offset + 28])[0] / 100.0,
                        "high": struct.unpack(">I", data[offset + 28:offset + 32])[0] / 100.0,
                        "low": struct.unpack(">I", data[offset + 32:offset + 36])[0] / 100.0,
                        "close": struct.unpack(">I", data[offset + 36:offset + 40])[0] / 100.0,
                    }
                    offset += 44

                elif mode == self.MODE_FULL:
                    # Full: 184 bytes
                    tick["last_price"] = struct.unpack(">I", data[offset:offset + 4])[0] / 100.0
                    tick["last_quantity"] = struct.unpack(">I", data[offset + 4:offset + 8])[0]
                    tick["average_price"] = struct.unpack(">I", data[offset + 8:offset + 12])[0] / 100.0
                    tick["volume"] = struct.unpack(">I", data[offset + 12:offset + 16])[0]
                    tick["buy_quantity"] = struct.unpack(">I", data[offset + 16:offset + 20])[0]
                    tick["sell_quantity"] = struct.unpack(">I", data[offset + 20:offset + 24])[0]

                    # OHLC
                    tick["ohlc"] = {
                        "open": struct.unpack(">I", data[offset + 24:offset + 28])[0] / 100.0,
                        "high": struct.unpack(">I", data[offset + 28:offset + 32])[0] / 100.0,
                        "low": struct.unpack(">I", data[offset + 32:offset + 36])[0] / 100.0,
                        "close": struct.unpack(">I", data[offset + 36:offset + 40])[0] / 100.0,
                    }

                    # Change
                    tick["change"] = struct.unpack(">I", data[offset + 40:offset + 44])[0] / 100.0

                    # Timestamp
                    timestamp = struct.unpack(">I", data[offset + 44:offset + 48])[0]
                    tick["timestamp"] = datetime.fromtimestamp(timestamp)

                    # OI (Open Interest)
                    tick["oi"] = struct.unpack(">I", data[offset + 48:offset + 52])[0]
                    tick["oi_day_high"] = struct.unpack(">I", data[offset + 52:offset + 56])[0]
                    tick["oi_day_low"] = struct.unpack(">I", data[offset + 56:offset + 60])[0]

                    # Market depth
                    depth_offset = offset + 60
                    tick["depth"] = {"buy": [], "sell": []}

                    # Top 5 buy orders
                    for i in range(5):
                        tick["depth"]["buy"].append({
                            "quantity": struct.unpack(">I", data[depth_offset:depth_offset + 4])[0],
                            "price": struct.unpack(">I", data[depth_offset + 4:depth_offset + 8])[0] / 100.0,
                            "orders": struct.unpack(">H", data[depth_offset + 8:depth_offset + 10])[0],
                        })
                        depth_offset += 12

                    # Top 5 sell orders
                    for i in range(5):
                        tick["depth"]["sell"].append({
                            "quantity": struct.unpack(">I", data[depth_offset:depth_offset + 4])[0],
                            "price": struct.unpack(">I", data[depth_offset + 4:depth_offset + 8])[0] / 100.0,
                            "orders": struct.unpack(">H", data[depth_offset + 8:depth_offset + 10])[0],
                        })
                        depth_offset += 12

                    offset += 184

                ticks.append(tick)

        except Exception as e:
            logger.error(f"Error parsing binary data: {e}")
            raise KiteDataError(f"Failed to parse tick data: {e}")

        return ticks
