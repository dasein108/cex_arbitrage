"""
Private exchange interface for trading operations.

This interface handles authenticated operations including order management,
balance tracking, and position monitoring. It inherits from the public
interface to also provide market data functionality.
"""

import time
import asyncio
from abc import abstractmethod
from typing import Dict, List, Optional, Any, Callable, Awaitable
from exchanges.structs.common import (
    Symbol, AssetBalance, Order, Position, WithdrawalRequest, WithdrawalResponse, SymbolsInfo
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side
from config.structs import ExchangeConfig
from .base_public_exchange import CompositePublicExchange
from infrastructure.exceptions.exchange import BaseExchangeError
from infrastructure.logging import LoggingTimer, HFTLoggerInterface
from infrastructure.networking.websocket.handlers import (
    PrivateWebsocketHandlers, PublicWebsocketHandlers
)
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.ws.spot.base_ws_private import PrivateSpotWebsocket
# Removed unused event imports - using direct objects for better HFT performance  
# from exchanges.interfaces.base_events import (
#     OrderUpdateEvent, BalanceUpdateEvent, ExecutionReportEvent, 
#     ConnectionStatusEvent, ErrorEvent
# )



class CompositePrivateExchange(CompositePublicExchange):
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

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize private exchange interface.
        
        Args:
            config: Exchange configuration with API credentials
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        super().__init__(config=config, logger=logger)
        
        # Override tag to indicate private operations
        self._tag = f'{config.name}_private'
        
        # Private data state (HFT COMPLIANT - no caching of real-time data)
        self._balances: Dict[Symbol, AssetBalance] = {}
        self._open_orders: Dict[Symbol, List[Order]] = {}
        
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
            self.logger.warning("No API credentials provided - trading operations will fail")

    # Abstract properties for private data

    @property
    @abstractmethod
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """
        Get current account balances.
        
        Returns:
            Dictionary mapping asset symbols to balance information
        """
        pass

    @property
    @abstractmethod
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """
        Get current open orders.
        
        Returns:
            Dictionary mapping symbols to lists of open orders
        """
        pass


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

    @abstractmethod
    async def place_limit_order(
        self, 
        symbol: Symbol, 
        side: Side, 
        quantity: float, 
        price: float, 
        **kwargs
    ) -> Order:
        """
        Place a limit order.
        
        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            price: Limit price
            **kwargs: Exchange-specific parameters
            
        Returns:
            Order object with order details
            
        Raises:
            ExchangeError: If order placement fails
        """
        pass

    @abstractmethod
    async def place_market_order(
        self, 
        symbol: Symbol, 
        side: Side, 
        quantity: float, 
        **kwargs
    ) -> Order:
        """
        Place a market order.
        
        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            **kwargs: Exchange-specific parameters
            
        Returns:
            Order object with order details
            
        Raises:
            ExchangeError: If order placement fails
        """
        pass

    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> bool:
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
        pass

    @abstractmethod
    async def get_order_status(self, symbol: Symbol, order_id: str) -> Order:
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
        pass

    @abstractmethod
    async def get_order_history(
        self,
        symbol: Optional[Symbol] = None,
        limit: int = 100
    ) -> List[Order]:
        """
        Get order history.

        Args:
            symbol: Optional symbol filter
            limit: Maximum number of orders to return

        Returns:
            List of historical orders
        """
        pass

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
    async def cancel_withdrawal(self, withdrawal_id: str) -> bool:
        """
        Cancel a pending withdrawal.

        Args:
            withdrawal_id: Exchange withdrawal ID to cancel

        Returns:
            True if cancellation successful, False otherwise

        Raises:
            ExchangeError: If cancellation fails
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
    async def validate_withdrawal_address(
        self,
        asset: AssetName,
        address: str,
        network: Optional[str] = None
    ) -> bool:
        """
        Validate withdrawal address format.

        Args:
            asset: Asset name
            address: Destination address
            network: Network/chain name

        Returns:
            True if address is valid, False otherwise
        """
        pass

    @abstractmethod
    async def get_withdrawal_limits(
        self,
        asset: AssetName,
        network: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get withdrawal limits for an asset.

        Args:
            asset: Asset name
            network: Network/chain name

        Returns:
            Dictionary with 'min', 'max', and 'fee' limits
        """
        pass

    # ========================================
    # Abstract Factory Methods (COPIED FROM UnifiedCompositeExchange)
    # ========================================
    
    @abstractmethod
    async def _create_private_rest(self) -> PrivateSpotRest:
        """
        Create exchange-specific private REST client.
        PATTERN: Copied from UnifiedCompositeExchange line 200
        
        Returns:
            PrivateSpotRest implementation for this exchange
        """
        pass

    @abstractmethod  
    async def _create_private_ws_with_handlers(self, handlers: PrivateWebsocketHandlers) -> Optional[PrivateSpotWebsocket]:
        """
        Create exchange-specific private WebSocket client with handler objects.
        PATTERN: Copied from UnifiedCompositeExchange line 210
        
        Args:
            handlers: PrivateWebsocketHandlers object with event handlers
        
        Returns:
            PrivateSpotWebsocket implementation or None
        """
        pass


    # ========================================
    # Concrete Private Data Loading (COPIED FROM UnifiedCompositeExchange)
    # ========================================

    async def _load_balances(self) -> None:
        """
        Load account balances from REST API with error handling and metrics.
        PATTERN: Copied from UnifiedCompositeExchange line 350
        """
        if not self._private_rest:
            self.logger.warning("No private REST client available for balance loading")
            return
            
        try:
            with LoggingTimer(self.logger, "load_balances") as timer:
                balances_data = await self._private_rest.get_balances()
                
                # Update internal state (pattern from line 360)
                for asset, balance in balances_data.items():
                    self._balances[asset] = balance
                    
            self.logger.info("Balances loaded successfully",
                            balance_count=len(balances_data),
                            load_time_ms=timer.elapsed_ms)
                            
        except Exception as e:
            self.logger.error("Failed to load balances", error=str(e))
            raise BaseExchangeError(f"Balance loading failed: {e}") from e

    async def _load_open_orders(self) -> None:
        """
        Load open orders from REST API with error handling.
        PATTERN: Copied from UnifiedCompositeExchange line 380
        ENHANCED: Initialize executed orders cache per symbol
        """
        if not self._private_rest:
            return
            
        try:
            with LoggingTimer(self.logger, "load_open_orders") as timer:
                # Load orders for each active symbol
                for symbol in self.active_symbols:
                    orders = await self._private_rest.get_open_orders(symbol=symbol)
                    self._open_orders[symbol] = orders
                    
                    # NEW: Initialize executed orders cache for symbol
                    if symbol not in self._executed_orders:
                        self._executed_orders[symbol] = {}
                    
            self.logger.info("Open orders loaded",
                            symbol_count=len(self.active_symbols),
                            open_orders_count=sum(len(orders) for orders in self._open_orders.values()),
                            load_time_ms=timer.elapsed_ms)
                            
        except Exception as e:
            self.logger.error("Failed to load open orders", error=str(e))
            raise BaseExchangeError(f"Open orders loading failed: {e}") from e


    # ========================================
    # Enhanced Order Lifecycle Management (NEW FUNCTIONALITY)
    # ========================================

    async def get_active_order(self, symbol: Symbol, order_id: OrderId) -> Optional[Order]:
        """
        NEW METHOD: Get order with smart lookup priority and HFT-safe caching.
        
        Lookup Priority:
        1. Check _open_orders[symbol] first (real-time, no caching)  
        2. Check _executed_orders[symbol][order_id] (cached executed orders)
        3. Fallback to REST API and cache result in _executed_orders
        
        HFT COMPLIANCE: Only executed orders cached (static completed data).
        Open orders remain real-time to avoid stale price execution.
        
        Args:
            symbol: Trading symbol
            order_id: Order identifier
            
        Returns:
            Order object if found, None otherwise
        """
        # Step 1: Check open orders first (real-time lookup)
        if symbol in self._open_orders:
            for order in self._open_orders[symbol]:
                if order.order_id == order_id:
                    self.logger.debug("Order found in open orders cache", 
                                    order_id=order_id, status=order.status)
                    return order
        
        # Step 2: Check executed orders cache
        if symbol in self._executed_orders and order_id in self._executed_orders[symbol]:
            cached_order = self._executed_orders[symbol][order_id]
            self.logger.debug("Order found in executed orders cache", 
                            order_id=order_id, status=cached_order.status)
            return cached_order
        
        # Step 3: Fallback to REST API call
        if not self._private_rest:
            self.logger.warning("No private REST client available for order lookup", 
                              order_id=order_id)
            return None
        
        try:
            with LoggingTimer(self.logger, f"get_order_fallback_{symbol}") as timer:
                order = await self._private_rest.get_order(symbol, order_id)
                
                if order and order.status in ['filled', 'canceled', 'expired']:
                    # Cache executed orders (HFT-safe - completed orders are static)
                    if symbol not in self._executed_orders:
                        self._executed_orders[symbol] = {}
                    self._executed_orders[symbol][order_id] = order
                    
                    self.logger.info("Order cached in executed orders",
                                   order_id=order_id, status=order.status, 
                                   lookup_time_ms=timer.elapsed_ms)
                
                return order
                
        except Exception as e:
            self.logger.error("Failed to get order via REST fallback", 
                            order_id=order_id, error=str(e))
            return None

    # ========================================
    # Template Method Initialization (COPIED FROM UnifiedCompositeExchange)
    # ========================================

    async def initialize(self, symbols_info: SymbolsInfo) -> None:
        """
        Initialize private exchange with template method orchestration.
        PATTERN: Copied from UnifiedCompositeExchange line 45-100
        
        ELIMINATES DUPLICATION: This orchestration logic was previously 
        duplicated across ALL exchange implementations (80%+ code reduction).
        """
        # Initialize public functionality first (parent class)
        await super().initialize(symbols_info)
        
        try:
            # Step 1: Create REST clients using abstract factory
            self.logger.info(f"{self._tag} Creating REST clients...")
            self._private_rest = await self._create_private_rest()
            self._private_rest_connected = self._private_rest is not None
            
            # Step 2: Load private data via REST (parallel loading)
            self.logger.info(f"{self._tag} Loading private data...")
            await asyncio.gather(
                self._load_balances(),
                self._load_open_orders(),
                return_exceptions=True
            )
            
            # Step 3: Create WebSocket clients with handler injection
            self.logger.info(f"{self._tag} Creating WebSocket clients...")
            await self._initialize_private_websocket()
            
            # Step 4: Start private streaming if WebSocket enabled
            if self._private_ws:
                self.logger.info(f"{self._tag} Starting private streaming...")
                await self._start_private_streaming()
            
            self.logger.info(f"{self._tag} private initialization completed",
                            has_rest=self._private_rest is not None,
                            has_ws=self._private_ws is not None,
                            balance_count=len(self._balances),
                            order_count=sum(len(orders) for orders in self._open_orders.values()))
            
        except Exception as e:
            self.logger.error(f"Private exchange initialization failed: {e}")
            await self.close()  # Cleanup on failure
            raise

    # ========================================
    # WebSocket Handler Constructor Injection (COPIED FROM UnifiedCompositeExchange)
    # ========================================

    async def _initialize_private_websocket(self) -> None:
        """
        Initialize private WebSocket with constructor injection.
        PATTERN: Copied from UnifiedCompositeExchange line 600-650
        
        KEY INSIGHT: This pattern eliminates manual handler setup in each exchange.
        """
        if not self.config.has_credentials():
            self.logger.info("No credentials - skipping private WebSocket")
            return
            
        try:
            # Create handler objects for constructor injection (line 610)
            private_handlers = PrivateWebsocketHandlers(
                order_handler=self._handle_order_event,
                balance_handler=self._handle_balance_event,
                position_handler=None,  # Position handling removed from base class
                execution_handler=self._handle_execution_event,
                connection_handler=self._handle_private_connection_event,
                error_handler=self._handle_error_event
            )
            
            # Use abstract factory method to create client with handlers (line 620)
            self._private_ws = await self._create_private_ws_with_handlers(private_handlers)
            
            if self._private_ws:
                # Connect and start event processing (line 630)
                await self._private_ws.connect()
                self._private_ws_connected = self._private_ws.is_connected
                
                self.logger.info("Private WebSocket initialized",
                                connected=self._private_ws_connected,
                                has_order_handler=private_handlers.order_handler is not None,
                                has_balance_handler=private_handlers.balance_handler is not None)
                
        except Exception as e:
            self.logger.error("Private WebSocket initialization failed", error=str(e))
            raise

    async def _start_private_streaming(self) -> None:
        """Start private WebSocket subscriptions."""
        try:
            if self._private_ws:
                await asyncio.gather(
                    self._private_ws.subscribe_orders(),
                    self._private_ws.subscribe_balances(), 
                    self._private_ws.subscribe_executions(),
                    return_exceptions=True
                )
                
                self.logger.info("Private WebSocket streams started")
                
        except Exception as e:
            self.logger.error("Failed to start private WebSocket streams", error=str(e))
            raise

    # ========================================
    # Event Handler Methods (DISABLED - see websocket_refactoring.md)
    # ========================================
    
    # TODO: These methods need to be refactored to use direct objects instead of events
    # Currently disabled due to base_events.py removal. Will be re-implemented with 
    # direct object signatures like base_public_exchange.py does.
    
    # async def _handle_order_event(self, event: OrderUpdateEvent) -> None:
    # async def _handle_balance_event(self, event: BalanceUpdateEvent) -> None:  
    # async def _handle_execution_event(self, event: ExecutionReportEvent) -> None:

    # All event handlers disabled pending websocket_refactoring.md completion
    # async def _handle_private_connection_event(self, event: ConnectionStatusEvent) -> None:
    # async def _handle_error_event(self, event: ErrorEvent) -> None:

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
        try:
            # Refresh private data
            await self._load_balances()
            await self._load_open_orders()

            self.logger.info(f"{self._tag} all data refreshed after reconnection")

        except Exception as e:
            self.logger.error(f"Failed to refresh data for {self._tag}: {e}")
            raise

    # Utility methods for private data management

    def _update_balance(self, asset: Symbol, balance: AssetBalance) -> None:
        """
        Update internal balance state.
        
        Args:
            asset: Asset symbol
            balance: New balance information
        """
        self._balances[asset] = balance
        self.logger.debug(f"Updated balance for {asset}: {balance}")

    def _update_order(self, order: Order) -> None:
        """
        Update internal order state with enhanced lifecycle management.
        ENHANCED: Proper transitions between open → executed order states.
        
        Args:
            order: Updated order information
        """
        symbol = order.symbol
        self._ensure_order_containers_exist(symbol)
        
        # Try to update existing order
        if self._update_existing_order(order):
            return
            
        # Handle new order
        self._handle_new_order(order)

    def _ensure_order_containers_exist(self, symbol: Symbol) -> None:
        """Ensure order storage containers exist for the symbol."""
        if symbol not in self._open_orders:
            self._open_orders[symbol] = []
        if symbol not in self._executed_orders:
            self._executed_orders[symbol] = {}

    def _update_existing_order(self, order: Order) -> bool:
        """
        Update existing order if found.
        
        Args:
            order: Order to update
            
        Returns:
            True if existing order was found and updated, False otherwise
        """
        symbol = order.symbol
        existing_orders = self._open_orders[symbol]
        
        for i, existing_order in enumerate(existing_orders):
            if existing_order.order_id == order.order_id:
                if self._is_order_executed(order):
                    self._move_to_executed_orders(symbol, order, i)
                else:
                    self._update_open_order(order, i)
                return True
        return False

    def _is_order_executed(self, order: Order) -> bool:
        """Check if order is in an executed state."""
        return order.status in ['filled', 'canceled', 'expired']

    def _move_to_executed_orders(self, symbol: Symbol, order: Order, index: int) -> None:
        """Move order from open orders to executed orders cache."""
        # Remove from open orders
        self._open_orders[symbol].pop(index)
        
        # Add to executed orders cache with memory management
        self._add_to_executed_orders_cache(symbol, order)
        
        self.logger.info("Order moved to executed orders",
                        order_id=order.order_id,
                        symbol=symbol,
                        status=order.status,
                        executed_quantity=getattr(order, 'filled_quantity', 0))

    def _update_open_order(self, order: Order, index: int) -> None:
        """Update existing open order in place."""
        symbol = order.symbol
        self._open_orders[symbol][index] = order
        
        self.logger.debug("Open order updated",
                         order_id=order.order_id, 
                         status=order.status)

    def _handle_new_order(self, order: Order) -> None:
        """Handle new order that doesn't exist in current tracking."""
        symbol = order.symbol
        
        if self._is_order_executed(order):
            # Add directly to executed orders if already completed
            self._add_to_executed_orders_cache(symbol, order)
            self.logger.info("New executed order cached",
                           order_id=order.order_id,
                           symbol=symbol, 
                           status=order.status)
        else:
            # Add to open orders
            self._open_orders[symbol].append(order)
            self.logger.debug("New open order added",
                            order_id=order.order_id, 
                            symbol=symbol)

    def _add_to_executed_orders_cache(self, symbol: Symbol, order: Order) -> None:
        """
        Add order to executed orders cache with memory management.
        
        Implements LRU-style cleanup when cache exceeds size limits to prevent
        memory leaks in long-running HFT systems.
        
        Args:
            symbol: Trading symbol
            order: Executed order to cache
        """
        executed_orders = self._executed_orders[symbol]
        
        # Add the new order
        executed_orders[order.order_id] = order
        
        # Check if cleanup is needed
        if len(executed_orders) > self._max_executed_orders_per_symbol:
            self._cleanup_executed_orders_cache(symbol)

    def _cleanup_executed_orders_cache(self, symbol: Symbol) -> None:
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

    # ========================================
    # Connection Management & Recovery (COPIED FROM UnifiedCompositeExchange)
    # ========================================

    async def _reconnect_private_ws(self) -> None:
        """Reconnect private WebSocket with exponential backoff."""
        if self._private_ws:
            try:
                await self._private_ws.reconnect()
                self._private_ws_connected = self._private_ws.is_connected
                
                # Re-subscribe to private streams if connection restored
                if self._private_ws_connected:
                    await self._private_ws.subscribe_orders()
                    await self._private_ws.subscribe_balances()
                    await self._private_ws.subscribe_executions()
                    
            except Exception as e:
                self.logger.error("Private WebSocket reconnect failed", error=str(e))
                self._private_ws_connected = False

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