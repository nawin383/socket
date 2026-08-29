# 🟠 Bitcoin Virtual Trading Platform - Professional Edition

A comprehensive, enterprise-grade Bitcoin virtual trading platform with advanced analytics, risk management, and options strategy building capabilities.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-production-brightgreen.svg)

## 🚀 Features

### Core Trading Features
- ✅ **Real-time Bitcoin Data** - Live prices from Delta Exchange API
- 💹 **Futures & Perpetuals** - Trade Bitcoin futures and perpetual contracts
- 🎯 **Options Trading** - Full options chain with Greeks (Delta, Gamma, Theta, Vega, IV)
- 🛡️ **Risk Management** - Stop Loss and Take Profit automation
- 📝 **Trade Journal** - Notes, tags, and detailed trade history

### Advanced Analytics
- 📊 **Performance Metrics**
  - Sharpe Ratio & Sortino Ratio
  - Maximum Drawdown
  - Profit Factor & Expectancy
  - Win Rate & Average Win/Loss

- 📈 **Risk Metrics**
  - Value at Risk (VaR)
  - Conditional VaR (CVaR)
  - Kelly Criterion for position sizing
  - Portfolio Greeks aggregation

- 📉 **Performance Charts**
  - Portfolio equity curve
  - P&L distribution histogram
  - Interactive visualizations with Matplotlib/Plotly

### Options Strategy Builder
- 🎯 **10+ Professional Strategies**
  - Long/Short Call & Put
  - Bull/Bear Spreads
  - Straddles & Strangles
  - Iron Condor
  - Butterfly Spread
  - Covered Call & Protective Put

- 🔬 **Strategy Analysis**
  - Payoff diagrams
  - Risk/reward calculations
  - Optimal strike selection
  - Market outlook recommendations

### Data Management
- 💾 **SQLite Database** - Persistent storage with full trade history
- 📊 **Excel Export** - Advanced formatting and analytics
- 🔄 **Auto-backup** - Automatic data preservation
- 📈 **Historical Tracking** - Portfolio performance over time

### Technical Features
- ⚡ **WebSocket Support** - Real-time data streaming (with REST fallback)
- 🎨 **Modern UI** - ttkbootstrap theme support
- ⚙️ **Configurable** - Extensive configuration management
- 🔧 **Modular Architecture** - Separation of concerns for maintainability

## 📦 Installation

### Requirements
```bash
Python 3.8 or higher
```

### Install Dependencies
```bash
pip install -r requirements_btc_pro.txt
```

### Dependencies Breakdown
- **Core**: requests, python-dateutil
- **GUI**: ttkbootstrap
- **Data**: pandas, numpy, openpyxl
- **Charts**: matplotlib, plotly, kaleido
- **WebSocket**: websocket-client
- **Database**: sqlalchemy

## 🎯 Quick Start

### 1. Basic Usage
```bash
python btc_trading_platform_pro.py
```

### 2. First Time Setup
1. Launch the application
2. Wait for Bitcoin instruments to load (automatic)
3. Set your initial capital in Settings tab
4. Start trading!

### 3. Place Your First Trade
1. Go to **Trade** tab
2. Select contract type (Futures or Options)
3. Choose expiry date
4. Double-click on instrument to trade
5. Enter quantity, price, optional SL/TP
6. Click "Place Trade"

## 📖 User Guide

### Dashboard Tab
- **Portfolio Overview**: Real-time capital, P&L, Sharpe ratio
- **Market Status**: Current Bitcoin spot price with 24h change
- **Trade Statistics**: Total trades, win rate, profit factor
- **Recent Trades**: Last 20 trades with status

### Trade Tab
**Futures Trading**:
- Select "Futures" radio button
- Choose expiry (PERPETUAL for perpetual futures)
- View: Symbol, LTP, 24h Change, Open Interest
- Double-click to open trade dialog

**Options Trading**:
- Select "Options" radio button
- Choose expiry date
- View full options chain with:
  - Calls and Puts side by side
  - Last Traded Price (LTP)
  - Implied Volatility (IV)
  - Delta values
- Double-click on any row, then select Call or Put

### Positions Tab
**Open Positions**:
- View all active trades
- Current P&L (updated automatically)
- Stop Loss and Take Profit levels
- Actions: Close position, Edit SL/TP, Refresh

**Closed Positions**:
- Trade history with realized P&L
- Entry and exit prices
- Trade performance

### Analytics Tab
**Performance Report**:
- Summary statistics
- P&L breakdown
- Portfolio Greeks (for options positions)
- Risk management metrics
- Trade distribution analysis
- Holding period statistics

