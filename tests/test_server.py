"""
Unit tests for Kite WebSocket relay server
"""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from kite_websocket import KiteWebSocketServer


class TestKiteWebSocketServer(unittest.TestCase):
    """Test cases for KiteWebSocketServer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.server = KiteWebSocketServer(
            api_key="test_api_key",
            access_token="test_access_token",
            host="localhost",
            port=8765,
        )

    def test_initialization(self):
        """Test server initialization."""
        self.assertEqual(self.server.host, "localhost")
        self.assertEqual(self.server.port, 8765)
        self.assertEqual(len(self.server._clients), 0)
        self.assertIsNone(self.server._loop)

    def test_upstream_callbacks_wired(self):
        """Test that upstream KiteWebSocket callbacks are wired to the server."""
        self.assertEqual(self.server.kws.on_ticks, self.server._on_upstream_ticks)
        self.assertEqual(self.server.kws.on_connect, self.server._on_upstream_connect)
        self.assertEqual(self.server.kws.on_close, self.server._on_upstream_close)
        self.assertEqual(self.server.kws.on_error, self.server._on_upstream_error)

    def test_broadcast_noop_without_clients(self):
        """Broadcasting with no connected clients and no loop should be a no-op."""
        # Should not raise even though _loop is None
        self.server._broadcast({"type": "ticks", "data": []})

    def test_handle_client_message_subscribe(self):
        """Test that a subscribe control message calls through to KiteWebSocket."""
        self.server.kws.subscribe = MagicMock()
        websocket = MagicMock()

        asyncio.run(
            self.server._handle_client_message(
                websocket, json.dumps({"a": "subscribe", "v": [256265, 408065]})
            )
        )

        self.server.kws.subscribe.assert_called_once_with([256265, 408065])

    def test_handle_client_message_unsubscribe(self):
        """Test that an unsubscribe control message calls through to KiteWebSocket."""
        self.server.kws.unsubscribe = MagicMock()
        websocket = MagicMock()

        asyncio.run(
            self.server._handle_client_message(
                websocket, json.dumps({"a": "unsubscribe", "v": [256265]})
            )
        )

        self.server.kws.unsubscribe.assert_called_once_with([256265])

    def test_handle_client_message_mode(self):
        """Test that a mode control message calls through to KiteWebSocket."""
        self.server.kws.set_mode = MagicMock()
        websocket = MagicMock()

        asyncio.run(
            self.server._handle_client_message(
                websocket, json.dumps({"a": "mode", "v": ["full", [256265]]})
            )
        )

        self.server.kws.set_mode.assert_called_once_with("full", [256265])

    def test_handle_client_message_unknown_action_sends_error(self):
        """Test that an unknown action results in an error message to the client."""

        class FakeWebSocket:
            def __init__(self):
                self.sent = []

            async def send(self, message):
                self.sent.append(message)

        websocket = FakeWebSocket()

        asyncio.run(
            self.server._handle_client_message(
                websocket, json.dumps({"a": "bogus", "v": []})
            )
        )

        self.assertEqual(len(websocket.sent), 1)
        payload = json.loads(websocket.sent[0])
        self.assertEqual(payload["type"], "error")

    def test_broadcast_async_drops_failed_clients(self):
        """Clients whose send() raises should be removed from the client set."""

        class FakeWebSocket:
            def __init__(self, fail=False):
                self.fail = fail
                self.sent = []

            async def send(self, message):
                if self.fail:
                    raise ConnectionError("boom")
                self.sent.append(message)

        good_client = FakeWebSocket()
        bad_client = FakeWebSocket(fail=True)
        self.server._clients = {good_client, bad_client}

        asyncio.run(self.server._broadcast_async(json.dumps({"type": "ticks", "data": []})))

        self.assertIn(good_client, self.server._clients)
        self.assertNotIn(bad_client, self.server._clients)
        self.assertEqual(len(good_client.sent), 1)

    def test_on_upstream_ticks_broadcasts(self):
        """Test that upstream ticks trigger a broadcast call."""
        with patch.object(self.server, "_broadcast") as mock_broadcast:
            ticks = [{"instrument_token": 256265, "last_price": 100.0}]
            self.server._on_upstream_ticks(self.server.kws, ticks)
            mock_broadcast.assert_called_once_with({"type": "ticks", "data": ticks})


if __name__ == '__main__':
    unittest.main()
