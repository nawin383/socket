"""
Custom exceptions for Kite WebSocket client
"""


class KiteWebSocketException(Exception):
    """Base exception class for Kite WebSocket"""
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code
        self.message = message


class KiteConnectionError(KiteWebSocketException):
    """Exception raised for connection related errors"""
    pass


class KiteAuthenticationError(KiteWebSocketException):
    """Exception raised for authentication failures"""
    pass


class KiteSubscriptionError(KiteWebSocketException):
    """Exception raised for subscription related errors"""
    pass


class KiteReconnectionError(KiteWebSocketException):
    """Exception raised when reconnection fails"""
    pass


class KiteDataError(KiteWebSocketException):
    """Exception raised for data parsing errors"""
    pass
