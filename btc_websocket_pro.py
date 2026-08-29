"""
WebSocket Handler for Real-Time Bitcoin Data - Delta Exchange
"""
import json
import threading
import time
from typing import Callable, Dict, Any, Optional
import websocket


class DeltaWebSocket:
    """Delta Exchange WebSocket client for real-time data"""

    def __init__(self, on_message_callback: Optional[Callable] = None):
        self.ws_url = "wss://socket.india.delta.exchange"
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_connected = False
        self.subscriptions = set()
        self.on_message_callback = on_message_callback
        self.reconnect_delay = 5
        self.thread: Optional[threading.Thread] = None

    def connect(self) -> None:
        """Connect to WebSocket"""
        if self.thread and self.thread.is_alive():
            return

        self.thread = threading.Thread(target=self._run_websocket, daemon=True)
        self.thread.start()

    def _run_websocket(self) -> None:
        """Run WebSocket connection"""
        while True:
            try:
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever()
            except Exception as e:
                print(f"WebSocket error: {e}")

            if not self.is_connected:
                break

            print(f"Reconnecting in {self.reconnect_delay} seconds...")
            time.sleep(self.reconnect_delay)

    def _on_open(self, ws) -> None:
        """Handle connection open"""
        print("✅ WebSocket connected to Delta Exchange")
        self.is_connected = True

        # Resubscribe to previous subscriptions
        for symbol in self.subscriptions:
            self._subscribe(symbol)

    def _on_message(self, ws, message: str) -> None:
        """Handle incoming message"""
        try:
            data = json.loads(message)

            # Call callback if provided
            if self.on_message_callback:
                self.on_message_callback(data)

        except json.JSONDecodeError:
            print(f"Failed to decode message: {message}")
        except Exception as e:
            print(f"Error processing message: {e}")

    def _on_error(self, ws, error) -> None:
        """Handle error"""
        print(f"❌ WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """Handle connection close"""
        print(f"⚠️ WebSocket closed: {close_status_code} - {close_msg}")
        self.is_connected = False

    def _subscribe(self, symbol: str) -> None:
        """Subscribe to a symbol"""
        if not self.ws or not self.is_connected:
            return

        subscribe_msg = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {
                        "name": "v2/ticker",
                        "symbols": [symbol]
                    }
                ]
            }
        }

        try:
            self.ws.send(json.dumps(subscribe_msg))
            print(f"📡 Subscribed to {symbol}")
        except Exception as e:
            print(f"Failed to subscribe to {symbol}: {e}")

    def subscribe(self, symbols: list) -> None:
        """Subscribe to multiple symbols"""
        for symbol in symbols:
            self.subscriptions.add(symbol)
            if self.is_connected:
                self._subscribe(symbol)

    def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from a symbol"""
        if symbol in self.subscriptions:
            self.subscriptions.remove(symbol)

        if not self.ws or not self.is_connected:
            return

        unsubscribe_msg = {
            "type": "unsubscribe",
            "payload": {
                "channels": [
                    {
                        "name": "v2/ticker",
                        "symbols": [symbol]
                    }
                ]
            }
        }

        try:
            self.ws.send(json.dumps(unsubscribe_msg))
            print(f"📡 Unsubscribed from {symbol}")
        except Exception as e:
            print(f"Failed to unsubscribe from {symbol}: {e}")

    def disconnect(self) -> None:
        """Disconnect WebSocket"""
        self.is_connected = False
        if self.ws:
            self.ws.close()
        print("WebSocket disconnected")


# Fallback: REST API based pseudo-realtime (if WebSocket not available)
class PseudoRealtimeHandler:
    """Fallback handler using REST API polling"""

    def __init__(self, api_handler, on_update_callback: Optional[Callable] = None):
        self.api_handler = api_handler
        self.on_update_callback = on_update_callback
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.symbols = set()
        self.update_interval = 10  # seconds

    def start(self) -> None:
        """Start polling"""
        if self.thread and self.thread.is_alive():
            return

        self.is_running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()

    def _poll_loop(self) -> None:
        """Polling loop"""
        while self.is_running:
            try:
                if self.symbols and self.on_update_callback:
                    # Fetch latest data
                    tickers = self.api_handler.fetch_tickers('BTC')

                    # Filter for subscribed symbols
                    updates = [
                        t for t in tickers
                        if t.get('symbol') in self.symbols
                    ]

                    if updates:
                        self.on_update_callback(updates)

            except Exception as e:
                print(f"Polling error: {e}")

            time.sleep(self.update_interval)

    def subscribe(self, symbols: list) -> None:
        """Subscribe to symbols"""
        self.symbols.update(symbols)

    def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from symbol"""
        self.symbols.discard(symbol)

    def stop(self) -> None:
        """Stop polling"""
        self.is_running = False
