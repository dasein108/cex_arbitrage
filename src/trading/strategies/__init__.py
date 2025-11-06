"""
Trading Strategies Package

Strategy signal implementations for arbitrage trading with unified interface
for both real-time trading and backtesting operations.
"""

from trading.strategies.base.base_strategy_signal import BaseStrategySignal
from trading.strategies.base.strategy_signal_factory import (
    StrategySignalFactory,
    create_strategy_signal,
    register_strategy_signal,
    get_available_strategy_signals,
    normalize_strategy_type
)

__all__ = [
    'BaseStrategySignal',
    'StrategySignalFactory',
    'create_strategy_signal',
    'register_strategy_signal',
    'get_available_strategy_signals',
    'normalize_strategy_type'
]