**Charts**:
- Portfolio equity curve
- P&L distribution
- Interactive visualizations

### Strategy Builder Tab
**Available Strategies**:
1. **Long Call** - Bullish, unlimited profit potential
2. **Long Put** - Bearish, high profit potential
3. **Bull Call Spread** - Moderate bullish, limited risk
4. **Bear Put Spread** - Moderate bearish, limited risk
5. **Long Straddle** - High volatility expected
6. **Short Straddle** - Low volatility expected
7. **Long Strangle** - Moderate volatility, lower cost
8. **Iron Condor** - Neutral, range-bound market
9. **Butterfly Spread** - Precise price target
10. **Covered Call** - Income generation (if holding BTC)
11. **Protective Put** - Downside protection (if holding BTC)

### Settings Tab
**Portfolio Settings**:
- Adjust initial capital
- View current capital and returns

**Data Management**:
- Export trades to Excel
- Update analytics
- View activity log

**Activity Log**:
- Real-time application events
- API status updates
- Trade confirmations
- System messages

## 🔧 Configuration

### Configuration File: `btc_pro_config.json`

```json
{
  "trading": {
    "initial_capital": 100000.0,
    "max_position_size": 0.1,
    "max_risk_per_trade": 0.02,
    "auto_refresh_interval": 15,
    "enable_websocket": true,
    "use_stop_loss": false,
    "default_stop_loss_pct": 0.05,
    "use_take_profit": false,
    "default_take_profit_pct": 0.10,
    "theme": "darkly",
    "show_greeks": true,
    "show_charts": true,
    "database_path": "btc_trading_pro.db"
  },
  "api": {
    "delta_api_url": "https://cdn.india.deltaex.org/v2/tickers",
    "timeout": 10,
    "max_retries": 3
  }
}
```

## 📊 Analytics Explained

### Performance Metrics

**Sharpe Ratio**
- Measures risk-adjusted returns
- Formula: (Return - Risk-free rate) / Standard deviation
- Higher is better (> 1.0 is good, > 2.0 is excellent)

**Sortino Ratio**
- Like Sharpe but only considers downside volatility
- Better for strategies with asymmetric returns

**Maximum Drawdown**
- Largest peak-to-trough decline
- Measures worst-case scenario
- Lower is better

**Profit Factor**
- Gross profit / Gross loss
- > 1.0 means profitable
- > 2.0 is excellent

**Expectancy**
- Average expected profit per trade
- Positive expectancy = profitable system over time

### Risk Metrics

**Value at Risk (VaR)**
- Maximum expected loss at confidence level
- Example: 95% VaR of $1000 = 95% chance loss won't exceed $1000

**Conditional VaR (CVaR)**
- Average loss beyond VaR threshold
- Also called Expected Shortfall

**Kelly Criterion**
- Optimal position sizing formula
- Prevents over-leveraging
- Platform caps at 25% for safety

**Portfolio Greeks**
- **Delta**: Price sensitivity (sum of all positions)
- **Gamma**: Delta sensitivity
- **Theta**: Time decay (negative = losing value daily)
- **Vega**: Volatility sensitivity

## 🗂️ File Structure

```
btc_trading_platform_pro/
├── btc_trading_platform_pro.py    # Main application
├── btc_config_pro.py               # Configuration management
├── btc_models_pro.py               # Database models & ORM
├── btc_analytics_pro.py            # Analytics & risk metrics
├── btc_strategies_pro.py           # Options strategy builder
├── btc_websocket_pro.py            # WebSocket handler
├── requirements_btc_pro.txt        # Dependencies
├── README_BTC_TRADING_PRO.md       # This file
├── btc_pro_config.json             # Configuration (auto-generated)
└── btc_trading_pro.db              # SQLite database (auto-generated)
```

## 🎨 Architecture

### Modular Design
```
┌─────────────────────────────────────────┐
│         Main Application (GUI)          │
├─────────────────────────────────────────┤
│  ConfigManager │ DatabaseManager        │
├─────────────────────────────────────────┤
│  DeltaExchangeAPI │ WebSocketHandler    │
├─────────────────────────────────────────┤
│  PerformanceAnalytics │ RiskMetrics     │
├─────────────────────────────────────────┤
│  StrategyBuilder │ StrategyAnalyzer     │
└─────────────────────────────────────────┘
```

### Database Schema
- **trades**: Complete trade history with Greeks
- **portfolio**: Portfolio metrics and statistics
- **portfolio_history**: Daily snapshots for charts

## 🔐 Security & Privacy

