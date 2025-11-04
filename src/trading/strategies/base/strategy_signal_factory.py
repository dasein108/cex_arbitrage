"""
Strategy Signal Factory

Factory pattern implementation for creating strategy signal instances.
Eliminates if/else chains and provides type-safe strategy instantiation.
"""

from typing import Dict, Type, Any, Optional
import logging

from trading.strategies.base.strategy_signal_interface import StrategySignalInterface


class StrategySignalFactory:
    """
    Factory for creating strategy signal instances.
    
    Provides centralized strategy instantiation with registration pattern
    to eliminate if/else chains throughout the codebase.
    """
    
    _strategies: Dict[str, Type[StrategySignalInterface]] = {}
    _logger = logging.getLogger(__name__)
    
    @classmethod
    def register_strategy(cls, strategy_type: str, strategy_class: Type[StrategySignalInterface]) -> None:
        """
        Register a strategy signal implementation.
        
        Args:
            strategy_type: Unique strategy identifier
            strategy_class: Strategy implementation class
        """
        if strategy_type in cls._strategies:
            cls._logger.warning(f"Overriding existing strategy: {strategy_type}")
        
        cls._strategies[strategy_type] = strategy_class
        cls._logger.info(f"Registered strategy signal: {strategy_type}")
    
    @classmethod
    def create_strategy(cls, strategy_type: str, **params) -> StrategySignalInterface:
        """
        Create a strategy signal instance.
        
        Args:
            strategy_type: Strategy type identifier
            **params: Parameters to pass to strategy constructor
            
        Returns:
            Strategy signal instance
            
        Raises:
            ValueError: If strategy type is not registered
        """
        if strategy_type not in cls._strategies:
            available = list(cls._strategies.keys())
            raise ValueError(f"Unknown strategy type: {strategy_type}. Available: {available}")
        
        strategy_class = cls._strategies[strategy_type]
        return strategy_class(strategy_type=strategy_type, **params)
    
    @classmethod
    def get_available_strategies(cls) -> list[str]:
        """
        Get list of available strategy types.
        
        Returns:
            List of registered strategy type names
        """
        return list(cls._strategies.keys())
    
    @classmethod
    def is_strategy_registered(cls, strategy_type: str) -> bool:
        """
        Check if a strategy type is registered.
        
        Args:
            strategy_type: Strategy type to check
            
        Returns:
            True if strategy is registered, False otherwise
        """
        return strategy_type in cls._strategies
    
    @classmethod
    def clear_registry(cls) -> None:
        """Clear all registered strategies (mainly for testing)."""
        cls._strategies.clear()
        cls._logger.info("Cleared all registered strategies")


# Convenience functions for factory usage

def create_strategy_signal(strategy_type: str, **params) -> StrategySignalInterface:
    """
    Convenience function to create a strategy signal.
    
    Args:
        strategy_type: Strategy type identifier
        **params: Parameters to pass to strategy constructor
        
    Returns:
        Strategy signal instance
    """
    return StrategySignalFactory.create_strategy(strategy_type, **params)


def register_strategy_signal(strategy_type: str, strategy_class: Type[StrategySignalInterface]) -> None:
    """
    Convenience function to register a strategy signal.
    
    Args:
        strategy_type: Unique strategy identifier
        strategy_class: Strategy implementation class
    """
    StrategySignalFactory.register_strategy(strategy_type, strategy_class)


def get_available_strategy_signals() -> list[str]:
    """
    Get list of available strategy signal types.
    
    Returns:
        List of registered strategy type names
    """
    return StrategySignalFactory.get_available_strategies()


# Default strategy type mappings
DEFAULT_STRATEGY_MAPPINGS = {
    'reverse_delta_neutral': 'reverse_delta_neutral',
    'delta_neutral': 'reverse_delta_neutral',  # Alias
    'inventory_spot': 'inventory_spot',
    'volatility_harvesting': 'volatility_harvesting',
    'volatility': 'volatility_harvesting',  # Alias
}


def normalize_strategy_type(strategy_type: str) -> str:
    """
    Normalize strategy type name to canonical form.
    
    Args:
        strategy_type: Input strategy type (may be alias)
        
    Returns:
        Canonical strategy type name
    """
    return DEFAULT_STRATEGY_MAPPINGS.get(strategy_type, strategy_type)