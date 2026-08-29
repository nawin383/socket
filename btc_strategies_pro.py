"""
Options Strategies Builder for Bitcoin Trading Platform Pro
"""
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from btc_models_pro import Trade


@dataclass
class StrategyLeg:
    """Single leg of an options strategy"""
    action: str  # 'buy' or 'sell'
    option_type: str  # 'CE' or 'PE'
    strike: float
    quantity: int
    premium: float


@dataclass
class OptionsStrategy:
    """Options strategy definition"""
    name: str
    legs: List[StrategyLeg]
    description: str
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    breakeven: Optional[List[float]] = None


class OptionsStrategyBuilder:
    """Builder for common options strategies"""

    @staticmethod
    def long_call(strike: float, premium: float, quantity: int = 1) -> OptionsStrategy:
        """Long Call strategy"""
        leg = StrategyLeg('buy', 'CE', strike, quantity, premium)
        return OptionsStrategy(
            name='Long Call',
            legs=[leg],
            description=f'Bullish strategy: Buy {quantity} Call @ ${strike}',
            max_profit=float('inf'),
            max_loss=premium * quantity,
            breakeven=[strike + premium]
        )

    @staticmethod
    def long_put(strike: float, premium: float, quantity: int = 1) -> OptionsStrategy:
        """Long Put strategy"""
        leg = StrategyLeg('buy', 'PE', strike, quantity, premium)
        return OptionsStrategy(
            name='Long Put',
            legs=[leg],
            description=f'Bearish strategy: Buy {quantity} Put @ ${strike}',
            max_profit=(strike - premium) * quantity,
            max_loss=premium * quantity,
            breakeven=[strike - premium]
        )

    @staticmethod
    def covered_call(
        stock_price: float,
        call_strike: float,
        call_premium: float,
        quantity: int = 1
    ) -> OptionsStrategy:
        """Covered Call strategy"""
        legs = [
            StrategyLeg('buy', 'FUT', stock_price, quantity, stock_price),  # Long futures as proxy
            StrategyLeg('sell', 'CE', call_strike, quantity, call_premium)
        ]

        max_profit = (call_strike - stock_price + call_premium) * quantity
        max_loss = (stock_price - call_premium) * quantity

        return OptionsStrategy(
            name='Covered Call',
            legs=legs,
            description=f'Hold BTC + Sell {quantity} Call @ ${call_strike}',
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven=[stock_price - call_premium]
        )

    @staticmethod
    def protective_put(
        stock_price: float,
        put_strike: float,
        put_premium: float,
        quantity: int = 1
    ) -> OptionsStrategy:
        """Protective Put strategy"""
        legs = [
            StrategyLeg('buy', 'FUT', stock_price, quantity, stock_price),
            StrategyLeg('buy', 'PE', put_strike, quantity, put_premium)
        ]

        max_profit = float('inf')
        max_loss = (stock_price - put_strike + put_premium) * quantity

        return OptionsStrategy(
            name='Protective Put',
            legs=legs,
            description=f'Hold BTC + Buy {quantity} Put @ ${put_strike}',
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven=[stock_price + put_premium]
        )

    @staticmethod
    def bull_call_spread(
        lower_strike: float,
        upper_strike: float,
        lower_premium: float,
        upper_premium: float,
        quantity: int = 1
    ) -> OptionsStrategy:
        """Bull Call Spread strategy"""
        legs = [
            StrategyLeg('buy', 'CE', lower_strike, quantity, lower_premium),
            StrategyLeg('sell', 'CE', upper_strike, quantity, upper_premium)
        ]

        net_debit = (lower_premium - upper_premium) * quantity
        max_profit = (upper_strike - lower_strike - (lower_premium - upper_premium)) * quantity
        max_loss = net_debit
        breakeven = lower_strike + (lower_premium - upper_premium)

        return OptionsStrategy(
            name='Bull Call Spread',
            legs=legs,
            description=f'Buy Call @ ${lower_strike}, Sell Call @ ${upper_strike}',
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven=[breakeven]
        )

    @staticmethod
    def bear_put_spread(
        higher_strike: float,
        lower_strike: float,
        higher_premium: float,
        lower_premium: float,
        quantity: int = 1
    ) -> OptionsStrategy:
        """Bear Put Spread strategy"""
        legs = [
            StrategyLeg('buy', 'PE', higher_strike, quantity, higher_premium),
            StrategyLeg('sell', 'PE', lower_strike, quantity, lower_premium)
        ]

        net_debit = (higher_premium - lower_premium) * quantity
        max_profit = (higher_strike - lower_strike - (higher_premium - lower_premium)) * quantity
        max_loss = net_debit
        breakeven = higher_strike - (higher_premium - lower_premium)

        return OptionsStrategy(
            name='Bear Put Spread',
            legs=legs,
            description=f'Buy Put @ ${higher_strike}, Sell Put @ ${lower_strike}',
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven=[breakeven]
        )

    @staticmethod
    def long_straddle(
        strike: float,
        call_premium: float,
        put_premium: float,
        quantity: int = 1
    ) -> OptionsStrategy:
        """Long Straddle strategy"""
        legs = [
            StrategyLeg('buy', 'CE', strike, quantity, call_premium),
            StrategyLeg('buy', 'PE', strike, quantity, put_premium)
        ]

        total_premium = (call_premium + put_premium) * quantity
        breakeven_upper = strike + (call_premium + put_premium)
        breakeven_lower = strike - (call_premium + put_premium)

        return OptionsStrategy(
            name='Long Straddle',
            legs=legs,
            description=f'Buy Call + Put @ ${strike} (expect high volatility)',
            max_profit=float('inf'),
            max_loss=total_premium,
            breakeven=[breakeven_lower, breakeven_upper]
        )

    @staticmethod
    def short_straddle(
        strike: float,
        call_premium: float,
        put_premium: float,
        quantity: int = 1
    ) -> OptionsStrategy:
        """Short Straddle strategy"""
        legs = [
            StrategyLeg('sell', 'CE', strike, quantity, call_premium),
            StrategyLeg('sell', 'PE', strike, quantity, put_premium)
        ]

        total_premium = (call_premium + put_premium) * quantity
        breakeven_upper = strike + (call_premium + put_premium)
        breakeven_lower = strike - (call_premium + put_premium)

        return OptionsStrategy(
            name='Short Straddle',
            legs=legs,
            description=f'Sell Call + Put @ ${strike} (expect low volatility)',
            max_profit=total_premium,
            max_loss=float('inf'),
            breakeven=[breakeven_lower, breakeven_upper]
        )

    @staticmethod
    def long_strangle(
        call_strike: float,
        put_strike: float,
        call_premium: float,
        put_premium: float,
        quantity: int = 1
    ) -> OptionsStrategy:
        """Long Strangle strategy"""
        legs = [
            StrategyLeg('buy', 'CE', call_strike, quantity, call_premium),
            StrategyLeg('buy', 'PE', put_strike, quantity, put_premium)
        ]

        total_premium = (call_premium + put_premium) * quantity
        breakeven_upper = call_strike + (call_premium + put_premium)
        breakeven_lower = put_strike - (call_premium + put_premium)

        return OptionsStrategy(
            name='Long Strangle',
            legs=legs,
            description=f'Buy Call @ ${call_strike} + Put @ ${put_strike}',
            max_profit=float('inf'),
            max_loss=total_premium,
            breakeven=[breakeven_lower, breakeven_upper]
        )

    @staticmethod
    def iron_condor(
        lower_put_strike: float,
        higher_put_strike: float,
        lower_call_strike: float,
        higher_call_strike: float,
        premiums: Dict[str, float],  # {'lp': x, 'hp': x, 'lc': x, 'hc': x}
        quantity: int = 1
    ) -> OptionsStrategy:
        """Iron Condor strategy"""
        legs = [
            StrategyLeg('buy', 'PE', lower_put_strike, quantity, premiums['lp']),
            StrategyLeg('sell', 'PE', higher_put_strike, quantity, premiums['hp']),
            StrategyLeg('sell', 'CE', lower_call_strike, quantity, premiums['lc']),
            StrategyLeg('buy', 'CE', higher_call_strike, quantity, premiums['hc'])
        ]

        net_credit = (
            premiums['hp'] + premiums['lc'] - premiums['lp'] - premiums['hc']
        ) * quantity

        max_profit = net_credit
        max_loss = (
            (higher_put_strike - lower_put_strike) -
            (premiums['hp'] + premiums['lc'] - premiums['lp'] - premiums['hc'])
        ) * quantity

        breakeven_lower = higher_put_strike - (premiums['hp'] + premiums['lc'] - premiums['lp'] - premiums['hc'])
        breakeven_upper = lower_call_strike + (premiums['hp'] + premiums['lc'] - premiums['lp'] - premiums['hc'])

        return OptionsStrategy(
            name='Iron Condor',
            legs=legs,
            description='Neutral strategy: Profit from low volatility',
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven=[breakeven_lower, breakeven_upper]
        )

    @staticmethod
    def butterfly_spread(
        lower_strike: float,
        middle_strike: float,
        upper_strike: float,
        option_type: str,  # 'CE' or 'PE'
        premiums: Dict[str, float],  # {'lower': x, 'middle': x, 'upper': x}
        quantity: int = 1
    ) -> OptionsStrategy:
        """Butterfly Spread strategy"""
        legs = [
            StrategyLeg('buy', option_type, lower_strike, quantity, premiums['lower']),
            StrategyLeg('sell', option_type, middle_strike, quantity * 2, premiums['middle']),
            StrategyLeg('buy', option_type, upper_strike, quantity, premiums['upper'])
        ]

        net_debit = (
            premiums['lower'] + premiums['upper'] - 2 * premiums['middle']
        ) * quantity

        max_profit = ((middle_strike - lower_strike) - net_debit / quantity) * quantity
        max_loss = net_debit

        option_name = 'Call' if option_type == 'CE' else 'Put'

        return OptionsStrategy(
            name=f'{option_name} Butterfly Spread',
            legs=legs,
            description=f'Neutral strategy with limited risk/reward',
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven=[lower_strike + net_debit / quantity, upper_strike - net_debit / quantity]
        )


