"""
3-Exchange Delta Neutral Arbitrage Strategy

High-performance state machine for coordinating delta neutral arbitrage across
Gate.io spot/futures and MEXC spot exchanges.

Core Components:
- State Machine: Sophisticated state management for multi-exchange coordination
- Position Management: Real-time tracking of delta neutral positions
- Risk Management: Comprehensive risk controls and monitoring
- Performance Tracking: Real-time metrics and alerting

Optimized for HFT requirements with sub-50ms execution cycles.
"""

from .state_machine import (
    DeltaNeutralArbitrageStateMachine,
    StrategyState,
    StrategyConfiguration,
    PositionType,
    PositionData,
    DeltaNeutralStatus,
    ArbitrageOpportunityState
)

__all__ = [
    "DeltaNeutralArbitrageStateMachine",
    "StrategyState", 
    "StrategyConfiguration",
    "PositionType",
    "PositionData",
    "DeltaNeutralStatus",
    "ArbitrageOpportunityState"
]