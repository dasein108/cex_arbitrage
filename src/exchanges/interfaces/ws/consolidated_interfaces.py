"""
Consolidated WebSocket Interfaces - Public and Private

Specialized interfaces that extend the consolidated base with domain-specific
mixin functionality for public (market data) and private (trading) operations.

Architecture:
- ConsolidatedPublicWebSocketInterface: Market data operations
- ConsolidatedPrivateWebSocketInterface: Trading operations
- Both integrate mixins directly without intermediate layers
"""

from typing import Optional, List, Callable, Awaitable

from config.structs import ExchangeConfig
from infrastructure.networking.websocket.mixins import PublicWebSocketMixin, PrivateWebSocketMixin
from infrastructure.networking.websocket.structs import ConnectionState
from exchanges.structs.common import Symbol

from .consolidated_base import ConsolidatedWebSocketInterface


class ConsolidatedPublicWebSocketInterface(ConsolidatedWebSocketInterface, PublicWebSocketMixin):
    """
    Consolidated public WebSocket interface for market data operations.
    
    Integrates ConnectionMixin, SubscriptionMixin, and PublicWebSocketMixin
    directly without any intermediate layers for optimal performance.
    
    Features:
    - Direct market data processing (orderbooks, trades, tickers)
    - Built-in subscription management
    - Automatic reconnection with resubscription
    - HFT optimized message processing
    - No authentication required
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
        logger=None
    ):
        """
        Initialize consolidated public WebSocket interface.
        
        Args:
            config: Exchange configuration
            connection_handler: Optional callback for connection state changes
            logger: Optional logger instance
        """
        # Initialize base with public configuration
        super().__init__(
            config=config,
            is_private=False,
            connection_handler=connection_handler,
            logger=logger
        )
        
        # Initialize public WebSocket mixin
        self.setup_public_websocket()
        
        self.logger.info("Consolidated public WebSocket interface initialized",
                        exchange=config.name,
                        features=["market_data", "subscriptions", "reconnection"])
    
    async def start_market_data(self, symbols: Optional[List[Symbol]] = None) -> None:
        """
        Start market data streaming for specified symbols.
        
        Args:
            symbols: Optional list of symbols to subscribe to initially
        """
        await self.start(symbols)
    
    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to market data subscription.
        
        Args:
            symbols: List of symbols to add
        """
        await self.subscribe(symbols)
    
    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from market data subscription.
        
        Args:
            symbols: List of symbols to remove
        """
        await self.unsubscribe(symbols)
    
    def get_subscribed_symbols(self) -> List[Symbol]:
        """Get currently subscribed symbols."""
        return list(self._active_symbols)


class ConsolidatedPrivateWebSocketInterface(ConsolidatedWebSocketInterface, PrivateWebSocketMixin):
    """
    Consolidated private WebSocket interface for trading operations.
    
    Integrates ConnectionMixin, SubscriptionMixin, and PrivateWebSocketMixin
    directly without any intermediate layers for optimal performance.
    
    Features:
    - Direct trading operations (orders, balances, positions)
    - Built-in authentication handling
    - Built-in subscription management for private channels
    - Automatic reconnection with authentication and resubscription
    - HFT optimized message processing
    - Trading safety and validation
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        user_id: Optional[str] = None,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
        logger=None
    ):
        """
        Initialize consolidated private WebSocket interface.
        
        Args:
            config: Exchange configuration
            user_id: Optional user ID for private operations
            connection_handler: Optional callback for connection state changes
            logger: Optional logger instance
        """
        # Initialize base with private configuration
        super().__init__(
            config=config,
            is_private=True,
            connection_handler=connection_handler,
            logger=logger
        )
        
        # Initialize private WebSocket mixin
        self.setup_private_websocket(user_id)
        
        self.logger.info("Consolidated private WebSocket interface initialized",
                        exchange=config.name,
                        user_id=user_id,
                        features=["trading", "authentication", "subscriptions", "reconnection"])
    
    async def start_trading(self, symbols: Optional[List[Symbol]] = None) -> None:
        """
        Start trading WebSocket for specified symbols.
        
        This will automatically handle authentication and subscription to
        private channels for the specified symbols.
        
        Args:
            symbols: Optional list of symbols for private channel subscriptions
        """
        await self.start(symbols)
    
    async def add_trading_symbols(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to private trading subscriptions.
        
        Args:
            symbols: List of symbols to add for trading
        """
        await self.subscribe(symbols)
    
    async def remove_trading_symbols(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from private trading subscriptions.
        
        Args:
            symbols: List of symbols to remove from trading
        """
        await self.unsubscribe(symbols)
    
    def get_trading_symbols(self) -> List[Symbol]:
        """Get currently subscribed trading symbols."""
        return list(self._active_symbols)
    
    @property
    def is_authenticated(self) -> bool:
        """Check if interface is authenticated for trading."""
        return self._is_authenticated
    
    async def refresh_authentication(self) -> bool:
        """
        Refresh authentication credentials.
        
        Returns:
            True if authentication successful
        """
        if self.is_connected():
            try:
                return await self.authenticate()
            except Exception as e:
                self.logger.error("Failed to refresh authentication",
                                error_type=type(e).__name__,
                                error_message=str(e))
                return False
        return False