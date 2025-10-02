"""
Base state machine interfaces and abstract classes for all trading strategies.

This module provides the foundational components for state-machine-based trading
strategies, including abstract base classes, common state definitions, and
shared utilities.
"""

from .base_state_machine import (
    BaseStrategyStateMachine,
    BaseStrategyContext,
    StrategyResult,
    StrategyState,
    StrategyError
)

from .mixins import (
    StateTransitionMixin,
    OrderManagementMixin,
    MarketDataMixin,
    PerformanceMonitoringMixin,
    RiskManagementMixin
)

from .factory import StateMachineFactory, StrategyType, state_machine_factory

from .protocols import (
    SymbolProtocol,
    OrderProtocol,
    BookTickerProtocol,
    SymbolInfoProtocol,
    PrivateExchangeProtocol,
    PublicExchangeProtocol,
    LoggerProtocol,
    SimpleSymbol,
    SimpleOrder,
    SimpleBookTicker,
    SimpleSymbolInfo,
    SimpleLogger
)

__all__ = [
    "BaseStrategyStateMachine",
    "BaseStrategyContext", 
    "StrategyResult",
    "StrategyState",
    "StrategyError",
    "StateTransitionMixin",
    "OrderManagementMixin",
    "MarketDataMixin",
    "PerformanceMonitoringMixin",
    "RiskManagementMixin",
    "StateMachineFactory",
    "StrategyType",
    "state_machine_factory",
    # Protocols
    "SymbolProtocol",
    "OrderProtocol",
    "BookTickerProtocol",
    "SymbolInfoProtocol",
    "PrivateExchangeProtocol",
    "PublicExchangeProtocol",
    "LoggerProtocol",
    # Simple implementations
    "SimpleSymbol",
    "SimpleOrder",
    "SimpleBookTicker",
    "SimpleSymbolInfo",
    "SimpleLogger"
]