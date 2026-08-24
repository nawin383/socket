#!/usr/bin/env python3
"""
Server Example: Relay a single Kite WebSocket connection to multiple clients

This example demonstrates:
- Running a local relay server backed by one upstream Kite connection
- Multiple downstream clients sharing that single connection
- Downstream clients sending subscribe/unsubscribe/mode control messages
- Downstream clients receiving broadcasted tick data

Run the server:
    python examples/server_example.py

Then connect any number of WebSocket clients to ws://localhost:8765 and send:
    {"a": "subscribe", "v": [256265, 408065]}
    {"a": "mode", "v": ["full", [256265, 408065]]}
"""

import os
import logging
from kite_websocket import KiteWebSocketServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

API_KEY = os.getenv("KITE_API_KEY", "your_api_key")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "your_access_token")


def main():
    """Start the relay server (blocking)."""
    server = KiteWebSocketServer(
        api_key=API_KEY,
        access_token=ACCESS_TOKEN,
        host="localhost",
        port=8765,
    )

    print("Starting Kite WebSocket relay server on ws://localhost:8765 ...")
    server.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Shutting down...")
    except Exception as e:
        print(f"Error: {e}")
