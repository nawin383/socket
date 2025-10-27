# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-10-27

### Added
- Initial release of Kite WebSocket Python client
- WebSocket connection management with auto-reconnection
- Support for three subscription modes (LTP, Quote, Full)
- Binary tick data parsing
- Thread-safe operation with threaded mode support
- Comprehensive error handling and custom exceptions
- Callback system for events (ticks, connect, disconnect, errors)
- Market depth data parsing for Full mode
- Order update notifications
- Exponential backoff for reconnection attempts
- Complete type hints for better IDE support
- Example scripts demonstrating various features
- Unit tests with pytest
- CI/CD pipeline with GitHub Actions
- Comprehensive documentation

### Features
- **Real-time Market Data**: Stream live quotes, ticks, and order updates
- **Multiple Subscription Modes**: LTP, Quote, and Full modes for different data needs
- **Auto-reconnection**: Automatic reconnection with exponential backoff
- **Thread Support**: Run in background thread or blocking mode
- **Market Depth**: Full market depth with top 5 bids and asks
- **OHLC Data**: Open, High, Low, Close data in Quote and Full modes
- **Order Updates**: Real-time order status notifications
- **Error Handling**: Comprehensive error handling with custom exceptions
- **Type Safety**: Full type annotations for better development experience

### Documentation
- README with quick start guide
- Detailed API documentation
- Three example scripts (basic, advanced, multi-mode)
- Contributing guidelines
- Configuration examples
- Test coverage

### Technical Details
- Python 3.7+ support
- WebSocket-client library for WebSocket connections
- Binary data parsing with struct module
- Thread-safe operations
- Configurable reconnection strategy
- SSL/TLS support

## [Unreleased]

### Planned Features
- Historical data support
- More subscription management utilities
- Performance optimizations
- Additional examples
- Enhanced logging options
- Connection pooling
- Rate limiting utilities

---

## Version History

- **1.0.0** (2025-10-27): Initial release with core WebSocket functionality
