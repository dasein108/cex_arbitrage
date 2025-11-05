"""
Strategy Signal Backtesting System

High-performance backtesting framework supporting vectorized operations
and real-time strategy signal testing.

Note: PositionTracker functionality has been moved internal to individual
strategy implementations for better performance and isolation.
"""

from .vectorized_strategy_backtester import VectorizedStrategyBacktester


__all__ = [
    'VectorizedStrategyBacktester',
]