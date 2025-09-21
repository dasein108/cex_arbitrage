"""
Gate.io Public Futures WebSocket Implementation

Clean implementation using dependency injection similar to spot WebSocket pattern.
Handles public futures WebSocket streams for market data including:
- Futures orderbook depth updates  
- Futures trade stream data
- Real-time futures market information
- Funding rates and mark prices

Features:
- Dependency injection via base class (like REST and spot WebSocket pattern)
- HFT-optimized message processing
- Event-driven architecture with injected handlers
- Clean separation of concerns
- Gate.io futures-specific JSON message parsing

Gate.io Public Futures WebSocket Specifications:
- Endpoint: wss://fx-ws.gateio.ws/v4/ws/usdt/ (USDT futures)
- Endpoint: wss://fx-ws.gateio.ws/v4/ws/delivery/ (delivery futures)  
- Protocol: JSON-based message format
- Performance: <50ms latency with optimized processing

Architecture: Dependency injection with base class coordination
"""

from typing import List, Dict, Optional, Callable, Awaitable, Set

from structs.common import Symbol, Trade, OrderBook, BookTicker
from core.config.structs import ExchangeConfig
from core.exchanges.websocket.spot.base_ws_public import BaseExchangePublicWebsocketInterface
from core.transport.websocket.structs import ConnectionState, MessageType


class GateioWebsocketPublicFutures(BaseExchangePublicWebsocketInterface):
    """Gate.io public futures WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        config: ExchangeConfig,
        orderbook_diff_handler: Optional[Callable[[any, Symbol], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
        book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
        state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
    ):
        """
        Initialize Gate.io public futures WebSocket with dependency injection.
        
        Base class handles all strategy creation, WebSocket manager setup, and dependency injection.
        Only Gate.io futures-specific initialization logic goes here.
        """
        # Validate Gate.io futures-specific requirements
        if not config.websocket:
            raise ValueError("Gate.io futures exchange configuration missing WebSocket settings")
        
        # Ensure futures WebSocket URL is configured
        if not hasattr(config, 'futures_websocket_url') or not config.futures_websocket_url:
            # Set default USDT futures endpoint if not configured
            config.futures_websocket_url = "wss://fx-ws.gateio.ws/v4/ws/usdt/"
        
        # Initialize via base class dependency injection (like REST pattern)
        super().__init__(
            config=config,
            orderbook_diff_handler=orderbook_diff_handler,
            trades_handler=trades_handler,
            book_ticker_handler=book_ticker_handler,
            state_change_handler=state_change_handler,
            is_futures=True  # Flag to indicate futures WebSocket
        )
        
        # State management for futures symbols (moved from WebSocket manager)
        self._active_symbols: Set[Symbol] = set()

        self.logger.info("Gate.io public futures WebSocket initialized with dependency injection")

    # Gate.io futures-specific message handling can be added here if needed
    # Base class handles all common WebSocket operations:
    # - initialize(), close(), is_connected(), get_performance_metrics()
    # - Message routing for ORDERBOOK, TRADE, HEARTBEAT, etc.
    # - Default event handlers with dependency injection support
    
    # Enhanced symbol management using symbol-channel mapping
    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add futures symbols for subscription using enhanced symbol-channel mapping."""
        if not symbols:
            return
            

        # Use unified subscription method with symbols parameter
        await self._ws_manager.subscribe(symbols=symbols)
        
        # Move from pending to active on successful subscription
        self._active_symbols.update(symbols)

        self.logger.info(f"Added {len(symbols)} futures symbols: {[str(s) for s in symbols]}")
    
    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """Remove futures symbols from subscription using enhanced symbol-channel mapping."""
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
        
        self.logger.info(f"Removed {len(symbols_to_remove)} futures symbols: {[str(s) for s in symbols_to_remove]}")
    

    def get_active_symbols(self) -> Set[Symbol]:
        """Get currently active futures symbols."""
        return self._active_symbols.copy()
    
    # Override default handlers if Gate.io futures needs specific behavior
    async def on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Gate.io futures-specific orderbook update handler."""
        self.logger.info(f"Gate.io futures orderbook update for {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")

    async def on_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """Gate.io futures-specific trade update handler."""
        self.logger.info(f"Gate.io futures trades update for {symbol}: {len(trades)} trades")

    async def on_funding_rate_update(self, symbol: Symbol, funding_data: Dict):
        """Gate.io futures-specific funding rate update handler."""
        funding_rate = funding_data.get("funding_rate", 0)
        timestamp = funding_data.get("timestamp", 0)
        self.logger.info(f"Gate.io futures funding rate update for {symbol}: {funding_rate} at {timestamp}")

    async def on_mark_price_update(self, symbol: Symbol, mark_price_data: Dict):
        """Gate.io futures-specific mark price update handler."""
        mark_price = mark_price_data.get("mark_price", 0)
        timestamp = mark_price_data.get("timestamp", 0)
        self.logger.info(f"Gate.io futures mark price update for {symbol}: {mark_price} at {timestamp}")

    # Futures-specific utility methods
    def is_futures_symbol(self, symbol: Symbol) -> bool:
        """Check if symbol is a futures contract."""
        # Gate.io futures symbols typically have contract dates or are perpetual
        symbol_str = str(symbol)
        return (
            symbol.is_futures or  # Symbol explicitly marked as futures
            "_USDT" in symbol_str or  # USDT perpetual futures
            len(symbol_str.split("_")) > 2  # Delivery futures with dates
        )

    def get_contract_type(self, symbol: Symbol) -> str:
        """Get contract type for futures symbol."""
        symbol_str = str(symbol)
        if "_USDT" in symbol_str and len(symbol_str.split("_")) == 2:
            return "perpetual"
        elif len(symbol_str.split("_")) > 2:
            return "delivery"
        else:
            return "unknown"

    async def get_futures_info(self, symbols: List[Symbol]) -> Dict[Symbol, Dict]:
        """Get futures contract information for symbols."""
        # This would typically fetch from REST API or cached data
        # For now, return basic info based on symbol analysis
        info = {}
        for symbol in symbols:
            info[symbol] = {
                "contract_type": self.get_contract_type(symbol),
                "is_futures": self.is_futures_symbol(symbol),
                "base_asset": symbol.base,
                "quote_asset": symbol.quote
            }
        return info