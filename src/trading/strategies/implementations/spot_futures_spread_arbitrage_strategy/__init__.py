"""
Spot-Futures Spread Arbitrage Strategy

A delta-neutral arbitrage strategy that captures basis spread opportunities
between spot and futures markets on the same exchange.

Key Features:
- Delta-neutral position management (long spot + short futures)
- Basis spread signal generation using historical candle data
- Dynamic spread validation with ArbStats thresholds
- Real-time position rebalancing
- Comprehensive PnL tracking

Strategy Components:
- SpotFuturesArbitrageTask: Main strategy execution engine
- Position: Unified position tracking with PnL calculation
- Context: Strategy configuration and state management
"""

from .spot_futures_arbitrage_task import (
    SpotFuturesArbitrageTask,
    SpotFuturesArbitrageTaskContext,
    SPOT_FUTURES_ARBITRAGE_TASK_TYPE
)

__all__ = [
    'SpotFuturesArbitrageTask',
    'SpotFuturesArbitrageTaskContext', 
    'SPOT_FUTURES_ARBITRAGE_TASK_TYPE',
]