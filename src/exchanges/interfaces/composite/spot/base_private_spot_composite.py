"""
Private exchange interface for trading operations.

This interface handles authenticated operations including order management,
balance tracking, and position monitoring. It inherits from the public
interface to also provide market data functionality.
"""

import time
import asyncio
from abc import abstractmethod
from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
from exchanges.structs.common import (
    Symbol, AssetBalance, Order, AssetInfo, WithdrawalRequest, WithdrawalResponse, SymbolsInfo
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderStatus, Trade, OrderType
from config.structs import ExchangeConfig
from infrastructure.exceptions.system import InitializationError
from .base_public_spot_composite import BaseCompositeExchange
from infrastructure.logging import LoggingTimer, HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
from exchanges.utils.exchange_utils import is_order_done


class CompositePrivateExchange(BaseCompositeExchange):
    """
    Base interface for private exchange operations (trading + market data).
    
    Handles:
    - All public exchange functionality (inherits from BasePublicExchangeInterface)
    - Account balance tracking
    - Order management (place, cancel, status)
    - Position monitoring (for margin/futures trading)
    - Authenticated data streaming via WebSocket
    
    This interface requires valid API credentials and provides full trading
    functionality on top of market data operations.
    """

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = PrivateWebsocketHandlers()) -> None:
        """
        Initialize private exchange interface.
        
        Args:
            config: Exchange configuration with API credentials
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        super().__init__(config=config, is_private=True, logger=logger)
        self.handlers = handlers
        self._tag = f'{config.name}_private'
        self._assets_info: Dict[AssetName, AssetInfo] = {}

        # Private data state (HFT COMPLIANT - no caching of real-time data)
        self._balances: Dict[AssetName, AssetBalance] = {}
        self._open_orders: Dict[Symbol, Dict[OrderId, Order]] = {}

        # NEW: Executed orders state management (HFT-safe caching of completed orders only)
        self._executed_orders: Dict[Symbol, Dict[OrderId, Order]] = {}
        self._max_executed_orders_per_symbol = 1000  # Memory management limit

        # Client instances (managed by abstract factory methods)
        self._private_rest: Optional[PrivateSpotRest] = None
        self._private_ws: Optional[PrivateSpotWebsocket] = None

        # Connection status tracking
        self._private_rest_connected = False
        self._private_ws_connected = False

        # Authentication validation
        if not config.has_credentials():
            self.logger.error("No API credentials provided - trading operations will fail")

    # Abstract properties for private data

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

    # Abstract trading operations

    async def get_open_orders(self, symbol: Optional[Symbol] = None, force=False) -> List[Order]:
        """
        Get current open orders.

        Args:
            symbol: Optional symbol filter

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
        """Place a limit order via MEXC REST API."""
        si = self.symbols_info.get(symbol)
        quantity_ = si.round_base(quantity)
        price_ = si.round_quote(price)
        return await self._private_rest.place_order(symbol, side, OrderType.LIMIT, quantity_, price_, **kwargs)

    async def place_market_order(self, symbol: Symbol, side: Side, quote_quantity: float, **kwargs) -> Order:
        """Place a market order via MEXC REST API."""
        quote_quantity_ = self.symbols_info.get(symbol).round_quote(quote_quantity)
        return await self._private_rest.place_order(symbol, side, OrderType.MARKET,
                                                    quote_quantity=quote_quantity_, **kwargs)


    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """
        Cancel an existing order.
        
        Args:
            symbol: Trading symbol
            order_id: Exchange order ID to cancel
            
        Returns:
            True if cancellation successful, False otherwise
            
        Raises:
            ExchangeError: If cancellation fails
        """
        return await self._private_rest.cancel_order(symbol, order_id)

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
        return await self._private_rest.get_order(symbol, order_id)

    # TODO: not necessary at the moment
    # @abstractmethod
    # async def get_order_history(
    #     self,
    #     symbol: Optional[Symbol] = None,
    #     limit: int = 100
    # ) -> List[Order]:
    #     """
    #     Get order history.
    #
    #     Args:
    #         symbol: Optional symbol filter
    #         limit: Maximum number of orders to return
    #
    #     Returns:
    #         List of historical orders
    #     """
    #     pass

    # Abstract withdrawal operations

    @abstractmethod
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """
        Submit a withdrawal request.

        Args:
            request: Withdrawal request parameters

        Returns:
            WithdrawalResponse with withdrawal details

        Raises:
            ExchangeError: If withdrawal submission fails
            ValidationError: If request parameters are invalid
        """
        pass

    @abstractmethod
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """
        Get current status of a withdrawal.

        Args:
            withdrawal_id: Exchange withdrawal ID

        Returns:
            WithdrawalResponse with current status

        Raises:
            ExchangeError: If withdrawal not found or query fails
        """
        pass

    @abstractmethod
    async def get_withdrawal_history(
        self,
        asset: Optional[AssetName] = None,
        limit: int = 100
    ) -> List[WithdrawalResponse]:
        """
        Get withdrawal history.

        Args:
            asset: Optional asset filter
            limit: Maximum number of withdrawals to return

        Returns:
            List of historical withdrawals
        """
        pass

    @abstractmethod
    async def _create_private_rest(self) -> PrivateSpotRest:
        """
        Create exchange-specific private REST client.
        PATTERN: Copied from composite exchange line 200
        
        Returns:
            PrivateSpotRest implementation for this exchange
        """
        pass

    @abstractmethod
    async def _create_private_ws_with_handlers(self, handlers: PrivateWebsocketHandlers) -> Optional[PrivateSpotWebsocket]:
        """
        Create exchange-specific private WebSocket client with handler objects.
        PATTERN: Copied from composite exchange line 210
        
        Args:
            handlers: PrivateWebsocketHandlers object with event handlers
        
        Returns:
            PrivateSpotWebsocket implementation or None
        """
        pass

    async def _load_assets_info(self) -> None:
        """
        Load asset information from REST API with error handling.
        PATTERN: Copied from composite exchange line 320
        """
        try:
            with LoggingTimer(self.logger, "load_assets_info") as timer:
                assets_info_data = await self._private_rest.get_assets_info()
                self._assets_info = assets_info_data

            self.logger.info("Assets info loaded successfully",
                            asset_count=len(assets_info_data),
                            load_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to load assets info", error=str(e))
            raise InitializationError(f"Assets info loading failed: {e}")
    async def _load_balances(self) -> None:
        """
        Load account balances from REST API with error handling and metrics.
        PATTERN: Copied from composite exchange line 350
        """
        if not self._private_rest:
            self.logger.warning("No private REST client available for balance loading")
            return

        try:
            with LoggingTimer(self.logger, "load_balances") as timer:
                balances_data = await self._private_rest.get_balances()

                self._balances = {b.asset: b for b in balances_data}

            self.logger.info("Balances loaded successfully",
                            balance_count=len(balances_data),
                            load_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to load balances", error=str(e))
            raise InitializationError(f"Balance loading failed: {e}")

    async def _load_open_orders(self, symbol: Optional[Symbol] = None) -> None:
        """
        Load open orders from REST API with error handling.
        PATTERN: Copied from composite exchange line 380
        ENHANCED: Initialize executed orders cache per symbol
        """
        if not self._private_rest:
            return

        try:
            with LoggingTimer(self.logger, "load_open_orders") as timer:
                # Load orders for each active symbol
                    orders = await self._private_rest.get_open_orders(symbol)
                    for o in orders:
                        self._update_open_order(o)

            self.logger.info("Open orders loaded",
                            open_orders_count=sum(len(orders) for orders in self._open_orders.values()),
                            load_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to load open orders", error=str(e))
            raise InitializationError(f"Open orders loading failed: {e}")


    # ========================================
    # Enhanced Order Lifecycle Management (NEW FUNCTIONALITY)
    # ========================================

    def _update_executed_order(self, order: Order):
        if order.symbol not in self._executed_orders:
            self._executed_orders[order.symbol] = {}

        self._executed_orders[order.symbol][order.order_id] = order
        self.logger.info("Order cached in executed orders",
                         order_id=order.order_id, status=order.status)

    def _update_open_order(self, order: Order):
        if order.symbol not in self._open_orders:
            self._open_orders[order.symbol] = {}

        self._open_orders[order.symbol][order.order_id] = order
        self.logger.debug("Open order updated",
                         order_id=order.order_id,
                         status=order.status)

    def _get_open_order(self, symbol: Symbol, order_id: OrderId):
        return self._open_orders[symbol][order_id]

    def _get_executed_order(self, symbol: Symbol, order_id: OrderId):
        if symbol in self._executed_orders and order_id in self._executed_orders[symbol]:
            return self._executed_orders[symbol][order_id]

    def _remove_open_order(self, order: Order):
        if self._get_open_order(order.symbol, order.order_id):
            del self._open_orders[order.symbol][order.order_id]
            self.logger.debug("Open order removed",
                             order_id=order.order_id,
                             status=order.status)

    def _update_order(self, order: Order):
        if is_order_done(order):
            self._remove_open_order(order)
            self._update_executed_order(order)
        else:
            self._update_open_order(order)

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
            with LoggingTimer(self.logger, f"get_order_fallback_{symbol}") as timer:
                order = await self._private_rest.get_order(symbol, order_id)
                self._update_order(order)
                return order

        except Exception as e:
            self.logger.error("Failed to get order via REST fallback",
                            order_id=order_id, error=str(e))
            return None

    async def get_asset_balance(self, asset: AssetName, force= False) -> Optional[AssetBalance]:
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
                with LoggingTimer(self.logger, f"get_asset_balance_{asset}") as timer:
                    balance = await self._private_rest.get_asset_balance(asset)
                    if balance:
                        self._update_balance(asset, balance)
                    return balance

            except Exception as e:
                self.logger.error("Failed to get asset balance via REST fallback",
                                asset=asset, error=str(e))
                return None

        return AssetBalance(asset=asset, available=0.0, locked=0.0)


    async def initialize(self, symbols_info: SymbolsInfo) -> None:
        """
        symbols_info: SymbolsInfo object with all exchange symbols details
        """
        # Initialize public functionality first (parent class)
        await super().initialize()

        self._symbols_info = symbols_info

        try:
            # Step 1: Create REST clients using abstract factory
            self.logger.info(f"{self._tag} Creating REST clients...")
            self._private_rest = await self._create_private_rest()
            self._private_rest_connected = self._private_rest is not None

            # Step 2: Load private data via REST (parallel loading)
            self.logger.info(f"{self._tag} Loading private data...")
            await self._load_assets_info()
            await self._refresh_exchange_data()

            # Step 3: Create WebSocket clients with handler injection
            self.logger.info(f"{self._tag} Creating WebSocket clients...")
            await self._initialize_private_websocket()

            self.logger.info(f"{self._tag} private initialization completed",
                            has_rest=self._private_rest is not None,
                            has_ws=self._private_ws is not None,
                            balance_count=len(self._balances),
                            order_count=sum(len(orders) for orders in self._open_orders.values()))

        except Exception as e:
            self.logger.error(f"Private exchange initialization failed: {e}")
            await self.close()  # Cleanup on failure
            raise

    def _get_websocket_handlers(self) ->PrivateWebsocketHandlers:
        return PrivateWebsocketHandlers(
                order_handler=self._order_handler,
                balance_handler=self._balance_handler,
                execution_handler=self._execution_handler,
            )

    async def _initialize_private_websocket(self) -> None:
        """
        Initialize private WebSocket with constructor injection.

        """
        if not self.config.has_credentials():
            self.logger.info("No credentials - skipping private WebSocket")
            return

        try:
            private_handlers = self._get_websocket_handlers()

            # Use abstract factory method to create client with handlers (line 620)
            self._private_ws = await self._create_private_ws_with_handlers(private_handlers)
            await self._private_ws.initialize()

        except Exception as e:
            self.logger.error("Private WebSocket initialization failed", error=str(e))
            raise InitializationError(f"Private WebSocket initialization failed: {e}")

    async def _order_handler(self, order: Order) -> None:
        """Handle order update event."""
        self._update_order(order)
        self.logger.info("order update processed",
                         exchange=self._exchange_name,
                         symbol=order.symbol,
                         order_id=order.order_id,
                         status=order.status.name,
                         filled=f"{order.filled_quantity}/{order.quantity}")

        await self.handlers.order_handler(order)

    async def _balance_handler(self, balances: Dict[AssetName, AssetBalance]) -> None:
        """Handle balance update event."""
        self._balances.update(balances)
        non_zero_balances = [b for b in balances.values() if b.available > 0 or b.locked > 0]
        self.logger.info("balance update processed",
                         exchange=self._exchange_name,
                         updated_assets=len(balances),
                         non_zero_balances=len(non_zero_balances))

        await self.handlers.balance_handler(balances)

    async def _execution_handler(self, trade: Trade) -> None:
        """Handle execution report/trade event."""
        self.logger.info(f"trade execution processed",
                         exchange=self._exchange_name,
                         symbol=trade.symbol,
                         side=trade.side.name,
                         quantity=trade.quantity,
                         price=trade.price,
                         is_maker=trade.is_maker)
        await self.handlers.execution_handler(trade)

    def _track_operation(self, operation_name: str) -> None:
        """Track operation for performance monitoring."""
        # Simple implementation - can be enhanced with performance tracking
        self.logger.debug(f"Operation tracked: {operation_name}")

    # Data refresh implementation for reconnections

    async def _refresh_exchange_data(self) -> None:
        """
        Refresh all exchange data after reconnection.
        
        Refreshes both public data (orderbooks, symbols) and private data
        (balances, orders, positions).
        """
        await asyncio.gather(
            self._load_balances(),
            self._load_open_orders(),
            return_exceptions=True
        )

    # Utility methods for private data management

    def _update_balance(self, asset: AssetName, balance: AssetBalance) -> None:
        """
        Update internal balance state.
        
        Args:
            asset: Asset symbol
            balance: New balance information
        """
        self._balances[asset] = balance
        self.logger.debug(f"Updated balance for {asset}: {balance}")

    def _cleanup_executed_orders(self, symbol: Symbol) -> None:
        """
        Cleanup executed orders cache for a symbol to prevent memory leaks.
        
        Removes oldest orders when cache exceeds limit, keeping most recent orders
        for faster lookups in get_active_order method.
        
        Args:
            symbol: Symbol to cleanup cache for
        """
        executed_orders = self._executed_orders[symbol]
        current_size = len(executed_orders)
        target_size = int(self._max_executed_orders_per_symbol * 0.8)  # Remove 20% when cleanup needed

        if current_size <= target_size:
            return

        # Sort by timestamp and keep most recent orders
        # This assumes orders have timestamp or we can use order_id for ordering
        orders_list = list(executed_orders.items())

        # Simple cleanup: remove oldest entries (first in dict)
        # More sophisticated approach could use order timestamps
        orders_to_remove = current_size - target_size
        for i in range(orders_to_remove):
            if orders_list:
                order_id, _ = orders_list.pop(0)
                del executed_orders[order_id]

        self.logger.debug(f"Cleaned up executed orders cache for {symbol}",
                         removed=orders_to_remove,
                         remaining=len(executed_orders))


    # Monitoring and diagnostics

    def get_trading_stats(self) -> Dict[str, Any]:
        """
        Get enhanced trading statistics for monitoring.
        ENHANCED: Include executed orders metrics.
        
        Returns:
            Dictionary with trading and account statistics including executed orders
        """
        # Count executed orders across all symbols
        executed_orders_count = sum(len(orders_dict) for orders_dict in self._executed_orders.values())

        trading_stats = {
            'total_balances': len(self._balances),
            'open_orders_count': sum(len(orders) for orders in self._open_orders.values()),
            'executed_orders_count': executed_orders_count,  # NEW: executed orders tracking
            'has_credentials': self._config.has_credentials(),
            'symbols_with_executed_orders': len([s for s, orders in self._executed_orders.items() if orders]),  # NEW
            'connection_status': {  # Enhanced connection tracking
                'private_rest_connected': self._private_rest_connected,
                'private_ws_connected': self._private_ws_connected,
            }
        }

        return {**trading_stats}

    async def close(self) -> None:
        """Close private exchange connections."""
        try:
            close_tasks = []

            if self._private_ws:
                close_tasks.append(self._private_ws.close())
            if self._private_rest:
                close_tasks.append(self._private_rest.close())

            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

            # Call parent cleanup
            await super().close()

            # Reset connection status
            self._private_rest_connected = False
            self._private_ws_connected = False

        except Exception as e:
            self.logger.error("Error closing private exchange", error=str(e))
            raise