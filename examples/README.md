# Examples

This directory contains example scripts demonstrating various features of the Kite WebSocket client.

## Setup

Before running the examples, make sure to:

1. Install dependencies:
   ```bash
   pip install -r ../requirements.txt
   ```

2. Set your credentials as environment variables:
   ```bash
   export KITE_API_KEY="your_api_key"
   export KITE_ACCESS_TOKEN="your_access_token"
   ```

   Alternatively, edit the example files and replace the placeholder values.

3. Update instrument tokens with valid ones for your use case.

## Running Examples

### Basic Example
Simple connection and subscription:
```bash
python basic_example.py
```

### Advanced Example
Full-featured implementation with threaded mode:
```bash
python advanced_example.py
```

### Multi-Mode Example
Demonstrates different subscription modes:
```bash
python multi_mode_example.py
```

## Getting Instrument Tokens

You can get instrument tokens from:
- Kite Connect API instrument dump
- Kite web interface (check the URL when viewing an instrument)
- Your trading app/platform

Example instrument tokens:
- SBIN: 779521
- INFY: 408065
- RELIANCE: 738561
- TCS: 2953217

**Note:** Instrument tokens change when contracts expire (for F&O). Always verify tokens are current.

## Troubleshooting

### Authentication Errors
- Verify your API key and access token are correct
- Ensure your access token hasn't expired (tokens expire at end of day)
- Check that your API subscription is active

### Connection Issues
- Check your internet connection
- Verify firewall settings allow WebSocket connections
- Try with SSL verification disabled (not recommended for production)

### No Data Received
- Ensure markets are open (9:15 AM - 3:30 PM IST on trading days)
- Verify instrument tokens are valid
- Check if instruments are subscribed correctly

## Learn More

- [Kite Connect Documentation](https://kite.trade/docs/connect/v3/)
- [WebSocket API Reference](https://kite.trade/docs/connect/v3/websocket/)
