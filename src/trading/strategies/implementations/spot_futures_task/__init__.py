"""
Simplified Spot-Futures Task Strategy

A minimalistic arbitrage strategy focused on market-market order execution
between 1 spot exchange and 1 futures exchange using dynamic threshold optimization.

Key Features:
- Simple market-market order execution (no limit orders)
- Fee-adjusted quantile-based entry/exit thresholds
- Dynamic column keys for backtesting framework compatibility
- Minimal configuration and state management
- Optimal threshold calculation integrated from signal logic

Strategy Components:
- SpotFuturesTaskContext: Minimal configuration context
- SpotFuturesStrategyTask: Core strategy execution engine with simplified logic
"""

from .spot_futures_task import (
    SpotFuturesTaskContext,
    SpotFuturesStrategyTask,
    create_spot_futures_strategy_task
)

__all__ = [
    'SpotFuturesTaskContext',
    'SpotFuturesStrategyTask', 
    'create_spot_futures_strategy_task',
]