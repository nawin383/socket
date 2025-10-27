# Kite WebSocket Python Client

A robust Python client for connecting to Zerodha Kite's WebSocket API for real-time market data streaming.

## Features

- **Real-time Market Data**: Stream live quotes, ticks, and order updates
- **Multiple Modes**: Support for LTP, Quote, and Full modes
- **Auto-reconnection**: Automatic reconnection with exponential backoff
- **Thread-safe**: Safe to use in multi-threaded applications
- **Easy to Use**: Simple API with callback support
- **Type Hints**: Full type annotations for better IDE support
- **Comprehensive Error Handling**: Custom exceptions for better debugging

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from kite_websocket import KiteWebSocket

# Initialize
kws = KiteWebSocket(
    api_key="your_api_key",
    access_token="your_access_token"
)

# Define callbacks
def on_ticks(ws, ticks):
    print("Ticks:", ticks)

def on_connect(ws, response):
    print("Connected!")
    # Subscribe to instruments
    ws.subscribe([256265, 408065])  # Instrument tokens
    ws.set_mode(ws.MODE_FULL, [256265, 408065])

def on_error(ws, code, reason):
    print(f"Error: {code} - {reason}")

def on_close(ws, code, reason):
    print("Connection closed")

# Assign callbacks
kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_error = on_error
kws.on_close = on_close

# Start connection
kws.connect()
```

## Features Overview

### Subscription Modes

- **MODE_LTP**: Last Traded Price only
- **MODE_QUOTE**: LTP + Market depth (top 5 bids and asks)
- **MODE_FULL**: Complete market depth and OHLC data

### Methods

#### Connection
- `connect(threaded=False)` - Establish WebSocket connection
- `close()` - Close the connection
- `stop()` - Stop and cleanup

#### Subscription
- `subscribe(instrument_tokens)` - Subscribe to instruments
- `unsubscribe(instrument_tokens)` - Unsubscribe from instruments
- `set_mode(mode, instrument_tokens)` - Change subscription mode
- `resubscribe()` - Resubscribe to all instruments

#### Callbacks
- `on_connect(ws, response)` - Called on successful connection
- `on_ticks(ws, ticks)` - Called when ticks are received
- `on_error(ws, code, reason)` - Called on error
- `on_close(ws, code, reason)` - Called when connection closes
- `on_reconnect(ws, attempts)` - Called on reconnection attempt
- `on_noreconnect(ws)` - Called when max reconnection attempts reached

## Advanced Usage

### Threaded Mode

```python
# Run in background thread
kws.connect(threaded=True)

# Your main program continues
# ...

# Stop when done
kws.stop()
```

### Custom Reconnection Settings

```python
kws = KiteWebSocket(
    api_key="your_api_key",
    access_token="your_access_token",
    reconnect=True,
    reconnect_max_tries=50,
    reconnect_max_delay=60
)
```

### Multiple Instruments

```python
def on_connect(ws, response):
    instruments = [256265, 408065, 738561, 895745]
    ws.subscribe(instruments)
    ws.set_mode(ws.MODE_FULL, instruments)
```

## Examples

Check the `examples/` directory for more examples:
- `basic_example.py` - Simple connection and subscription
- `advanced_example.py` - Advanced features with error handling
- `multi_mode_example.py` - Multiple subscription modes

## Configuration

### Environment Variables

You can set credentials via environment variables:

```bash
export KITE_API_KEY="your_api_key"
export KITE_ACCESS_TOKEN="your_access_token"
```

Then use:
```python
import os
kws = KiteWebSocket(
    api_key=os.getenv("KITE_API_KEY"),
    access_token=os.getenv("KITE_ACCESS_TOKEN")
)
```

## Tick Structure

Ticks received contain the following information:

```python
{
    'instrument_token': 256265,
    'mode': 'full',
    'tradeable': True,
    'last_price': 1234.5,
    'last_quantity': 1,
    'average_price': 1233.2,
    'volume': 12345,
    'buy_quantity': 100,
    'sell_quantity': 200,
    'ohlc': {
        'open': 1230.0,
        'high': 1240.0,
        'low': 1225.0,
        'close': 1235.0
    },
    'change': 0.5,
    'last_trade_time': datetime,
    'oi': 12345,  # Open Interest (for F&O)
    'oi_day_high': 13000,
    'oi_day_low': 11000,
    'depth': {
        'buy': [...],  # Top 5 buy orders
        'sell': [...]  # Top 5 sell orders
    }
}
```

## Error Handling

The client provides specific exceptions:

```python
from kite_websocket.exceptions import (
    KiteWebSocketException,
    KiteConnectionError,
    KiteAuthenticationError,
    KiteSubscriptionError
)

try:
    kws.connect()
except KiteAuthenticationError as e:
    print("Authentication failed:", e)
except KiteConnectionError as e:
    print("Connection failed:", e)
```

## Testing

Run tests with pytest:

```bash
pytest tests/
```

## Requirements

- Python 3.7+
- websocket-client
- six
- twisted (optional, for threaded mode)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Disclaimer

This is an unofficial client library. Use at your own risk. Make sure to comply with Zerodha's API usage policies.

## Support

For issues and questions:
- Create an issue on GitHub
- Check Zerodha's official documentation: https://kite.trade/docs/connect/v3/websocket/

## Changelog

### v1.0.0 (2025-10-27)
- Initial release
- WebSocket connection support
- Multiple subscription modes
- Auto-reconnection
- Comprehensive error handling
