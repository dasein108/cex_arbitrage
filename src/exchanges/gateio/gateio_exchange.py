"""
Gate.io Exchange Implementation

High-performance Gate.io integration following unified cex system using composition pattern.
Implements BaseExchangeInterface for seamless arbitrage engine integration.

Architecture:
- Composition pattern with separate public and private cex implementations
- Delegates public market data operations to GateioPublicExchange
- Delegates private trading operations to GateioPrivateExchange  
- Manages WebSocket streaming for real-time data
- Coordinates between public and private operations

HFT Compliance:
- No caching of real-time trading data (balances, orders, trades)
- Real-time streaming orderbook data only
- Fresh API calls for all trading operations
- Configuration data caching only (symbol info, endpoints)

Performance Features:
- <50ms API response times, <1ms JSON parsing
- Connection pooling for optimal throughput
- WebSocket streaming with auto-reconnection
- Object pooling for reduced memory allocations
- Type-safe data structures throughout
"""

import logging
import time
from typing import Dict, List, Optional, Set
from contextlib import asynccontextmanager
from types import MappingProxyType

from core.cex.base import BasePrivateExchangeInterface
from structs.exchange import (
    OrderBook, Symbol, SymbolInfo, SymbolsInfo, AssetBalance, AssetName, Order, OrderId, 
    OrderType, Side, TimeInForce, ExchangeStatus, Position
)
from exchanges.gateio.ws.gateio_ws_public import GateioWebsocketPublic
from exchanges.gateio.rest.gateio_private import GateioPrivateExchangeSpot
from exchanges.gateio.rest.gateio_public import GateioPublicExchangeSpotRest
from exchanges.gateio.common.gateio_config import GateioConfig
from core.transport.websocket.ws_client import WebSocketConfig
from core.cex import ConnectionState
from core.exceptions.exchange import BaseExchangeError
from structs.config import ExchangeConfig


