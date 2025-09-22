"""
WebSocket Strategy Factory

Factory for creating and managing exchange-specific WebSocket strategies.
Provides both class-based factory pattern and function-based creation.
"""

import logging
from typing import Dict, Tuple, Type, Optional, Any, TYPE_CHECKING

from core.transport.websocket.strategies.strategy_set import WebSocketStrategySet
from core.transport.websocket.strategies.connection import ConnectionStrategy
from core.transport.websocket.strategies.subscription import SubscriptionStrategy
from core.transport.websocket.strategies.message_parser import MessageParser
from core.exchanges.services.exchange_mapper.factory import ExchangeMapperFactory
from core.exceptions.exchange import ConfigurationError

if TYPE_CHECKING:
    from structs.common import ExchangeEnum
else:
    from structs.common import ExchangeEnum


class WebSocketStrategyFactory:
    """
    Factory for WebSocket strategy creation and registration.
    
    Supports both registration-based factory pattern and direct creation.
    """
    
    _registered_strategies: Dict[Tuple[ExchangeEnum, bool], Tuple[Type[ConnectionStrategy], Type[SubscriptionStrategy], Type[MessageParser]]] = {}
    _logger = logging.getLogger(__name__)
    
    @classmethod
    def register_strategies(
        cls,
        exchange: ExchangeEnum,
        is_private: bool,
        connection_strategy: Type[ConnectionStrategy],
        subscription_strategy: Type[SubscriptionStrategy],
        message_parser: Type[MessageParser]
    ) -> None:
        """
        Register strategy classes for an exchange.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            is_private: Whether strategies are for private API
            connection_strategy: Connection strategy class
            subscription_strategy: Subscription strategy class  
            message_parser: Message parser class
        """
        # Use tuple key for clean separation
        key = (exchange, is_private)
        cls._registered_strategies[key] = (connection_strategy, subscription_strategy, message_parser)
        cls._logger.info(f"Registered WebSocket strategies for {exchange.value} (private={is_private})")
    
    @classmethod
    def inject(cls, exchange: ExchangeEnum, is_private: bool, config: Any = None, **kwargs) -> WebSocketStrategySet:
        """
        Create strategy set using dependency injection.
        
        Args:
            exchange: Exchange enum (clean, no suffixes)
            is_private: True for private API, False for public API
            config: Exchange configuration
            **kwargs: Additional arguments
            
        Returns:
            Complete WebSocket strategy set
            
        Raises:
            ConfigurationError: If strategy not found
        """
        # Use tuple key for lookup
        key = (exchange, is_private)
        
        if key not in cls._registered_strategies:
            available_keys = list(cls._registered_strategies.keys())
            raise ConfigurationError(f"No strategies registered for {exchange.value} (private={is_private}). Available: {available_keys}")
        
        connection_cls, subscription_cls, parser_cls = cls._registered_strategies[key]
        
        # Get exchange mappings (includes symbol mapper)
        try:
            # Pass exchange enum directly
            mapper = ExchangeMapperFactory.inject(exchange)
        except Exception as e:
            cls._logger.error(f"Failed to get mapper for {exchange.value}: {e}")
            raise ConfigurationError(f"Mapper not available for {exchange.value}")
        
        # Create strategy instances
        try:
            if config is not None and hasattr(connection_cls, '__init__'):
                # Check if connection strategy accepts config
                import inspect
                sig = inspect.signature(connection_cls.__init__)
                if 'config' in sig.parameters:
                    connection_strategy = connection_cls(config)
                else:
                    connection_strategy = connection_cls()
            else:
                connection_strategy = connection_cls()
            
            subscription_strategy = subscription_cls(mapper=mapper)
            message_parser = parser_cls(mapper)
            
            return WebSocketStrategySet(
                connection_strategy=connection_strategy,
                subscription_strategy=subscription_strategy,
                message_parser=message_parser
            )
            
        except Exception as e:
            cls._logger.error(f"Failed to create strategies for {exchange.value} (private={is_private}): {e}")
            raise ConfigurationError(f"Strategy creation failed: {e}")
    
    @classmethod
    def get_registered_strategies(cls) -> Dict[Tuple[ExchangeEnum, bool], Tuple[Type, Type, Type]]:
        """Get all registered strategies."""
        return cls._registered_strategies.copy()
    
    @classmethod
    def clear_registrations(cls) -> None:
        """Clear all registered strategies (for testing)."""
        cls._registered_strategies.clear()


def create_websocket_strategies(
    exchange_name: str,
    is_private: bool = False
) -> WebSocketStrategySet:
    """
    Create WebSocket strategies for the specified exchange.
    
    Legacy function that delegates to the factory pattern.
    
    Args:
        exchange_name: Name of the exchange (mexc, gateio)
        is_private: Whether to create private or public strategies
    
    Returns:
        Complete strategy set for the exchange
    
    Raises:
        ConfigurationError: If exchange is not supported
    """
    # Normalize exchange name to ExchangeEnum and delegate to factory
    from core.utils.exchange_utils import exchange_name_to_enum
    exchange_enum = exchange_name_to_enum(exchange_name)
    return WebSocketStrategyFactory.inject(exchange_enum, is_private)


