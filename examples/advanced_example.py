#!/usr/bin/env python3
"""
Advanced Example: Full-featured WebSocket implementation

This example demonstrates:
- Threaded mode operation
- Multiple subscription modes
- Reconnection handling
- Order updates
- Advanced error handling
- Dynamic subscription management
"""

import os
import time
import logging
from kite_websocket import KiteWebSocket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Credentials
API_KEY = os.getenv("KITE_API_KEY", "your_api_key")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "your_access_token")

# Instrument groups
LTP_INSTRUMENTS = [256265, 408065]  # SBIN, INFY
QUOTE_INSTRUMENTS = [738561]  # RELIANCE
FULL_INSTRUMENTS = [895745]  # TCS


class AdvancedKiteClient:
    """Advanced Kite WebSocket client with additional features."""

    def __init__(self, api_key: str, access_token: str):
        self.api_key = api_key
        self.access_token = access_token
        self.tick_count = 0
        self.last_tick_time = None

        # Initialize WebSocket
        self.kws = KiteWebSocket(
            api_key=self.api_key,
            access_token=self.access_token,
            debug=False,
            reconnect=True,
            reconnect_max_tries=50,
            reconnect_max_delay=60
        )

        # Assign callbacks
        self.kws.on_ticks = self.on_ticks
        self.kws.on_connect = self.on_connect
        self.kws.on_close = self.on_close
        self.kws.on_error = self.on_error
        self.kws.on_reconnect = self.on_reconnect
        self.kws.on_noreconnect = self.on_noreconnect
        self.kws.on_order_update = self.on_order_update

    def on_ticks(self, ws, ticks):
        """Handle tick data."""
        self.tick_count += len(ticks)
        self.last_tick_time = time.time()

        for tick in ticks:
            mode = tick.get('mode', 'unknown')
            token = tick['instrument_token']
            ltp = tick.get('last_price', 0)

            if mode == 'ltp':
                logger.info(f"[LTP] Token: {token}, Price: {ltp:.2f}")

            elif mode == 'quote':
                logger.info(
                    f"[QUOTE] Token: {token}, "
                    f"LTP: {ltp:.2f}, "
                    f"Volume: {tick.get('volume', 0)}, "
                    f"Buy Qty: {tick.get('buy_quantity', 0)}, "
                    f"Sell Qty: {tick.get('sell_quantity', 0)}"
                )

            elif mode == 'full':
                ohlc = tick.get('ohlc', {})
                depth = tick.get('depth', {})
                logger.info(
                    f"[FULL] Token: {token}, "
                    f"LTP: {ltp:.2f}, "
                    f"Volume: {tick.get('volume', 0)}, "
                    f"Open: {ohlc.get('open', 0):.2f}, "
                    f"High: {ohlc.get('high', 0):.2f}, "
                    f"Low: {ohlc.get('low', 0):.2f}, "
                    f"Close: {ohlc.get('close', 0):.2f}, "
                    f"OI: {tick.get('oi', 0)}"
                )

                # Display market depth
                if depth:
                    logger.info(f"  Market Depth - Buy: {len(depth.get('buy', []))}, "
                                f"Sell: {len(depth.get('sell', []))}")

    def on_connect(self, ws, response):
        """Handle connection established."""
        logger.info("=" * 60)
        logger.info("Connected to Kite WebSocket!")
        logger.info("=" * 60)

        # Subscribe to different modes
        if LTP_INSTRUMENTS:
            logger.info(f"Subscribing to LTP mode: {LTP_INSTRUMENTS}")
            ws.subscribe(LTP_INSTRUMENTS)
            ws.set_mode(ws.MODE_LTP, LTP_INSTRUMENTS)

        if QUOTE_INSTRUMENTS:
            logger.info(f"Subscribing to QUOTE mode: {QUOTE_INSTRUMENTS}")
            ws.subscribe(QUOTE_INSTRUMENTS)
            ws.set_mode(ws.MODE_QUOTE, QUOTE_INSTRUMENTS)

        if FULL_INSTRUMENTS:
            logger.info(f"Subscribing to FULL mode: {FULL_INSTRUMENTS}")
            ws.subscribe(FULL_INSTRUMENTS)
            ws.set_mode(ws.MODE_FULL, FULL_INSTRUMENTS)

        logger.info("All subscriptions complete. Waiting for data...")

    def on_close(self, ws, code, reason):
        """Handle connection closed."""
        logger.warning(f"Connection closed: {code} - {reason}")
        logger.info(f"Total ticks received: {self.tick_count}")

    def on_error(self, ws, code, reason):
        """Handle errors."""
        logger.error(f"WebSocket error: {code} - {reason}")

    def on_reconnect(self, ws, attempts):
        """Handle reconnection attempts."""
        logger.warning(f"Attempting to reconnect (attempt {attempts})...")

    def on_noreconnect(self, ws):
        """Handle max reconnection attempts reached."""
        logger.error("Max reconnection attempts reached. Giving up.")
        logger.info(f"Total ticks received before disconnect: {self.tick_count}")

    def on_order_update(self, ws, data):
        """Handle order updates."""
        logger.info(f"Order update received: {data}")

    def start(self, threaded=True):
        """Start the WebSocket connection."""
        logger.info("Starting Kite WebSocket client in threaded mode...")
        self.kws.connect(threaded=threaded)

    def stop(self):
        """Stop the WebSocket connection."""
        logger.info("Stopping Kite WebSocket client...")
        self.kws.stop()

    def add_instruments(self, tokens, mode='ltp'):
        """
        Dynamically add instruments.

        Args:
            tokens: List of instrument tokens
            mode: Subscription mode (ltp, quote, full)
        """
        logger.info(f"Adding instruments: {tokens} with mode: {mode}")
        self.kws.subscribe(tokens)

        if mode == 'ltp':
            self.kws.set_mode(self.kws.MODE_LTP, tokens)
        elif mode == 'quote':
            self.kws.set_mode(self.kws.MODE_QUOTE, tokens)
        elif mode == 'full':
            self.kws.set_mode(self.kws.MODE_FULL, tokens)

    def remove_instruments(self, tokens):
        """
        Dynamically remove instruments.

        Args:
            tokens: List of instrument tokens
        """
        logger.info(f"Removing instruments: {tokens}")
        self.kws.unsubscribe(tokens)

    def get_stats(self):
        """Get client statistics."""
        return {
            "connected": self.kws.is_connected(),
            "tick_count": self.tick_count,
            "last_tick_time": self.last_tick_time,
            "subscribed_instruments": len(self.kws._subscribed_tokens)
        }


def main():
    """Main function."""
    logger.info("Initializing Advanced Kite WebSocket Client...")

    # Create client
    client = AdvancedKiteClient(API_KEY, ACCESS_TOKEN)

    # Start in threaded mode
    client.start(threaded=True)

    try:
        # Run for a while
        logger.info("Client is running. Press Ctrl+C to stop.")

        while True:
            time.sleep(10)

            # Print stats
            stats = client.get_stats()
            logger.info(f"Stats: {stats}")

            # Example: Dynamically add/remove instruments after 30 seconds
            if stats['tick_count'] > 10:
                # Example of dynamic subscription
                # client.add_instruments([1234567], mode='quote')
                pass

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user.")

    finally:
        # Cleanup
        client.stop()
        logger.info("Client stopped.")


if __name__ == "__main__":
    main()
