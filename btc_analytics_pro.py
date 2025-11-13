"""
Analytics and Risk Metrics for Bitcoin Trading Platform Pro
"""
import numpy as np
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
from btc_models_pro import Trade, Portfolio


class PerformanceAnalytics:
    """Performance analytics calculator"""

    @staticmethod
    def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        if not returns or len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        excess_returns = returns_array - (risk_free_rate / 252)  # Daily risk-free rate

        if np.std(excess_returns) == 0:
            return 0.0

        return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)

    @staticmethod
    def calculate_sortino_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (downside deviation)"""
        if not returns or len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        excess_returns = returns_array - (risk_free_rate / 252)

        # Only negative returns for downside deviation
        downside_returns = excess_returns[excess_returns < 0]

        if len(downside_returns) == 0:
            return 0.0

        downside_std = np.std(downside_returns)
        if downside_std == 0:
            return 0.0

        return np.mean(excess_returns) / downside_std * np.sqrt(252)

    @staticmethod
    def calculate_max_drawdown(equity_curve: List[float]) -> Tuple[float, float]:
        """Calculate maximum drawdown and percentage"""
        if not equity_curve or len(equity_curve) < 2:
            return 0.0, 0.0

        equity = np.array(equity_curve)
        running_max = np.maximum.accumulate(equity)
        drawdown = (equity - running_max) / running_max
        max_dd = np.min(drawdown)
        max_dd_value = np.min(equity - running_max)

        return abs(max_dd_value), abs(max_dd) * 100

    @staticmethod
    def calculate_win_rate(trades: List[Trade]) -> float:
        """Calculate win rate"""
        closed_trades = [t for t in trades if t.status == 'closed']
        if not closed_trades:
            return 0.0

        winning = len([t for t in closed_trades if t.realized_pnl > 0])
        return (winning / len(closed_trades)) * 100

    @staticmethod
    def calculate_profit_factor(trades: List[Trade]) -> float:
        """Calculate profit factor"""
        closed_trades = [t for t in trades if t.status == 'closed']
        if not closed_trades:
            return 0.0

        gross_profit = sum(t.realized_pnl for t in closed_trades if t.realized_pnl > 0)
        gross_loss = abs(sum(t.realized_pnl for t in closed_trades if t.realized_pnl < 0))

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    @staticmethod
    def calculate_average_win_loss(trades: List[Trade]) -> Tuple[float, float]:
        """Calculate average win and average loss"""
        closed_trades = [t for t in trades if t.status == 'closed']
        if not closed_trades:
            return 0.0, 0.0

        wins = [t.realized_pnl for t in closed_trades if t.realized_pnl > 0]
        losses = [abs(t.realized_pnl) for t in closed_trades if t.realized_pnl < 0]

        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0

        return avg_win, avg_loss

    @staticmethod
    def calculate_expectancy(trades: List[Trade]) -> float:
        """Calculate trade expectancy"""
        win_rate = PerformanceAnalytics.calculate_win_rate(trades)
        avg_win, avg_loss = PerformanceAnalytics.calculate_average_win_loss(trades)

        if avg_loss == 0:
            return avg_win * (win_rate / 100)

        return (win_rate / 100) * avg_win - ((100 - win_rate) / 100) * avg_loss

    @staticmethod
    def calculate_daily_returns(equity_curve: List[Tuple[str, float]]) -> List[float]:
        """Calculate daily returns from equity curve"""
        if len(equity_curve) < 2:
            return []

        returns = []
        for i in range(1, len(equity_curve)):
            prev_equity = equity_curve[i-1][1]
            curr_equity = equity_curve[i][1]
            if prev_equity > 0:
                daily_return = (curr_equity - prev_equity) / prev_equity
                returns.append(daily_return)

        return returns


class RiskMetrics:
    """Risk management metrics"""

    @staticmethod
    def calculate_position_size(
        capital: float,
        risk_pct: float,
        entry_price: float,
        stop_loss_price: float
    ) -> float:
        """Calculate position size based on risk"""
        if stop_loss_price == 0 or entry_price == stop_loss_price:
            return 0.0

        risk_amount = capital * risk_pct
        risk_per_unit = abs(entry_price - stop_loss_price)

        return risk_amount / risk_per_unit

    @staticmethod
    def calculate_var(returns: List[float], confidence_level: float = 0.95) -> float:
        """Calculate Value at Risk (VaR)"""
        if not returns:
            return 0.0

        returns_array = np.array(returns)
        var = np.percentile(returns_array, (1 - confidence_level) * 100)
        return abs(var)

    @staticmethod
    def calculate_cvar(returns: List[float], confidence_level: float = 0.95) -> float:
        """Calculate Conditional Value at Risk (CVaR) / Expected Shortfall"""
        if not returns:
            return 0.0

        returns_array = np.array(returns)
        var = np.percentile(returns_array, (1 - confidence_level) * 100)
        cvar = returns_array[returns_array <= var].mean()
        return abs(cvar)

    @staticmethod
    def calculate_portfolio_greeks(trades: List[Trade]) -> Dict[str, float]:
        """Calculate aggregated portfolio Greeks"""
        open_trades = [t for t in trades if t.status == 'open' and t.instrument_type in ['CE', 'PE']]

        if not open_trades:
            return {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0, 'rho': 0}

        total_delta = sum((t.delta or 0) * t.quantity for t in open_trades)
        total_gamma = sum((t.gamma or 0) * t.quantity for t in open_trades)
        total_theta = sum((t.theta or 0) * t.quantity for t in open_trades)
        total_vega = sum((t.vega or 0) * t.quantity for t in open_trades)
        total_rho = sum((t.rho or 0) * t.quantity for t in open_trades)

        return {
            'delta': total_delta,
            'gamma': total_gamma,
            'theta': total_theta,
            'vega': total_vega,
            'rho': total_rho
        }

    @staticmethod
    def calculate_kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Calculate Kelly Criterion for position sizing"""
        if avg_loss == 0:
            return 0.0

        win_prob = win_rate / 100
        loss_prob = 1 - win_prob
        win_loss_ratio = avg_win / avg_loss

        kelly = (win_prob * win_loss_ratio - loss_prob) / win_loss_ratio
        return max(0, min(kelly, 0.25))  # Cap at 25% for safety


