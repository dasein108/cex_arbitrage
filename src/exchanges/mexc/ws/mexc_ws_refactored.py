"""
MEXC WebSocket Client using WebSocketManager and Strategy Pattern

HFT-compliant WebSocket client that uses the new strategy-based architecture.
Maintains backward compatibility while leveraging composition over inheritance.

HFT COMPLIANCE: Sub-millisecond message processing, zero-copy patterns.
"""

import logging
from typing import List, Optional, Callable, Awaitable, Dict, Any

from core.cex.websocket import WebSocketManager, WebSocketManagerConfig
from core.cex.websocket import WebSocketStrategySet, ParsedMessage, MessageType
from exchanges.mexc.ws.strategies_mexc import (
    MexcPublicConnectionStrategy, MexcPublicSubscriptionStrategy, MexcPublicMessageParser,
    MexcPrivateConnectionStrategy, MexcPrivateSubscriptionStrategy, MexcPrivateMessageParser
)
from structs.exchange import Symbol, OrderBook, Trade
from structs.config import ExchangeConfig
from core.transport.websocket.ws_client import WebSocketConfig


class MexcWebsocketPublicRefactored:
    """
    MEXC Public WebSocket client using strategy pattern.
    
    Provides the same cex as the legacy implementation while
    using the new WebSocketManager internally for improved performance.
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        orderbook_handler: Optional[Callable[[Symbol, OrderBook], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None
    ):
        self.config = config
        self.orderbook_handler = orderbook_handler
        self.trades_handler = trades_handler
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Create strategy set for MEXC public WebSocket
        strategies = WebSocketStrategySet(
            connection_strategy=MexcPublicConnectionStrategy(config),
            subscription_strategy=MexcPublicSubscriptionStrategy(),
            message_parser=MexcPublicMessageParser()
        )
        
        # Configure manager for HFT performance
        manager_config = WebSocketManagerConfig(
            batch_processing_enabled=True,
            batch_size=100,
            max_pending_messages=1000,
            enable_performance_tracking=True
        )
        
        # Create WebSocket configuration from ExchangeConfig
        ws_config = WebSocketConfig(
            name="mexc_public",
            url=config.websocket_url,
            timeout=30.0,
            ping_interval=20.0,
            ping_timeout=10.0,
            close_timeout=5.0,
            max_reconnect_attempts=10,
            reconnect_delay=1.0,
            reconnect_backoff=2.0,
            max_reconnect_delay=60.0,
            max_message_size=1024 * 1024,  # 1MB
            max_queue_size=1000,
            heartbeat_interval=30.0,
            enable_compression=True,
            text_encoding="utf-8"
        )
        
        # Initialize WebSocket manager
        self.ws_manager = WebSocketManager(
            config=ws_config,
            strategies=strategies,
            message_handler=self._handle_parsed_message,
            manager_config=manager_config
        )
        
        self.logger.info("MEXC WebSocket client initialized with strategy pattern")
    
    async def initialize(self, symbols: List[Symbol]) -> None:
        """Initialize WebSocket connection and subscriptions."""
        await self.ws_manager.initialize(symbols)
        self.logger.info(f"MEXC WebSocket initialized with {len(symbols)} symbols")
    
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


class MexcWebsocketPrivateRefactored:
    """
    MEXC Private WebSocket client using strategy pattern.
    
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
        
        # Create strategy set for MEXC private WebSocket
        strategies = WebSocketStrategySet(
            connection_strategy=MexcPrivateConnectionStrategy(api_key, secret_key),
            subscription_strategy=MexcPrivateSubscriptionStrategy(),
            message_parser=MexcPrivateMessageParser()
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
        
        self.logger.info("MEXC Private WebSocket client initialized with strategy pattern")
    
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """Initialize private WebSocket connection."""
        await self.ws_manager.initialize(symbols or [])
        self.logger.info("MEXC Private WebSocket initialized")
    
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
def create_mexc_public_websocket(
    config: WebSocketConfig,
    orderbook_handler: Optional[Callable[[Symbol, OrderBook], Awaitable[None]]] = None,
    trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None
) -> MexcWebsocketPublicRefactored:
    """Factory function to create MEXC public WebSocket client."""
    return MexcWebsocketPublicRefactored(
        config=config,
        orderbook_handler=orderbook_handler,
        trades_handler=trades_handler
    )


def create_mexc_private_websocket(
    config: WebSocketConfig,
    api_key: str,
    secret_key: str,
    balance_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    order_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
) -> MexcWebsocketPrivateRefactored:
    """Factory function to create MEXC private WebSocket client."""
    return MexcWebsocketPrivateRefactored(
        config=config,
        api_key=api_key,
        secret_key=secret_key,
        balance_handler=balance_handler,
        order_handler=order_handler
    )