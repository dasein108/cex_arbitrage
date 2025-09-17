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
from core.factories.base_composite_factory import BaseCompositeFactory


class WebSocketStrategyFactory(BaseCompositeFactory[WebSocketStrategySet]):
    """
    Factory for creating WebSocket strategy sets with standardized infrastructure.
    
    Inherits from BaseCompositeFactory to provide standardized factory patterns:
    - Component configuration management (stores strategy configurations)
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
        
        Implements BaseCompositeFactory.register() for WebSocket strategies.
        
        Args:
            exchange_name: Exchange identifier with API type (e.g., 'MEXC_public', 'MEXC_private')
            strategy_config: Dictionary containing strategy class mappings
            **kwargs: Additional registration parameters
        """
        # Use base class validation and normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Validate strategy configuration using base class method
        required_strategies = ['connection', 'subscription', 'parser']
        cls._validate_strategy_config(strategy_config, required_strategies)
        
        # Register with base class registry
        cls._implementations[exchange_key] = strategy_config
    
    @classmethod
    def inject(cls, exchange_name: str, config=None, **kwargs) -> WebSocketStrategySet:
        """
        Create or retrieve WebSocket strategy set for an exchange.
        
        Implements BaseCompositeFactory.inject() with auto-dependency injection.
        
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
        
        # Get strategy configuration and delegate to assembly method
        strategy_config = cls._implementations[exchange_key]
        return cls._assemble_components(exchange_name, strategy_config, config=config, **kwargs)
    
    @classmethod
    def _assemble_components(cls, exchange_name: str, strategy_config: Dict[str, type], **kwargs) -> WebSocketStrategySet:
        """
        Assemble WebSocket strategy components into WebSocketStrategySet.
        
        Implements BaseCompositeFactory._assemble_components() for WebSocket strategies.
        
        Args:
            exchange_name: Exchange identifier
            strategy_config: Component configuration
            **kwargs: Assembly parameters including config
            
        Returns:
            Assembled WebSocketStrategySet
        """
        config = kwargs.get('config')
        if not config:
            raise ValueError("Config required for WebSocket strategy assembly")
        
        # Auto-resolve dependencies - strip _PUBLIC/_PRIVATE suffix for base exchange name
        base_exchange_name = exchange_name.replace('_PUBLIC', '').replace('_PRIVATE', '')
        resolved_kwargs = cls._resolve_dependencies(base_exchange_name, **{k: v for k, v in kwargs.items() if k != 'config'})
        
        # Create WebSocket strategy set with appropriate parameters for each strategy type
        # Connection strategy takes only config (no other dependencies)
        connection_strategy = strategy_config['connection'](config)
        
        # Create subscription and parser strategies with intelligent parameter handling
        symbol_mapper = resolved_kwargs.get('symbol_mapper')
        filtered_kwargs = {k: v for k, v in resolved_kwargs.items() if k not in ['symbol_mapper', 'exchange_mappings']}
        
        # Use base class helper for fallback constructor patterns
        subscription_strategy = cls._create_component_with_fallback(
            strategy_config['subscription'],
            exchange_name,
            {**({'symbol_mapper': symbol_mapper} if symbol_mapper else {}), **filtered_kwargs},  # Primary
            filtered_kwargs  # Fallback: without symbol_mapper
        )
        
        message_parser = cls._create_component_with_fallback(
            strategy_config['parser'],
            exchange_name,
            {**({'symbol_mapper': symbol_mapper} if symbol_mapper else {}), **filtered_kwargs},  # Primary
            filtered_kwargs  # Fallback: without symbol_mapper
        )
        
        return WebSocketStrategySet(
            connection_strategy=connection_strategy,
            subscription_strategy=subscription_strategy,
            message_parser=message_parser
        )
    
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
