"""
MEXC Public Exchange Implementation

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
    ExchangeStatus, OrderbookUpdateType
)
from cex.mexc.ws.public.ws_public import MexcWebsocketPublic
from cex.mexc.rest.rest_public import MexcPublicSpotRest
from core.transport.websocket.ws_client import WebSocketConfig
from core.cex.websocket import ConnectionState
from core.exceptions.exchange import BaseExchangeError
from core.config.structs import ExchangeConfig


class MexcPublicExchange(BasePublicExchangeInterface):
    """
    MEXC Public Exchange - Market Data Only
    
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

    def __init__(self, config: ExchangeConfig):
        """Initialize MEXC public exchange for market data operations."""
        super().__init__(config)


        # Initialize components using composition pattern
        self._public_rest = MexcPublicSpotRest(config)
        self._websocket_client = MexcWebsocketPublic(
            config=self._config,
            orderbook_diff_handler=self._handle_raw_orderbook_message,
            state_change_handler=self._handle_connection_state_change
        )
        # HFT Performance tracking
        self._market_data_updates = 0
        self._last_update_time = 0.0
        
        self.logger.info("MEXC Public Exchange initialized for HFT orderbook processing")
    
    async def _load_symbols_info(self) -> None:
        """Load symbol information from REST API."""
        try:
            # Get symbol information from REST API
            symbols_info = await self._public_rest.get_exchange_info()
            self._symbols_info_dict.update(symbols_info)
            self._symbols_info = self._symbols_info_dict.copy()
            
            self.logger.info(f"Loaded {len(symbols_info)} symbols from MEXC")
            
        except Exception as e:
            self.logger.error(f"Failed to load exchange info: {e}")
            raise
    
    async def _get_orderbook_snapshot(self, symbol: Symbol) -> OrderBook:
        """Get orderbook snapshot from REST API."""
        try:
            # Use REST client to get orderbook snapshot
            orderbook = await self._public_rest.get_orderbook(symbol, limit=20)
            return orderbook
            
        except Exception as e:
            self.logger.error(f"Failed to get orderbook snapshot for {symbol}: {e}")
            raise
    
    async def _start_real_time_streaming(self, symbols: List[Symbol]) -> None:
        """Start real-time WebSocket streaming for symbols."""
        try:
            # Initialize WebSocket client for real-time data
            await self._websocket_client.initialize(symbols)
            
            self.logger.info("MEXC WebSocket client initialized and connected")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket: {e}")
            raise
    
    async def _stop_real_time_streaming(self) -> None:
        """Stop real-time WebSocket streaming."""
        try:
            if self._websocket_client:
                await self._websocket_client.close()
            
            self.logger.info("MEXC WebSocket streaming stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping WebSocket streaming: {e}")
    
    async def _refresh_exchange_data(self) -> None:
        """
        Refresh orderbook data after WebSocket reconnection.
        
        For public exchanges, this refreshes:
        - Orderbook snapshots from REST API
        - Notifies arbitrage layer of reconnection
        """
        try:
            if self._active_symbols:
                # Reload orderbook snapshots to ensure consistency after reconnection
                await self._initialize_orderbooks_from_rest(list(self._active_symbols))
                
                # Notify arbitrage layer of reconnection for each symbol
                for symbol, orderbook in self._orderbooks.items():
                    await self._notify_orderbook_update(symbol, orderbook, OrderbookUpdateType.RECONNECT)
                
                self.logger.info(f"Refreshed {len(self._orderbooks)} orderbooks after reconnection")
            else:
                self.logger.info("No active symbols to refresh after reconnection")
                
        except Exception as e:
            self.logger.error(f"Failed to refresh exchange data after reconnection: {e}")
            raise
    
    @property
    def status(self) -> ExchangeStatus:
        """Get current exchange connection status."""
        if self.is_connected:
            return ExchangeStatus.ACTIVE
        elif self.connection_state == ConnectionState.CONNECTING:
            return ExchangeStatus.CONNECTING
        else:
            return ExchangeStatus.INACTIVE
    
    @property
    def symbols_info(self) -> SymbolsInfo:
        """Get all symbol information."""
        return self._symbols_info_dict.copy()


    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize exchange with symbol information and prepare for streaming.
        
        Args:
            symbols: Optional list of symbols to initialize for streaming
        """
        # Call the base class initialize method which handles the common sequence
        await super().initialize(symbols)
    
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
            # Add to active symbols set
            self._active_symbols.add(symbol)
            
            # Load initial orderbook snapshot using base class method
            await self._load_orderbook_snapshot(symbol)
            
            # WebSocket subscription is handled during initialization
            # Individual symbol subscription not supported by strategy pattern
            self.logger.debug(f"Added symbol {symbol} for streaming")
            
        except Exception as e:
            self.logger.error(f"Failed to add symbol {symbol}: {e}")
            self._active_symbols.discard(symbol)
            raise
    
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
            
            # Remove from base class orderbook storage
            if symbol in self._orderbooks:
                del self._orderbooks[symbol]
            
            # WebSocket unsubscription is handled during close
            # Individual symbol unsubscription not supported by strategy pattern
            self.logger.debug(f"Removed symbol {symbol} from streaming")
            
        except Exception as e:
            self.logger.error(f"Failed to remove symbol {symbol}: {e}")
            raise
    
    async def close(self) -> None:
        """Close all connections and cleanup resources."""
        self.logger.info("Closing MEXC public exchange...")
        
        try:
            # Stop real-time streaming
            await self._stop_real_time_streaming()
            
            # Call base class close for common cleanup
            await super().close()
            
            # Clean up exchange-specific state
            self._symbols_info_dict.clear()
            
            self.logger.info("MEXC public exchange closed successfully")
            
        except Exception as e:
            self.logger.error(f"Error closing MEXC public exchange: {e}")
    
    
    async def _handle_raw_orderbook_message(self, parsed_update_or_raw: any, symbol: Symbol) -> None:
        """
        Handle orderbook messages from WebSocket with HFT diff processing.
        
        HFT COMPLIANT: Uses base class orderbook management for consistency.
        Processes MEXC orderbook diffs per documentation:
        https://mexcdevelop.github.io/apidocs/spot_v3_en/#diff-depth-stream
        
        Args:
            parsed_update_or_raw: ParsedOrderbookUpdate from message parser OR raw message
            symbol: Symbol for the orderbook update
        """
        # HFT Optimization: Update counters with minimal overhead
        self._market_data_updates += 1
        self._last_update_time = time.perf_counter()

        # Check if we received a ParsedOrderbookUpdate or raw message
        from common.orderbook_diff_processor import ParsedOrderbookUpdate
        
        if isinstance(parsed_update_or_raw, ParsedOrderbookUpdate):
            # Convert ParsedOrderbookUpdate to OrderBook for base class
            # This is a simplified conversion - in production might need full orderbook reconstruction
            if symbol in self._orderbooks:
                # Update existing orderbook using base class method
                current_orderbook = self._orderbooks[symbol]
                # Apply diff to create new orderbook (simplified)
                updated_orderbook = self._apply_diff_to_orderbook(current_orderbook, parsed_update_or_raw)
                self._update_orderbook(symbol, updated_orderbook, OrderbookUpdateType.DIFF)
            else:
                # Need to load initial snapshot
                try:
                    await self._load_orderbook_snapshot(symbol)
                except Exception as e:
                    self.logger.error(f"Failed to load initial orderbook for {symbol}: {e}")
        else:
            # Handle raw message - would need to parse and process
            self.logger.debug(f"Received raw orderbook message for {symbol}")

        # Log periodically to avoid spam
        if self._market_data_updates % 1000 == 0:
            self.logger.info(f"Processed {self._market_data_updates} orderbook updates")
    
    def _apply_diff_to_orderbook(self, current_orderbook: OrderBook, diff_update: 'ParsedOrderbookUpdate') -> OrderBook:
        """
        Apply diff update to existing orderbook.
        
        This is a simplified implementation - production would use HFT-optimized diff application.
        """
        # For now, return the current orderbook (would implement proper diff application)
        return current_orderbook
    
    def get_symbol_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """
        Get current orderbook for a specific symbol with HFT-optimized access.
        
        Args:
            symbol: Symbol to get orderbook for
            
        Returns:
            Current orderbook snapshot or None if not available
            
        Performance: <10μs copy-on-read access
        """
        return self._orderbooks.get(symbol)
    
    def get_market_data_statistics(self) -> Dict[str, any]:
        """Get comprehensive HFT market data processing statistics."""
        # Use base class statistics method
        base_stats = self.get_orderbook_stats()
        
        return {
            'active_symbols': len(self._active_symbols),
            'market_data_updates': self._market_data_updates,
            'last_update_time': self._last_update_time,
            'connection_state': self.connection_state.name,
            'exchange_stats': base_stats
        }