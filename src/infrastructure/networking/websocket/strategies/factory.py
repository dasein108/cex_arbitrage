"""
WebSocket Strategy Factory

Factory for creating and managing exchange-specific WebSocket strategies.
Provides both class-based factory pattern and function-based creation.
"""

from typing import Dict, Tuple, Type, Any, TYPE_CHECKING

from infrastructure.networking.websocket.strategies.strategy_set import WebSocketStrategySet
from infrastructure.networking.websocket.strategies.connection import ConnectionStrategy
from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from exchanges.services.exchange_mapper.factory import ExchangeMapperFactory
from infrastructure.exceptions.exchange import ConfigurationError

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, LoggingTimer

from exchanges.structs import ExchangeEnum


class WebSocketStrategyFactory:
    """
    Factory for WebSocket strategy creation and registration.
    
    Supports both registration-based factory pattern and direct creation.
    """
    
    _registered_strategies: Dict[Tuple[ExchangeEnum, bool], Tuple[Type[ConnectionStrategy], Type[SubscriptionStrategy], Type[MessageParser]]] = {}
    
    # Initialize HFT logger for factory operations
    _logger = get_strategy_logger('ws.strategy.factory', ['core', 'factory', 'ws', 'strategy'])
    
    # Track factory initialization
    _logger.info("WebSocketStrategyFactory initialized")
    _logger.metric("ws_strategy_factories_initialized", 1, tags={"component": "factory"})
    
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
        
        # Log strategy registration with structured data
        api_type = 'private' if is_private else 'public'
        cls._logger.info("WebSocket strategies registered",
                        exchange=exchange.value,
                        api_type=api_type,
                        connection_strategy=connection_strategy.__name__,
                        subscription_strategy=subscription_strategy.__name__,
                        message_parser=message_parser.__name__)
        
        # Track strategy registration metrics
        cls._logger.metric("ws_strategy_registrations", 1,
                          tags={"exchange": exchange.value, "api_type": api_type})
    
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
        api_type = 'private' if is_private else 'public'
        
        # Track strategy injection performance
        with LoggingTimer(cls._logger, "ws_strategy_injection") as timer:
            cls._logger.info("Starting WebSocket strategy injection",
                           exchange=exchange.value,
                           api_type=api_type,
                           has_config=config is not None)
            
            # Use tuple key for lookup
            key = (exchange, is_private)
            
            if key not in cls._registered_strategies:
                available_keys = list(cls._registered_strategies.keys())
                cls._logger.error("Strategy not found for exchange",
                                exchange=exchange.value,
                                api_type=api_type,
                                available_strategies=[f"{k[0].value}_{k[1]}" for k in available_keys])
                
                # Track failed injection
                cls._logger.metric("ws_strategy_injections", 1,
                                  tags={"exchange": exchange.value, "api_type": api_type, "status": "not_found"})
                
                raise ConfigurationError(f"No strategies registered for {exchange.value} (private={is_private}). Available: {available_keys}")
            
            connection_cls, subscription_cls, parser_cls = cls._registered_strategies[key]
            
            # Get exchange mappings (includes symbol mapper)
            try:
                cls._logger.debug("Creating exchange mapper",
                                exchange=exchange.value)
                mapper = ExchangeMapperFactory.inject(exchange)
            except Exception as e:
                cls._logger.error("Failed to create mapper",
                                exchange=exchange.value,
                                error_type=type(e).__name__,
                                error_message=str(e))
                
                # Track mapper creation failure
                cls._logger.metric("ws_strategy_injections", 1,
                                  tags={"exchange": exchange.value, "api_type": api_type, "status": "mapper_failed"})
                
                raise ConfigurationError(f"Mapper not available for {exchange.value}")
            
            # Create strategy instances
            try:
                cls._logger.debug("Creating strategy instances",
                                exchange=exchange.value,
                                connection_strategy=connection_cls.__name__,
                                subscription_strategy=subscription_cls.__name__,
                                message_parser=parser_cls.__name__)
                
                # Create connection strategy with config if supported
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
                
                # Create logger for message parser
                api_type_str = "private" if is_private else "public"
                exchange_name = exchange.value.lower()
                parser_logger = get_strategy_logger(
                    f'ws.message_parser.{exchange_name}.{api_type_str}',
                    [exchange_name, 'ws', 'message_parser', api_type_str]
                )
                message_parser = parser_cls(mapper, parser_logger)
                
                strategy_set = WebSocketStrategySet(
                    connection_strategy=connection_strategy,
                    subscription_strategy=subscription_strategy,
                    message_parser=message_parser
                )
                
                # Log successful strategy creation
                cls._logger.info("WebSocket strategy set created successfully",
                               exchange=exchange.value,
                               api_type=api_type,
                               creation_time_ms=timer.elapsed_ms)
                
                # Track successful injection
                cls._logger.metric("ws_strategy_injections", 1,
                                  tags={"exchange": exchange.value, "api_type": api_type, "status": "success"})
                
                cls._logger.metric("ws_strategy_injection_duration_ms", timer.elapsed_ms,
                                  tags={"exchange": exchange.value, "api_type": api_type})
                
                return strategy_set
                
            except Exception as e:
                cls._logger.error("Failed to create strategy instances",
                                exchange=exchange.value,
                                api_type=api_type,
                                error_type=type(e).__name__,
                                error_message=str(e),
                                creation_time_ms=timer.elapsed_ms)
                
                # Track strategy creation failure
                cls._logger.metric("ws_strategy_injections", 1,
                                  tags={"exchange": exchange.value, "api_type": api_type, "status": "creation_failed"})
                
                raise ConfigurationError(f"Strategy creation failed: {e}")
    
    @classmethod
    def get_registered_strategies(cls) -> Dict[Tuple[ExchangeEnum, bool], Tuple[Type, Type, Type]]:
        """Get all registered strategies."""
        return cls._registered_strategies.copy()
    
    @classmethod
    def clear_registrations(cls) -> None:
        """Clear all registered strategies (for testing)."""
        cls._registered_strategies.clear()

