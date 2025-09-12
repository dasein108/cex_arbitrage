"""
MEXC Exchange Implementation

Complete implementation of MEXC exchange with WebSocket order book streaming
and REST API balance management. Integrates existing MEXC components for
production-ready trading functionality.

Key Features:
- Real-time order book updates via WebSocket
- REST API balance fetching with intelligent caching
- Dynamic symbol subscription/unsubscription
- Thread-safe data storage with typed containers
- Comprehensive error handling and recovery
- Production-grade performance optimization

Performance Targets:
- <50ms WebSocket order book updates
- <100ms REST API balance queries
- Zero-copy JSON parsing with msgspec
- Memory-efficient O(1) data structures
"""

import asyncio
import logging
import time
from typing import List, Dict, Optional, Set
from contextlib import asynccontextmanager

from exchanges.interface.base_exchange import BaseExchangeInterface
from structs.exchange import OrderBook, Symbol, AssetBalance, AssetName
from exchanges.mexc.ws.mexc_ws_public import MexcWebsocketPublic
from exchanges.mexc.rest.mexc_private import MexcPrivateExchange
from exchanges.mexc.rest.mexc_public import MexcPublicExchange
from exchanges.mexc.common.mexc_config import MexcConfig
from common.ws_client import WebSocketConfig
from common.exceptions import ExchangeAPIError