- ✅ **No API keys required** - Uses public Delta Exchange data
- ✅ **Local storage only** - All data stored locally in SQLite
- ✅ **No external data sharing** - Your trades stay private
- ✅ **Virtual trading only** - No real money at risk

## 🐛 Troubleshooting

### Common Issues

**1. "No data received from Delta Exchange"**
- Check internet connection
- Delta Exchange API might be down (wait and retry)
- Firewall blocking requests

**2. "matplotlib not available"**
- Install: `pip install matplotlib`
- Charts will be disabled if not installed

**3. Database locked error**
- Close any other instances of the app
- Delete `btc_trading_pro.db` to start fresh (loses data)

**4. Slow performance**
- Reduce auto-refresh interval in config
- Disable WebSocket if connection is slow
- Close unused tabs

### Reset Application
```bash
# Delete database (loses all trades)
rm btc_trading_pro.db

# Delete configuration (resets to defaults)
rm btc_pro_config.json

# Fresh start
python btc_trading_platform_pro.py
```

## 🚀 Advanced Usage

### Custom Risk Parameters
Edit `btc_pro_config.json`:
```json
{
  "trading": {
    "max_position_size": 0.2,        // 20% of capital max
    "max_risk_per_trade": 0.03,      // 3% risk per trade
    "default_stop_loss_pct": 0.08,   // 8% stop loss
    "default_take_profit_pct": 0.15  // 15% take profit
  }
}
```

### Batch Export for Analysis
```python
from btc_models_pro import DatabaseManager
import pandas as pd

db = DatabaseManager('btc_trading_pro.db')
trades = db.get_all_trades()

# Convert to DataFrame
df = pd.DataFrame([t.to_dict() for t in trades])
df.to_csv('my_analysis.csv', index=False)
```

### Custom Analytics
```python
from btc_analytics_pro import PerformanceAnalytics, generate_performance_report
from btc_models_pro import DatabaseManager

db = DatabaseManager('btc_trading_pro.db')
trades = db.get_all_trades()
portfolio = db.get_portfolio()

report = generate_performance_report(trades, portfolio)
print(report)
```

## 📈 Best Practices

### Trading Guidelines
1. **Start Small** - Begin with small position sizes
2. **Use Stop Losses** - Always protect your capital
3. **Diversify** - Don't put all capital in one trade
4. **Track Performance** - Review analytics regularly
5. **Journal Trades** - Use notes to track reasoning

### Risk Management
1. **2% Rule** - Risk max 2% of capital per trade
2. **Kelly Criterion** - Use for position sizing guidance
3. **Monitor Greeks** - Especially for options portfolios
4. **Review Drawdowns** - Keep max drawdown under 20%
5. **Adjust Strategy** - If Sharpe ratio < 1.0, reevaluate

### Options Trading Tips
1. **Understand Greeks** - Know how your position behaves
2. **IV Rank** - Buy options when IV is low, sell when high
3. **Time Decay** - Theta works against long options
4. **Spreads** - Reduce cost and define risk
5. **Exit Plan** - Know your profit target and loss limit

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Additional technical indicators
- More options strategies
- Backtesting engine
- Paper trading mode with live data
- Mobile-responsive web interface
- Multi-asset support (ETH, etc.)

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- **Delta Exchange** - Bitcoin options and futures data
- **ttkbootstrap** - Modern UI components
- **Matplotlib/Plotly** - Charting libraries
- **SQLite** - Embedded database

## 📞 Support

For issues and questions:
1. Check troubleshooting section
2. Review configuration settings
3. Check activity log for errors
4. Search for similar issues

## 🔮 Roadmap

### Version 2.0 (Future)
- [ ] Multi-cryptocurrency support (ETH, SOL, etc.)
- [ ] Backtesting engine with historical data
- [ ] Strategy optimizer using genetic algorithms
- [ ] Machine learning price prediction
- [ ] Web-based interface
- [ ] Mobile app
- [ ] Social trading features
- [ ] Advanced charting (candlesticks, indicators)
- [ ] News integration
- [ ] Telegram/Discord notifications

### Version 1.1 (Next Release)
- [ ] Enhanced WebSocket implementation
- [ ] More chart types
- [ ] Trade alerts and notifications
- [ ] CSV import for historical trades
- [ ] Performance comparison vs BTC buy-and-hold
- [ ] Tax report generation

---

**Disclaimer**: This is a virtual trading platform for educational purposes only. It does not execute real trades. Past performance does not guarantee future results. Cryptocurrency trading involves substantial risk.

**Version**: 1.0.0
**Last Updated**: 2025
**Author**: Bitcoin Trading Platform Pro Team

🟠 **Happy Trading!** 🚀
