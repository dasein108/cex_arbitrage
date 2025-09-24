"""
Gate.io Public WebSocket Implementation

Clean implementation using dependency injection similar to REST pattern.
Handles public WebSocket streams for market data including:
- Orderbook depth updates  
- Trade stream data
- Real-time market information

Features:
- Dependency injection via composite class (like REST pattern)
- HFT-optimized message processing
- Event-driven architecture with injected handlers
- Clean separation of concerns
- Gate.io-specific JSON message parsing

Gate.io Public WebSocket Specifications:
- Endpoint: wss://api.gateio.ws/ws/v4/
- Protocol: JSON-based message format
- Performance: <50ms latency with optimized processing

Architecture: Dependency injection with composite class coordination
"""

from typing import List, Optional, Callable, Awaitable, Set

from exchanges.structs.common import Symbol, Trade, OrderBook, BookTicker
from config.structs import ExchangeConfig
from exchanges.interfaces import PublicSpotWebsocket
from infrastructure.networking.websocket.structs import ConnectionState


class GateioPublicSpotWebsocket(PublicSpotWebsocket):
    """Gate.io public WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        config: ExchangeConfig,
        orderbook_diff_handler: Optional[Callable[[any, Symbol], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
        book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
        state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
    ):
        """
        Initialize Gate.io public WebSocket with dependency injection.
        
        Base class handles all strategy creation, WebSocket manager setup, and dependency injection.
        Only Gate.io-specific initialization logic goes here.
        """
        # Validate Gate.io-specific requirements
        if not config.websocket:
            raise ValueError("Gate.io exchange configuration missing WebSocket settings")
        
        # Initialize via composite class dependency injection (like REST pattern)
        super().__init__(
            config=config,
            orderbook_diff_handler=orderbook_diff_handler,
            trades_handler=trades_handler,
            book_ticker_handler=book_ticker_handler,
            state_change_handler=state_change_handler
        )
        
        # State management for symbols (moved from WebSocket manager)
        self._active_symbols: Set[Symbol] = set()

        self.logger.info("Gate.io public WebSocket initialized with dependency injection")

    # Gate.io-specific message handling can be added here if needed
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
        await self._ws_manager.subscribe(symbols=symbols)
        
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
        await self._ws_manager.unsubscribe(symbols=symbols_to_remove)
        
        # Remove from active state
        self._active_symbols.difference_update(symbols_to_remove)
        
        self.logger.info(f"Removed {len(symbols_to_remove)} symbols: {[str(s) for s in symbols_to_remove]}")
    

    def get_active_symbols(self) -> Set[Symbol]:
        """Get currently active symbols."""
        return self._active_symbols.copy()
    
    # Override default handlers if Gate.io needs specific behavior
    async def on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Gate.io-specific orderbook update handler."""
        self.logger.info(f"Gate.io orderbook update for {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")

    async def on_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """Gate.io-specific trade update handler."""
        self.logger.info(f"Gate.io trades update for {symbol}: {len(trades)} trades")