"""
Strategy Signal Backtesting System

High-performance backtesting framework supporting vectorized operations
and real-time strategy signal testing.
"""

from .strategy_signal_backtester import StrategySignalBacktester
from .vectorized_strategy_backtester import VectorizedStrategyBacktester

__all__ = [
    'StrategySignalBacktester',
    'VectorizedStrategyBacktester'
]