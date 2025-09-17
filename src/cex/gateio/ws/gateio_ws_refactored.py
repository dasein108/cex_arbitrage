"""
Gate.io WebSocket Client using WebSocketManager and Strategy Pattern

HFT-compliant WebSocket client that uses the new strategy-based architecture.
Maintains backward compatibility while leveraging composition over inheritance.

HFT COMPLIANCE: Sub-millisecond message processing, zero-copy patterns.
"""

import logging
from typing import List, Optional, Callable, Awaitable, Dict, Any

from core.cex.websocket import WebSocketManager, WebSocketManagerConfig
from core.cex.websocket import ParsedMessage, MessageType
from core.transport.websocket.strategies import WebSocketStrategySet
from cex.gateio.ws.strategies_gateio import (
    GateioPublicConnectionStrategy, GateioPublicSubscriptionStrategy, GateioPublicMessageParser,
    GateioPrivateConnectionStrategy, GateioPrivateSubscriptionStrategy, GateioPrivateMessageParser
)
from structs.exchange import Symbol, OrderBook, Trade
from core.transport.websocket.ws_client import WebSocketConfig


class GateioWebsocketPublicRefactored:
    """
    Gate.io Public WebSocket client using strategy pattern.
    
    Provides the same cex as the legacy implementation while
    using the new WebSocketManager internally for improved performance.
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        orderbook_handler: Optional[Callable[[Symbol, OrderBook], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None
    ):
        self.config = config
        self.orderbook_handler = orderbook_handler
        self.trades_handler = trades_handler
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Create strategy set for Gate.io public WebSocket
        strategies = WebSocketStrategySet(
            connection_strategy=GateioPublicConnectionStrategy(),
            subscription_strategy=GateioPublicSubscriptionStrategy(),
            message_parser=GateioPublicMessageParser()
        )
        
        # Configure manager for HFT performance
        manager_config = WebSocketManagerConfig(
            batch_processing_enabled=True,
            batch_size=50,  # Gate.io may have different optimal batch size
            max_pending_messages=1000,
            enable_performance_tracking=True
        )
        
        # Initialize WebSocket manager
        self.ws_manager = WebSocketManager(
            config=config,
            strategies=strategies,
            message_handler=self._handle_parsed_message,
            manager_config=manager_config
        )
        
        self.logger.info("Gate.io WebSocket client initialized with strategy pattern")
    
    async def initialize(self, symbols: List[Symbol]) -> None:
        """Initialize WebSocket connection and subscriptions."""
        await self.ws_manager.initialize(symbols)
        self.logger.info(f"Gate.io WebSocket initialized with {len(symbols)} symbols")
    
    async def start_symbol(self, symbol: Symbol) -> None:
        """Start streaming data for a symbol."""
        await self.ws_manager.add_symbols([symbol])
    
    async def stop_symbol(self, symbol: Symbol) -> None:
        """Stop streaming data for a symbol."""
        await self.ws_manager.remove_symbols([symbol])
    
    async def close(self) -> None:
        """Close WebSocket connection."""
        await self.ws_manager.close()
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.ws_manager.is_connected()
    
    def get_active_symbols(self) -> List[Symbol]:
        """Get list of active symbols."""
        return self.ws_manager.get_active_symbols()
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get HFT performance metrics."""
        return self.ws_manager.get_performance_metrics()
    
    async def _handle_parsed_message(self, parsed_message: ParsedMessage) -> None:
        """Handle parsed messages from WebSocketManager."""
        try:
            if parsed_message.message_type == MessageType.ORDERBOOK:
                if self.orderbook_handler and parsed_message.symbol and parsed_message.data:
                    await self.orderbook_handler(parsed_message.symbol, parsed_message.data)
            
            elif parsed_message.message_type == MessageType.TRADE:
                if self.trades_handler and parsed_message.symbol and parsed_message.data:
                    await self.trades_handler(parsed_message.symbol, parsed_message.data)
            
            elif parsed_message.message_type == MessageType.HEARTBEAT:
                self.logger.debug("Received heartbeat")
            
            elif parsed_message.message_type == MessageType.SUBSCRIPTION_CONFIRM:
                self.logger.debug("Subscription confirmed")
            
            elif parsed_message.message_type == MessageType.ERROR:
                self.logger.error(f"WebSocket error: {parsed_message.raw_data}")
            
        except Exception as e:
            self.logger.error(f"Error handling parsed message: {e}")


class GateioWebsocketPrivateRefactored:
    """
    Gate.io Private WebSocket client using strategy pattern.
    
    Provides authenticated WebSocket access for account data.
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        api_key: str,
        secret_key: str,
        balance_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        order_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ):
        self.config = config
        self.api_key = api_key
        self.secret_key = secret_key
        self.balance_handler = balance_handler
        self.order_handler = order_handler
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Create strategy set for Gate.io private WebSocket
        strategies = WebSocketStrategySet(
            connection_strategy=GateioPrivateConnectionStrategy(api_key, secret_key),
            subscription_strategy=GateioPrivateSubscriptionStrategy(),
            message_parser=GateioPrivateMessageParser()
        )
        
        # Configure manager for private WebSocket
        manager_config = WebSocketManagerConfig(
            batch_processing_enabled=False,  # Private messages are less frequent
            enable_performance_tracking=True
        )
        
        # Initialize WebSocket manager
        self.ws_manager = WebSocketManager(
            config=config,
            strategies=strategies,
            message_handler=self._handle_parsed_message,
            manager_config=manager_config
        )
        
        self.logger.info("Gate.io Private WebSocket client initialized with strategy pattern")
    
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """Initialize private WebSocket connection."""
        await self.ws_manager.initialize(symbols or [])
        self.logger.info("Gate.io Private WebSocket initialized")
    
    async def close(self) -> None:
        """Close WebSocket connection."""
        await self.ws_manager.close()
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.ws_manager.is_connected()
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return self.ws_manager.get_performance_metrics()
    
    async def _handle_parsed_message(self, parsed_message: ParsedMessage) -> None:
        """Handle parsed private messages."""
        try:
            if parsed_message.message_type == MessageType.BALANCE:
                if self.balance_handler and parsed_message.data:
                    await self.balance_handler(parsed_message.data)
            
            elif parsed_message.message_type == MessageType.ORDER:
                if self.order_handler and parsed_message.data:
                    await self.order_handler(parsed_message.data)
            
            elif parsed_message.message_type == MessageType.HEARTBEAT:
                self.logger.debug("Private WebSocket heartbeat")
            
            elif parsed_message.message_type == MessageType.ERROR:
                self.logger.error(f"Private WebSocket error: {parsed_message.raw_data}")
            
        except Exception as e:
            self.logger.error(f"Error handling private message: {e}")


# Backward compatibility factory functions
def create_gateio_public_websocket(
    config: WebSocketConfig,
    orderbook_handler: Optional[Callable[[Symbol, OrderBook], Awaitable[None]]] = None,
    trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None
) -> GateioWebsocketPublicRefactored:
    """Factory function to create Gate.io public WebSocket client."""
    return GateioWebsocketPublicRefactored(
        config=config,
        orderbook_handler=orderbook_handler,
        trades_handler=trades_handler
    )


def create_gateio_private_websocket(
    config: WebSocketConfig,
    api_key: str,
    secret_key: str,
    balance_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    order_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
) -> GateioWebsocketPrivateRefactored:
    """Factory function to create Gate.io private WebSocket client."""
    return GateioWebsocketPrivateRefactored(
        config=config,
        api_key=api_key,
        secret_key=secret_key,
        balance_handler=balance_handler,
        order_handler=order_handler
    )