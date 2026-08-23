"""
Kite WebSocket Relay Server

Maintains a single upstream connection to Kite's WebSocket API and
broadcasts tick data to any number of local downstream clients, so
multiple consumers can share one Kite connection.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

import websockets
from websockets.asyncio.server import Server, ServerConnection, serve

from .client import KiteWebSocket
from .exceptions import KiteSubscriptionError

logger = logging.getLogger(__name__)


def _tick_json_default(value: Any) -> str:
    """JSON fallback encoder for non-serializable tick fields (e.g. datetime)."""
    return str(value)


class KiteWebSocketServer:
    """
    Relay server that fans out a single Kite WebSocket connection to
    multiple local downstream clients over plain WebSocket connections.

    Downstream clients send JSON control messages identical in shape to
    the Kite protocol:
        {"a": "subscribe", "v": [256265, 408065]}
        {"a": "unsubscribe", "v": [256265]}
        {"a": "mode", "v": ["full", [256265]]}

    and receive JSON-encoded ticks as they arrive from upstream:
        {"type": "ticks", "data": [...]}
    """

    def __init__(
        self,
        api_key: str,
        access_token: str,
        host: str = "localhost",
        port: int = 8765,
        **kws_kwargs: Any,
    ):
        """
        Args:
            api_key: Kite API key
            access_token: User access token
            host: Host to bind the local relay server to
            port: Port to bind the local relay server to
            **kws_kwargs: Extra keyword arguments forwarded to KiteWebSocket
        """
        self.host = host
        self.port = port

        self.kws = KiteWebSocket(api_key, access_token, **kws_kwargs)
        self.kws.on_ticks = self._on_upstream_ticks
        self.kws.on_connect = self._on_upstream_connect
        self.kws.on_close = self._on_upstream_close
        self.kws.on_error = self._on_upstream_error

        self._clients: Set[ServerConnection] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Optional[Server] = None

    def start(self, threaded: bool = False):
        """
        Start the upstream Kite connection and the local relay server.

        Args:
            threaded: Run the relay server in a background thread instead
                of blocking the calling thread.
        """
        self.kws.connect(threaded=True)

        if threaded:
            import threading

            thread = threading.Thread(target=lambda: asyncio.run(self._serve()))
            thread.daemon = True
            thread.start()
        else:
            asyncio.run(self._serve())

    def stop(self):
        """Stop the upstream connection and the relay server."""
        self.kws.stop()
        if self._server is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._server.close)

    async def _serve(self):
        self._loop = asyncio.get_running_loop()
        async with serve(self._handle_client, self.host, self.port) as server:
            self._server = server
            logger.info(f"Kite WebSocket relay server listening on ws://{self.host}:{self.port}")
            await server.wait_closed()

    async def _handle_client(self, websocket: ServerConnection):
        self._clients.add(websocket)
        logger.info(f"Client connected ({len(self._clients)} total)")

        try:
            async for message in websocket:
                await self._handle_client_message(websocket, message)
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info(f"Client disconnected ({len(self._clients)} total)")

    async def _handle_client_message(self, websocket: ServerConnection, message: str):
        try:
            data = json.loads(message)
            action = data.get("a")
            value = data.get("v")

            if action == "subscribe":
                self.kws.subscribe(value)
            elif action == "unsubscribe":
                self.kws.unsubscribe(value)
            elif action == "mode":
                mode, tokens = value
                self.kws.set_mode(mode, tokens)
            else:
                raise KiteSubscriptionError(f"Unknown action: {action}")
        except Exception as e:
            logger.error(f"Error handling client message: {e}")
            await websocket.send(json.dumps({"type": "error", "data": str(e)}))

    def _on_upstream_ticks(self, ws: KiteWebSocket, ticks: list):
        self._broadcast({"type": "ticks", "data": ticks})

    def _on_upstream_connect(self, ws: KiteWebSocket, response: Any):
        self._broadcast({"type": "connect", "data": response})

    def _on_upstream_close(self, ws: KiteWebSocket, code: Any, reason: Any):
        self._broadcast({"type": "close", "data": {"code": code, "reason": reason}})

    def _on_upstream_error(self, ws: KiteWebSocket, code: Any, reason: Any):
        self._broadcast({"type": "error", "data": {"code": code, "reason": reason}})

    def _broadcast(self, payload: Dict[str, Any]):
        if not self._clients or self._loop is None:
            return

        message = json.dumps(payload, default=_tick_json_default)
        asyncio.run_coroutine_threadsafe(self._broadcast_async(message), self._loop)

    async def _broadcast_async(self, message: str):
        clients = list(self._clients)
        if not clients:
            return

        results = await asyncio.gather(
            *(client.send(message) for client in clients),
            return_exceptions=True,
        )
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                logger.debug(f"Failed to send to client: {result}")
                self._clients.discard(client)
