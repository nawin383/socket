"""
Unit tests for Kite WebSocket client
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from kite_websocket import (
    KiteWebSocket,
    KiteWebSocketException,
    KiteConnectionError,
    KiteAuthenticationError,
    KiteSubscriptionError
)


class TestKiteWebSocket(unittest.TestCase):
    """Test cases for KiteWebSocket class."""

    def setUp(self):
        """Set up test fixtures."""
        self.api_key = "test_api_key"
        self.access_token = "test_access_token"
        self.kws = KiteWebSocket(
            api_key=self.api_key,
            access_token=self.access_token,
            reconnect=False
        )

    def test_initialization(self):
        """Test client initialization."""
        self.assertEqual(self.kws.api_key, self.api_key)
        self.assertEqual(self.kws.access_token, self.access_token)
        self.assertFalse(self.kws._is_connected)
        self.assertEqual(len(self.kws._subscribed_tokens), 0)

    def test_ws_url_generation(self):
        """Test WebSocket URL generation."""
        url = self.kws._get_ws_url()
        self.assertIn(self.api_key, url)
        self.assertIn(self.access_token, url)
        self.assertTrue(url.startswith("wss://"))

    def test_subscription_modes(self):
        """Test subscription mode constants."""
        self.assertEqual(self.kws.MODE_LTP, "ltp")
        self.assertEqual(self.kws.MODE_QUOTE, "quote")
        self.assertEqual(self.kws.MODE_FULL, "full")

    def test_subscribe_not_connected(self):
        """Test subscribe when not connected."""
        with self.assertRaises(KiteConnectionError):
            self.kws.subscribe([256265])

    def test_unsubscribe_not_connected(self):
        """Test unsubscribe when not connected."""
        with self.assertRaises(KiteConnectionError):
            self.kws.unsubscribe([256265])

    def test_set_mode_not_connected(self):
        """Test set_mode when not connected."""
        with self.assertRaises(KiteConnectionError):
            self.kws.set_mode(self.kws.MODE_LTP, [256265])

    def test_set_mode_invalid_mode(self):
        """Test set_mode with invalid mode."""
        self.kws._is_connected = True
        with self.assertRaises(KiteSubscriptionError):
            self.kws.set_mode("invalid_mode", [256265])

    @patch('kite_websocket.client.websocket.WebSocketApp')
    def test_subscribe_connected(self, mock_ws_app):
        """Test subscribe when connected."""
        # Mock WebSocket instance
        mock_ws = MagicMock()
        self.kws.ws = mock_ws
        self.kws._is_connected = True

        # Subscribe
        tokens = [256265, 408065]
        self.kws.subscribe(tokens)

        # Verify
        self.assertEqual(len(self.kws._subscribed_tokens), 2)
        self.assertTrue(all(t in self.kws._subscribed_tokens for t in tokens))
        mock_ws.send.assert_called_once()

    @patch('kite_websocket.client.websocket.WebSocketApp')
    def test_unsubscribe_connected(self, mock_ws_app):
        """Test unsubscribe when connected."""
        # Mock WebSocket instance
        mock_ws = MagicMock()
        self.kws.ws = mock_ws
        self.kws._is_connected = True

        # Add tokens first
        tokens = [256265, 408065]
        self.kws._subscribed_tokens.update(tokens)

        # Unsubscribe
        self.kws.unsubscribe([256265])

        # Verify
        self.assertEqual(len(self.kws._subscribed_tokens), 1)
        self.assertNotIn(256265, self.kws._subscribed_tokens)
        self.assertIn(408065, self.kws._subscribed_tokens)
        mock_ws.send.assert_called_once()

    @patch('kite_websocket.client.websocket.WebSocketApp')
    def test_set_mode_connected(self, mock_ws_app):
        """Test set_mode when connected."""
        # Mock WebSocket instance
        mock_ws = MagicMock()
        self.kws.ws = mock_ws
        self.kws._is_connected = True

        # Set mode
        tokens = [256265, 408065]
        self.kws.set_mode(self.kws.MODE_FULL, tokens)

        # Verify
        for token in tokens:
            self.assertEqual(self.kws._mode_map[token], self.kws.MODE_FULL)
        mock_ws.send.assert_called_once()

    def test_is_connected(self):
        """Test connection state check."""
        self.assertFalse(self.kws.is_connected())
        self.kws._is_connected = True
        self.assertTrue(self.kws.is_connected())

    def test_callbacks_assignment(self):
        """Test callback assignment."""
        # Define callbacks
        on_ticks = Mock()
        on_connect = Mock()
        on_close = Mock()
        on_error = Mock()

        # Assign callbacks
        self.kws.on_ticks = on_ticks
        self.kws.on_connect = on_connect
        self.kws.on_close = on_close
        self.kws.on_error = on_error

        # Verify
        self.assertEqual(self.kws.on_ticks, on_ticks)
        self.assertEqual(self.kws.on_connect, on_connect)
        self.assertEqual(self.kws.on_close, on_close)
        self.assertEqual(self.kws.on_error, on_error)

    def test_parse_binary_ltp(self):
        """Test parsing binary LTP data."""
        # Create mock LTP packet
        # 2 bytes: packet count (1)
        # 4 bytes: instrument token
        # 8 bytes: LTP data (4 bytes price + 4 bytes padding)
        import struct

        packet = struct.pack(">H", 1)  # 1 packet
        packet += struct.pack(">I", 256265)  # instrument token
        packet += struct.pack(">I", 125000)  # price * 100 = 1250.00
        packet += struct.pack(">I", 0)  # padding

        # Set mode
        self.kws._mode_map[256265] = self.kws.MODE_LTP

        # Parse
        ticks = self.kws._parse_binary(packet)

        # Verify
        self.assertEqual(len(ticks), 1)
        self.assertEqual(ticks[0]['instrument_token'], 256265)
        self.assertEqual(ticks[0]['last_price'], 1250.0)
        self.assertEqual(ticks[0]['mode'], 'ltp')

    def test_reconnection_settings(self):
        """Test reconnection configuration."""
        kws = KiteWebSocket(
            api_key="test",
            access_token="test",
            reconnect=True,
            reconnect_max_tries=50,
            reconnect_max_delay=60
        )

        self.assertTrue(kws.reconnect)
        self.assertEqual(kws.reconnect_max_tries, 50)
        self.assertEqual(kws.reconnect_max_delay, 60)


class TestExceptions(unittest.TestCase):
    """Test custom exceptions."""

    def test_base_exception(self):
        """Test base exception."""
        exc = KiteWebSocketException("Test error", code=500)
        self.assertEqual(exc.message, "Test error")
        self.assertEqual(exc.code, 500)

    def test_connection_error(self):
        """Test connection error."""
        exc = KiteConnectionError("Connection failed")
        self.assertIsInstance(exc, KiteWebSocketException)

    def test_authentication_error(self):
        """Test authentication error."""
        exc = KiteAuthenticationError("Auth failed")
        self.assertIsInstance(exc, KiteWebSocketException)

    def test_subscription_error(self):
        """Test subscription error."""
        exc = KiteSubscriptionError("Subscription failed")
        self.assertIsInstance(exc, KiteWebSocketException)


if __name__ == '__main__':
    unittest.main()
