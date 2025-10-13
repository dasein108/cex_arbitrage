"""
Base private composite exchange without withdrawal functionality.

This is the common base for both spot and futures private exchanges,
containing shared trading operations but excluding withdrawal methods
which are only needed for spot exchanges.
"""

import asyncio
from typing import Dict, List, Optional, Any
from exchanges.structs.common import (
    Symbol, AssetBalance, Order, SymbolsInfo
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, Trade, OrderType
from config.structs import ExchangeConfig
from infrastructure.exceptions.exchange import OrderNotFoundError
from infrastructure.exceptions.system import InitializationError
from exchanges.interfaces.composite.base_composite import BaseCompositeExchange
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebsocketType
from exchanges.interfaces.composite.mixins import BalanceSyncMixin
from infrastructure.logging import LoggingTimer, HFTLoggerInterface
from utils.exchange_utils import is_order_done
from exchanges.interfaces.common.binding import BoundHandlerInterface
from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType, WebsocketChannelType

class BasePrivateComposite(BalanceSyncMixin,
                           BaseCompositeExchange[PrivateRestType, PrivateWebsocketType],
                           BoundHandlerInterface[PrivateWebsocketChannelType]):
    """
    Base private composite exchange interface WITHOUT withdrawal functionality.
    
    This class contains all common private exchange operations that are shared
    between spot and futures exchanges, excluding withdrawal methods which are
    spot-only.
    
    Handles:
    - All public exchange functionality (inherits from BaseCompositeExchange)
    - Account balance tracking
    - Order management (place, cancel, status)
    - Authenticated data streaming via WebSocket
    
    Does NOT handle:
    - Withdrawal operations (spot-only via WithdrawalMixin)
    - Position management (futures-only via futures subclass)
    """

    def __init__(self,
                 config: ExchangeConfig,
                 rest_client: PrivateRestType,
                 websocket_client: PrivateWebsocketType,
                 logger: Optional[HFTLoggerInterface] = None,
                 balance_sync_interval: Optional[float] = None) -> None:
        """
        Initialize base private exchange interface with dependency injection.

        Args:
            config: Exchange configuration with API credentials
            rest_client: Injected private REST client instance
            websocket_client: Injected private WebSocket client instance (optional)
            logger: Optional injected HFT logger (auto-created if not provided)
            balance_sync_interval: Optional interval in seconds for automatic balance syncing
        """
        BoundHandlerInterface.__init__(self)
        super().__init__(config=config,
                         rest_client=rest_client,
                         websocket_client=websocket_client,
                         is_private=True,
                         logger=logger)

        # bind WebSocket handlers to websocket client events
        websocket_client.bind(PrivateWebsocketChannelType.BALANCE, self._balance_handler)
        websocket_client.bind(PrivateWebsocketChannelType.ORDER, self._order_handler)
        websocket_client.bind(PrivateWebsocketChannelType.EXECUTION, self._execution_handler)

        # Private data state (HFT COMPLIANT - no caching of real-time data)
        self._balances: Dict[AssetName, AssetBalance] = {}
        # Unified order storage - single source of truth for all orders
        self._orders: Dict[OrderId, Order] = {}
        self._max_total_orders = 10000  # Memory management limit for total orders

        # Balance sync configuration (now handled by BalanceSyncMixin)
        self._balance_sync_interval = balance_sync_interval

        # Authentication validation
        if not config.has_credentials():
            self.logger.error("No API credentials provided - trading operations will fail")

    # ========================================
    # Type-Safe Channel Publishing (Phase 1)
    # ========================================
    
    def publish(self, channel: PrivateWebsocketChannelType, data: Any) -> None:
        """
        Type-safe publish method for private channels using enum types.
        
        Args:
            channel: Private channel enum type
                   - PrivateWebsocketChannelType.EXECUTION: Trade execution updates
                   - PrivateWebsocketChannelType.BALANCE: Account balance updates  
                   - PrivateWebsocketChannelType.ORDER: Order status updates
                   - PrivateWebsocketChannelType.POSITION: Position updates (futures only)
            data: Event data to publish
        """
        # Convert enum to string for internal publishing
        if hasattr(self, '_exec_bound_handler'):
            try:
                import asyncio
                if asyncio.iscoroutinefunction(self._exec_bound_handler):
                    asyncio.create_task(self._exec_bound_handler(channel, data))
                else:
                    self._exec_bound_handler(channel, data)
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error("Error publishing event",
                                    channel=channel,
                                    error_type=type(e).__name__,
                                    error_message=str(e))

    # Properties for private data

    @property
    def balances(self) -> Dict[AssetName, AssetBalance]:
        """Get current account balances (thread-safe)."""
        return self._balances.copy()

    @property
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """Get current open orders (thread-safe)."""
        # Filter orders by status from unified storage
        open_orders_by_symbol: Dict[Symbol, List[Order]] = {}
        for order in self._orders.values():
            if not is_order_done(order):
                if order.symbol not in open_orders_by_symbol:
                    open_orders_by_symbol[order.symbol] = []
                open_orders_by_symbol[order.symbol].append(order)
        return open_orders_by_symbol

    @property
    def executed_orders(self) -> Dict[Symbol, Dict[OrderId, Order]]:
        """
        Get cached executed orders (filled/canceled/expired).
        
        HFT COMPLIANCE: These are static completed orders - safe to cache.
        Real-time trading data (open orders, balances) remain uncached.
        
        Returns:
            Dictionary mapping symbols to executed orders cache
        """
        # Filter executed orders from unified storage
        executed_by_symbol: Dict[Symbol, Dict[OrderId, Order]] = {}
        for order_id, order in self._orders.items():
            if is_order_done(order):
                if order.symbol not in executed_by_symbol:
                    executed_by_symbol[order.symbol] = {}
                executed_by_symbol[order.symbol][order_id] = order
        return executed_by_symbol

    # Trading operations

    async def get_open_orders(self, symbol: Optional[Symbol] = None, force=False) -> List[Order]:
        """
        Get current open orders.

        Args:
            symbol: Optional symbol filter
            force: If True, refresh from REST API

        Returns:
            List of open orders (all symbols or filtered by symbol)

        Raises:
            ExchangeError: If query fails
        """
        if force:
            await self._load_open_orders(symbol)
        # Filter open orders from unified storage
        open_orders = [order for order in self._orders.values() if not is_order_done(order)]
        if symbol:
            return [order for order in open_orders if order.symbol == symbol]
        return open_orders

    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Order:
        """Place a limit order via REST API."""
        si = self.symbols_info.get(symbol)
        quantity_ = si.round_base(quantity)
        price_ = si.round_quote(price)
        order = await self._rest.place_order(symbol, side, OrderType.LIMIT, quantity_, price_, **kwargs)
        return await self._update_order(order)

    async def place_market_order(self, symbol: Symbol, side: Side, quote_quantity: float,
                                 price: Optional[float]=None,
                                 ensure: bool=True, **kwargs) -> Order:
        """Place a market order via REST API."""
        si = self.symbols_info.get(symbol)
        quote_quantity_ = si.round_quote(quote_quantity)
        
        # For futures markets, convert quote_quantity to base quantity
        # Futures market orders require quantity parameter instead of quote_quantity
        if self.config.is_futures:
            if price is None:
                raise ValueError("Futures market orders require price parameter for quote_quantity conversion")
            base_quantity = quote_quantity_ / price
            quantity_ = si.round_base(base_quantity)
            order = await self._rest.place_order(symbol, side, OrderType.MARKET,
                                                price=price,
                                                quantity=quantity_, **kwargs)
        else:
            # Spot markets can use quote_quantity directly
            order = await self._rest.place_order(symbol, side, OrderType.MARKET,
                                                price=price,
                                                quote_quantity=quote_quantity_, **kwargs)

        if ensure:
            return await self.fetch_order(symbol, order.order_id)
            # # wait until order is no longer open
            # while True:
            #     await asyncio.sleep(0.1)
            #     o = await self.get_active_order(symbol, order.order_id)
            #     if not o or is_order_done(o):
            #         break
        return await self._update_order(order)

    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """
        Cancel an existing order.
        
        Args:
            symbol: Trading symbol
            order_id: Exchange order ID to cancel
            
        Returns:
            Canceled order object
            
        Raises:
            ExchangeError: If cancellation fails
        """

        try:
            order =  await self._rest.cancel_order(symbol, order_id)
            return await self._update_order(order, order_id)
        except OrderNotFoundError as e:
            self.logger.error("Order cancellation failed", order_id=order_id, error=str(e))
            self.remove_order(order_id)
            return await self.fetch_order(symbol, order_id)

    async def fetch_order(self, symbol: Symbol, order_id: OrderId) -> Order | None:
        """
        Get current status of an order.
        
        Args:
            symbol: Trading symbol
            order_id: Exchange order ID
            
        Returns:
            Order object with current status
            
        Raises:
            ExchangeError: If order not found or query fails
        """
        try:
            order = await self._rest.get_order(symbol, order_id)
            if order:
                return await self._update_order(order, order_id)

            return None
        except OrderNotFoundError as e:
            self.logger.error("Failed to fetch order status", order_id=order_id, error=str(e))
            self.remove_order(order_id)
            return None

    # Factory methods ELIMINATED - clients injected via constructor

    # Data loading methods

    async def _load_balances(self) -> None:
        """
        Load account balances from REST API with error handling and metrics.
        """
        if not self._rest:
            self.logger.warning("No REST client available for balance loading")
            return

        try:
            with LoggingTimer(self.logger, "load_balances") as timer:
                balances_data = await self._rest.get_balances()
                for b in balances_data:
                    await self._update_balance(b.asset, b)

            self.logger.info("Balances loaded successfully",
                             balance_count=len(balances_data),
                             load_time_ms=timer.elapsed_ms)



        except Exception as e:
            self.logger.error("Failed to load balances", error=str(e))
            raise InitializationError(f"Balance loading failed: {e}")

    async def _load_open_orders(self, symbol: Optional[Symbol] = None) -> None:
        """
        Load open orders from REST API with error handling.
        """
        if not self._rest:
            return

        try:
            # sync with prev in case of reconnect
            prev_open_orders = {order_id: order for order_id, order in self._orders.items() 
                               if not is_order_done(order)}

            with LoggingTimer(self.logger, "load_open_orders") as timer:
                orders = await self._rest.get_open_orders(symbol)
                for o in orders:
                    # if it was opened before reconnect, remove from forced reload list
                    if o.order_id in prev_open_orders:
                        del prev_open_orders[o.order_id]
                    await self._update_order(o)

                # orders that can be filled in-between reconnects, publish their updates
                for prev_o in prev_open_orders.values():
                    await self._update_order(prev_o)

            open_order_count = sum(1 for order in self._orders.values() if not is_order_done(order))
            self.logger.info("Open orders loaded",
                             open_orders_count=open_order_count,
                             load_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to load open orders", error=str(e))
            raise InitializationError(f"Open orders loading failed: {e}")

    # Order lifecycle management

    def get_orders_by_symbol(self, symbol: Symbol) -> Dict[OrderId, Order]:
        """Get order by ID from unified storage.

        Args:
            symbol: Trading symbol

        Returns:
            Orders by symbol
        """
        return {o.order_id: o for o in self._orders.values() if o.symbol == symbol}

    def get_order(self, order_id: OrderId) -> Optional[Order]:
        """Get order by ID from unified storage.
        
        Args:
            order_id: Order identifier
            
        Returns:
            Order object if found, None otherwise
        """
        return self._orders.get(order_id)

    def remove_order(self, order_id: OrderId) -> bool:
        """Remove order by ID from unified storage.
        
        Args:
            order_id: Order identifier to remove
            
        Returns:
            True if order was removed, False if not found
        """
        if order_id in self._orders:
            del self._orders[order_id]
            self.logger.debug("Order removed from storage", order_id=order_id)
            return True
        return False

    def get_cached_order(self, symbol: Symbol, order_id: OrderId) -> Optional[Order]:
        """Get order from local cache (backward compatibility).
        
        Args:
            symbol: Trading symbol (ignored, kept for compatibility)
            order_id: Order identifier
            
        Returns:
            Order object if found, None otherwise
        """
        return self.get_order(order_id)

    async def _update_order(self, order: Order | None, order_id: OrderId | None = None) -> Order | None:
        """Update order in unified storage.
        
        Args:
            order: Order object to store/update
        """
        # Store in unified storage
        if not order:
            self.logger.warning("No order provided for update", order_id=order_id)
            return None

        self._orders[order.order_id] = order

        # Log status appropriately
        if is_order_done(order):
            self.logger.info("Order completed",
                           order_id=order.order_id, status=order.status)
        else:
            self.logger.info("Order updated",
                            order_id=order.order_id,
                            status=order.status)
        

        self.publish(PrivateWebsocketChannelType.ORDER, order)

        return order


    async def get_active_order(self, symbol: Symbol, order_id: OrderId) -> Optional[Order]:
        """
        Get order with smart lookup priority and HFT-safe caching.
        
        Args:
            symbol: Trading symbol
            order_id: Order identifier
            
        Returns:
            Order object if found, None otherwise
        """
        # Direct lookup from unified storage
        order = self.get_order(order_id)
        if order:
            status_type = "executed" if is_order_done(order) else "open"
            self.logger.debug(f"Order found in {status_type} state",
                            order_id=order_id, status=order.status)
            return order

        try:
            with LoggingTimer(self.logger, f"get_order_fallback_{symbol}"):
                order = await self.fetch_order(symbol, order_id)
                return order

        except Exception as e:
            self.logger.error("Failed to get order via REST fallback",
                              order_id=order_id, error=str(e))
            return None

    async def get_asset_balance(self, asset: AssetName, force=False) -> Optional[AssetBalance]:
        """
        Get balance for a specific asset with fallback to REST if not cached.

        Args:
            asset: Asset symbol
            force: If True, bypass cache and fetch from REST

        Returns:
            AssetBalance object if found, None otherwise
        """
        # Step 1: Check local cache first
        if asset in self._balances:
            return self._balances[asset]

        if force:
            # Step 2: Fallback to REST API
            try:
                with LoggingTimer(self.logger, f"get_asset_balance_{asset}"):
                    balance = await self._rest.get_asset_balance(asset)
                    if balance:
                        await self._update_balance(asset, balance)
                    return balance

            except Exception as e:
                self.logger.error("Failed to get asset balance via REST fallback",
                                  asset=asset, error=str(e))
                return None

        return AssetBalance(asset=asset, available=0.0, locked=0.0)

    def set_symbol_info(self, symbol_info: SymbolsInfo):
        self._symbols_info = symbol_info

    # Initialization
    async def initialize(self, symbols_info: Optional[SymbolsInfo] = None, channels: List[WebsocketChannelType]=None) -> None:
        """Initialize base private exchange functionality."""
        # Initialize public functionality first (parent class)
        await super().initialize()

        self._symbols_info = symbols_info
        if not channels:
            channels = [WebsocketChannelType.ORDER,
                      WebsocketChannelType.BALANCE,
                      WebsocketChannelType.EXECUTION]

        try:
            # Clients are already injected via constructor - no creation needed

            # Step 1: Load private data
            self.logger.info(f"{self._tag} Loading private data...")
            await self._refresh_exchange_data()
            
            # Step 1.5: Start balance sync if configured (from BalanceSyncMixin)
            if self._balance_sync_interval:
                self.start_balance_sync()
            # Step 2: Initialize WebSocket if available
            if self._ws:
                self.logger.info(f"{self._tag} Initializing WebSocket client...")
                await self._ws.initialize()
                await self._ws.subscribe(channels)

            else:
                self.logger.info(f"{self._tag} No WebSocket client available - skipping WebSocket initialization")

            self.logger.info(f"{self._tag} private initialization completed",
                             has_rest=self._rest is not None,
                             has_ws=self._ws is not None,
                             balance_count=len(self._balances),
                             order_count=sum(1 for order in self._orders.values() if not is_order_done(order)))

        except Exception as e:
            self.logger.error(f"Private exchange initialization failed: {e}")
            await self.close()  # Cleanup on failure
            raise

    # WebSocket initialization method ELIMINATED - client injected via constructor

    # Event handlers

    async def _order_handler(self, order: Order) -> None:
        """Handle order update event."""
        o = await self._update_order(order)
        self.logger.info("order update processed", order_id=order.order_id, order=str(o))


    async def _balance_handler(self, balance: AssetBalance) -> None:
        """Handle balance update event."""
        await self._update_balance(balance.asset, balance)
        self.logger.info("balance update processed",
                         exchange=self._exchange_name,
                         asset_balance=balance.asset)


    async def _execution_handler(self, trade: Trade) -> None:
        """Handle execution report/trade event."""
        self.logger.info(f"trade execution processed",
                         exchange=self._exchange_name,
                         symbol=trade.symbol,
                         side=trade.side.name,
                         quantity=trade.quantity,
                         price=trade.price,
                         is_maker=trade.is_maker)

        # await self.publish('trades', trade)

    # Data refresh and utilities

    async def _refresh_exchange_data(self) -> None:
        """
        Refresh all exchange data after reconnection.
        
        Refreshes both public data (orderbooks, symbols) and private data
        (balances, orders).
        """
        await asyncio.gather(
            self._load_balances(),
            self._load_open_orders(),
            return_exceptions=True
        )

    async def _update_balance(self, asset: AssetName, balance: AssetBalance) -> None:
        """Update internal balance state."""
        self._balances[asset] = balance


        self.publish(PrivateWebsocketChannelType.BALANCE, balance)

        self.logger.debug(f"Updated balance for {asset}: {balance}")
    

    async def close(self) -> None:
        """Close private exchange connections."""
        try:
            # Stop balance sync first (from BalanceSyncMixin)
            self._cleanup_balance_sync()
            
            close_tasks = []

            if self._ws:
                close_tasks.append(self._ws.close())
            if self._rest:
                close_tasks.append(self._rest.close())

            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

            # Clear bound handlers
            self.clear_handlers()

            # Call parent cleanup
            await super().close()

            # Reset connection status
            self._rest_connected = False
            self._ws_connected = False

        except Exception as e:
            self.logger.error("Error closing private exchange", error=str(e))
            raise
