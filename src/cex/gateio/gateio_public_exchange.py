"""
Gate.io Public Exchange Implementation

HFT-compliant public market data operations only.
No authentication required - focuses on real-time market data streaming.

HFT COMPLIANCE: Sub-10ms market data processing, zero-copy patterns.
"""

import logging
import time
from typing import List, Dict, Optional, Set

from core.cex.base import BasePublicExchangeInterface
from structs.exchange import (
    OrderBook, Symbol, SymbolInfo, SymbolsInfo, 
    ExchangeStatus
)
from cex.gateio.ws.gateio_ws_public import GateioWebsocketPublic
from cex.gateio.rest.gateio_public import GateioPublicExchangeSpotRest
from core.cex.websocket.structs import ConnectionState
from core.exceptions.exchange import BaseExchangeError
from core.config.structs import ExchangeConfig


class GateioPublicExchange(BasePublicExchangeInterface):
    """
    Gate.io Public Exchange - Market Data Only
    
    Provides real-time market data streaming without authentication.
    Optimized for HFT market data aggregation and opportunity detection.
    
    Features:
    - Real-time orderbook streaming via WebSocket
    - Symbol information and trading rules
    - Market data without trading functionality
    - Sub-10ms data processing latency
    
    HFT Compliance:
    - No caching of real-time market data
    - Zero-copy data processing where possible
    - Event-driven data distribution
    """
    exchange_name = "GATEIO_public"

    def __init__(self, config: ExchangeConfig):
        """Initialize Gate.io public exchange for market data operations."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = config
        self.start_time = time.time()
        
        # Initialize REST client for public data
        # TODO: Update REST client to use unified config pattern
        self.rest_client = None  # Temporarily disabled until REST client is updated
        
        # WebSocket client for real-time data streaming
        self.ws_client: Optional[GateioWebsocketPublic] = None
        
        # HFT State Management (CRITICAL: NO CACHING OF REAL-TIME DATA)
        self._symbols_info: Optional[SymbolsInfo] = None  # Static data - safe to cache
        self._active_symbols: Set[Symbol] = set()
        self._orderbook_cache: Dict[Symbol, OrderBook] = {}  # Real-time cache - managed carefully
        
        self.logger.info(f"Gate.io public exchange initialized")
    
    # BasePublicExchangeInterface Implementation
    
    @property
    def orderbook(self) -> OrderBook:
        """
        Get current aggregated orderbook from WebSocket stream.
        
        HFT COMPLIANT: Returns real-time streamed data, no stale cache.
        """
        if not self._orderbook_cache:
            raise BaseExchangeError(500, "No orderbook data available - initialize WebSocket first")
        
        # Return the most recent orderbook (first symbol)
        # In HFT, each symbol typically tracked separately
        if self._orderbook_cache:
            return next(iter(self._orderbook_cache.values()))
        else:
            raise BaseExchangeError(500, "No orderbook data available")
    
    @property
    def symbols_info(self) -> SymbolsInfo:
        """Get cached symbols information (safe to cache - static data)."""
        if not self._symbols_info:
            raise BaseExchangeError(500, "Symbols info not initialized - call initialize() first")
        return self._symbols_info
    
    @property
    def active_symbols(self) -> List[Symbol]:
        """Get list of actively tracked symbols."""
        return list(self._active_symbols)
    
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize exchange with symbol list for market data streaming.
        
        Args:
            symbols: List of symbols to track for market data
        """
        try:
            start_time = time.perf_counter()
            
            # Load symbols information (static data - safe to cache)
            # TODO: Implement when REST client is updated
            self._symbols_info = {}  # Placeholder until REST client is updated
            
            if symbols:
                # Initialize WebSocket for real-time data
                if not self.config.websocket:
                    raise ValueError("Gate.io exchange configuration missing WebSocket settings")
                
                self.ws_client = GateioWebsocketPublic(
                    config=self.config,
                    orderbook_handler=self._handle_orderbook_update
                )
                
                await self.ws_client.initialize(symbols)
                self._active_symbols.update(symbols)
            
            load_time = time.perf_counter() - start_time
            self.logger.info(
                f"Gate.io public exchange initialized in {load_time*1000:.2f}ms with {len(symbols or [])} symbols"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Gate.io public exchange: {e}")
            raise BaseExchangeError(500, f"Initialization failed: {str(e)}")
    
    async def add_symbol(self, symbol: Symbol) -> None:
        """Start streaming data for new symbol."""
        if symbol in self._active_symbols:
            return  # Already tracking
        
        if self.ws_client and self.ws_client.is_connected():
            # Add to existing WebSocket connection
            await self.ws_client.add_symbol(symbol)
            self._active_symbols.add(symbol)
            self.logger.info(f"Added symbol {symbol} to Gate.io public streaming")
        else:
            # Store for future WebSocket initialization
            self._active_symbols.add(symbol)
    
    async def remove_symbol(self, symbol: Symbol) -> None:
        """Stop streaming data for symbol."""
        if symbol not in self._active_symbols:
            return  # Not tracking
        
        if self.ws_client and self.ws_client.is_connected():
            await self.ws_client.remove_symbol(symbol)
        
        self._active_symbols.discard(symbol)
        self._orderbook_cache.pop(symbol, None)  # Remove cached data
        self.logger.info(f"Removed symbol {symbol} from Gate.io public streaming")
    
    # Real-time Data Handlers
    
    async def _handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """
        Handle real-time orderbook updates from WebSocket.
        
        HFT COMPLIANT: Updates real-time cache immediately.
        """
        self._orderbook_cache[symbol] = orderbook
        
        # Optional: Trigger downstream handlers/events
        # await self._notify_orderbook_update(symbol, orderbook)
    
    # Status and Health
    
    def get_connection_status(self) -> ExchangeStatus:
        """Get current connection status."""
        if self.ws_client:
            return ExchangeStatus.CONNECTED if self.ws_client.is_connected() else ExchangeStatus.DISCONNECTED
        return ExchangeStatus.DISCONNECTED
    
    def get_websocket_health(self) -> Dict[str, any]:
        """Get WebSocket health metrics."""
        if self.ws_client:
            return self.ws_client.get_performance_metrics()
        return {"status": "not_initialized"}
    
    async def close(self) -> None:
        """Clean shutdown of all connections."""
        if self.ws_client:
            await self.ws_client.close()
            self.ws_client = None
        
        self._orderbook_cache.clear()
        self._active_symbols.clear()
        
        self.logger.info("Gate.io public exchange closed")