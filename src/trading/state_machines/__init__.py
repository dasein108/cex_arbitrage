"""
Trading state machines module.

This module provides state machine implementations for various trading strategies
including hedging, market making, and arbitrage. All strategies follow a common
architecture with base interfaces and shared utilities.

Usage Example:
    from trading.state_machines import state_machine_factory, StrategyType
    from exchanges.structs import Symbol, AssetName
    
    # Create symbol
    symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False)
    
    # Create strategy
    strategy = state_machine_factory.create_strategy(
        strategy_type=StrategyType.SIMPLE_ARBITRAGE,
        symbol=symbol,
        position_size_usdt=100.0,
        # ... other parameters
    )
    
    # Execute strategy
    result = await strategy.execute_strategy()
    print(f"Strategy completed with profit: ${result.profit_usdt}")
"""

# Base interfaces and utilities
from .base import (
    BaseStrategyStateMachine,
    BaseStrategyContext,
    StrategyResult,
    StrategyState,
    StrategyError,
    StateTransitionMixin,
    OrderManagementMixin,
    MarketDataMixin,
    PerformanceMonitoringMixin,
    RiskManagementMixin,
    StateMachineFactory,
    StrategyType,
    state_machine_factory,
    # Protocols and simple implementations
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

# Strategy implementations
from .hedging import (
    SpotFuturesHedgingStateMachine,
    SpotFuturesHedgingContext,
    SpotFuturesHedgingState,
    FuturesFuturesHedgingStateMachine,
    FuturesFuturesHedgingContext,
    FuturesFuturesHedgingState
)

from .market_making import (
    MarketMakingStateMachine,
    MarketMakingContext,
    MarketMakingState
)

from .arbitrage import (
    SimpleArbitrageStateMachine,
    SimpleArbitrageContext,
    SimpleArbitrageState
)

# Register all strategies with the factory
def _register_strategies():
    """Register all available strategies with the factory."""
    
    # Register spot/futures hedging
    state_machine_factory.register_strategy(
        StrategyType.SPOT_FUTURES_HEDGING,
        SpotFuturesHedgingStateMachine,
        SpotFuturesHedgingContext
    )
    
    # Register futures/futures hedging
    state_machine_factory.register_strategy(
        StrategyType.FUTURES_FUTURES_HEDGING,
        FuturesFuturesHedgingStateMachine,
        FuturesFuturesHedgingContext
    )
    
    # Register market making
    state_machine_factory.register_strategy(
        StrategyType.MARKET_MAKING,
        MarketMakingStateMachine,
        MarketMakingContext
    )
    
    # Register simple arbitrage
    state_machine_factory.register_strategy(
        StrategyType.SIMPLE_ARBITRAGE,
        SimpleArbitrageStateMachine,
        SimpleArbitrageContext
    )

# Auto-register strategies on module import
_register_strategies()

__all__ = [
    # Base interfaces
    "BaseStrategyStateMachine",
    "BaseStrategyContext",
    "StrategyResult",
    "StrategyState", 
    "StrategyError",
    
    # Mixins
    "StateTransitionMixin",
    "OrderManagementMixin",
    "MarketDataMixin",
    "PerformanceMonitoringMixin",
    "RiskManagementMixin",
    
    # Factory
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
    "SimpleLogger",
    
    # Hedging strategies
    "SpotFuturesHedgingStateMachine",
    "SpotFuturesHedgingContext",
    "SpotFuturesHedgingState",
    "FuturesFuturesHedgingStateMachine", 
    "FuturesFuturesHedgingContext",
    "FuturesFuturesHedgingState",
    
    # Market making
    "MarketMakingStateMachine",
    "MarketMakingContext",
    "MarketMakingState",
    
    # Arbitrage
    "SimpleArbitrageStateMachine",
    "SimpleArbitrageContext",
    "SimpleArbitrageState"
]