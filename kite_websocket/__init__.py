"""
Kite WebSocket Python Client

A robust Python client for connecting to Zerodha Kite's WebSocket API
for real-time market data streaming.
"""

from .client import KiteWebSocket
from .exceptions import (
    KiteWebSocketException,
    KiteConnectionError,
    KiteAuthenticationError,
    KiteSubscriptionError,
    KiteReconnectionError
)
from . import utils

__version__ = "1.0.0"
__all__ = [
    "KiteWebSocket",
    "KiteWebSocketException",
    "KiteConnectionError",
    "KiteAuthenticationError",
    "KiteSubscriptionError",
    "KiteReconnectionError",
    "utils",
]