class StrategyAnalyzer:
    """Analyze options strategies"""

    @staticmethod
    def calculate_payoff(
        strategy: OptionsStrategy,
        spot_prices: List[float]
    ) -> List[Tuple[float, float]]:
        """Calculate strategy payoff at different spot prices"""
        payoffs = []

        for spot in spot_prices:
            total_payoff = 0

            for leg in strategy.legs:
                if leg.option_type == 'CE':
                    # Call option
                    intrinsic = max(0, spot - leg.strike)
                elif leg.option_type == 'PE':
                    # Put option
                    intrinsic = max(0, leg.strike - spot)
                else:
                    # Futures/Stock
                    intrinsic = spot - leg.strike

                if leg.action == 'buy':
                    payoff = (intrinsic - leg.premium) * leg.quantity
                else:  # sell
                    payoff = (leg.premium - intrinsic) * leg.quantity

                total_payoff += payoff

            payoffs.append((spot, total_payoff))

        return payoffs

    @staticmethod
    def find_optimal_strikes(
        current_price: float,
        iv: float,
        strategy_type: str
    ) -> Dict[str, float]:
        """Find optimal strikes for a strategy based on current price and IV"""
        # Standard deviation based on IV
        std_dev = current_price * (iv / 100) * (1 / 12) ** 0.5  # Monthly

        if strategy_type == 'bull_call_spread':
            return {
                'lower_strike': round(current_price, -2),  # ATM
                'upper_strike': round(current_price + std_dev, -2)  # 1 SD up
            }
        elif strategy_type == 'bear_put_spread':
            return {
                'higher_strike': round(current_price, -2),  # ATM
                'lower_strike': round(current_price - std_dev, -2)  # 1 SD down
            }
        elif strategy_type == 'iron_condor':
            return {
                'lower_put': round(current_price - 2 * std_dev, -2),
                'higher_put': round(current_price - std_dev, -2),
                'lower_call': round(current_price + std_dev, -2),
                'higher_call': round(current_price + 2 * std_dev, -2)
            }
        elif strategy_type == 'butterfly':
            return {
                'lower_strike': round(current_price - std_dev, -2),
                'middle_strike': round(current_price, -2),
                'upper_strike': round(current_price + std_dev, -2)
            }
        else:
            return {'strike': round(current_price, -2)}

    @staticmethod
    def get_strategy_recommendations(
        current_price: float,
        iv: float,
        outlook: str  # 'bullish', 'bearish', 'neutral', 'volatile'
    ) -> List[str]:
        """Get strategy recommendations based on market outlook"""
        recommendations = []

        if outlook == 'bullish':
            recommendations = [
                'Long Call',
                'Bull Call Spread',
                'Covered Call (if holding BTC)',
                'Short Put'
            ]
        elif outlook == 'bearish':
            recommendations = [
                'Long Put',
                'Bear Put Spread',
                'Protective Put (if holding BTC)',
                'Short Call'
            ]
        elif outlook == 'neutral':
            recommendations = [
                'Iron Condor',
                'Short Straddle',
                'Butterfly Spread',
                'Covered Call'
            ]
        elif outlook == 'volatile':
            recommendations = [
                'Long Straddle',
                'Long Strangle',
                'Long Call + Long Put'
            ]

        return recommendations
