#!/usr/bin/env python3
"""
Multi-Mode Example: Demonstrating different subscription modes

This example shows how to use different subscription modes for different
instruments simultaneously:
- MODE_LTP: Minimal data, just last traded price
- MODE_QUOTE: Market depth with top 5 bids/asks
- MODE_FULL: Complete market data with full depth and OHLC
"""

import os
import logging
from kite_websocket import KiteWebSocket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Credentials
API_KEY = os.getenv("KITE_API_KEY", "your_api_key")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "your_access_token")

# Different instrument groups for different modes
# Replace these with actual instrument tokens

# LTP Mode: For instruments where you only need price updates
LTP_WATCHLIST = {
    256265: "SBIN",
    408065: "INFY",
    415745: "WIPRO",
    492033: "TECHM",
}

# Quote Mode: For instruments where you need basic market depth
QUOTE_WATCHLIST = {
    738561: "RELIANCE",
    779521: "COALINDIA",
    884737: "HINDUNILVR",
}

# Full Mode: For instruments where you need complete market data
FULL_WATCHLIST = {
    895745: "TCS",
    969473: "HDFCBANK",
    340481: "ICICIBANK",
}


def format_price(price):
    """Format price for display."""
    return f"₹{price:,.2f}"


def on_ticks(ws, ticks):
    """Process and display ticks based on mode."""
    for tick in ticks:
        token = tick['instrument_token']
        mode = tick.get('mode', 'unknown')
        ltp = tick.get('last_price', 0)

        # Get instrument name
        name = (LTP_WATCHLIST.get(token) or
                QUOTE_WATCHLIST.get(token) or
                FULL_WATCHLIST.get(token) or
                f"Token-{token}")

        if mode == 'ltp':
            # Display minimal info for LTP mode
            print(f"[LTP] {name:12} | Price: {format_price(ltp)}")

        elif mode == 'quote':
            # Display quote with volume and quantities
            volume = tick.get('volume', 0)
            buy_qty = tick.get('buy_quantity', 0)
            sell_qty = tick.get('sell_quantity', 0)
            avg_price = tick.get('average_price', 0)

            ohlc = tick.get('ohlc', {})
            change_pct = ((ltp - ohlc.get('close', ltp)) / ohlc.get('close', ltp) * 100
                          if ohlc.get('close', 0) > 0 else 0)

            print(f"[QUOTE] {name:12} | "
                  f"LTP: {format_price(ltp)} | "
                  f"Avg: {format_price(avg_price)} | "
                  f"Vol: {volume:,} | "
                  f"Buy: {buy_qty:,} | "
                  f"Sell: {sell_qty:,} | "
                  f"Change: {change_pct:+.2f}%")

        elif mode == 'full':
            # Display full market data
            volume = tick.get('volume', 0)
            ohlc = tick.get('ohlc', {})
            depth = tick.get('depth', {})
            oi = tick.get('oi', 0)

            change_pct = ((ltp - ohlc.get('close', ltp)) / ohlc.get('close', ltp) * 100
                          if ohlc.get('close', 0) > 0 else 0)

            print(f"\n{'=' * 80}")
            print(f"[FULL] {name} (Token: {token})")
            print(f"{'=' * 80}")
            print(f"  LTP: {format_price(ltp)} | Change: {change_pct:+.2f}% | Volume: {volume:,}")
            print(f"  OHLC: O={format_price(ohlc.get('open', 0))} | "
                  f"H={format_price(ohlc.get('high', 0))} | "
                  f"L={format_price(ohlc.get('low', 0))} | "
                  f"C={format_price(ohlc.get('close', 0))}")

            if oi:
                print(f"  Open Interest: {oi:,} | "
                      f"High: {tick.get('oi_day_high', 0):,} | "
                      f"Low: {tick.get('oi_day_low', 0):,}")

            # Display market depth
            if depth:
                print(f"\n  Market Depth:")
                print(f"    {'BUY':<40} | {'SELL':<40}")
                print(f"    {'-' * 40}-+-{'-' * 40}")

                buy_orders = depth.get('buy', [])
                sell_orders = depth.get('sell', [])

                for i in range(5):
                    buy = buy_orders[i] if i < len(buy_orders) else {}
                    sell = sell_orders[i] if i < len(sell_orders) else {}

                    buy_str = (f"{buy.get('orders', 0):3d} orders | "
                               f"{buy.get('quantity', 0):6d} qty @ {format_price(buy.get('price', 0))}"
                               if buy else " " * 40)

                    sell_str = (f"{sell.get('orders', 0):3d} orders | "
                                f"{sell.get('quantity', 0):6d} qty @ {format_price(sell.get('price', 0))}"
                                if sell else " " * 40)

                    print(f"    {buy_str} | {sell_str}")

            print(f"{'=' * 80}\n")


def on_connect(ws, response):
    """Setup subscriptions on connect."""
    logger.info("=" * 80)
    logger.info("Connected! Setting up multi-mode subscriptions...")
    logger.info("=" * 80)

    # Subscribe to LTP mode instruments
    if LTP_WATCHLIST:
        ltp_tokens = list(LTP_WATCHLIST.keys())
        logger.info(f"Setting up LTP mode for {len(ltp_tokens)} instruments: "
                    f"{', '.join(LTP_WATCHLIST.values())}")
        ws.subscribe(ltp_tokens)
        ws.set_mode(ws.MODE_LTP, ltp_tokens)

    # Subscribe to QUOTE mode instruments
    if QUOTE_WATCHLIST:
        quote_tokens = list(QUOTE_WATCHLIST.keys())
        logger.info(f"Setting up QUOTE mode for {len(quote_tokens)} instruments: "
                    f"{', '.join(QUOTE_WATCHLIST.values())}")
        ws.subscribe(quote_tokens)
        ws.set_mode(ws.MODE_QUOTE, quote_tokens)

    # Subscribe to FULL mode instruments
    if FULL_WATCHLIST:
        full_tokens = list(FULL_WATCHLIST.keys())
        logger.info(f"Setting up FULL mode for {len(full_tokens)} instruments: "
                    f"{', '.join(FULL_WATCHLIST.values())}")
        ws.subscribe(full_tokens)
        ws.set_mode(ws.MODE_FULL, full_tokens)

    logger.info("=" * 80)
    logger.info("All subscriptions active. Streaming data...")
    logger.info("=" * 80)
    print()


def on_close(ws, code, reason):
    """Handle connection close."""
    logger.warning(f"\nConnection closed: {code} - {reason}")


def on_error(ws, code, reason):
    """Handle errors."""
    logger.error(f"Error: {code} - {reason}")


def main():
    """Main function."""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║         Kite WebSocket Multi-Mode Subscription Demo           ║
    ╚════════════════════════════════════════════════════════════════╝

    This demo shows three different subscription modes:

    📊 LTP Mode (Lightweight):
       - Minimal data overhead
       - Just last traded price
       - Best for large watchlists

    📈 Quote Mode (Standard):
       - Market depth with top 5 bids/asks
       - Volume and OHLC data
       - Good balance of data vs. performance

    📉 Full Mode (Comprehensive):
       - Complete market depth
       - All available data points
       - Use for instruments you're actively trading

    Press Ctrl+C to stop...
    """)

    # Initialize WebSocket
    kws = KiteWebSocket(
        api_key=API_KEY,
        access_token=ACCESS_TOKEN,
        debug=False
    )

    # Assign callbacks
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.on_error = on_error

    # Start connection
    try:
        kws.connect()
    except KeyboardInterrupt:
        logger.info("\nStopping...")
        kws.stop()


if __name__ == "__main__":
    main()