class TradeAnalytics:
    """Trade-specific analytics"""

    @staticmethod
    def analyze_trade_distribution(trades: List[Trade]) -> Dict[str, Any]:
        """Analyze trade distribution by various factors"""
        if not trades:
            return {}

        closed_trades = [t for t in trades if t.status == 'closed']

        # By instrument type
        by_type = {}
        for trade in closed_trades:
            inst_type = trade.instrument_type
            if inst_type not in by_type:
                by_type[inst_type] = {'count': 0, 'pnl': 0, 'wins': 0}
            by_type[inst_type]['count'] += 1
            by_type[inst_type]['pnl'] += trade.realized_pnl
            if trade.realized_pnl > 0:
                by_type[inst_type]['wins'] += 1

        # Calculate win rates
        for inst_type in by_type:
            count = by_type[inst_type]['count']
            by_type[inst_type]['win_rate'] = (by_type[inst_type]['wins'] / count * 100) if count > 0 else 0

        # By direction
        long_trades = [t for t in closed_trades if t.trade_type == 'buy']
        short_trades = [t for t in closed_trades if t.trade_type == 'sell']

        long_pnl = sum(t.realized_pnl for t in long_trades)
        short_pnl = sum(t.realized_pnl for t in short_trades)

        return {
            'by_instrument_type': by_type,
            'long_trades': {
                'count': len(long_trades),
                'pnl': long_pnl,
                'win_rate': len([t for t in long_trades if t.realized_pnl > 0]) / len(long_trades) * 100 if long_trades else 0
            },
            'short_trades': {
                'count': len(short_trades),
                'pnl': short_pnl,
                'win_rate': len([t for t in short_trades if t.realized_pnl > 0]) / len(short_trades) * 100 if short_trades else 0
            }
        }

    @staticmethod
    def calculate_holding_period_stats(trades: List[Trade]) -> Dict[str, float]:
        """Calculate holding period statistics"""
        closed_trades = [t for t in trades if t.status == 'closed' and t.exit_date]

        if not closed_trades:
            return {'avg_days': 0, 'min_days': 0, 'max_days': 0}

        holding_periods = []
        for trade in closed_trades:
            try:
                entry = datetime.strptime(trade.entry_date, '%Y-%m-%d')
                exit_dt = datetime.strptime(trade.exit_date, '%Y-%m-%d')
                days = (exit_dt - entry).days
                holding_periods.append(days)
            except:
                continue

        if not holding_periods:
            return {'avg_days': 0, 'min_days': 0, 'max_days': 0}

        return {
            'avg_days': np.mean(holding_periods),
            'min_days': np.min(holding_periods),
            'max_days': np.max(holding_periods),
            'median_days': np.median(holding_periods)
        }


def generate_performance_report(trades: List[Trade], portfolio: Portfolio) -> Dict[str, Any]:
    """Generate comprehensive performance report"""
    closed_trades = [t for t in trades if t.status == 'closed']

    # Basic metrics
    win_rate = PerformanceAnalytics.calculate_win_rate(trades)
    profit_factor = PerformanceAnalytics.calculate_profit_factor(trades)
    avg_win, avg_loss = PerformanceAnalytics.calculate_average_win_loss(trades)
    expectancy = PerformanceAnalytics.calculate_expectancy(trades)

    # Distribution analysis
    distribution = TradeAnalytics.analyze_trade_distribution(trades)
    holding_stats = TradeAnalytics.calculate_holding_period_stats(trades)

    # Portfolio Greeks
    portfolio_greeks = RiskMetrics.calculate_portfolio_greeks(trades)

    # Kelly Criterion
    kelly = RiskMetrics.calculate_kelly_criterion(win_rate, avg_win, avg_loss)

    return {
        'summary': {
            'total_trades': len(trades),
            'open_trades': len([t for t in trades if t.status == 'open']),
            'closed_trades': len(closed_trades),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_pnl': portfolio.total_pnl,
            'realized_pnl': portfolio.realized_pnl,
            'unrealized_pnl': portfolio.unrealized_pnl,
            'max_drawdown': portfolio.max_drawdown,
            'sharpe_ratio': portfolio.sharpe_ratio
        },
        'distribution': distribution,
        'holding_period': holding_stats,
        'portfolio_greeks': portfolio_greeks,
        'risk_management': {
            'kelly_criterion': kelly,
            'recommended_position_size': kelly * 100  # As percentage
        }
    }
