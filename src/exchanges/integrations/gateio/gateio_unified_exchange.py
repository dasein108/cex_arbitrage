"""
Gate.io Unified Exchange Implementation

Single interface combining public market data and private trading operations
for Gate.io exchange, following the UnifiedCompositeExchange pattern.

Architecture:
- Unified interface eliminating Abstract vs Composite confusion  
- Real-time WebSocket streaming for market data
- REST API for trading operations
- HFT-compliant performance with sub-50ms execution targets
- Comprehensive error handling and automatic reconnection

HFT Compliance:
- No caching of real-time trading data (balances, orders, positions)
- Real-time streaming orderbook data only
- Fresh API calls for all trading operations  
- Configuration data caching only (symbol info, endpoints)
"""

import time
import asyncio
from typing import Dict, List, Optional, Any, AsyncIterator
from contextlib import asynccontextmanager

from exchanges.interfaces.composite.unified_exchange import UnifiedCompositeExchange
from exchanges.structs.common import (
    Symbol, AssetBalance, Order, Position, Trade, OrderBook, Ticker, Kline,
    WithdrawalRequest, WithdrawalResponse, SymbolsInfo, SymbolInfo, OrderBookEntry
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderType, TimeInForce
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, get_exchange_logger
from infrastructure.exceptions.exchange import BaseExchangeError

# Gate.io specific imports
from exchanges.integrations.gateio.rest.gateio_rest_public import GateioPublicSpotRest
from exchanges.integrations.gateio.rest.gateio_rest_private import GateioPrivateSpotRest
from exchanges.integrations.gateio.ws.gateio_ws_public import GateioPublicSpotWebsocket
from exchanges.integrations.gateio.ws.gateio_ws_private import GateioPrivateSpotWebsocket


class GateioUnifiedExchange(UnifiedCompositeExchange):
    """
    Gate.io Unified Exchange - Complete Trading & Market Data Operations
    
    Single interface providing both market data observation and trading execution
    optimized for arbitrage operations that require both capabilities.
    
    Key Features:
    1. **Market Data Streaming**: Real-time orderbook, ticker, and trade data via WebSocket
    2. **Trading Operations**: Full order management, balance tracking, position monitoring
    3. **HFT Performance**: Sub-50ms order execution with minimal latency data access
    4. **Resource Management**: Proper async context managers and connection pooling
    5. **Error Recovery**: Automatic reconnection with exponential backoff
    6. **Batch Operations**: Efficient multiple order placement and cancellation
    7. **Withdrawal Support**: Complete cryptocurrency withdrawal management
    
    Architecture:
    - REST clients for trading operations (public + private)
    - WebSocket clients for real-time streaming (public + private)  
    - Unified data structures for consistent API across all operations
    - Performance tracking and health monitoring throughout
    """
    
    def __init__(self, 
                 config: ExchangeConfig, 
                 symbols: Optional[List[Symbol]] = None,
                 logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize Gate.io unified exchange.
        
        Args:
            config: Exchange configuration with credentials and WebSocket settings
            symbols: Symbols to initialize for trading/market data  
            logger: Optional logger instance
        """
        super().__init__(config, symbols, logger)
        
        # REST clients for API operations
        self._public_rest: Optional[GateioPublicSpotRest] = None
        self._private_rest: Optional[GateioPrivateSpotRest] = None
        
        # WebSocket clients for real-time streaming
        self._public_ws: Optional[GateioPublicSpotWebsocket] = None
        self._private_ws: Optional[GateioPrivateSpotWebsocket] = None
        
        # Market data storage (real-time streaming data)
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._tickers: Dict[Symbol, Ticker] = {}
        self._symbols_info: SymbolsInfo = {}
        
        # Trading data (NEVER CACHED - always fresh from API)
        self._last_balances_fetch = 0.0
        self._last_orders_fetch = 0.0
        self._last_positions_fetch = 0.0
        
        # Performance tracking
        self._orderbook_updates = 0
        self._trade_updates = 0
        self._order_operations = 0
        
        # Connection state
        self._public_ws_connected = False
        self._private_ws_connected = False
        self._rest_initialized = False
        
        self.logger.info("Gate.io unified exchange initialized",
                        exchange="gateio",
                        symbol_count=len(self.symbols),
                        has_credentials=config.has_credentials())
    
    # ========================================
    # Lifecycle Management
    # ========================================
    
    async def initialize(self) -> None:
        """
        Initialize all Gate.io exchange connections and load initial data.
        
        Initialization sequence:
        1. Initialize REST clients (public + private if credentials available)
        2. Load symbols info and trading rules  
        3. Initialize WebSocket connections for real-time data
        4. Load initial orderbook snapshots
        5. Start private WebSocket if credentials available
        6. Set up background tasks for health monitoring
        """
        start_time = time.perf_counter()
        
        try:
            # Step 1: Initialize REST clients
            await self._initialize_rest_clients()
            
            # Step 2: Load symbols info and trading rules
            await self._load_symbols_info()
            
            # Step 3: Initialize WebSocket connections
            await self._initialize_websockets()
            
            # Step 4: Load initial orderbook snapshots
            await self._load_initial_orderbooks()
            
            # Step 5: Validate private access if credentials provided
            if self.config.has_credentials():
                await self._validate_private_access()
            
            # Mark as initialized
            self._initialized = True
            self._connected = self._public_ws_connected and self._rest_initialized
            
            init_time = time.perf_counter() - start_time
            self.logger.info("Gate.io exchange initialized successfully",
                           initialization_time_ms=f"{init_time*1000:.2f}",
                           symbols_loaded=len(self._symbols_info),
                           has_private_access=self.config.has_credentials())
            
        except Exception as e:
            self.logger.error("Failed to initialize Gate.io exchange", error=str(e))
            await self.close()  # Clean up any partial initialization
            raise BaseExchangeError(500, f"Gate.io initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """
        Close all Gate.io connections and clean up resources.
        
        Cleanup sequence:
        1. Close WebSocket connections gracefully
        2. Close REST client sessions
        3. Clear cached data
        4. Reset connection state
        """
        try:
            self.logger.info("Closing Gate.io unified exchange...")
            
            # Close WebSocket connections
            if self._public_ws:
                await self._public_ws.close()
                self._public_ws = None
            
            if self._private_ws:
                await self._private_ws.close()
                self._private_ws = None
            
            # Close REST clients
            if self._public_rest:
                await self._public_rest.close()
                self._public_rest = None
                
            if self._private_rest:
                await self._private_rest.close() 
                self._private_rest = None
            
            # Clear cached data
            self._orderbooks.clear()
            self._tickers.clear()
            self._symbols_info = {}
            
            # Reset state
            self._initialized = False
            self._connected = False
            self._public_ws_connected = False
            self._private_ws_connected = False
            self._rest_initialized = False
            
            self.logger.info("Gate.io exchange closed successfully")
            
        except Exception as e:
            self.logger.error("Error closing Gate.io exchange", error=str(e))
    
    async def _initialize_rest_clients(self) -> None:
        """Initialize REST clients for API operations."""
        try:
            # Initialize public REST client (always available)
            self._public_rest = GateioPublicSpotRest(
                config=self.config,
                logger=self.logger
            )
            await self._public_rest.initialize()
            
            # Initialize private REST client if credentials available
            if self.config.has_credentials():
                self._private_rest = GateioPrivateSpotRest(
                    config=self.config,
                    logger=self.logger
                )
                await self._private_rest.initialize()
                
            self._rest_initialized = True
            self.logger.info("Gate.io REST clients initialized",
                           has_private_client=self._private_rest is not None)
                           
        except Exception as e:
            self.logger.error("Failed to initialize Gate.io REST clients", error=str(e))
            raise
    
    async def _initialize_websockets(self) -> None:
        """Initialize WebSocket connections for real-time streaming."""
        try:
            # Initialize public WebSocket for market data
            if not self.config.websocket:
                raise ValueError("Gate.io WebSocket configuration missing")
                
            self._public_ws = GateioPublicSpotWebsocket(
                config=self.config,
                orderbook_handler=self._handle_orderbook_update,
                ticker_handler=self._handle_ticker_update,
                trade_handler=self._handle_trade_update,
                state_change_handler=self._handle_connection_state_change,
                logger=self.logger
            )
            
            await self._public_ws.initialize(self.symbols)
            self._public_ws_connected = True
            
            # Initialize private WebSocket if credentials available
            if self.config.has_credentials():
                self._private_ws = GateioPrivateSpotWebsocket(
                    config=self.config,
                    balance_handler=self._handle_balance_update,
                    order_handler=self._handle_order_update,
                    state_change_handler=self._handle_private_connection_state_change,
                    logger=self.logger
                )
                
                await self._private_ws.initialize()
                self._private_ws_connected = True
            
            self.logger.info("Gate.io WebSocket connections initialized",
                           public_ws_connected=self._public_ws_connected,
                           private_ws_connected=self._private_ws_connected)
                           
        except Exception as e:
            self.logger.error("Failed to initialize Gate.io WebSockets", error=str(e))
            raise
    
    async def _load_symbols_info(self) -> None:
        """Load symbols information and trading rules."""
        if not self._public_rest:
            raise BaseExchangeError(500, "Public REST client not initialized")
            
        try:
            self._symbols_info = await self._public_rest.get_exchange_info()
            self.logger.info("Gate.io symbols info loaded",
                           symbols_count=len(self._symbols_info))
                           
        except Exception as e:
            self.logger.error("Failed to load Gate.io symbols info", error=str(e))
            raise
    
    async def _load_initial_orderbooks(self) -> None:
        """Load initial orderbook snapshots for all symbols."""
        if not self._public_rest:
            raise BaseExchangeError(500, "Public REST client not initialized")
            
        try:
            # Load orderbook snapshots for all symbols
            for symbol in self.symbols:
                try:
                    orderbook = await self._public_rest.get_orderbook(symbol)
                    self._orderbooks[symbol] = orderbook
                    
                except Exception as e:
                    self.logger.warning(f"Failed to load initial orderbook for {symbol}",
                                      error=str(e))
                    
            self.logger.info("Gate.io initial orderbooks loaded",
                           orderbooks_loaded=len(self._orderbooks))
                           
        except Exception as e:
            self.logger.error("Failed to load Gate.io initial orderbooks", error=str(e))
            raise
    
    async def _validate_private_access(self) -> None:
        """Validate private API access with test call."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
            
        try:
            # Test private access with account info call
            await self._private_rest.get_account_info()
            self.logger.info("Gate.io private API access validated")
            
        except Exception as e:
            self.logger.error("Gate.io private API validation failed", error=str(e))
            raise
    
    # ========================================
    # Market Data Operations (Public)
    # ========================================
    
    @property
    def symbols_info(self) -> SymbolsInfo:
        """Get symbols information and trading rules."""
        if not self._symbols_info:
            raise BaseExchangeError(500, "Symbols info not loaded")
        return self._symbols_info.copy()
    
    @property  
    def active_symbols(self) -> List[Symbol]:
        """Get currently active symbols for market data."""
        return list(self._orderbooks.keys())
    
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """
        Get current orderbook for symbol.
        
        Returns cached orderbook data from WebSocket streams.
        HFT COMPLIANT: <1ms access time.
        """
        self._track_operation("get_orderbook")
        return self._orderbooks.get(symbol)
    
    def get_ticker(self, symbol: Symbol) -> Optional[Ticker]:
        """Get 24hr ticker statistics for symbol."""
        self._track_operation("get_ticker")
        return self._tickers.get(symbol)
    
    async def get_klines(self, 
                        symbol: Symbol, 
                        interval: str, 
                        limit: int = 500) -> List[Kline]:
        """Get historical klines/candlestick data."""
        if not self._public_rest:
            raise BaseExchangeError(500, "Public REST client not available")
            
        self._track_operation("get_klines")
        
        try:
            return await self._public_rest.get_klines(symbol, interval, limit)
        except Exception as e:
            self.logger.error("Failed to get klines", symbol=symbol, error=str(e))
            raise BaseExchangeError(500, f"Klines fetch failed: {str(e)}")
    
    async def get_recent_trades(self, symbol: Symbol, limit: int = 100) -> List[Trade]:
        """Get recent trade history for symbol."""
        if not self._public_rest:
            raise BaseExchangeError(500, "Public REST client not available")
            
        self._track_operation("get_recent_trades")
        
        try:
            return await self._public_rest.get_recent_trades(symbol, limit)
        except Exception as e:
            self.logger.error("Failed to get recent trades", symbol=symbol, error=str(e))
            raise BaseExchangeError(500, f"Recent trades fetch failed: {str(e)}")
    
    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols for market data streaming."""
        try:
            if self._public_ws:
                await self._public_ws.subscribe_symbols(symbols)
                
            # Load initial orderbook snapshots for new symbols
            for symbol in symbols:
                if symbol not in self._orderbooks:
                    try:
                        orderbook = await self._public_rest.get_orderbook(symbol)
                        self._orderbooks[symbol] = orderbook
                    except Exception as e:
                        self.logger.warning(f"Failed to load orderbook for new symbol {symbol}",
                                          error=str(e))
            
            self.logger.info("Added symbols for streaming", symbols=symbols)
            
        except Exception as e:
            self.logger.error("Failed to add symbols", symbols=symbols, error=str(e))
            raise BaseExchangeError(500, f"Add symbols failed: {str(e)}")
    
    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """Remove symbols from market data streaming."""
        try:
            if self._public_ws:
                await self._public_ws.unsubscribe_symbols(symbols)
                
            # Remove from local storage
            for symbol in symbols:
                self._orderbooks.pop(symbol, None)
                self._tickers.pop(symbol, None)
            
            self.logger.info("Removed symbols from streaming", symbols=symbols)
            
        except Exception as e:
            self.logger.error("Failed to remove symbols", symbols=symbols, error=str(e))
            raise BaseExchangeError(500, f"Remove symbols failed: {str(e)}")
    
    # ========================================
    # Trading Operations (Private)
    # ========================================
    
    # REMOVED: Properties that encouraged unsafe caching of real-time trading data
    # HFT SAFETY: All trading data access now uses async methods with fresh API calls
    
    async def get_balances(self) -> Dict[str, AssetBalance]:
        """Get current account balances with fresh API call."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
            
        self._track_operation("get_balances")
        
        try:
            with LoggingTimer(self.logger, "get_balances") as timer:
                balances = await self._private_rest.get_account_balances()
                
                self._last_balances_fetch = time.time()
                self.logger.metric("get_balances_duration_ms", timer.elapsed_ms,
                                 tags={"exchange": "gateio"})
                
                return balances
                
        except Exception as e:
            self.logger.error("Failed to get balances", error=str(e))
            raise BaseExchangeError(500, f"Balance fetch failed: {str(e)}")
    
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, List[Order]]:
        """Get current open orders with fresh API call."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
            
        self._track_operation("get_open_orders")
        
        try:
            with LoggingTimer(self.logger, "get_open_orders") as timer:
                orders = await self._private_rest.get_open_orders(symbol)
                
                self._last_orders_fetch = time.time()
                self.logger.metric("get_open_orders_duration_ms", timer.elapsed_ms,
                                 tags={"exchange": "gateio"})
                
                return orders
                
        except Exception as e:
            self.logger.error("Failed to get open orders", error=str(e))
            raise BaseExchangeError(500, f"Open orders fetch failed: {str(e)}")
    
    async def get_positions(self) -> Dict[Symbol, Position]:
        """Get current positions (spot trading returns empty dict)."""
        # Gate.io spot trading doesn't have positions
        self._last_positions_fetch = time.time()
        return {}
    
    # Order management
    async def place_limit_order(self,
                              symbol: Symbol,
                              side: Side,
                              quantity: float,
                              price: float,
                              time_in_force: TimeInForce = TimeInForce.GTC,
                              **kwargs) -> Order:
        """
        Place a limit order.
        
        HFT TARGET: <50ms execution time.
        """
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("place_limit_order")
        self._order_operations += 1
        
        try:
            with LoggingTimer(self.logger, "place_limit_order") as timer:
                order = await self._private_rest.place_limit_order(
                    symbol, side, quantity, price, time_in_force, **kwargs
                )
                
                self.logger.metric("place_limit_order_duration_ms", timer.elapsed_ms,
                                 tags={"exchange": "gateio", "symbol": str(symbol), "side": side.value})
                
                self.logger.info("Limit order placed",
                               symbol=symbol,
                               side=side.value,
                               quantity=quantity,
                               price=price,
                               order_id=order.order_id)
                
                return order
                
        except Exception as e:
            self.logger.error("Failed to place limit order",
                            symbol=symbol,
                            side=side.value,
                            quantity=quantity,
                            price=price,
                            error=str(e))
            raise BaseExchangeError(500, f"Limit order placement failed: {str(e)}")
    
    async def place_market_order(self,
                               symbol: Symbol,
                               side: Side,
                               quantity: float,
                               **kwargs) -> Order:
        """
        Place a market order.
        
        HFT TARGET: <50ms execution time.
        """
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("place_market_order")
        self._order_operations += 1
        
        try:
            with LoggingTimer(self.logger, "place_market_order") as timer:
                order = await self._private_rest.place_market_order(
                    symbol, side, quantity, **kwargs
                )
                
                self.logger.metric("place_market_order_duration_ms", timer.elapsed_ms,
                                 tags={"exchange": "gateio", "symbol": str(symbol), "side": side.value})
                
                self.logger.info("Market order placed",
                               symbol=symbol,
                               side=side.value,
                               quantity=quantity,
                               order_id=order.order_id)
                
                return order
                
        except Exception as e:
            self.logger.error("Failed to place market order",
                            symbol=symbol,
                            side=side.value,
                            quantity=quantity,
                            error=str(e))
            raise BaseExchangeError(500, f"Market order placement failed: {str(e)}")
    
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> bool:
        """
        Cancel an order.
        
        HFT TARGET: <50ms execution time.
        """
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("cancel_order")
        
        try:
            with LoggingTimer(self.logger, "cancel_order") as timer:
                success = await self._private_rest.cancel_order(order_id, symbol)
                
                self.logger.metric("cancel_order_duration_ms", timer.elapsed_ms,
                                 tags={"exchange": "gateio", "symbol": str(symbol)})
                
                self.logger.info("Order cancellation result",
                               symbol=symbol,
                               order_id=order_id,
                               success=success)
                
                return success
                
        except Exception as e:
            self.logger.error("Failed to cancel order",
                            symbol=symbol,
                            order_id=order_id,
                            error=str(e))
            raise BaseExchangeError(500, f"Order cancellation failed: {str(e)}")
    
    async def cancel_all_orders(self, symbol: Optional[Symbol] = None) -> List[bool]:
        """Cancel all orders for symbol (or all symbols)."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("cancel_all_orders")
        
        try:
            with LoggingTimer(self.logger, "cancel_all_orders") as timer:
                results = await self._private_rest.cancel_all_orders(symbol)
                
                self.logger.metric("cancel_all_orders_duration_ms", timer.elapsed_ms,
                                 tags={"exchange": "gateio"})
                
                self.logger.info("Bulk order cancellation completed",
                               symbol=symbol,
                               cancelled_count=sum(results))
                
                return results
                
        except Exception as e:
            self.logger.error("Failed to cancel all orders", symbol=symbol, error=str(e))
            raise BaseExchangeError(500, f"Bulk cancellation failed: {str(e)}")
    
    async def get_order(self, order_id: OrderId, symbol: Symbol) -> Optional[Order]:
        """Get order details."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("get_order")
        
        try:
            return await self._private_rest.get_order_status(order_id, symbol)
        except Exception as e:
            self.logger.error("Failed to get order details",
                            order_id=order_id,
                            symbol=symbol,
                            error=str(e))
            raise BaseExchangeError(500, f"Order query failed: {str(e)}")
    
    async def get_order_history(self, 
                               symbol: Optional[Symbol] = None,
                               limit: int = 100) -> List[Order]:
        """Get historical orders."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("get_order_history")
        
        try:
            return await self._private_rest.get_order_history(symbol, limit)
        except Exception as e:
            self.logger.error("Failed to get order history", symbol=symbol, error=str(e))
            raise BaseExchangeError(500, f"Order history fetch failed: {str(e)}")
    
    # Batch operations for efficiency
    async def place_multiple_orders(self, orders: List[Dict[str, Any]]) -> List[Order]:
        """Place multiple orders in batch for efficiency."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("place_multiple_orders")
        
        try:
            with LoggingTimer(self.logger, "place_multiple_orders") as timer:
                results = await self._private_rest.place_multiple_orders(orders)
                
                self.logger.metric("place_multiple_orders_duration_ms", timer.elapsed_ms,
                                 tags={"exchange": "gateio", "order_count": len(orders)})
                
                self.logger.info("Batch order placement completed",
                               requested_orders=len(orders),
                               successful_orders=len(results))
                
                return results
                
        except Exception as e:
            self.logger.error("Failed to place multiple orders", 
                            order_count=len(orders),
                            error=str(e))
            raise BaseExchangeError(500, f"Batch order placement failed: {str(e)}")
    
    async def cancel_multiple_orders(self, 
                                   order_cancellations: List[Dict[str, Any]]) -> List[bool]:
        """Cancel multiple orders in batch."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("cancel_multiple_orders")
        
        try:
            with LoggingTimer(self.logger, "cancel_multiple_orders") as timer:
                results = await self._private_rest.cancel_multiple_orders(order_cancellations)
                
                self.logger.metric("cancel_multiple_orders_duration_ms", timer.elapsed_ms,
                                 tags={"exchange": "gateio", "cancellation_count": len(order_cancellations)})
                
                self.logger.info("Batch order cancellation completed",
                               requested_cancellations=len(order_cancellations),
                               successful_cancellations=sum(results))
                
                return results
                
        except Exception as e:
            self.logger.error("Failed to cancel multiple orders",
                            cancellation_count=len(order_cancellations),
                            error=str(e))
            raise BaseExchangeError(500, f"Batch cancellation failed: {str(e)}")
    
    # ========================================
    # Withdrawal Operations
    # ========================================
    
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """Submit withdrawal request."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("withdraw")
        
        try:
            return await self._private_rest.submit_withdrawal(request)
        except Exception as e:
            self.logger.error("Failed to submit withdrawal", error=str(e))
            raise BaseExchangeError(500, f"Withdrawal submission failed: {str(e)}")
    
    async def cancel_withdrawal(self, withdrawal_id: str) -> bool:
        """Cancel pending withdrawal."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("cancel_withdrawal")
        
        try:
            return await self._private_rest.cancel_withdrawal(withdrawal_id)
        except Exception as e:
            self.logger.error("Failed to cancel withdrawal", 
                            withdrawal_id=withdrawal_id,
                            error=str(e))
            raise BaseExchangeError(500, f"Withdrawal cancellation failed: {str(e)}")
    
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """Get withdrawal status."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("get_withdrawal_status")
        
        try:
            return await self._private_rest.get_withdrawal_status(withdrawal_id)
        except Exception as e:
            self.logger.error("Failed to get withdrawal status",
                            withdrawal_id=withdrawal_id,
                            error=str(e))
            raise BaseExchangeError(500, f"Withdrawal status query failed: {str(e)}")
    
    async def get_withdrawal_history(self,
                                   asset: Optional[AssetName] = None,
                                   limit: int = 100) -> List[WithdrawalResponse]:
        """Get withdrawal history."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("get_withdrawal_history")
        
        try:
            return await self._private_rest.get_withdrawal_history(asset, limit)
        except Exception as e:
            self.logger.error("Failed to get withdrawal history", error=str(e))
            raise BaseExchangeError(500, f"Withdrawal history fetch failed: {str(e)}")
    
    async def validate_withdrawal_address(self,
                                        asset: AssetName,
                                        address: str,
                                        network: Optional[str] = None) -> bool:
        """Validate withdrawal address."""
        if not self._private_rest:
            return False
            
        self._track_operation("validate_withdrawal_address")
        
        try:
            return await self._private_rest.validate_withdrawal_address(asset, address, network)
        except Exception as e:
            self.logger.error("Failed to validate withdrawal address",
                            asset=asset,
                            address=address,
                            network=network,
                            error=str(e))
            return False
    
    async def get_withdrawal_limits(self,
                                  asset: AssetName,
                                  network: Optional[str] = None) -> Dict[str, float]:
        """Get withdrawal limits."""
        if not self._private_rest:
            raise BaseExchangeError(500, "Private REST client not available")
        
        self._track_operation("get_withdrawal_limits")
        
        try:
            return await self._private_rest.get_withdrawal_limits(asset, network)
        except Exception as e:
            self.logger.error("Failed to get withdrawal limits",
                            asset=asset,
                            network=network,
                            error=str(e))
            raise BaseExchangeError(500, f"Withdrawal limits query failed: {str(e)}")
    
    # ========================================
    # Event Handlers for Real-time Data
    # ========================================
    
    async def _handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """Handle orderbook update events from WebSocket."""
        try:
            self._orderbooks[symbol] = orderbook
            self._orderbook_updates += 1
            
            # Call optional override
            await self.on_orderbook_update(symbol, orderbook)
            
            # Log periodically to avoid spam
            if self._orderbook_updates % 1000 == 0:
                self.logger.debug("Orderbook updates processed",
                                count=self._orderbook_updates)
                                
        except Exception as e:
            self.logger.error("Error handling orderbook update",
                            symbol=symbol,
                            error=str(e))
    
    async def _handle_ticker_update(self, symbol: Symbol, ticker: Ticker) -> None:
        """Handle ticker update events from WebSocket."""
        try:
            self._tickers[symbol] = ticker
            # No need to track count for tickers
            
        except Exception as e:
            self.logger.error("Error handling ticker update",
                            symbol=symbol,
                            error=str(e))
    
    async def _handle_trade_update(self, symbol: Symbol, trade: Trade) -> None:
        """Handle new trade events from WebSocket."""
        try:
            self._trade_updates += 1
            
            # Call optional override
            await self.on_trade_update(symbol, trade)
            
        except Exception as e:
            self.logger.error("Error handling trade update",
                            symbol=symbol,
                            error=str(e))
    
    async def _handle_order_update(self, order: Order) -> None:
        """Handle order status updates from private WebSocket."""
        try:
            # Call optional override
            await self.on_order_update(order)
            
            self.logger.debug("Order update received",
                            order_id=order.order_id,
                            status=order.status,
                            symbol=order.symbol)
                            
        except Exception as e:
            self.logger.error("Error handling order update",
                            order_id=order.order_id if hasattr(order, 'order_id') else 'unknown',
                            error=str(e))
    
    async def _handle_balance_update(self, asset: str, balance: AssetBalance) -> None:
        """Handle balance updates from private WebSocket."""
        try:
            # Call optional override  
            await self.on_balance_update(asset, balance)
            
            self.logger.debug("Balance update received",
                            asset=asset,
                            available=balance.available,
                            locked=balance.locked)
                            
        except Exception as e:
            self.logger.error("Error handling balance update",
                            asset=asset,
                            error=str(e))
    
    async def _handle_connection_state_change(self, connected: bool, exchange: str = "gateio") -> None:
        """Handle public WebSocket connection state changes."""
        self._public_ws_connected = connected
        self._connected = self._public_ws_connected and self._rest_initialized
        
        self.logger.info("Gate.io public WebSocket connection state changed",
                        connected=connected,
                        overall_connected=self._connected)
    
    async def _handle_private_connection_state_change(self, connected: bool, exchange: str = "gateio") -> None:
        """Handle private WebSocket connection state changes."""
        self._private_ws_connected = connected
        
        self.logger.info("Gate.io private WebSocket connection state changed",
                        connected=connected)
    
    # ========================================
    # Health and Performance Monitoring
    # ========================================
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        base_stats = super().get_performance_stats()
        
        gate_stats = {
            "orderbook_updates": self._orderbook_updates,
            "trade_updates": self._trade_updates, 
            "order_operations": self._order_operations,
            "public_ws_connected": self._public_ws_connected,
            "private_ws_connected": self._private_ws_connected,
            "rest_initialized": self._rest_initialized,
            "symbols_loaded": len(self._symbols_info),
            "active_orderbooks": len(self._orderbooks),
            "active_tickers": len(self._tickers),
            "last_balances_fetch": self._last_balances_fetch,
            "last_orders_fetch": self._last_orders_fetch
        }
        
        return {**base_stats, **gate_stats}
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get detailed health status for monitoring."""
        base_health = super().get_health_status()
        
        # Check data freshness (5 second threshold)
        current_time = time.time()
        fresh_threshold = 5.0
        
        gate_health = {
            "connections": {
                "rest_public": self._public_rest is not None,
                "rest_private": self._private_rest is not None,
                "websocket_public": self._public_ws_connected,
                "websocket_private": self._private_ws_connected
            },
            "data_freshness": {
                "orderbooks": len(self._orderbooks) > 0,
                "balances": (current_time - self._last_balances_fetch) < fresh_threshold if self._last_balances_fetch > 0 else False,
                "orders": (current_time - self._last_orders_fetch) < fresh_threshold if self._last_orders_fetch > 0 else False
            },
            "performance": {
                "orderbook_updates_per_sec": self._orderbook_updates / max(current_time - self._last_operation_time, 1) if self._last_operation_time > 0 else 0,
                "symbols_loaded": len(self._symbols_info) > 0
            }
        }
        
        # Override healthy status based on Gate.io specific requirements
        gate_healthy = (
            self._rest_initialized and 
            self._public_ws_connected and 
            len(self._orderbooks) > 0 and
            len(self._symbols_info) > 0
        )
        
        return {
            **base_health,
            "healthy": gate_healthy,
            **gate_health
        }


# Import LoggingTimer for performance measurement
from infrastructure.logging.hft_logger import LoggingTimer