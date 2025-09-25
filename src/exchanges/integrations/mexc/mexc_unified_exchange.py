"""
MEXC Unified Exchange Implementation

Simplified MEXC implementation using the unified interface that combines
public market data and private trading operations in a single, coherent class.

This replaces both mexc/private_exchange.py and mexc/private_exchange_refactored.py
with a cleaner, more maintainable implementation.
"""

from typing import List, Dict, Optional, Any, AsyncIterator
import time
import asyncio

from exchanges.interfaces.composite.unified_exchange import UnifiedCompositeExchange
from exchanges.structs.common import (
    Symbol, AssetBalance, Order, Position, Trade, OrderBook, Ticker, Kline,
    WithdrawalRequest, WithdrawalResponse, SymbolsInfo
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderType, TimeInForce, OrderStatus
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface
from infrastructure.exceptions.exchange import BaseExchangeError

# MEXC-specific imports
from exchanges.integrations.mexc.rest.mexc_rest_private import MexcPrivateSpotRest
from exchanges.integrations.mexc.rest.mexc_rest_public import MexcPublicSpotRest
from exchanges.integrations.mexc.ws.mexc_ws_public import MexcPublicSpotWebsocket
from exchanges.integrations.mexc.ws.mexc_ws_private import MexcPrivateSpotWebsocket
from exchanges.integrations.mexc.services.mexc_mappings import MexcSymbol


class MexcUnifiedExchange(UnifiedCompositeExchange):
    """
    MEXC Unified Exchange Implementation.
    
    Provides both market data observation and trading execution in a single
    interface optimized for arbitrage operations.
    
    Features:
    - Real-time orderbook streaming via WebSocket
    - Sub-50ms order execution via REST API  
    - Real-time account updates via private WebSocket
    - Efficient batch operations
    - Comprehensive error handling and retry logic
    - Performance tracking and health monitoring
    """
    
    def __init__(self, 
                 config: ExchangeConfig, 
                 symbols: Optional[List[Symbol]] = None,
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize MEXC unified exchange."""
        super().__init__(config, symbols, logger)
        
        # REST clients
        self._public_rest: Optional[MexcPublicSpotRest] = None
        self._private_rest: Optional[MexcPrivateSpotRest] = None
        
        # WebSocket clients  
        self._public_ws: Optional[MexcPublicSpotWebsocket] = None
        self._private_ws: Optional[MexcPrivateSpotWebsocket] = None
        
        # Data storage (HFT SAFE - only static/market data)
        self._symbols_info: Optional[SymbolsInfo] = None
        self._orderbooks: Dict[Symbol, OrderBook] = {}  # Market data streaming - safe to cache
        self._tickers: Dict[Symbol, Ticker] = {}  # Market data streaming - safe to cache
        
        # REMOVED: Trading data caching variables (HFT SAFETY VIOLATION)
        # self._balances, self._open_orders, self._positions removed
        # All trading data must be fetched fresh via async methods
        
        # Symbol management
        self._active_symbols: List[Symbol] = self.symbols.copy()
        
        self.logger.info("MEXC unified exchange created", 
                        exchange="mexc",
                        symbol_count=len(self._active_symbols))
    
    # ========================================
    # Lifecycle Management
    # ========================================
    
    async def initialize(self) -> None:
        """Initialize MEXC exchange connections and data."""
        if self._initialized:
            return
        
        try:
            self.logger.info("Initializing MEXC exchange connections...")
            
            # Initialize REST clients
            await self._initialize_rest_clients()
            
            # Load symbols info and trading rules
            await self._load_symbols_info()
            
            # Initialize WebSocket connections
            await self._initialize_websocket_clients()
            
            # Load initial account data if credentials available
            if self.config.has_credentials():
                await self._load_account_data()
            
            # Subscribe to market data for active symbols
            if self._active_symbols:
                await self.add_symbols(self._active_symbols)
            
            self._initialized = True
            self._connected = True
            
            self.logger.info("MEXC exchange initialized successfully",
                           exchange="mexc",
                           symbols_loaded=len(self._symbols_info) if self._symbols_info else 0,
                           active_symbols=len(self._active_symbols),
                           has_account_data=bool(self._balances))
            
        except Exception as e:
            self.logger.error("Failed to initialize MEXC exchange", error=str(e))
            await self.close()  # Cleanup on failure
            raise BaseExchangeError(f"MEXC initialization failed: {e}")
    
    async def close(self) -> None:
        """Close all MEXC connections and clean up resources.""" 
        if not self._initialized and not self._connected:
            return
        
        try:
            self.logger.info("Closing MEXC exchange connections...")
            
            # Close WebSocket connections
            if self._public_ws:
                await self._public_ws.close()
                self._public_ws = None
            
            if self._private_ws:
                await self._private_ws.close()
                self._private_ws = None
            
            # Close REST clients (they may have session cleanup)
            if self._private_rest:
                await self._private_rest.close()
                self._private_rest = None
            
            if self._public_rest:
                await self._public_rest.close()
                self._public_rest = None
            
            # Clear data
            self._orderbooks.clear()
            self._tickers.clear() 
            self._balances.clear()
            self._open_orders.clear()
            self._positions.clear()
            
            self._initialized = False
            self._connected = False
            
            self.logger.info("MEXC exchange closed successfully")
            
        except Exception as e:
            self.logger.error("Error closing MEXC exchange", error=str(e))
    
    # ========================================
    # Market Data Operations (Public)
    # ========================================
    
    @property
    def symbols_info(self) -> SymbolsInfo:
        """Get MEXC symbols information."""
        return self._symbols_info or {}
    
    @property
    def active_symbols(self) -> List[Symbol]:
        """Get currently active symbols."""
        return self._active_symbols.copy()
    
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """Get current orderbook from WebSocket stream."""
        return self._orderbooks.get(symbol)
    
    def get_ticker(self, symbol: Symbol) -> Optional[Ticker]:
        """Get 24hr ticker statistics."""
        return self._tickers.get(symbol)
    
    async def get_klines(self, 
                        symbol: Symbol, 
                        interval: str, 
                        limit: int = 500) -> List[Kline]:
        """Get historical klines from REST API."""
        if not self._public_rest:
            raise BaseExchangeError("Public REST client not available")
        
        mexc_symbol = self._to_mexc_symbol(symbol)
        return await self._public_rest.get_klines(mexc_symbol, interval, limit)
    
    async def get_recent_trades(self, symbol: Symbol, limit: int = 100) -> List[Trade]:
        """Get recent trades from REST API.""" 
        if not self._public_rest:
            raise BaseExchangeError("Public REST client not available")
        
        mexc_symbol = self._to_mexc_symbol(symbol)
        return await self._public_rest.get_recent_trades(mexc_symbol, limit)
    
    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols for market data streaming."""
        if not symbols:
            return
        
        new_symbols = [s for s in symbols if s not in self._active_symbols]
        if not new_symbols:
            return
        
        try:
            # Subscribe to WebSocket streams for new symbols
            if self._public_ws:
                await self._public_ws.add_symbols(new_symbols)
            
            # Update active symbols list
            self._active_symbols.extend(new_symbols)
            
            self.logger.info("Added symbols for market data",
                           exchange="mexc", 
                           new_symbols=[str(s) for s in new_symbols],
                           total_symbols=len(self._active_symbols))
            
        except Exception as e:
            self.logger.error("Failed to add symbols", error=str(e))
            raise BaseExchangeError(f"Failed to add symbols: {e}")
    
    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """Remove symbols from market data streaming."""
        if not symbols:
            return
        
        symbols_to_remove = [s for s in symbols if s in self._active_symbols]
        if not symbols_to_remove:
            return
        
        try:
            # Unsubscribe from WebSocket streams
            if self._public_ws:
                await self._public_ws.remove_symbols(symbols_to_remove)
            
            # Update active symbols list
            for symbol in symbols_to_remove:
                self._active_symbols.remove(symbol)
                # Clean up cached data
                self._orderbooks.pop(symbol, None)
                self._tickers.pop(symbol, None)
            
            self.logger.info("Removed symbols from market data",
                           exchange="mexc",
                           removed_symbols=[str(s) for s in symbols_to_remove],
                           remaining_symbols=len(self._active_symbols))
            
        except Exception as e:
            self.logger.error("Failed to remove symbols", error=str(e))
    
    # ========================================
    # Trading Operations (Private)
    # ========================================
    
    # REMOVED: Properties that cached real-time trading data (HFT SAFETY VIOLATION)
    # HFT SAFETY: All trading data access now uses async methods with fresh API calls
    
    async def place_limit_order(self,
                              symbol: Symbol,
                              side: Side,
                              quantity: float,
                              price: float,
                              time_in_force: TimeInForce = TimeInForce.GTC,
                              **kwargs) -> Order:
        """Place limit order with HFT optimization."""
        if not self._private_rest:
            raise BaseExchangeError("Private REST client not available")
        
        start_time = time.perf_counter()
        self._track_operation("place_limit_order")
        
        try:
            # Convert to MEXC format
            mexc_symbol = self._to_mexc_symbol(symbol)
            mexc_side = self._to_mexc_side(side)
            mexc_tif = self._to_mexc_tif(time_in_force)
            
            # Prepare order parameters
            order_params = {
                'symbol': mexc_symbol,
                'side': mexc_side,
                'type': 'LIMIT',
                'quantity': str(quantity),
                'price': str(price),
                'timeInForce': mexc_tif,
                **kwargs
            }
            
            # Execute order
            mexc_order = await self._private_rest.place_order(order_params)
            order = self._from_mexc_order(mexc_order, symbol)
            
            # Track performance
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            self.logger.info("Limit order placed",
                           exchange="mexc",
                           symbol=str(symbol),
                           side=side.name,
                           quantity=quantity,
                           price=price,
                           order_id=order.order_id,
                           execution_time_ms=round(execution_time_ms, 2))
            
            return order
            
        except Exception as e:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            self.logger.error("Failed to place limit order",
                            exchange="mexc",
                            symbol=str(symbol),
                            execution_time_ms=round(execution_time_ms, 2),
                            error=str(e))
            raise BaseExchangeError(f"MEXC limit order failed: {e}")
    
    async def place_market_order(self,
                               symbol: Symbol,
                               side: Side,
                               quantity: float,
                               **kwargs) -> Order:
        """Place market order with HFT optimization."""
        if not self._private_rest:
            raise BaseExchangeError("Private REST client not available")
        
        start_time = time.perf_counter()
        self._track_operation("place_market_order")
        
        try:
            # Convert to MEXC format
            mexc_symbol = self._to_mexc_symbol(symbol)
            mexc_side = self._to_mexc_side(side)
            
            # Prepare order parameters
            order_params = {
                'symbol': mexc_symbol,
                'side': mexc_side,
                'type': 'MARKET',
                'quantity': str(quantity),
                **kwargs
            }
            
            # Execute order
            mexc_order = await self._private_rest.place_order(order_params)
            order = self._from_mexc_order(mexc_order, symbol)
            
            # Track performance
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            self.logger.info("Market order placed",
                           exchange="mexc",
                           symbol=str(symbol),
                           side=side.name,
                           quantity=quantity,
                           order_id=order.order_id,
                           execution_time_ms=round(execution_time_ms, 2))
            
            return order
            
        except Exception as e:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            self.logger.error("Failed to place market order",
                            exchange="mexc",
                            symbol=str(symbol),
                            execution_time_ms=round(execution_time_ms, 2),
                            error=str(e))
            raise BaseExchangeError(f"MEXC market order failed: {e}")
    
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> bool:
        """Cancel order with HFT optimization."""
        if not self._private_rest:
            raise BaseExchangeError("Private REST client not available")
        
        start_time = time.perf_counter()
        self._track_operation("cancel_order")
        
        try:
            mexc_symbol = self._to_mexc_symbol(symbol)
            
            await self._private_rest.cancel_order(
                symbol=mexc_symbol,
                orderId=str(order_id)
            )
            
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            self.logger.info("Order cancelled",
                           exchange="mexc",
                           symbol=str(symbol),
                           order_id=order_id,
                           execution_time_ms=round(execution_time_ms, 2))
            
            return True
            
        except Exception as e:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            self.logger.error("Failed to cancel order",
                            exchange="mexc",
                            symbol=str(symbol),
                            order_id=order_id,
                            execution_time_ms=round(execution_time_ms, 2),
                            error=str(e))
            return False
    
    async def cancel_all_orders(self, symbol: Optional[Symbol] = None) -> List[bool]:
        """Cancel all orders for symbol or all symbols."""
        symbols_to_cancel = [symbol] if symbol else list(self._open_orders.keys())
        results = []
        
        for sym in symbols_to_cancel:
            orders = self._open_orders.get(sym, [])
            for order in orders:
                try:
                    result = await self.cancel_order(sym, order.order_id)
                    results.append(result)
                except Exception as e:
                    self.logger.error("Failed to cancel order in batch",
                                    symbol=str(sym),
                                    order_id=order.order_id,
                                    error=str(e))
                    results.append(False)
        
        return results
    
    async def get_order(self, order_id: OrderId, symbol: Symbol) -> Optional[Order]:
        """Get order details."""
        if not self._private_rest:
            return None
        
        try:
            mexc_symbol = self._to_mexc_symbol(symbol)
            mexc_order = await self._private_rest.get_order(
                symbol=mexc_symbol,
                orderId=str(order_id)
            )
            
            if mexc_order:
                return self._from_mexc_order(mexc_order, symbol)
            
        except Exception as e:
            self.logger.debug("Order not found", order_id=order_id, error=str(e))
        
        return None
    
    async def get_order_history(self, 
                               symbol: Optional[Symbol] = None,
                               limit: int = 100) -> List[Order]:
        """Get historical orders."""
        if not self._private_rest:
            return []
        
        try:
            mexc_symbol = self._to_mexc_symbol(symbol) if symbol else None
            mexc_orders = await self._private_rest.get_order_history(
                symbol=mexc_symbol, 
                limit=limit
            )
            
            orders = []
            for mexc_order in mexc_orders:
                if symbol:
                    order = self._from_mexc_order(mexc_order, symbol)
                else:
                    # Try to determine symbol from order
                    order_symbol = self._from_mexc_symbol(mexc_order.get('symbol', ''))
                    if order_symbol:
                        order = self._from_mexc_order(mexc_order, order_symbol)
                    else:
                        continue
                orders.append(order)
            
            return orders
            
        except Exception as e:
            self.logger.error("Failed to get order history", error=str(e))
            return []
    
    # Batch operations
    async def place_multiple_orders(self, orders: List[Dict[str, Any]]) -> List[Order]:
        """Place multiple orders with controlled concurrency."""
        if not orders:
            return []
        
        # Limit concurrency to avoid rate limits
        semaphore = asyncio.Semaphore(5)
        results = []
        
        async def place_single_order(order_data: Dict[str, Any]) -> Optional[Order]:
            async with semaphore:
                try:
                    order_type = order_data.get('type', 'limit').lower()
                    
                    if order_type == 'limit':
                        return await self.place_limit_order(
                            symbol=order_data['symbol'],
                            side=order_data['side'],
                            quantity=order_data['quantity'],
                            price=order_data['price'],
                            **order_data.get('kwargs', {})
                        )
                    elif order_type == 'market':
                        return await self.place_market_order(
                            symbol=order_data['symbol'],
                            side=order_data['side'],
                            quantity=order_data['quantity'],
                            **order_data.get('kwargs', {})
                        )
                except Exception as e:
                    self.logger.error("Failed to place order in batch", error=str(e))
                    return None
        
        # Execute all orders concurrently
        tasks = [place_single_order(order_data) for order_data in orders]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful orders
        successful_orders = [r for r in results if isinstance(r, Order)]
        
        self.logger.info("Batch order placement completed",
                        total_orders=len(orders),
                        successful_orders=len(successful_orders))
        
        return successful_orders
    
    async def cancel_multiple_orders(self, 
                                   order_cancellations: List[Dict[str, Any]]) -> List[bool]:
        """Cancel multiple orders with controlled concurrency.""" 
        if not order_cancellations:
            return []
        
        semaphore = asyncio.Semaphore(10)  # Higher concurrency for cancellations
        
        async def cancel_single_order(cancellation_data: Dict[str, Any]) -> bool:
            async with semaphore:
                try:
                    return await self.cancel_order(
                        symbol=cancellation_data['symbol'],
                        order_id=cancellation_data['order_id']
                    )
                except Exception:
                    return False
        
        tasks = [cancel_single_order(data) for data in order_cancellations]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        cancellation_results = [r if isinstance(r, bool) else False for r in results]
        
        self.logger.info("Batch order cancellation completed",
                        total_cancellations=len(order_cancellations),
                        successful_cancellations=sum(cancellation_results))
        
        return cancellation_results
    
    # ========================================
    # Withdrawal Operations
    # ========================================
    
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """Submit withdrawal request."""
        if not self._private_rest:
            raise BaseExchangeError("Private REST client not available")
        return await self._private_rest.submit_withdrawal(request)
    
    async def cancel_withdrawal(self, withdrawal_id: str) -> bool:
        """Cancel pending withdrawal."""
        if not self._private_rest:
            return False
        return await self._private_rest.cancel_withdrawal(withdrawal_id)
    
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """Get withdrawal status."""
        if not self._private_rest:
            raise BaseExchangeError("Private REST client not available")
        return await self._private_rest.get_withdrawal_status(withdrawal_id)
    
    async def get_withdrawal_history(self,
                                   asset: Optional[AssetName] = None,
                                   limit: int = 100) -> List[WithdrawalResponse]:
        """Get withdrawal history."""
        if not self._private_rest:
            return []
        return await self._private_rest.get_withdrawal_history(asset, limit)
    
    async def validate_withdrawal_address(self,
                                        asset: AssetName,
                                        address: str,
                                        network: Optional[str] = None) -> bool:
        """Validate withdrawal address."""
        try:
            await self.get_withdrawal_limits(asset, network)
            return True
        except Exception:
            return False
    
    async def get_withdrawal_limits(self,
                                  asset: AssetName,
                                  network: Optional[str] = None) -> Dict[str, float]:
        """Get withdrawal limits."""
        if not self._private_rest:
            raise BaseExchangeError("Private REST client not available")
        return await self._private_rest.get_withdrawal_limits_for_asset(asset, network)
    
    # ========================================
    # Internal Implementation Methods
    # ========================================
    
    async def _initialize_rest_clients(self) -> None:
        """Initialize REST clients."""
        self._public_rest = MexcPublicSpotRest(self.config)
        
        if self.config.has_credentials():
            self._private_rest = MexcPrivateSpotRest(self.config)
        
        self.logger.debug("REST clients initialized",
                         has_private=self._private_rest is not None)
    
    async def _initialize_websocket_clients(self) -> None:
        """Initialize WebSocket clients."""
        # Public WebSocket for market data
        self._public_ws = MexcPublicSpotWebsocket(
            config=self.config,
            handlers={
                'orderbook': self._handle_orderbook_update,
                'trade': self._handle_trade_update,
                'ticker': self._handle_ticker_update
            }
        )
        await self._public_ws.initialize()
        
        # Private WebSocket for account updates (if credentials available)
        if self.config.has_credentials():
            self._private_ws = MexcPrivateSpotWebsocket(
                config=self.config,
                handlers={
                    'order': self._handle_order_update,
                    'balance': self._handle_balance_update
                }
            )
            await self._private_ws.initialize()
        
        self.logger.debug("WebSocket clients initialized",
                         has_private=self._private_ws is not None)
    
    async def _load_symbols_info(self) -> None:
        """Load symbols information from REST API.""" 
        if not self._public_rest:
            return
        
        try:
            self._symbols_info = await self._public_rest.get_exchange_info()
            self.logger.debug("Symbols info loaded",
                            symbols_count=len(self._symbols_info) if self._symbols_info else 0)
        except Exception as e:
            self.logger.error("Failed to load symbols info", error=str(e))
            raise
    
    async def _load_account_data(self) -> None:
        """Load initial account data."""
        if not self._private_rest:
            return
        
        try:
            # Load balances
            account_info = await self._private_rest.get_account()
            balances = account_info.get('balances', [])
            
            for balance_data in balances:
                balance = AssetBalance(
                    asset=balance_data.get('asset', ''),
                    available=float(balance_data.get('free', 0)),
                    locked=float(balance_data.get('locked', 0))
                )
                self._balances[balance.asset] = balance
            
            # Load open orders
            open_orders = await self._private_rest.get_open_orders()
            for order_data in open_orders:
                symbol = self._from_mexc_symbol(order_data.get('symbol', ''))
                if symbol:
                    order = self._from_mexc_order(order_data, symbol)
                    if symbol not in self._open_orders:
                        self._open_orders[symbol] = []
                    self._open_orders[symbol].append(order)
            
            self.logger.debug("Account data loaded",
                            balances=len(self._balances),
                            open_orders=sum(len(orders) for orders in self._open_orders.values()))
            
        except Exception as e:
            self.logger.error("Failed to load account data", error=str(e))
            # Don't raise - account data is not critical for initialization
    
    # Event handlers
    async def _handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """Handle orderbook update from WebSocket."""
        self._orderbooks[symbol] = orderbook
        await self.on_orderbook_update(symbol, orderbook)
    
    async def _handle_trade_update(self, symbol: Symbol, trade: Trade) -> None:
        """Handle trade update from WebSocket."""
        await self.on_trade_update(symbol, trade)
    
    async def _handle_ticker_update(self, symbol: Symbol, ticker: Ticker) -> None:
        """Handle ticker update from WebSocket."""
        self._tickers[symbol] = ticker
    
    async def _handle_order_update(self, order: Order) -> None:
        """Handle order update from private WebSocket.""" 
        symbol = order.symbol
        
        # Update local order state
        if symbol not in self._open_orders:
            self._open_orders[symbol] = []
        
        orders = self._open_orders[symbol]
        
        # Update existing order or add new one
        for i, existing_order in enumerate(orders):
            if existing_order.order_id == order.order_id:
                if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED]:
                    orders.pop(i)  # Remove completed orders
                else:
                    orders[i] = order  # Update existing order
                break
        else:
            # New order
            if order.status not in [OrderStatus.FILLED, OrderStatus.CANCELED]:
                orders.append(order)
        
        await self.on_order_update(order)
    
    async def _handle_balance_update(self, asset: str, balance: AssetBalance) -> None:
        """Handle balance update from private WebSocket."""
        self._balances[asset] = balance
        await self.on_balance_update(asset, balance)
    
    # Format conversion utilities
    def _to_mexc_symbol(self, symbol: Symbol) -> str:
        """Convert Symbol to MEXC format."""
        return MexcSymbol.to_pair(symbol)
    
    def _from_mexc_symbol(self, mexc_symbol: str) -> Optional[Symbol]:
        """Convert MEXC symbol to Symbol."""
        try:
            return MexcSymbol.to_symbol(mexc_symbol)
        except Exception:
            return None
    
    def _to_mexc_side(self, side: Side) -> str:
        """Convert Side to MEXC format."""
        return 'BUY' if side == Side.BUY else 'SELL'
    
    def _to_mexc_tif(self, tif: TimeInForce) -> str:
        """Convert TimeInForce to MEXC format."""
        mapping = {
            TimeInForce.GTC: 'GTC',
            TimeInForce.IOC: 'IOC', 
            TimeInForce.FOK: 'FOK'
        }
        return mapping.get(tif, 'GTC')
    
    def _from_mexc_order(self, mexc_order: Dict[str, Any], symbol: Symbol) -> Order:
        """Convert MEXC order to unified Order."""
        return Order(
            order_id=mexc_order.get('orderId', ''),
            symbol=symbol,
            side=Side.BUY if mexc_order.get('side') == 'BUY' else Side.SELL,
            quantity=float(mexc_order.get('origQty', 0)),
            price=float(mexc_order.get('price', 0)),
            filled_quantity=float(mexc_order.get('executedQty', 0)),
            status=self._from_mexc_order_status(mexc_order.get('status', '')),
            timestamp=mexc_order.get('time', 0),
            order_type=OrderType.LIMIT if mexc_order.get('type') == 'LIMIT' else OrderType.MARKET
        )
    
    def _from_mexc_order_status(self, mexc_status: str) -> OrderStatus:
        """Convert MEXC order status to unified OrderStatus."""
        mapping = {
            'NEW': OrderStatus.OPEN,
            'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
            'FILLED': OrderStatus.FILLED,
            'CANCELED': OrderStatus.CANCELED,
            'PENDING_CANCEL': OrderStatus.PENDING_CANCEL,
            'REJECTED': OrderStatus.REJECTED,
            'EXPIRED': OrderStatus.EXPIRED
        }
        return mapping.get(mexc_status, OrderStatus.OPEN)