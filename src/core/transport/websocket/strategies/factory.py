"""
WebSocket Strategy Factory

Factory for creating and managing exchange-specific WebSocket strategies.
Provides both class-based factory pattern and function-based creation.
"""

import logging
from typing import Dict, Tuple, Type, Optional, Any

from core.transport.websocket.strategies.strategy_set import WebSocketStrategySet
from core.transport.websocket.strategies.connection import ConnectionStrategy
from core.transport.websocket.strategies.subscription import SubscriptionStrategy
from core.transport.websocket.strategies.message_parser import MessageParser
from core.exchanges.services import ExchangeSymbolMapperFactory
from core.exceptions.exchange import ConfigurationError


class WebSocketStrategyFactory:
    """
    Factory for WebSocket strategy creation and registration.
    
    Supports both registration-based factory pattern and direct creation.
    """
    
    _registered_strategies: Dict[str, Tuple[Type[ConnectionStrategy], Type[SubscriptionStrategy], Type[MessageParser]]] = {}
    _logger = logging.getLogger(__name__)
    
    @classmethod
    def register_strategies(
        cls,
        exchange_name: str,
        is_private: bool,
        connection_strategy: Type[ConnectionStrategy],
        subscription_strategy: Type[SubscriptionStrategy],
        message_parser: Type[MessageParser]
    ) -> None:
        """
        Register strategy classes for an exchange.
        
        Args:
            exchange_name: Exchange name (e.g., 'mexc', 'gateio')
            is_private: Whether strategies are for private API
            connection_strategy: Connection strategy class
            subscription_strategy: Subscription strategy class  
            message_parser: Message parser class
        """
        key = f"{exchange_name}_{'private' if is_private else 'public'}"
        cls._registered_strategies[key] = (connection_strategy, subscription_strategy, message_parser)
        cls._logger.info(f"Registered WebSocket strategies for {key}")
    
    @classmethod
    def inject(cls, strategy_key: str, config: Any = None, **kwargs) -> WebSocketStrategySet:
        """
        Create strategy set using dependency injection.
        
        Args:
            strategy_key: Strategy key (e.g., 'MEXC_public', 'GATEIO_private')
            config: Exchange configuration
            **kwargs: Additional arguments
            
        Returns:
            Complete WebSocket strategy set
            
        Raises:
            ConfigurationError: If strategy key not found
        """
        if strategy_key not in cls._registered_strategies:
            available_keys = list(cls._registered_strategies.keys())
            raise ConfigurationError(f"Strategy key '{strategy_key}' not found. Available: {available_keys}")
        
        connection_cls, subscription_cls, parser_cls = cls._registered_strategies[strategy_key]
        
        # Extract exchange name from strategy key
        exchange_name = strategy_key.split('_')[0]
        
        # Get symbol mapper
        try:
            symbol_mapper = ExchangeSymbolMapperFactory.inject(exchange_name)
        except Exception as e:
            cls._logger.error(f"Failed to get symbol mapper for {exchange_name}: {e}")
            raise ConfigurationError(f"Symbol mapper not available for {exchange_name}")
        
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
            
            subscription_strategy = subscription_cls(mapper=symbol_mapper)
            message_parser = parser_cls(symbol_mapper)
            
            return WebSocketStrategySet(
                connection_strategy=connection_strategy,
                subscription_strategy=subscription_strategy,
                message_parser=message_parser
            )
            
        except Exception as e:
            cls._logger.error(f"Failed to create strategies for {strategy_key}: {e}")
            raise ConfigurationError(f"Strategy creation failed: {e}")
    
    @classmethod
    def get_registered_strategies(cls) -> Dict[str, Tuple[Type, Type, Type]]:
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
    
    Args:
        exchange_name: Name of the exchange (mexc, gateio)
        is_private: Whether to create private or public strategies
    
    Returns:
        Complete strategy set for the exchange
    
    Raises:
        ConfigurationError: If exchange is not supported
    """
    logger = logging.getLogger(__name__)
    exchange_name = exchange_name.lower()
    
    # Get symbol mapper for the exchange
    symbol_mapper = ExchangeSymbolMapperFactory.inject(exchange_name.upper())
    
    if exchange_name == "mexc":
        return _create_mexc_strategies(symbol_mapper, is_private)
    elif exchange_name == "gateio":
        return _create_gateio_strategies(symbol_mapper, is_private)
    else:
        raise ConfigurationError(
            f"Unsupported exchange: {exchange_name}. Supported: mexc, gateio"
        )


def _create_mexc_strategies(symbol_mapper, is_private: bool) -> WebSocketStrategySet:
    """Create MEXC WebSocket strategies."""
    
    if is_private:
        # Import MEXC private strategies
        from exchanges.mexc.ws.strategies.private.connection import MexcPrivateConnectionStrategy
        from exchanges.mexc.ws.strategies.private.subscription import MexcPrivateSubscriptionStrategy
        from exchanges.mexc.ws.strategies.private.message_parser import MexcPrivateMessageParser
        
        return WebSocketStrategySet(
            connection_strategy=MexcPrivateConnectionStrategy(),
            subscription_strategy=MexcPrivateSubscriptionStrategy(mapper=symbol_mapper),
            message_parser=MexcPrivateMessageParser(symbol_mapper)
        )
    else:
        # Import MEXC public strategies
        from exchanges.mexc.ws.strategies.public.connection import MexcPublicConnectionStrategy
        from exchanges.mexc.ws.strategies.public.subscription import MexcPublicSubscriptionStrategy
        from exchanges.mexc.ws.strategies.public.message_parser import MexcPublicMessageParser
        
        return WebSocketStrategySet(
            connection_strategy=MexcPublicConnectionStrategy(),
            subscription_strategy=MexcPublicSubscriptionStrategy(mapper=symbol_mapper),
            message_parser=MexcPublicMessageParser(symbol_mapper)
        )


def _create_gateio_strategies(symbol_mapper, is_private: bool) -> WebSocketStrategySet:
    """Create Gate.io WebSocket strategies."""
    
    if is_private:
        # Import Gate.io private strategies
        from exchanges.gateio.ws.strategies.private.connection import GateioPrivateConnectionStrategy
        from exchanges.gateio.ws.strategies.private.subscription import GateioPrivateSubscriptionStrategy
        from exchanges.gateio.ws.strategies.private.message_parser import GateioPrivateMessageParser
        
        return WebSocketStrategySet(
            connection_strategy=GateioPrivateConnectionStrategy(),
            subscription_strategy=GateioPrivateSubscriptionStrategy(mapper=symbol_mapper),
            message_parser=GateioPrivateMessageParser(symbol_mapper)
        )
    else:
        # Import Gate.io public strategies
        from exchanges.gateio.ws.strategies.public.connection import GateioPublicConnectionStrategy
        from exchanges.gateio.ws.strategies.public.subscription import GateioPublicSubscriptionStrategy
        from exchanges.gateio.ws.strategies.public.message_parser import GateioPublicMessageParser
        
        return WebSocketStrategySet(
            connection_strategy=GateioPublicConnectionStrategy(),
            subscription_strategy=GateioPublicSubscriptionStrategy(mapper=symbol_mapper),
            message_parser=GateioPublicMessageParser(symbol_mapper)
        )