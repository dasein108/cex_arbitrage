"""
WebSocket Strategy Factory

HFT-compliant factory for WebSocket strategy sets using the standardized
BaseExchangeFactory infrastructure with enhanced auto-dependency injection.

HFT COMPLIANCE: Sub-millisecond strategy execution, zero-copy patterns.
Enhanced with generic dependency injection for factory-to-factory coordination.
"""

from typing import List, Dict, Type, Optional, Any

from core.transport.websocket.strategies import (ConnectionStrategy, SubscriptionStrategy, MessageParser,
                                                 WebSocketStrategySet)
from core.factories.base_exchange_factory import BaseExchangeFactory


class WebSocketStrategyFactory(BaseExchangeFactory[WebSocketStrategySet]):
    """
    Factory for creating WebSocket strategy sets with standardized infrastructure.
    
    Inherits from BaseExchangeFactory to provide standardized factory patterns:
    - Registry management via base class (_implementations stores strategy configurations)
    - Enhanced auto-injection with symbol_mapper and exchange_mappings
    - Standardized inject() method for consistent API
    - Factory-to-factory coordination for seamless dependency management
    
    HFT COMPLIANT: Fast strategy creation with pre-validated combinations.
    Strategy sets are registered by exchange and API type (public/private).
    """
    
    @classmethod
    def register(
        cls,
        exchange_name: str,
        strategy_config: Dict[str, type],
        **kwargs
    ) -> None:
        """
        Register strategy configuration for an exchange.
        
        Implements BaseExchangeFactory.register() for WebSocket strategies.
        
        Args:
            exchange_name: Exchange identifier with API type (e.g., 'MEXC_public', 'MEXC_private')
            strategy_config: Dictionary containing strategy class mappings
            **kwargs: Additional registration parameters
        """
        # Use base class validation and normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Validate strategy configuration
        required_strategies = ['connection', 'subscription', 'parser']
        for strategy_type in required_strategies:
            if strategy_type not in strategy_config:
                raise ValueError(f"Missing required strategy: {strategy_type}")
        
        # Register with base class registry
        cls._implementations[exchange_key] = strategy_config
    
    @classmethod
    def inject(cls, exchange_name: str, config=None, **kwargs) -> WebSocketStrategySet:
        """
        Create or retrieve WebSocket strategy set for an exchange.
        
        Implements BaseExchangeFactory.inject() with auto-dependency injection.
        
        Args:
            exchange_name: Exchange identifier with API type (e.g., 'MEXC_public')
            config: Optional configuration object
            **kwargs: Additional creation parameters
            
        Returns:
            WebSocketStrategySet with configured strategies and auto-injected dependencies
            
        Raises:
            ValueError: If exchange not registered
        """
        # Use base class normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Check if registered
        if exchange_key not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No strategies registered for {exchange_name}. Available: {available}"
            )
        
        # Validate config is provided for WebSocket strategies
        if config is None:
            raise ValueError(f"Config required for WebSocket strategy creation for {exchange_name}")
        
        # For strategy sets, we don't use singleton pattern as they need fresh dependencies
        # Get strategy configuration
        strategy_config = cls._implementations[exchange_key]
        
        # Auto-resolve dependencies - strip _PUBLIC/_PRIVATE suffix for base exchange name
        base_exchange_name = exchange_name.replace('_PUBLIC', '').replace('_PRIVATE', '')
        resolved_kwargs = cls._resolve_dependencies(base_exchange_name, config=config, **kwargs)
        
        # Create WebSocket strategy set with appropriate parameters for each strategy type
        # Connection strategy takes only config (no other dependencies)
        connection_strategy = strategy_config['connection'](config)
        
        # Create subscription and parser strategies with appropriate parameters
        # Some strategies (like private) don't need symbol_mapper, so try with and without
        symbol_mapper = resolved_kwargs.get('symbol_mapper')
        filtered_kwargs = {k: v for k, v in resolved_kwargs.items() if k not in ['symbol_mapper', 'exchange_mappings']}
        
        # Try creating subscription strategy - first with symbol_mapper, then without
        try:
            subscription_strategy = strategy_config['subscription'](symbol_mapper, **filtered_kwargs)
        except TypeError:
            # Constructor doesn't take symbol_mapper (e.g., private strategies)
            subscription_strategy = strategy_config['subscription'](**filtered_kwargs)
        
        # Try creating message parser - first with symbol_mapper, then without  
        try:
            message_parser = strategy_config['parser'](symbol_mapper, **filtered_kwargs)
        except TypeError:
            # Constructor doesn't take symbol_mapper (e.g., private strategies)
            message_parser = strategy_config['parser'](**filtered_kwargs)
        
        return WebSocketStrategySet(
            connection_strategy=connection_strategy,
            subscription_strategy=subscription_strategy,
            message_parser=message_parser
        )
    
    # Note: _resolve_dependencies() inherited from BaseExchangeFactory

    @classmethod
    def register_strategies(
            cls,
            exchange: str,
            is_private: bool,
            connection_strategy_cls: Type[ConnectionStrategy],
            subscription_strategy_cls: Type[SubscriptionStrategy],
            message_parser_cls: Type[MessageParser]
    ) -> None:
        """
        Register strategy implementations for an exchange.
        
        Legacy method that delegates to the standardized register() method.
        
        Args:
            exchange: Exchange name (e.g., 'mexc', 'gateio')
            is_private: True for private WebSocket, False for public
            connection_strategy_cls: ConnectionStrategy implementation
            subscription_strategy_cls: SubscriptionStrategy implementation
            message_parser_cls: MessageParser implementation
        """
        # Create strategy configuration
        strategy_config = {
            'connection': connection_strategy_cls,
            'subscription': subscription_strategy_cls,
            'parser': message_parser_cls
        }
        
        # Use standardized register method
        exchange_key = f"{exchange}_{'private' if is_private else 'public'}"
        cls.register(exchange_key, strategy_config)

    @classmethod
    def create_strategies(
            cls,
            exchange: str,
            is_private: bool,
            symbol_mapper_factory=None,
            **kwargs
    ) -> WebSocketStrategySet:
        """
        Create strategy set for an exchange with optional dependency injection.
        
        Legacy method that delegates to the standardized inject() method.
        
        Args:
            exchange: Exchange name
            is_private: True for private WebSocket
            symbol_mapper_factory: Optional factory for symbol mapper injection (deprecated)
            **kwargs: Strategy constructor arguments
            
        Returns:
            WebSocketStrategySet with configured strategies
            
        Note: Now uses standardized inject() method with auto-dependency injection
        """
        exchange_key = f"{exchange}_{'private' if is_private else 'public'}"
        
        # Delegate to standardized inject() method (auto-injection handles dependencies)
        return cls.inject(exchange_key, **kwargs)

    @classmethod
    def list_available_strategies(cls) -> Dict[str, List[str]]:
        """
        List all registered strategy combinations.
        
        Uses base class registry for consistent state management.
        
        Returns:
            Dictionary mapping exchange names to available types
        """
        result = {}
        for key in cls.get_registered_exchanges():
            if '_' in key:
                exchange, ws_type = key.rsplit('_', 1)
                if exchange not in result:
                    result[exchange] = []
                result[exchange].append(ws_type)
        return result
