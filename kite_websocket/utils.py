"""
Utility functions for Kite WebSocket client
"""

import os
import configparser
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def load_config(config_file: str = "config.ini") -> Dict[str, any]:
    """
    Load configuration from INI file.

    Args:
        config_file: Path to configuration file

    Returns:
        Dictionary with configuration values

    Example:
        >>> config = load_config("config.ini")
        >>> api_key = config['api_key']
        >>> access_token = config['access_token']
    """
    config = configparser.ConfigParser()

    if not os.path.exists(config_file):
        logger.warning(f"Config file {config_file} not found")
        return {}

    config.read(config_file)

    result = {}

    # Load Kite credentials
    if config.has_section('kite'):
        result['api_key'] = config.get('kite', 'api_key', fallback=None)
        result['access_token'] = config.get('kite', 'access_token', fallback=None)

    # Load WebSocket settings
    if config.has_section('websocket'):
        result['debug'] = config.getboolean('websocket', 'debug', fallback=False)
        result['reconnect'] = config.getboolean('websocket', 'reconnect', fallback=True)
        result['reconnect_max_tries'] = config.getint('websocket', 'reconnect_max_tries', fallback=30)
        result['reconnect_max_delay'] = config.getint('websocket', 'reconnect_max_delay', fallback=60)
        result['connect_timeout'] = config.getint('websocket', 'connect_timeout', fallback=30)

    # Load instrument settings
    if config.has_section('instruments'):
        tokens_str = config.get('instruments', 'tokens', fallback='')
        if tokens_str:
            result['tokens'] = [int(t.strip()) for t in tokens_str.split(',') if t.strip()]
        result['default_mode'] = config.get('instruments', 'default_mode', fallback='ltp')

    # Load logging settings
    if config.has_section('logging'):
        result['log_level'] = config.get('logging', 'level', fallback='INFO')
        result['log_format'] = config.get('logging', 'format', fallback='%(asctime)s - %(levelname)s - %(message)s')
        result['log_file'] = config.get('logging', 'file', fallback=None)

    return result


def load_credentials_from_env() -> Dict[str, str]:
    """
    Load credentials from environment variables.

    Returns:
        Dictionary with api_key and access_token

    Environment variables:
        KITE_API_KEY: Kite API key
        KITE_ACCESS_TOKEN: Kite access token

    Example:
        >>> creds = load_credentials_from_env()
        >>> api_key = creds['api_key']
        >>> access_token = creds['access_token']
    """
    return {
        'api_key': os.getenv('KITE_API_KEY'),
        'access_token': os.getenv('KITE_ACCESS_TOKEN')
    }


def validate_credentials(api_key: Optional[str], access_token: Optional[str]) -> bool:
    """
    Validate that credentials are provided and not empty.

    Args:
        api_key: Kite API key
        access_token: Kite access token

    Returns:
        True if credentials are valid, False otherwise

    Example:
        >>> is_valid = validate_credentials(api_key, access_token)
    """
    if not api_key or not access_token:
        logger.error("API key and access token are required")
        return False

    if api_key.strip() == "" or access_token.strip() == "":
        logger.error("API key and access token cannot be empty")
        return False

    return True


def setup_logging(level: str = "INFO", log_file: Optional[str] = None, log_format: Optional[str] = None):
    """
    Setup logging configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        log_format: Optional log format string

    Example:
        >>> setup_logging(level="DEBUG", log_file="app.log")
    """
    if log_format is None:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=handlers
    )


def parse_instrument_tokens(tokens_str: str) -> List[int]:
    """
    Parse comma-separated instrument tokens.

    Args:
        tokens_str: Comma-separated string of tokens

    Returns:
        List of integer tokens

    Example:
        >>> tokens = parse_instrument_tokens("256265,408065,738561")
        >>> print(tokens)  # [256265, 408065, 738561]
    """
    if not tokens_str:
        return []

    try:
        return [int(t.strip()) for t in tokens_str.split(',') if t.strip()]
    except ValueError as e:
        logger.error(f"Error parsing instrument tokens: {e}")
        return []


def format_tick_simple(tick: Dict) -> str:
    """
    Format tick data as simple string.

    Args:
        tick: Tick dictionary

    Returns:
        Formatted string

    Example:
        >>> formatted = format_tick_simple(tick)
        >>> print(formatted)
    """
    token = tick.get('instrument_token', 'N/A')
    ltp = tick.get('last_price', 0)
    volume = tick.get('volume', 0)

    return f"Token: {token}, LTP: {ltp:.2f}, Volume: {volume:,}"


def format_tick_detailed(tick: Dict) -> str:
    """
    Format tick data with detailed information.

    Args:
        tick: Tick dictionary

    Returns:
        Formatted string with details

    Example:
        >>> formatted = format_tick_detailed(tick)
        >>> print(formatted)
    """
    lines = []
    lines.append(f"Instrument Token: {tick.get('instrument_token', 'N/A')}")
    lines.append(f"Mode: {tick.get('mode', 'N/A')}")
    lines.append(f"Last Price: {tick.get('last_price', 0):.2f}")

    if 'last_quantity' in tick:
        lines.append(f"Last Quantity: {tick.get('last_quantity', 0):,}")

    if 'volume' in tick:
        lines.append(f"Volume: {tick.get('volume', 0):,}")

    if 'average_price' in tick:
        lines.append(f"Average Price: {tick.get('average_price', 0):.2f}")

    if 'ohlc' in tick:
        ohlc = tick['ohlc']
        lines.append(f"OHLC: O={ohlc.get('open', 0):.2f}, "
                     f"H={ohlc.get('high', 0):.2f}, "
                     f"L={ohlc.get('low', 0):.2f}, "
                     f"C={ohlc.get('close', 0):.2f}")

    if 'oi' in tick:
        lines.append(f"Open Interest: {tick.get('oi', 0):,}")

    return "\n".join(lines)


class RateLimiter:
    """
    Simple rate limiter for API calls.

    Example:
        >>> limiter = RateLimiter(max_calls=10, time_window=60)
        >>> if limiter.allow():
        >>>     # Make API call
        >>>     pass
    """

    def __init__(self, max_calls: int, time_window: int):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed
            time_window: Time window in seconds
        """
        import time
        from collections import deque

        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
        self._time = time

    def allow(self) -> bool:
        """
        Check if a call is allowed.

        Returns:
            True if call is allowed, False otherwise
        """
        now = self._time.time()

        # Remove old calls outside time window
        while self.calls and self.calls[0] < now - self.time_window:
            self.calls.popleft()

        # Check if we can make another call
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True

        return False

    def wait_time(self) -> float:
        """
        Get time to wait before next call is allowed.

        Returns:
            Seconds to wait
        """
        if len(self.calls) < self.max_calls:
            return 0.0

        oldest_call = self.calls[0]
        now = self._time.time()
        wait = (oldest_call + self.time_window) - now

        return max(0.0, wait)