class MexcExchange(BaseExchangeInterface):
    """
    Complete MEXC exchange implementation using existing components.
    
    Integrates MexcWebsocketPublic for real-time order books and 
    MexcPrivateExchange for balance management. Provides unified
    interface with production-ready error handling.
    
    Architecture:
    - WebSocket: Real-time order book streaming
    - REST Private: Account balance management 
    - REST Public: Market data and exchange info
    - Unified Interface: BaseExchangeInterface compliance
    
    Threading: All operations are async/await compatible
    Memory: O(n) for symbols, O(1) for balances with caching
    Performance: <50ms order book updates, <100ms API calls
    """
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        """
        Initialize MEXC exchange with optional API credentials.
        
        Args:
            api_key: MEXC API key for private operations (optional)
            secret_key: MEXC secret key for private operations (optional)
            
        Note:
            Credentials are required for balance queries and trading.
            Order book streaming works without authentication.
        """
        super().__init__('MEXC', api_key, secret_key)
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Thread-safe data storage containers
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._balances_dict: Dict[AssetName, AssetBalance] = {}
        self._active_symbols: Set[Symbol] = set()
        
        # Component clients
        self._ws_client: Optional[MexcWebsocketPublic] = None
        self._rest_private: Optional[MexcPrivateExchange] = None
        self._rest_public: Optional[MexcPublicExchange] = None
        
        # WebSocket configuration optimized for HFT
        self._ws_config = WebSocketConfig(
            name="mexc_orderbooks",
            url=MexcConfig.WEBSOCKET_URL,
            timeout=30.0,
            ping_interval=20.0,
            max_reconnect_attempts=10,
            reconnect_delay=1.0,
            max_queue_size=1000,
            enable_compression=False  # Disable for performance
        )
        
        # Internal state management
        self._initialized = False
        self._balance_cache_time = 0.0
        self._balance_cache_ttl = 30.0  # 30-second cache TTL
        
        self.logger.info(f"Initialized {self.exchange} exchange")
    
    @property
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """
        Get current account balances mapped by Symbol.
        
        Note: This property returns balances keyed by Symbol for interface compliance.
        Use get_asset_balance() for direct asset lookup.
        
        Returns:
            Dict mapping Symbol to AssetBalance (empty dict for asset-only balances)
        """
        # Convert asset-based balances to symbol-based for interface compliance
        # This is a workaround since the interface expects Symbol keys
        symbol_balances = {}
        for asset_name, balance in self._balances_dict.items():
            # Create a dummy symbol for interface compliance
            # In practice, balances are asset-based, not symbol-based
            dummy_symbol = Symbol(base=asset_name, quote=AssetName("USDT"))
            symbol_balances[dummy_symbol] = balance
        return symbol_balances
    
    @property
    def active_symbols(self) -> List[Symbol]:
        """
        Get list of currently subscribed symbols.
        
        Returns:
            List of Symbol objects for active WebSocket subscriptions
        """
        return list(self._active_symbols)
    
    @property
    def orderbook(self) -> OrderBook:
        """
        Get the most recent orderbook from any subscribed symbol.
        
        Note: This returns a single OrderBook for interface compliance.
        Use get_orderbook(symbol) for symbol-specific orderbooks.
        
        Returns:
            OrderBook object (most recently updated symbol)
        """
        if not self._orderbooks:
            return OrderBook(bids=[], asks=[], timestamp=time.time())
        
        # Return the most recently updated orderbook
        return max(self._orderbooks.values(), key=lambda ob: ob.timestamp)
    
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """
        Get orderbook for a specific symbol.
        
        Args:
            symbol: Symbol to get orderbook for
            
        Returns:
            OrderBook object if symbol is subscribed, None otherwise
        """
        return self._orderbooks.get(symbol)
    
    def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """
        Get balance for a specific asset.
        
        Args:
            asset: Asset name to get balance for
            
        Returns:
            AssetBalance object if asset has balance, None otherwise
        """
        return self._balances_dict.get(asset)
    
    def get_all_orderbooks(self) -> Dict[Symbol, OrderBook]:
        """
        Get all current orderbooks.
        
        Returns:
            Dict mapping Symbol to OrderBook for all subscribed symbols
        """
        return self._orderbooks.copy()
    
    async def init(self, symbols: Optional[List[Symbol]] = None) -> None:
        """
        Initialize the exchange with optional symbol subscriptions.
        
        Args:
            symbols: Optional list of symbols to subscribe to initially
            
        Raises:
            ExchangeAPIError: If initialization fails
        """
        if self._initialized:
            self.logger.warning("Exchange already initialized")
            return
        
        try:
            # Initialize public REST client
            self._rest_public = MexcPublicExchange()
            self.logger.info("Initialized public REST client")
            
            # Initialize private REST client if credentials provided
            if self.has_private:
                self._rest_private = MexcPrivateExchange(self.api_key, self.secret_key)
                self.logger.info("Initialized private REST client")
                
                # Load initial account balances
                await self.refresh_balances()
            
            # Initialize WebSocket client for orderbook streaming
            self._ws_client = MexcWebsocketPublic(
                config=self._ws_config,
                orderbook_handler=self._on_orderbook_update,
                trades_handler=None  # Only need orderbooks for this implementation
            )
            
            # Start WebSocket connection
            await self._ws_client.start()
            self.logger.info("Started WebSocket client")
            
            # Subscribe to initial symbols if provided
            if symbols:
                for symbol in symbols:
                    await self.add_symbol(symbol)
            
            self._initialized = True
            self.logger.info(f"Successfully initialized {self.exchange} exchange")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize exchange: {e}")
            await self._cleanup_partial_init()
            raise ExchangeAPIError(500, f"Exchange initialization failed: {str(e)}")
    
    async def add_symbol(self, symbol: Symbol) -> None:
        """
        Subscribe to orderbook updates for a symbol.
        
        Args:
            symbol: Symbol to subscribe to
            
        Raises:
            ExchangeAPIError: If subscription fails
        """
        if not self._initialized:
            raise ExchangeAPIError(400, "Exchange not initialized. Call init() first.")
        
        if symbol in self._active_symbols:
            self.logger.debug(f"Already subscribed to {symbol}")
            return
        
        try:
            # Subscribe via WebSocket using existing method
            if self._ws_client:
                await self._ws_client.start_symbol(symbol)
            
            # Add to active symbols set
            self._active_symbols.add(symbol)
            
            # Initialize empty orderbook
            self._orderbooks[symbol] = OrderBook(
                bids=[],
                asks=[],
                timestamp=time.time()
            )
            
            self.logger.info(f"Subscribed to {symbol}")
            
        except Exception as e:
            self.logger.error(f"Failed to subscribe to {symbol}: {e}")
            raise ExchangeAPIError(500, f"Symbol subscription failed: {str(e)}")
    
    async def remove_symbol(self, symbol: Symbol) -> None:
        """
        Unsubscribe from orderbook updates for a symbol.
        
        Args:
            symbol: Symbol to unsubscribe from
            
        Raises:
            ExchangeAPIError: If unsubscription fails
        """
        if symbol not in self._active_symbols:
            self.logger.debug(f"Not subscribed to {symbol}")
            return
        
        try:
            # Unsubscribe via WebSocket using existing method
            if self._ws_client:
                await self._ws_client.stop_symbol(symbol)
            
            # Remove from active symbols and clean up data
            self._active_symbols.discard(symbol)
            self._orderbooks.pop(symbol, None)
            
            self.logger.info(f"Unsubscribed from {symbol}")
            
        except Exception as e:
            self.logger.error(f"Failed to unsubscribe from {symbol}: {e}")
            raise ExchangeAPIError(500, f"Symbol unsubscription failed: {str(e)}")
    
    async def refresh_balances(self) -> None:
        """
        Refresh account balances from REST API.
        
        Updates the internal balance cache with fresh data from MEXC.
        
        Raises:
            ExchangeAPIError: If balance refresh fails
        """
        if not self.has_private or not self._rest_private:
            raise ExchangeAPIError(400, "Private API access not configured")
        
        try:
            # Fetch fresh balances from REST API
            balance_list = await self._rest_private.get_account_balance()
            
            # Update internal cache with asset-based mapping
            new_balances = {}
            for balance in balance_list:
                new_balances[balance.asset] = balance
            
            self._balances_dict = new_balances
            self._balance_cache_time = time.time()
            
            self.logger.debug(f"Refreshed {len(balance_list)} account balances")
            
        except Exception as e:
            self.logger.error(f"Failed to refresh balances: {e}")
            raise ExchangeAPIError(500, f"Balance refresh failed: {str(e)}")
    
    async def get_fresh_balances(self, max_age: float = 30.0) -> Dict[AssetName, AssetBalance]:
        """
        Get fresh account balances, refreshing if cache is stale.
        
        Args:
            max_age: Maximum cache age in seconds (default: 30)
            
        Returns:
            Dict mapping AssetName to AssetBalance
            
        Raises:
            ExchangeAPIError: If balance fetch fails
        """
        current_time = time.time()
        cache_age = current_time - self._balance_cache_time
        
        if cache_age > max_age:
            await self.refresh_balances()
        
        return self._balances_dict.copy()
    
    async def _on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """
        Handle orderbook updates from WebSocket.
        
        Args:
            symbol: Symbol that was updated
            orderbook: New OrderBook data
        """
        if symbol in self._active_symbols:
            self._orderbooks[symbol] = orderbook
            self.logger.debug(
                f"Updated orderbook for {symbol}: "
                f"{len(orderbook.bids)} bids, {len(orderbook.asks)} asks"
            )
    
    async def _cleanup_partial_init(self) -> None:
        """
        Clean up resources after failed initialization.
        """
        if self._ws_client:
            try:
                await self._ws_client.stop()
            except Exception as e:
                self.logger.error(f"Error stopping WebSocket during cleanup: {e}")
        
        if self._rest_private:
            try:
                await self._rest_private.close()
            except Exception as e:
                self.logger.error(f"Error closing private REST during cleanup: {e}")
        
        # Reset state
        self._active_symbols.clear()
        self._orderbooks.clear()
        self._balances_dict.clear()
        self._initialized = False
    
    async def close(self) -> None:
        """
        Clean up all resources and close connections.
        
        Should be called when exchange is no longer needed to prevent
        resource leaks and ensure graceful shutdown.
        """
        self.logger.info("Closing exchange connections...")
        
        # Close WebSocket client
        if self._ws_client:
            try:
                await self._ws_client.stop()
                self.logger.info("Closed WebSocket client")
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")
        
        # Close private REST client
        if self._rest_private:
            try:
                await self._rest_private.close()
                self.logger.info("Closed private REST client")
            except Exception as e:
                self.logger.error(f"Error closing private REST: {e}")
        
        # Public REST client doesn't need explicit closing
        
        # Clear all internal state
        self._active_symbols.clear()
        self._orderbooks.clear()
        self._balances_dict.clear()
        self._initialized = False
        
        self.logger.info(f"Successfully closed {self.exchange} exchange")
    
    @asynccontextmanager
    async def session(self, symbols: Optional[List[Symbol]] = None):
        """
        Async context manager for exchange operations.
        
        Args:
            symbols: Optional list of symbols to subscribe to
            
        Usage:
            async with MexcExchange().session([symbol]) as exchange:
                orderbook = exchange.get_orderbook(symbol)
                balances = await exchange.get_fresh_balances()
        """
        try:
            await self.init(symbols)
            yield self
        finally:
            await self.close()
    
    def __repr__(self) -> str:
        return (
            f"MexcExchange(symbols={len(self._active_symbols)}, "
            f"balances={len(self._balances_dict)}, "
            f"initialized={self._initialized})"
        )