"""
MEXC Public WebSocket Implementation

Clean implementation using dependency injection similar to REST pattern.
Handles public WebSocket streams for market data including:
- Orderbook depth updates
- Trade stream data
- Real-time market information

Features:
- Dependency injection via base class (like REST pattern)
- HFT-optimized message processing 
- Event-driven architecture with injected handlers
- Clean separation of concerns
- MEXC-specific protobuf message parsing

MEXC Public WebSocket Specifications:
- Endpoint: wss://wbs.mexc.com/ws
- Protocol: JSON and Protocol Buffers
- Performance: <50ms latency with batch processing

Architecture: Dependency injection with base class coordination
"""

from typing import List, Dict, Optional, Callable, Awaitable, Set

from structs.common import Symbol, Trade, OrderBook, BookTicker
from core.config.structs import ExchangeConfig
from core.cex.websocket.spot.base_ws_public import BaseExchangePublicWebsocketInterface
from core.transport.websocket.structs import ConnectionState, MessageType

# MEXC-specific protobuf imports for message parsing
from cex.mexc.structs.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
from cex.mexc.structs.protobuf.PublicLimitDepthsV3Api_pb2 import PublicLimitDepthsV3Api
from cex.mexc.structs.protobuf.PublicAggreDealsV3Api_pb2 import PublicAggreDealsV3Api


class MexcWebsocketPublic(BaseExchangePublicWebsocketInterface):
    """MEXC public WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        config: ExchangeConfig,
        orderbook_diff_handler: Optional[Callable[[any, Symbol], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
        book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
        state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
    ):
        """
        Initialize MEXC public WebSocket with dependency injection.
        
        Base class handles all strategy creation, WebSocket manager setup, and dependency injection.
        Only MEXC-specific initialization logic goes here.
        """
        # Validate MEXC-specific requirements
        if not config.websocket:
            raise ValueError("MEXC exchange configuration missing WebSocket settings")
        
        # Initialize via base class dependency injection (like REST pattern)
        super().__init__(
            config=config,
            orderbook_diff_handler=orderbook_diff_handler,
            trades_handler=trades_handler,
            book_ticker_handler=book_ticker_handler,
            state_change_handler=state_change_handler
        )
        
        # State management for symbols (moved from WebSocket manager)
        self._active_symbols: Set[Symbol] = set()

        self.logger.info("MEXC public WebSocket initialized with dependency injection")

    # MEXC-specific message handling can be added here if needed
    # Base class handles all common WebSocket operations:
    # - initialize(), close(), is_connected(), get_performance_metrics()
    # - Message routing for ORDERBOOK, TRADE, HEARTBEAT, etc.
    # - Default event handlers with dependency injection support
    
    # Enhanced symbol management using symbol-channel mapping
    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols for subscription using enhanced symbol-channel mapping."""
        if not symbols:
            return
            

        # Use unified subscription method with symbols parameter
        await self._ws_manager.add_subscription(symbols=symbols)
        
        # Move from pending to active on successful subscription
        self._active_symbols.update(symbols)

        self.logger.info(f"Added {len(symbols)} symbols: {[str(s) for s in symbols]}")
    
    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """Remove symbols from subscription using enhanced symbol-channel mapping."""
        if not symbols:
            return
            
        # Filter to only remove symbols we actually have
        symbols_to_remove = [s for s in symbols if s in self._active_symbols]
        if not symbols_to_remove:
            return
        
        # Use unified subscription removal method with symbols parameter
        await self._ws_manager.remove_subscription(symbols=symbols_to_remove)
        
        # Remove from active state
        self._active_symbols.difference_update(symbols_to_remove)
        
        self.logger.info(f"Removed {len(symbols_to_remove)} symbols: {[str(s) for s in symbols_to_remove]}")
    
    async def restore_subscriptions(self) -> None:
        """Restore all active subscriptions after reconnect using ws_manager restoration."""
        if not self._active_symbols:
            self.logger.info("No active symbols to restore")
            return
        
        # ws_manager handles restoration automatically using stored channels
        # No action needed here - channels are restored by ws_manager
        self.logger.info(f"Symbol subscriptions will be restored by ws_manager ({len(self._active_symbols)} symbols)")
    
    def get_active_symbols(self) -> Set[Symbol]:
        """Get currently active symbols."""
        return self._active_symbols.copy()
    
    # Override default handlers if MEXC needs specific behavior
    async def on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """MEXC-specific orderbook update handler."""
        self.logger.info(f"MEXC orderbook update for {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")

    async def on_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """MEXC-specific trade update handler."""
        self.logger.info(f"MEXC trades update for {symbol}: {len(trades)} trades")
