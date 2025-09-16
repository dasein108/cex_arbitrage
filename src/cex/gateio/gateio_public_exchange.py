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
from cex.gateio.rest.gateio_public import GateioPublicExchange as GateioPublicRest
from cex.gateio.common.gateio_config import GateioConfig
from core.transport.websocket.ws_client import WebSocketConfig
from core.cex import ConnectionState
from core.exceptions.exchange import BaseExchangeError


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
    
    def __init__(self):
        """Initialize Gate.io public exchange for market data operations."""
        super().__init__()
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # HFT Optimized: Real-time streaming data structures
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._symbols_info_dict: Dict[Symbol, SymbolInfo] = {}
        self._active_symbols: Set[Symbol] = set()
        
        # Current streaming state (not cached)
        self._latest_orderbook: Optional[OrderBook] = None
        self._connection_state = ConnectionState.DISCONNECTED
        
        # Initialize components using composition pattern
        self._public_rest = GateioPublicRest()
        self._websocket_client: Optional[GateioWebsocketPublic] = None
        
        # HFT Performance tracking
        self._market_data_updates = 0
        self._last_update_time = 0.0
        
        self.logger.info("Gate.io Public Exchange initialized for market data operations")
    
    @property
    def status(self) -> ExchangeStatus:
        """Get current exchange connection status."""
        if self._connection_state == ConnectionState.CONNECTED:
            return ExchangeStatus.ACTIVE
        elif self._connection_state == ConnectionState.CONNECTING:
            return ExchangeStatus.CONNECTING
        else:
            return ExchangeStatus.INACTIVE
    
    @property
    def orderbook(self) -> OrderBook:
        """Get current orderbook snapshot."""
        if self._latest_orderbook is None:
            raise BaseExchangeError("No orderbook data available")
        return self._latest_orderbook
    
    @property
    def symbols_info(self) -> SymbolsInfo:
        """Get all symbol information."""
        return self._symbols_info_dict.copy()
    
    @property
    def active_symbols(self) -> List[Symbol]:
        """Get list of actively streaming symbols."""
        return list(self._active_symbols)
    
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize exchange with symbol information and prepare for streaming.
        
        Args:
            symbols: Optional list of symbols to initialize for streaming
        """
        self.logger.info("Initializing Gate.io public exchange...")
        
        try:
            # Load exchange information and trading rules
            await self._load_exchange_info()
            
            # Initialize WebSocket client for real-time data
            await self._initialize_websocket()
            
            # Setup symbol subscriptions if provided
            if symbols:
                for symbol in symbols:
                    await self.add_symbol(symbol)
            
            self.logger.info(f"Gate.io public exchange initialized with {len(self._active_symbols)} symbols")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Gate.io public exchange: {e}")
            raise BaseExchangeError(f"Gate.io initialization failed: {e}")
    
    async def add_symbol(self, symbol: Symbol) -> None:
        """
        Start streaming market data for a symbol.
        
        Args:
            symbol: Symbol to start streaming
        """
        if symbol in self._active_symbols:
            self.logger.debug(f"Symbol {symbol} already active")
            return
        
        try:
            # Add to active symbols
            self._active_symbols.add(symbol)
            
            # Subscribe to WebSocket data if client is available
            if self._websocket_client:
                await self._websocket_client.subscribe_orderbook(symbol)
            
            self.logger.debug(f"Added symbol {symbol} for streaming")
            
        except Exception as e:
            self.logger.error(f"Failed to add symbol {symbol}: {e}")
            self._active_symbols.discard(symbol)
            raise BaseExchangeError(f"Failed to add symbol: {e}")
    
    async def remove_symbol(self, symbol: Symbol) -> None:
        """
        Stop streaming market data for a symbol.
        
        Args:
            symbol: Symbol to stop streaming
        """
        if symbol not in self._active_symbols:
            self.logger.debug(f"Symbol {symbol} not active")
            return
        
        try:
            # Remove from active symbols
            self._active_symbols.discard(symbol)
            
            # Unsubscribe from WebSocket data
            if self._websocket_client:
                await self._websocket_client.unsubscribe_orderbook(symbol)
            
            # Clean up cached data
            self._orderbooks.pop(symbol, None)
            
            self.logger.debug(f"Removed symbol {symbol} from streaming")
            
        except Exception as e:
            self.logger.error(f"Failed to remove symbol {symbol}: {e}")
            raise BaseExchangeError(f"Failed to remove symbol: {e}")
    
    async def close(self) -> None:
        """Close all connections and cleanup resources."""
        self.logger.info("Closing Gate.io public exchange...")
        
        try:
            # Close WebSocket connections
            if self._websocket_client:
                await self._websocket_client.close()
                self._websocket_client = None
            
            # Clean up state
            self._active_symbols.clear()
            self._orderbooks.clear()
            self._connection_state = ConnectionState.DISCONNECTED
            
            self.logger.info("Gate.io public exchange closed successfully")
            
        except Exception as e:
            self.logger.error(f"Error closing Gate.io public exchange: {e}")
    
    async def _load_exchange_info(self) -> None:
        """Load symbol information and trading rules from REST API."""
        try:
            # Get symbol information from REST API
            symbols_info = await self._public_rest.get_symbols_info()
            self._symbols_info_dict.update(symbols_info)
            
            self.logger.info(f"Loaded {len(symbols_info)} symbols from Gate.io")
            
        except Exception as e:
            self.logger.error(f"Failed to load exchange info: {e}")
            raise
    
    async def _initialize_websocket(self) -> None:
        """Initialize WebSocket client for real-time market data."""
        try:
            # Create WebSocket configuration
            ws_config = WebSocketConfig(
                url=GateioConfig.WEBSOCKET_PUBLIC_URL,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            )
            
            # Initialize WebSocket client
            self._websocket_client = GateioWebsocketPublic(
                websocket_config=ws_config,
                orderbook_callback=self._handle_orderbook_update
            )
            
            # Connect to WebSocket
            await self._websocket_client.connect()
            self._connection_state = ConnectionState.CONNECTED
            
            self.logger.info("Gate.io WebSocket client initialized and connected")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket: {e}")
            self._connection_state = ConnectionState.DISCONNECTED
            raise
    
    def _handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """
        Handle real-time orderbook updates from WebSocket.
        
        HFT COMPLIANT: Sub-millisecond processing, no blocking operations.
        
        Args:
            symbol: Symbol for the orderbook update
            orderbook: Updated orderbook data
        """
        # HFT Optimization: Update counters with minimal overhead
        self._market_data_updates += 1
        self._last_update_time = time.perf_counter()
        
        # Store current orderbook (overwrites previous)
        self._orderbooks[symbol] = orderbook
        self._latest_orderbook = orderbook
        
        # Log periodically to avoid spam
        if self._market_data_updates % 1000 == 0:
            self.logger.debug(
                f"Processed {self._market_data_updates} market data updates "
                f"for {len(self._orderbooks)} symbols"
            )
    
    def get_symbol_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """
        Get current orderbook for a specific symbol.
        
        Args:
            symbol: Symbol to get orderbook for
            
        Returns:
            Current orderbook or None if not available
        """
        return self._orderbooks.get(symbol)
    
    def get_market_data_statistics(self) -> Dict[str, any]:
        """Get market data processing statistics."""
        return {
            'active_symbols': len(self._active_symbols),
            'market_data_updates': self._market_data_updates,
            'last_update_time': self._last_update_time,
            'connection_state': self._connection_state.name,
            'orderbooks_cached': len(self._orderbooks)
        }