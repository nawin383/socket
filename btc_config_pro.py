"""
Configuration Management for Bitcoin Trading Platform Pro
"""
import os
import json
from typing import Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class TradingConfig:
    """Trading configuration"""
    initial_capital: float = 100000.0
    max_position_size: float = 0.1  # 10% of capital
    max_risk_per_trade: float = 0.02  # 2% of capital
    auto_refresh_interval: int = 15  # seconds
    enable_websocket: bool = True
    cache_duration: int = 300  # seconds

    # Risk management
    use_stop_loss: bool = False
    default_stop_loss_pct: float = 0.05  # 5%
    use_take_profit: bool = False
    default_take_profit_pct: float = 0.10  # 10%

    # UI settings
    theme: str = "darkly"
    show_greeks: bool = True
    show_charts: bool = True
    decimal_places: int = 2

    # Data management
    database_path: str = "btc_trading.db"
    export_path: str = "exports"
    log_level: str = "INFO"


@dataclass
class APIConfig:
    """API configuration"""
    delta_api_url: str = "https://cdn.india.deltaex.org/v2/tickers"
    delta_ws_url: str = "wss://socket.india.delta.exchange"
    timeout: int = 10
    max_retries: int = 3
    retry_delay: int = 2


class ConfigManager:
    """Configuration manager"""

    def __init__(self, config_file: str = "btc_pro_config.json"):
        self.config_file = Path(config_file)
        self.trading_config = TradingConfig()
        self.api_config = APIConfig()
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)

                    if 'trading' in data:
                        for key, value in data['trading'].items():
                            if hasattr(self.trading_config, key):
                                setattr(self.trading_config, key, value)

                    if 'api' in data:
                        for key, value in data['api'].items():
                            if hasattr(self.api_config, key):
                                setattr(self.api_config, key, value)

            except Exception as e:
                print(f"Error loading config: {e}")

    def save_config(self) -> None:
        """Save configuration to file"""
        try:
            config_data = {
                'trading': asdict(self.trading_config),
                'api': asdict(self.api_config)
            }

            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2)

        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        if section == 'trading':
            return getattr(self.trading_config, key, default)
        elif section == 'api':
            return getattr(self.api_config, key, default)
        return default

    def set(self, section: str, key: str, value: Any) -> None:
        """Set configuration value"""
        if section == 'trading' and hasattr(self.trading_config, key):
            setattr(self.trading_config, key, value)
        elif section == 'api' and hasattr(self.api_config, key):
            setattr(self.api_config, key, value)
        self.save_config()
