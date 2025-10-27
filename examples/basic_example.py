#!/usr/bin/env python3
"""
Basic Example: Simple WebSocket connection and subscription

This example demonstrates:
- Connecting to Kite WebSocket
- Subscribing to instruments
- Receiving tick data
- Basic error handling
"""

import os
import logging
from kite_websocket import KiteWebSocket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Credentials (replace with your own or use environment variables)
API_KEY = os.getenv("KITE_API_KEY", "your_api_key")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "your_access_token")

# Instrument tokens (examples - replace with actual tokens)
INSTRUMENT_TOKENS = [
    256265,  # Example: SBIN
    408065,  # Example: INFY
    738561,  # Example: RELIANCE
]


def on_ticks(ws, ticks):
    """
    Callback for tick data.

    Args:
        ws: WebSocket instance
        ticks: List of tick data
    """
    for tick in ticks:
        print(f"Tick: Token={tick['instrument_token']}, "
              f"LTP={tick.get('last_price', 0):.2f}, "
              f"Volume={tick.get('volume', 0)}")


def on_connect(ws, response):
    """
    Callback when connection is established.

    Args:
        ws: WebSocket instance
        response: Connection response
    """
    print("Connected to Kite WebSocket!")

    # Subscribe to instruments
    print(f"Subscribing to {len(INSTRUMENT_TOKENS)} instruments...")
    ws.subscribe(INSTRUMENT_TOKENS)

    # Set mode to LTP (Last Traded Price)
    ws.set_mode(ws.MODE_LTP, INSTRUMENT_TOKENS)
    print("Subscription complete. Waiting for ticks...")


def on_close(ws, code, reason):
    """
    Callback when connection is closed.

    Args:
        ws: WebSocket instance
        code: Close code
        reason: Close reason
    """
    print(f"Connection closed: {code} - {reason}")


def on_error(ws, code, reason):
    """
    Callback for errors.

    Args:
        ws: WebSocket instance
        code: Error code
        reason: Error reason
    """
    print(f"Error: {code} - {reason}")


def main():
    """Main function to run the WebSocket client."""

    # Initialize WebSocket
    kws = KiteWebSocket(
        api_key=API_KEY,
        access_token=ACCESS_TOKEN,
        debug=False  # Set to True for verbose logging
    )

    # Assign callbacks
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.on_error = on_error

    # Start connection (blocking)
    print("Starting Kite WebSocket client...")
    kws.connect()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Closing connection...")
    except Exception as e:
        print(f"Error: {e}")
