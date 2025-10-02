"""
Hedging strategy state machines.

This module contains state machine implementations for various hedging strategies
including spot/futures hedging and futures/futures cross-exchange arbitrage.
"""

from .spot_futures_hedging import (
    SpotFuturesHedgingStateMachine,
    SpotFuturesHedgingContext,
    SpotFuturesHedgingState
)

from .futures_futures_hedging import (
    FuturesFuturesHedgingStateMachine,
    FuturesFuturesHedgingContext,
    FuturesFuturesHedgingState
)

__all__ = [
    "SpotFuturesHedgingStateMachine",
    "SpotFuturesHedgingContext", 
    "SpotFuturesHedgingState",
    "FuturesFuturesHedgingStateMachine",
    "FuturesFuturesHedgingContext",
    "FuturesFuturesHedgingState"
]