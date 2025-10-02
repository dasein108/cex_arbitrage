"""
Factory for creating state machine trading strategies.

Provides a centralized factory for instantiating different trading strategy
state machines with proper configuration and dependencies.
"""

from typing import Dict, Type, Any, Optional
from enum import Enum

from exchanges.interfaces.composite import BasePrivateComposite, BasePublicComposite
from exchanges.structs import Symbol
from infrastructure.logging import get_logger
from .base_state_machine import BaseStrategyStateMachine, BaseStrategyContext


class StrategyType(Enum):
    """Available trading strategy types."""
    SPOT_FUTURES_HEDGING = "spot_futures_hedging"
    FUTURES_FUTURES_HEDGING = "futures_futures_hedging" 
    MARKET_MAKING = "market_making"
    SIMPLE_ARBITRAGE = "simple_arbitrage"


class StateMachineFactory:
    """Factory for creating trading strategy state machines."""
    
    def __init__(self):
        self._strategy_registry: Dict[StrategyType, Type[BaseStrategyStateMachine]] = {}
        self._context_registry: Dict[StrategyType, Type[BaseStrategyContext]] = {}
    
    def register_strategy(
        self,
        strategy_type: StrategyType,
        strategy_class: Type[BaseStrategyStateMachine],
        context_class: Type[BaseStrategyContext]
    ) -> None:
        """Register a strategy implementation."""
        self._strategy_registry[strategy_type] = strategy_class
        self._context_registry[strategy_type] = context_class
    
    def create_strategy(
        self,
        strategy_type: StrategyType,
        symbol: Symbol,
        private_exchange: Optional[BasePrivateComposite] = None,
        public_exchange: Optional[BasePublicComposite] = None,
        **kwargs
    ) -> BaseStrategyStateMachine:
        """
        Create a strategy state machine instance.
        
        Args:
            strategy_type: Type of strategy to create
            symbol: Trading symbol
            private_exchange: Private exchange for trading operations
            public_exchange: Public exchange for market data
            **kwargs: Additional strategy-specific parameters
            
        Returns:
            Configured strategy state machine instance
        """
        if strategy_type not in self._strategy_registry:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        
        # Get strategy and context classes
        strategy_class = self._strategy_registry[strategy_type]
        context_class = self._context_registry[strategy_type]
        
        # Create logger
        logger = get_logger(f"strategy_{strategy_type.value}")
        
        # Create context with common parameters
        context_params = {
            'strategy_name': strategy_type.value,
            'symbol': symbol,
            'logger': logger,
        }
        
        # Add exchange references if provided
        if private_exchange:
            context_params['private_exchange'] = private_exchange
        if public_exchange:
            context_params['public_exchange'] = public_exchange
        
        # Add strategy-specific parameters
        context_params.update(kwargs)
        
        # Create context and strategy
        context = context_class(**context_params)
        strategy = strategy_class(context)
        
        return strategy
    
    def get_available_strategies(self) -> list[StrategyType]:
        """Get list of available strategy types."""
        return list(self._strategy_registry.keys())


# Global factory instance
state_machine_factory = StateMachineFactory()