"""
Base private composite exchange without withdrawal functionality.

This is the common base for both spot and futures private exchanges,
containing shared trading operations but excluding withdrawal methods
which are only needed for spot exchanges.
"""

import asyncio
from abc import abstractmethod, ABC
from typing import Dict, List, Optional, Any
from exchanges.structs.common import (
    Symbol, AssetBalance, Order, SymbolsInfo
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, Trade, OrderType
from config.structs import ExchangeConfig
from infrastructure.exceptions.system import InitializationError
from exchanges.interfaces.composite.base_composite import BaseCompositeExchange
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebsocketType
from infrastructure.logging import LoggingTimer, HFTLoggerInterface
from exchanges.utils.exchange_utils import is_order_done
from exchanges.interfaces.common.binding import BoundHandlerInterface
from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType, WebsocketChannelType
from exchanges.interfaces.ractive import PrivateObservableStreams


class BasePrivateComposite(BaseCompositeExchange[PrivateRestType, PrivateWebsocketType],
                           BoundHandlerInterface[PrivateWebsocketChannelType],
                           PrivateObservableStreams):
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
                 logger: Optional[HFTLoggerInterface] = None) -> None:
        """
        Initialize base private exchange interface with dependency injection.

        Args:
            config: Exchange configuration with API credentials
            rest_client: Injected private REST client instance
            websocket_client: Injected private WebSocket client instance (optional)
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        PrivateObservableStreams.__init__(self)
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
        self._open_orders: Dict[Symbol, Dict[OrderId, Order]] = {}

        # Executed orders state management (HFT-safe caching of completed orders only)
        self._executed_orders: Dict[Symbol, Dict[OrderId, Order]] = {}
        self._max_executed_orders_per_symbol = 1000  # Memory management limit

        # Authentication validation
        if not config.has_credentials():
            self.logger.error("No API credentials provided - trading operations will fail")

    # Properties for private data

    @property
    def balances(self) -> Dict[AssetName, AssetBalance]:
        """Get current account balances (thread-safe)."""
        return self._balances.copy()

    @property
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """Get current open orders (thread-safe)."""
        return {symbol: list(orders.values()) for symbol, orders in self._open_orders.items()}

    @property
    def executed_orders(self) -> Dict[Symbol, Dict[OrderId, Order]]:
        """
        Get cached executed orders (filled/canceled/expired).
        
        HFT COMPLIANCE: These are static completed orders - safe to cache.
        Real-time trading data (open orders, balances) remain uncached.
        
        Returns:
            Dictionary mapping symbols to executed orders cache
        """
        return self._executed_orders.copy()

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
        if symbol:
            return list(self._open_orders.get(symbol, {}).values())
        else:
            return [order for orders in self._open_orders.values() for order in orders.values()]

    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Order:
        """Place a limit order via REST API."""
        si = self.symbols_info.get(symbol)
        quantity_ = si.round_base(quantity)
        price_ = si.round_quote(price)
        return await self._rest.place_order(symbol, side, OrderType.LIMIT, quantity_, price_, **kwargs)

    async def place_market_order(self, symbol: Symbol, side: Side, quote_quantity: float, **kwargs) -> Order:
        """Place a market order via REST API."""
        quote_quantity_ = self.symbols_info.get(symbol).round_quote(quote_quantity)
        # TODO: FIX: infrastructure.exceptions.exchange.ExchangeRestError: (500, 'Futures order placement failed: Futures market orders with quote_quantity require current price. Use quantity parameter instead.')
        return await self._rest.place_order(symbol, side, OrderType.MARKET,
                                            quote_quantity=quote_quantity_, **kwargs)

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
        return await self._rest.cancel_order(symbol, order_id)

    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
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
        return await self._rest.get_order(symbol, order_id)

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
            prev_open_orders = self._open_orders.copy()

            with LoggingTimer(self.logger, "load_open_orders") as timer:
                orders = await self._rest.get_open_orders(symbol)
                for o in orders:
                    # if it was opened before reconnect, remove from forced reload list
                    if prev_open_orders.get(o.symbol, {}).get(o.order_id):
                        del prev_open_orders[o.symbol][o.order_id]
                    await self._update_order(o)

                # orders that can be filled in-between reconnects, publish  their updates
                for prev_o_symbol in prev_open_orders.keys():
                    for prev_o in prev_open_orders[prev_o_symbol].values():
                        await self._update_order(prev_o)


            self.logger.info("Open orders loaded",
                             open_orders_count=sum(len(orders) for orders in self._open_orders.values()),
                             load_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to load open orders", error=str(e))
            raise InitializationError(f"Open orders loading failed: {e}")

    # Order lifecycle management

    def _update_executed_order(self, order: Order):
        """Update executed orders cache."""
        if order.symbol not in self._executed_orders:
            self._executed_orders[order.symbol] = {}

        self._executed_orders[order.symbol][order.order_id] = order
        self.logger.info("Order cached in executed orders",
                         order_id=order.order_id, status=order.status)

    def _update_open_order(self, order: Order):
        """Update open orders state."""
        if order.symbol not in self._open_orders:
            self._open_orders[order.symbol] = {}

        self._open_orders[order.symbol][order.order_id] = order

        self.logger.debug("Open order updated",
                          order_id=order.order_id,
                          status=order.status)

    def _get_open_order(self, symbol: Symbol, order_id: OrderId):
        """Get open order from local cache."""
        if symbol in self._open_orders and order_id in self._open_orders[symbol]:
            return self._open_orders[symbol][order_id]
        return None

    def _get_executed_order(self, symbol: Symbol, order_id: OrderId):
        """Get executed order from cache."""
        if symbol in self._executed_orders and order_id in self._executed_orders[symbol]:
            return self._executed_orders[symbol][order_id]

    def _remove_open_order(self, order: Order):
        """Remove order from open orders."""
        if self._get_open_order(order.symbol, order.order_id):
            del self._open_orders[order.symbol][order.order_id]
            self.logger.debug("Open order removed",
                              order_id=order.order_id,
                              status=order.status)

    async def _update_order(self, order: Order):
        """Update order state based on completion status."""
        if is_order_done(order):
            self._remove_open_order(order)
            self._update_executed_order(order)
        else:
            self._update_open_order(order)
        # TODO: remove
        await self._exec_bound_handler(PrivateWebsocketChannelType.ORDER, order)

        self.publish('orders', order)


    async def get_active_order(self, symbol: Symbol, order_id: OrderId) -> Optional[Order]:
        """
        Get order with smart lookup priority and HFT-safe caching.
        
        Args:
            symbol: Trading symbol
            order_id: Order identifier
            
        Returns:
            Order object if found, None otherwise
        """
        # Step 1: Check open orders first (real-time lookup)
        order = self._get_open_order(symbol, order_id)
        if order:
            self.logger.debug("Order found in open orders cache", order_id=order_id, status=order.status)
            return order

        # Step 2: Check executed orders cache
        order = self._get_executed_order(symbol, order_id)
        if order:
            self.logger.debug("Order found in executed orders cache",
                              order_id=order_id, status=order.status)
            return order

        try:
            with LoggingTimer(self.logger, f"get_order_fallback_{symbol}"):
                order = await self._rest.get_order(symbol, order_id)
                await self._update_order(order)
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

    # Initialization

    async def initialize(self, symbols_info: SymbolsInfo) -> None:
        """Initialize base private exchange functionality."""
        # Initialize public functionality first (parent class)
        await super().initialize()

        self._symbols_info = symbols_info

        try:
            # Clients are already injected via constructor - no creation needed

            # Step 1: Load private data via REST if available
            if self._rest:
                self.logger.info(f"{self._tag} Loading private data...")
                await self._refresh_exchange_data()
            else:
                self.logger.warning(f"{self._tag} No REST client available - skipping data loading")

            # Step 2: Initialize WebSocket if available
            if self._ws:
                self.logger.info(f"{self._tag} Initializing WebSocket client...")
                await self._ws.initialize()
                await self._ws.subscribe([WebsocketChannelType.ORDER,
                                          WebsocketChannelType.BALANCE,
                                          WebsocketChannelType.EXECUTION])

            else:
                self.logger.info(f"{self._tag} No WebSocket client available - skipping WebSocket initialization")

            self.logger.info(f"{self._tag} private initialization completed",
                             has_rest=self._rest is not None,
                             has_ws=self._ws is not None,
                             balance_count=len(self._balances),
                             order_count=sum(len(orders) for orders in self._open_orders.values()))

        except Exception as e:
            self.logger.error(f"Private exchange initialization failed: {e}")
            await self.close()  # Cleanup on failure
            raise

    # WebSocket initialization method ELIMINATED - client injected via constructor

    # Event handlers

    async def _order_handler(self, order: Order) -> None:
        """Handle order update event."""
        await self._update_order(order)
        self.logger.info("order update processed",
                         exchange=self._exchange_name,
                         symbol=order.symbol,
                         order_id=order.order_id,
                         status=order.status.name,
                         filled=f"{order.filled_quantity}/{order.quantity}")


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
        # TODO: remove
        await self._exec_bound_handler(PrivateWebsocketChannelType.EXECUTION, trade)

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

        # TODO: remove
        await self._exec_bound_handler(PrivateWebsocketChannelType.BALANCE, balance)

        self.publish('balances', balance)

        self.logger.debug(f"Updated balance for {asset}: {balance}")

    def _cleanup_executed_orders(self, symbol: Symbol) -> None:
        """Cleanup executed orders cache for a symbol to prevent memory leaks."""
        executed_orders = self._executed_orders[symbol]
        current_size = len(executed_orders)
        target_size = int(self._max_executed_orders_per_symbol * 0.8)

        if current_size <= target_size:
            return

        # Simple cleanup: remove oldest entries (first in dict)
        orders_list = list(executed_orders.items())
        orders_to_remove = current_size - target_size
        for i in range(orders_to_remove):
            if orders_list:
                order_id, _ = orders_list.pop(0)
                del executed_orders[order_id]

        self.logger.debug(f"Cleaned up executed orders cache for {symbol}",
                          removed=orders_to_remove,
                          remaining=len(executed_orders))


    async def close(self) -> None:
        """Close private exchange connections."""
        try:
            close_tasks = []

            if self._ws:
                close_tasks.append(self._ws.close())
            if self._rest:
                close_tasks.append(self._rest.close())

            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

            # Call parent cleanup
            await super().close()

            self.dispose()

            # Reset connection status
            self._rest_connected = False
            self._ws_connected = False

        except Exception as e:
            self.logger.error("Error closing private exchange", error=str(e))
            raise