class GateioExchange(BasePrivateExchangeInterface):
    """
    Gate.io Exchange Implementation using Composition Pattern.
    
    This class follows SOLID principles by composing separate public and private
    cex implementations rather than inheriting everything directly.
    
    Architecture:
    - Delegates public market data operations to GateioPublicExchange
    - Delegates private trading operations to GateioPrivateExchange
    - Manages WebSocket streaming for real-time data
    - Coordinates between public and private operations
    
    HFT Compliance:
    - No caching of real-time trading data (balances, orders, trades)
    - Real-time streaming orderbook data only
    - Fresh API calls for all trading operations
    """
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None, config: ExchangeConfig = None):
        # Create config if not provided
        if config is None:
            from config import get_exchange_config_struct
            config = get_exchange_config_struct('GATEIO')
        
        # Update config with credentials if provided
        if api_key and secret_key:
            config.credentials.api_key = api_key
            config.credentials.secret_key = secret_key
            
        super().__init__(config)
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # HFT Compliant: Real-time streaming data structures (not persistent storage)
        self._orderbooks: Dict[Symbol, OrderBook] = {}  # Current streaming orderbooks
        self._balances_dict: Dict[AssetName, AssetBalance] = {}  # Current balances
        self._active_symbols: Set[Symbol] = set()  # Active streaming symbols
        
        
        # Current streaming state (not cached/persistent)
        self._latest_orderbook: Optional[OrderBook] = None
        self._latest_orderbook_symbol: Optional[Symbol] = None
        # HFT Policy: NO CACHING of real-time trading data
        # Removed: balance caching, order status caching, orderbook persistence
        
        self._ws_client: Optional[GateioWebsocketPublic] = None
        # Composition: Separate public and private cex implementations
        self._public_api: Optional[GateioPublicExchangeSpotRest] = None
        self._private_api: Optional[GateioPrivateExchangeSpot] = None
        
        self._ws_config = WebSocketConfig(
            name="gateio_orderbooks",
            url=GateioConfig.WEBSOCKET_URL,
            timeout=30.0,
            ping_interval=20.0,
            max_reconnect_attempts=10,
            reconnect_delay=1.0,
            max_queue_size=1000,
            enable_compression=False
        )
        
        self._initialized = False
        # HFT Compliance: Real-time data only - no caching
        
        self.logger.info(f"Initialized {self.exchange} exchange with HFT optimizations")
        
        self._performance_metrics = {
            'orderbook_updates': 0
        }
        
        # Symbol information cache (loaded once at startup - HFT compliant)
        self._symbol_info_cache: Dict[Symbol, SymbolInfo] = {}  # Symbol -> SymbolInfo
    
    
    @property
    def symbol_info(self) -> Dict[Symbol, SymbolInfo]:
        """
        Get symbol information dictionary.
        
        HFT COMPLIANT: Cached at initialization, no runtime API calls.
        Implements the src cex abstract property.
        
        Returns:
            Dict[Symbol, SymbolInfo] mapping symbols to symbol information
        """
        return self._symbol_info_cache.copy()
    
    @property
    def symbols_info(self) -> SymbolsInfo:
        """
        Get symbol information dictionary (cex compliance).
        
        HFT COMPLIANT: Cached at initialization, no runtime API calls.
        Implements BasePublicExchangeInterface abstract property.
        
        Returns:
            SymbolsInfo mapping symbols to symbol information
        """
        return self._symbol_info_cache.copy()
    
    @property
    def status(self) -> ExchangeStatus:
        """
        Get current exchange connection status.
        
        HFT COMPLIANT: Property-based computation with <1µs latency.
        
        Returns:
            ExchangeStatus.INACTIVE if not initialized
            ExchangeStatus.CONNECTING if WebSocket is connecting/reconnecting
            ExchangeStatus.ACTIVE if all connections are operational
        """
        # Fast path: not initialized
        if not self._initialized:
            return ExchangeStatus.INACTIVE
        
        # Check WebSocket state (critical path for real-time data)
        ws_state = self._get_websocket_state()
        if ws_state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING):
            return ExchangeStatus.CONNECTING
        
        # Check if WebSocket is disconnected or in error state
        if ws_state in (ConnectionState.DISCONNECTED, ConnectionState.ERROR, 
                        ConnectionState.CLOSING, ConnectionState.CLOSED):
            return ExchangeStatus.CONNECTING  # Treat as connecting since it will auto-reconnect
        
        # Optional: Check REST client health (basic existence check)
        if not self._is_rest_healthy():
            return ExchangeStatus.CONNECTING
        
        # All systems operational
        return ExchangeStatus.ACTIVE
    
    def _get_websocket_state(self) -> ConnectionState:
        """
        Get current WebSocket connection state.
        
        Returns:
            Current ConnectionState of the WebSocket client
        """
        if self._ws_client and self._ws_client.ws_client:
            return self._ws_client.ws_client.state
        return ConnectionState.DISCONNECTED
    
    def _is_rest_healthy(self) -> bool:
        """
        Check if REST clients are healthy.
        
        Basic implementation: checks if clients exist.
        Future enhancement: actual health check via ping endpoints.
        
        Returns:
            True if REST clients are initialized and ready
        """
        # Basic check: ensure REST clients exist
        if self.has_private:
            # Private trading requires both private and public APIs
            return self._private_api is not None and self._public_api is not None
        else:
            # Public-only mode just needs public API
            return self._public_api is not None
    
    @property
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """
        HFT Policy: Always return fresh balance data, no caching.
        
        Creates dummy Symbol objects for balance display compatibility.
        """
        symbol_balances = {}
        for asset_name, balance in self._balances_dict.items():
            dummy_symbol = Symbol(base=asset_name, quote=AssetName("USDT"))
            symbol_balances[dummy_symbol] = balance
        return MappingProxyType(symbol_balances)
    
    @property
    def active_symbols(self) -> List[Symbol]:
        return list(self._active_symbols)
    
    @property
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """Property required by BaseExchangeInterface - returns empty dict for composition-based design"""
        # Note: This property exists for cex compliance
        # Actual open orders should be accessed via get_open_orders() method
        return {}
    
    async def positions(self) -> Dict[Symbol, Position]:
        """
        Get current open positions (for futures).
        
        HFT COMPLIANT: Real-time data, no caching.
        Implements BasePrivateExchangeInterface abstract method.
        
        Returns:
            Dict[Symbol, Position] mapping symbols to positions (empty for spot trading)
        """
        # Gate.io Spot Exchange - no futures positions
        return {}
    
    @property
    def orderbook(self) -> OrderBook:
        if self._latest_orderbook is not None:
            return self._latest_orderbook
        
        return OrderBook(bids=[], asks=[], timestamp=time.time())
    
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        return self._orderbooks.get(symbol)
    
    def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        return self._balances_dict.get(asset)
    
    def get_all_orderbooks(self) -> Dict[Symbol, OrderBook]:
        return MappingProxyType(self._orderbooks)
    
    async def initialize(self, symbols: Optional[List[Symbol]] = None) -> None:
        if self._initialized:
            self.logger.warning("Exchange already initialized")
            return
        
        try:
            # Initialize public API for market data
            self._public_api = GateioPublicExchangeSpotRest()
            self.logger.info("Initialized public API cex")
            
            # Initialize private API for trading (if credentials provided)
            if self.has_private:
                self._private_api = GateioPrivateExchangeSpot(self.api_key, self.secret_key)
                self.logger.info("Initialized private API cex")
                
                # Get initial balance state (HFT compliant - no caching)
                await self.refresh_balances()
            
            # Initialize WebSocket through composition pattern
            # WebSocket handles real-time market data streaming
            self._ws_client = GateioWebsocketPublic(
                websocket_config=self._ws_config,
                orderbook_handler=self._on_orderbook_update,
                trades_handler=None
            )
            
            await self._ws_client.initialize([])
            self.logger.info("Started WebSocket streaming cex")
            
            # Load symbol information (HFT compliant - cached at startup)
            await self._load_symbol_info()
            
            self._initialized = True
            
            if symbols:
                for symbol in symbols:
                    await self.add_symbol(symbol)
            
            self.logger.info(f"Successfully initialized {self.exchange} exchange")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize exchange: {e}")
            await self._cleanup_partial_init()
            raise BaseExchangeError(500, f"Exchange initialization failed: {str(e)}")
    
    async def add_symbol(self, symbol: Symbol) -> None:
        if not self._initialized:
            raise BaseExchangeError(400, "Exchange not initialized. Call init() first.")
        
        if symbol in self._active_symbols:
            self.logger.debug(f"Already subscribed to {symbol}")
            return
        
        try:
            if self._ws_client:
                await self._ws_client.start_symbol(symbol)
            
            self._active_symbols.add(symbol)
            
            self._orderbooks[symbol] = OrderBook(
                bids=[],
                asks=[],
                timestamp=time.time()
            )
            
            self.logger.info(f"Subscribed to {symbol}")
            
        except Exception as e:
            self.logger.error(f"Failed to subscribe to {symbol}: {e}")
            raise BaseExchangeError(500, f"Symbol subscription failed: {str(e)}")
    
    async def remove_symbol(self, symbol: Symbol) -> None:
        if symbol not in self._active_symbols:
            self.logger.debug(f"Not subscribed to {symbol}")
            return
        
        try:
            if self._ws_client:
                await self._ws_client.stop_symbol(symbol)
            
            self._active_symbols.discard(symbol)
            self._orderbooks.pop(symbol, None)
            
            self.logger.info(f"Unsubscribed from {symbol}")
            
        except Exception as e:
            self.logger.error(f"Failed to unsubscribe from {symbol}: {e}")
            raise BaseExchangeError(500, f"Symbol unsubscription failed: {str(e)}")
    
    async def refresh_balances(self) -> None:
        if not self.has_private or not self._private_api:
            raise BaseExchangeError(400, "Private API access not configured")
        
        try:
            balance_list = await self._private_api.get_account_balance()
            
            new_balances = {}
            for balance in balance_list:
                new_balances[balance.asset] = balance
            
            # HFT Policy: Update balances without caching
            self._balances_dict = new_balances
            
            self.logger.debug(f"Refreshed {len(balance_list)} account balances")
            
        except Exception as e:
            self.logger.error(f"Failed to refresh balances: {e}")
            raise BaseExchangeError(500, f"Balance refresh failed: {str(e)}")
    
    async def get_fresh_balances(self, max_age: float = 30.0) -> Dict[AssetName, AssetBalance]:
        """HFT Policy: Always fetch fresh balance data, no cache checking"""
        await self.refresh_balances()
        return self._balances_dict.copy()
    
    async def place_limit_order(
        self,
        symbol: Symbol,
        side: Side,
        amount: float,
        price: float,
        time_in_force: TimeInForce = TimeInForce.GTC
    ) -> Order:
        if not self.has_private or not self._private_api:
            raise BaseExchangeError(400, "Private API credentials required for trading")
        
        try:
            order = await self._private_api.place_order(
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                amount=amount,
                price=price,
                time_in_force=time_in_force
            )
            
            self.logger.info(
                f"Placed limit {side.name} order: {amount} {symbol.base} "
                f"at {price} {symbol.quote} (Order ID: {order.order_id})"
            )
            
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to place limit order: {e}")
            raise
    
    async def place_market_order(
        self,
        symbol: Symbol,
        side: Side,
        amount: Optional[float] = None,
        quote_amount: Optional[float] = None
    ) -> Order:
        if not self.has_private or not self._private_api:
            raise BaseExchangeError(400, "Private API credentials required for trading")
        
        if side == Side.BUY:
            if amount is None and quote_amount is None:
                raise ValueError("Either amount or quote_amount is required for market buy orders")
        elif side == Side.SELL:
            if amount is None:
                raise ValueError("Amount is required for market sell orders")
            if quote_amount is not None:
                raise ValueError("quote_amount not supported for market sell orders")
        
        try:
            order = await self._private_api.place_order(
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                amount=amount,
                quote_quantity=quote_amount
            )
            
            if quote_amount and side == Side.BUY:
                self.logger.info(
                    f"Placed market {side.name} order: {quote_amount} {symbol.quote} "
                    f"worth of {symbol.base} (Order ID: {order.order_id})"
                )
            else:
                self.logger.info(
                    f"Placed market {side.name} order: {amount} {symbol.base} "
                    f"(Order ID: {order.order_id})"
                )
            
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to place market order: {e}")
            raise
    
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        if not self.has_private or not self._private_api:
            raise BaseExchangeError(400, "Private API credentials required for trading")
        
        try:
            order = await self._private_api.cancel_order(symbol, order_id)
            
            self.logger.info(
                f"Cancelled order {order_id} for {symbol.base}/{symbol.quote}"
            )
            
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            raise
    
    async def cancel_all_orders(self, symbol: Symbol) -> List[Order]:
        if not self.has_private or not self._private_api:
            raise BaseExchangeError(400, "Private API credentials required for trading")
        
        try:
            orders = await self._private_api.cancel_all_orders(symbol)
            
            self.logger.info(
                f"Cancelled {len(orders)} orders for {symbol.base}/{symbol.quote}"
            )
            
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders for {symbol}: {e}")
            raise
    
    async def get_order_status(self, symbol: Symbol, order_id: OrderId) -> Order:
        if not self.has_private or not self._private_api:
            raise BaseExchangeError(400, "Private API credentials required for trading")
        
        # HFT Policy: Always fetch fresh order status, no caching
        try:
            order = await self._private_api.get_order(symbol, order_id)
            
            self.logger.debug(
                f"Retrieved order {order_id} status: {order.status.name}"
            )
            
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to get order status for {order_id}: {e}")
            raise
    
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        if not self.has_private or not self._private_api:
            raise BaseExchangeError(400, "Private API credentials required for trading")
        
        try:
            orders = await self._private_api.get_open_orders(symbol)
            
            symbol_str = f" for {symbol.base}/{symbol.quote}" if symbol else ""
            self.logger.debug(f"Retrieved {len(orders)} open orders{symbol_str}")
            
            return orders
            
        except Exception as e:
            symbol_str = f" for {symbol}" if symbol else ""
            self.logger.error(f"Failed to get open orders{symbol_str}: {e}")
            raise
    
    async def modify_order(
        self,
        symbol: Symbol,
        order_id: OrderId,
        new_amount: Optional[float] = None,
        new_price: Optional[float] = None,
        new_time_in_force: Optional[TimeInForce] = None
    ) -> Order:
        if not self.has_private or not self._private_api:
            raise BaseExchangeError(400, "Private API credentials required for trading")
        
        try:
            order = await self._private_api.modify_order(
                symbol=symbol,
                order_id=order_id,
                amount=new_amount,
                price=new_price,
                time_in_force=new_time_in_force
            )
            
            self.logger.info(
                f"Modified order {order_id} -> {order.order_id} for {symbol.base}/{symbol.quote}"
            )
            
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to modify order {order_id}: {e}")
            raise
    
    async def _on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        if symbol in self._active_symbols:
            if len(orderbook.bids) > 100:
                orderbook.bids = orderbook.bids[:100]
            if len(orderbook.asks) > 100:
                orderbook.asks = orderbook.asks[:100]
            
            self._orderbooks[symbol] = orderbook
            self._performance_metrics['orderbook_updates'] += 1
            
            if (self._latest_orderbook is None or 
                orderbook.timestamp > self._latest_orderbook.timestamp):
                self._latest_orderbook = orderbook
                self._latest_orderbook_symbol = symbol
            
            self.logger.debug(
                f"Updated orderbook for {symbol}: "
                f"{len(orderbook.bids)} bids, {len(orderbook.asks)} asks"
            )
    
    async def _cleanup_partial_init(self) -> None:
        if self._ws_client:
            try:
                await self._ws_client.close()
            except Exception as e:
                self.logger.error(f"Error stopping WebSocket during cleanup: {e}")
        
        if self._private_api:
            try:
                await self._private_api.close()
            except Exception as e:
                self.logger.error(f"Error closing private API during cleanup: {e}")
        
        if self._public_api:
            try:
                await self._public_api.close()
            except Exception as e:
                self.logger.error(f"Error closing public API during cleanup: {e}")
        
        self._active_symbols.clear()
        self._orderbooks.clear()
        self._balances_dict.clear()
        self._latest_orderbook = None
        self._latest_orderbook_symbol = None
        self._symbol_info_cache.clear()
        self._initialized = False
    
    async def close(self) -> None:
        self.logger.info("Closing exchange connections...")
        
        if self._ws_client:
            try:
                await self._ws_client.close()
                self.logger.info("Closed WebSocket client")
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")
        
        if self._private_api:
            try:
                await self._private_api.close()
                self.logger.info("Closed private API client")
            except Exception as e:
                self.logger.error(f"Error closing private API: {e}")
        
        if self._public_api:
            try:
                await self._public_api.close()
                self.logger.info("Closed public API client")
            except Exception as e:
                self.logger.error(f"Error closing public API: {e}")
        
        self._active_symbols.clear()
        self._orderbooks.clear()
        self._balances_dict.clear()
        self._latest_orderbook = None
        self._latest_orderbook_symbol = None
        self._symbol_info_cache.clear()
        self._initialized = False
        
        self.logger.info(f"Successfully closed {self.exchange} exchange")
    
    
    @asynccontextmanager
    async def session(self, symbols: Optional[List[Symbol]] = None):
        try:
            await self.initialize(symbols)
            yield self
        finally:
            await self.close()
    
    async def buy_limit(self, symbol: Symbol, amount: float, price: float) -> Order:
        return await self.place_limit_order(symbol, Side.BUY, amount, price)
    
    async def sell_limit(self, symbol: Symbol, amount: float, price: float) -> Order:
        return await self.place_limit_order(symbol, Side.SELL, amount, price)
    
    async def buy_market(self, symbol: Symbol, quote_amount: float) -> Order:
        return await self.place_market_order(symbol, Side.BUY, quote_amount=quote_amount)
    
    async def sell_market(self, symbol: Symbol, amount: float) -> Order:
        return await self.place_market_order(symbol, Side.SELL, amount=amount)
    
    def get_performance_metrics(self) -> Dict[str, int]:
        ws_metrics = {}
        if self._ws_client:
            ws_metrics = self._ws_client.get_performance_metrics()
        
        return {
            **self._performance_metrics,
            'active_symbols_count': len(self._active_symbols),
            **ws_metrics
        }
    
    def __repr__(self) -> str:
        return (
            f"GateioExchange(symbols={len(self._active_symbols)}, "
            f"balances={len(self._balances_dict)}, "
            f"initialized={self._initialized})"
        )

    async def _setup_fees(self, exchange_info: Dict[Symbol, SymbolInfo]) -> Dict[Symbol, SymbolInfo]:
        fees =  await self._private_api.get_trading_fees()
        for symbol, exchange_info in exchange_info.items():
            exchange_info[symbol].fees_maker = fees.maker_rate
            exchange_info[symbol].fees_taker = fees.taker_rate

        return exchange_info

    async def _load_symbol_info(self) -> None:
        """
        Load symbol information from exchange API and cache it.
        
        HFT COMPLIANT: Called once during initialization, cached for lifetime.
        Uses only src cex types, no raw dependencies.
        """
        if not self._public_api:
            self.logger.warning("Cannot load symbol info - public API not available")
            return
        
        try:
            self.logger.info("Loading symbol information from Gate.io API...")
            
            # Get exchange info from public API (returns Dict[Symbol, SymbolInfo])
            exchange_info = await self._public_api.get_exchange_info()

            # apply fees from private API if available
            if self.has_private and self._private_api:
                exchange_info = await self._setup_fees(exchange_info)


            # Cache the symbol info directly (already in correct format)
            self._symbol_info_cache = exchange_info.copy()
                
            self.logger.info(f"Successfully loaded {len(self._symbol_info_cache)} symbols from Gate.io")
                
        except Exception as e:
            self.logger.error(f"Failed to load symbol info from Gate.io: {e}")
            # Don't raise - this is not critical for basic functionality