"""
Live tick feed for spot + the currently-held CE leg, built on this repo's
own kite_websocket.KiteWebSocket client (rather than pulling in a second
ticker implementation) so roll decisions react to real-time prices instead
of only polling.
"""

import logging

from kite_websocket import KiteWebSocket

logger = logging.getLogger(__name__)


class TickerFeed:
    def __init__(self, api_key: str, access_token: str, on_ticks):
        self.kws = KiteWebSocket(api_key=api_key, access_token=access_token, reconnect=True)
        self.kws.on_ticks = lambda ws, ticks: on_ticks(ticks)
        self.kws.on_connect = self._on_connect
        self._tokens = set()

    def _on_connect(self, ws, response):
        logger.info("Ticker connected")
        if self._tokens:
            ws.subscribe(list(self._tokens))
            ws.set_mode(ws.MODE_LTP, list(self._tokens))

    def start(self):
        self.kws.connect(threaded=True)

    def stop(self):
        self.kws.stop()

    def set_tokens(self, tokens):
        new_tokens = set(tokens)
        added = new_tokens - self._tokens
        removed = self._tokens - new_tokens
        self._tokens = new_tokens
        if not self.kws.is_connected():
            return
        if removed:
            self.kws.unsubscribe(list(removed))
        if added:
            self.kws.subscribe(list(added))
            self.kws.set_mode(self.kws.MODE_LTP, list(added))
