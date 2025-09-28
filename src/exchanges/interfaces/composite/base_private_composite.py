"""
Base private composite exchange without withdrawal functionality.

This is the common base for both spot and futures private exchanges,
containing shared trading operations but excluding withdrawal methods
which are only needed for spot exchanges.
"""

import asyncio
from abc import abstractmethod
from typing import Dict, List, Optional, Any, TypeVar, Generic
from exchanges.structs import (
    Symbol, AssetBalance, Order, SymbolsInfo, ExchangeType
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, Trade, OrderType
from config.structs import ExchangeConfig
from infrastructure.exceptions.system import InitializationError
from exchanges.interfaces.composite.base_composite import BaseCompositeExchange
from infrastructure.logging import LoggingTimer, HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from exchanges.interfaces.rest.interfaces.trading_interface import PrivateTradingInterface
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
from exchanges.utils.exchange_utils import is_order_done

# Generic type variables for REST and WebSocket interfaces
RestT = TypeVar('RestT', bound=PrivateTradingInterface)
WebsocketT = TypeVar('WebsocketT', bound=PrivateSpotWebsocket)


class BasePrivateComposite(BaseCompositeExchange, Generic[RestT, WebsocketT]):
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

    def __init__(self, config: ExchangeConfig, exchange_type: ExchangeType, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None) -> None:
        """
        Initialize base private exchange interface.
        
        Args:
            config: Exchange configuration with API credentials
            exchange_type: Exchange type (SPOT, FUTURES) for behavior customization
            logger: Optional injected HFT logger (auto-created if not provided)
            handlers: Optional private WebSocket handlers
        """
        # Create default handlers if none provided
        if not handlers:
            handlers = PrivateWebsocketHandlers()
            
        super().__init__(config=config, is_private=True, exchange_type=exchange_type,
                         logger=logger, handlers=handlers)

        # Private data state (HFT COMPLIANT - no caching of real-time data)
        self._balances: Dict[AssetName, AssetBalance] = {}
        self._open_orders: Dict[Symbol, Dict[OrderId, Order]] = {}

        # Executed orders state management (HFT-safe caching of completed orders only)
        self._executed_orders: Dict[Symbol, Dict[OrderId, Order]] = {}
        self._max_executed_orders_per_symbol = 1000  # Memory management limit

        # Client instances (managed by abstract factory methods)
        self._private_rest: Optional[RestT] = None
        self._private_ws: Optional[WebsocketT] = None

        # Connection status tracking
        self._private_rest_connected = False
        self._private_ws_connected = False

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
        return await self._private_rest.place_order(symbol, side, OrderType.LIMIT, quantity_, price_, **kwargs)

    async def place_market_order(self, symbol: Symbol, side: Side, quote_quantity: float, **kwargs) -> Order:
        """Place a market order via REST API."""
        quote_quantity_ = self.symbols_info.get(symbol).round_quote(quote_quantity)
        # TODO: FIX: infrastructure.exceptions.exchange.ExchangeRestError: (500, 'Futures order placement failed: Futures market orders with quote_quantity require current price. Use quantity parameter instead.')
        return await self._private_rest.place_order(symbol, side, OrderType.MARKET,
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

    # Abstract factory methods

    @abstractmethod
    async def _create_private_rest(self) -> RestT:
        """
        Create exchange-specific private REST client.
        
        Returns:
            RestT implementation for this exchange
        """
        pass

    @abstractmethod
    async def _create_private_websocket(self) -> Optional[WebsocketT]:
        """
        Create exchange-specific private WebSocket client with handler objects.
        
        Returns:
            WebsocketT implementation or None
        """
        pass

    # Data loading methods

    async def _load_balances(self) -> None:
        """
        Load account balances from REST API with error handling and metrics.
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
        """
        if not self._private_rest:
            return

        try:
            with LoggingTimer(self.logger, "load_open_orders") as timer:
                orders = await self._private_rest.get_open_orders(symbol)
                for o in orders:
                    self._update_open_order(o)

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

    def _update_order(self, order: Order):
        """Update order state based on completion status."""
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
            with LoggingTimer(self.logger, f"get_order_fallback_{symbol}"):
                order = await self._private_rest.get_order(symbol, order_id)
                self._update_order(order)
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
                    balance = await self._private_rest.get_asset_balance(asset)
                    if balance:
                        self._update_balance(asset, balance)
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
            # Step 1: Create REST clients using abstract factory
            self.logger.info(f"{self._tag} Creating REST clients...")
            self._private_rest = await self._create_private_rest()
            self._private_rest_connected = self._private_rest is not None

            # Step 2: Load private data via REST (parallel loading)
            self.logger.info(f"{self._tag} Loading private data...")
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

    def _create_inner_websocket_handlers(self) -> PrivateWebsocketHandlers:
        """
        Create handlers to connect websocket events to internal methods.
        """
        return PrivateWebsocketHandlers(
            order_handler=self._order_handler,
            balance_handler=self._balance_handler,
            execution_handler=self._execution_handler,
        )

    async def _initialize_private_websocket(self) -> None:
        """Initialize private WebSocket with constructor injection."""
        if not self.config.has_credentials():
            self.logger.info("No credentials - skipping private WebSocket")
            return

        try:
            self._private_ws = await self._create_private_websocket()
            await self._private_ws.initialize()

        except Exception as e:
            self.logger.error("Private WebSocket initialization failed", error=str(e))
            raise InitializationError(f"Private WebSocket initialization failed: {e}")

    # Event handlers

    async def _order_handler(self, order: Order) -> None:
        """Handle order update event."""
        self._update_order(order)
        self.logger.info("order update processed",
                         exchange=self._exchange_name,
                         symbol=order.symbol,
                         order_id=order.order_id,
                         status=order.status.name,
                         filled=f"{order.filled_quantity}/{order.quantity}")

        await self.handlers.handle_order(order)

    async def _balance_handler(self, balance: AssetBalance) -> None:
        """Handle balance update event."""
        self._balances[balance.asset] = balance
        self.logger.info("balance update processed",
                         exchange=self._exchange_name,
                         asset_balance=balance.asset)

        await self.handlers.handle_balance(balance)

    async def _execution_handler(self, trade: Trade) -> None:
        """Handle execution report/trade event."""
        self.logger.info(f"trade execution processed",
                         exchange=self._exchange_name,
                         symbol=trade.symbol,
                         side=trade.side.name,
                         quantity=trade.quantity,
                         price=trade.price,
                         is_maker=trade.is_maker)
        await self.handlers.handle_execution(trade)

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

    def _update_balance(self, asset: AssetName, balance: AssetBalance) -> None:
        """Update internal balance state."""
        self._balances[asset] = balance
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

    # Monitoring and diagnostics

    def get_trading_stats(self) -> Dict[str, Any]:
        """
        Get trading statistics for monitoring.
        
        Returns:
            Dictionary with trading and account statistics
        """
        executed_orders_count = sum(len(orders_dict) for orders_dict in self._executed_orders.values())

        trading_stats = {
            'total_balances': len(self._balances),
            'open_orders_count': sum(len(orders) for orders in self._open_orders.values()),
            'executed_orders_count': executed_orders_count,
            'has_credentials': self._config.has_credentials(),
            'symbols_with_executed_orders': len([s for s, orders in self._executed_orders.items() if orders]),
            'connection_status': {
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