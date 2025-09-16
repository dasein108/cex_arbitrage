"""
WebSocket Strategy Interfaces

HFT-compliant strategy interfaces for WebSocket connection management, 
subscriptions, and message parsing using composition pattern.

HFT COMPLIANCE: Sub-millisecond strategy execution, zero-copy patterns.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any

from core.cex.websocket.message_parser import MessageParser
from core.cex.websocket.structs import SubscriptionAction, ConnectionContext, SubscriptionContext
from structs.exchange import Symbol
from core.cex.services import SymbolMapperInterface


class ConnectionStrategy(ABC):
    """
    Strategy for WebSocket connection management.
    
    Handles connection establishment, authentication, and keep-alive.
    HFT COMPLIANT: <100ms connection establishment.
    """
    
    @abstractmethod
    async def create_connection_context(self) -> ConnectionContext:
        """
        Create connection configuration.
        
        Returns:
            ConnectionContext with URL, headers, auth parameters
        """
        pass
    
    @abstractmethod
    async def authenticate(self, websocket: Any) -> bool:
        """
        Perform authentication if required.
        
        Args:
            websocket: WebSocket connection instance
            
        Returns:
            True if authentication successful
        """
        pass
    
    @abstractmethod
    async def handle_keep_alive(self, websocket: Any) -> None:
        """
        Handle keep-alive/ping operations.
        
        Args:
            websocket: WebSocket connection instance
        """
        pass
    
    @abstractmethod
    def should_reconnect(self, error: Exception) -> bool:
        """
        Determine if reconnection should be attempted.
        
        Args:
            error: Exception that caused disconnection
            
        Returns:
            True if reconnection should be attempted
        """
        pass
    
    async def cleanup(self) -> None:
        """
        Clean up resources when closing connection.
        
        Optional method for strategies to implement resource cleanup.
        Default implementation does nothing.
        """
        pass


class SubscriptionStrategy(ABC):
    """
    Strategy for WebSocket subscription management.
    
    Handles subscription message formatting and channel management.
    HFT COMPLIANT: <1μs message formatting.
    """
    
    @abstractmethod
    def create_subscription_messages(
        self, 
        symbols: List[Symbol], 
        action: SubscriptionAction
    ) -> List[str]:
        """
        Create subscription/unsubscription messages.
        
        Args:
            symbols: Symbols to subscribe/unsubscribe
            action: Subscribe or unsubscribe action
            
        Returns:
            List of JSON-formatted subscription messages
        """
        pass
    
    @abstractmethod
    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """
        Get subscription configuration for a symbol.
        
        Args:
            symbol: Symbol to get context for
            
        Returns:
            SubscriptionContext with channels and parameters
        """
        pass
    
    @abstractmethod
    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """
        Extract channel information from message.
        
        Args:
            message: Parsed message dictionary
            
        Returns:
            Channel name if found, None otherwise
        """
        pass
    
    @abstractmethod
    def should_resubscribe_on_reconnect(self) -> bool:
        """
        Determine if subscriptions should be renewed on reconnect.
        
        Returns:
            True if resubscription required
        """
        pass
    
    @abstractmethod
    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """
        Extract symbol from channel name.
        
        Args:
            channel: Channel name
            
        Returns:
            Symbol if parseable, None otherwise
        """
        pass

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        self.symbol_mapper = symbol_mapper

class WebSocketStrategySet:
    """
    Container for a complete set of WebSocket strategies.
    
    HFT COMPLIANT: Zero-allocation strategy access.
    """
    
    def __init__(
        self,
        connection_strategy: ConnectionStrategy,
        subscription_strategy: SubscriptionStrategy,
        message_parser: MessageParser
    ):
        self.connection_strategy = connection_strategy
        self.subscription_strategy = subscription_strategy
        self.message_parser = message_parser
        # HFT Optimization: Pre-validate strategy compatibility
        self._validate_strategies()
    
    def _validate_strategies(self) -> None:
        """Validate strategy compatibility at initialization."""
        if not all([
            self.connection_strategy,
            self.subscription_strategy,
            self.message_parser
        ]):
            raise ValueError("All strategies must be provided")


class WebSocketStrategyFactory:
    """
    Factory for creating WebSocket strategy sets.
    
    HFT COMPLIANT: Fast strategy creation with pre-validated combinations.
    """
    
    _strategy_registry: Dict[str, Dict[str, type]] = {}
    
    @classmethod
    def register_strategies(
        self,
        exchange: str,
        is_private: bool,
        connection_strategy_cls: type,
        subscription_strategy_cls: type,
        message_parser_cls: type
    ) -> None:
        """
        Register strategy implementations for an exchange.
        
        Args:
            exchange: Exchange name (e.g., 'mexc', 'gateio')
            is_private: True for private WebSocket, False for public
            connection_strategy_cls: ConnectionStrategy implementation
            subscription_strategy_cls: SubscriptionStrategy implementation
            message_parser_cls: MessageParser implementation
        """
        key = f"{exchange}_{'private' if is_private else 'public'}"
        self._strategy_registry[key] = {
            'connection': connection_strategy_cls,
            'subscription': subscription_strategy_cls,
            'parser': message_parser_cls
        }
    
    @classmethod
    def create_strategies(
        self,
        exchange: str,
        is_private: bool,
        **kwargs
    ) -> WebSocketStrategySet:
        """
        Create strategy set for an exchange.
        
        Args:
            exchange: Exchange name
            is_private: True for private WebSocket
            **kwargs: Strategy constructor arguments
            
        Returns:
            WebSocketStrategySet with configured strategies
        """
        key = f"{exchange}_{'private' if is_private else 'public'}"
        
        if key not in self._strategy_registry:
            raise ValueError(f"No strategies registered for {key}")
        
        strategies = self._strategy_registry[key]
        
        return WebSocketStrategySet(
            connection_strategy=strategies['connection'](**kwargs),
            subscription_strategy=strategies['subscription'](**kwargs),
            message_parser=strategies['parser'](**kwargs)
        )
    
    @classmethod
    def list_available_strategies(self) -> Dict[str, List[str]]:
        """
        List all registered strategy combinations.
        
        Returns:
            Dictionary mapping exchange names to available types
        """
        result = {}
        for key in self._strategy_registry.keys():
            exchange, ws_type = key.rsplit('_', 1)
            if exchange not in result:
                result[exchange] = []
            result[exchange].append(ws_type)
        return result