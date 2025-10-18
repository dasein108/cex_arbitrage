"""
Exchange Manager for Multi-Exchange Arbitrage Strategies

Provides centralized management of multiple DualExchange instances for arbitrage strategies.
Handles coordination, performance monitoring, and event orchestration across N exchanges.

Features:
- DualExchange registry and lifecycle management
- Real-time event handler orchestration
- Performance monitoring and metrics collection
- HFT-optimized parallel operations
- Automatic error recovery and failover
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any, Literal
# Float-only policy - no Decimal imports per PROJECT_GUIDES.md
import time
from enum import Enum
from msgspec import Struct

from exchanges.dual_exchange import DualExchange
from exchanges.structs import Symbol, BookTicker, Order, AssetBalance, Position, Side, ExchangeEnum
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from config.config_manager import get_exchange_config
import msgspec


class ExchangeRole(msgspec.Struct):
    """Defines role and configuration for an exchange in arbitrage strategy."""
    exchange_enum: ExchangeEnum
    role: str  # e.g., 'primary_spot', 'hedge_futures', 'arbitrage_target'
    side: Optional[Side] = None  # For strategies with fixed sides per exchange
    max_position_size: Optional[float] = None
    priority: int = 0  # Execution priority (0 = highest)


ArbitrageExchangeType = Literal['spot', 'futures']

class ExchangeStatus(Enum):
    """Exchange connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECOVERING = "recovering"


class OrderPlacementParams(Struct, frozen=True):
    """Type-safe order placement parameters following struct-first policy."""
    side: Side
    quantity: float
    price: float
    order_type: str = 'market'  # 'market' or 'limit'

    def __str__(self):
        return f"[{self.side.name} {self.quantity} @ {self.price} {self.order_type}]"
    
    def validate(self) -> bool:
        """Validate order parameters for HFT compliance."""
        return (
            self.quantity > 0.0 and 
            self.price > 0.0 and
            self.order_type in ['market', 'limit']
        )


class ExchangeBalanceSummary(Struct, frozen=True):
    """Balance summary for a single exchange with AssetBalance structs."""
    role_key: ArbitrageExchangeType
    balances: Dict[str, AssetBalance]  # asset_name -> AssetBalance


class BalanceSummaryResponse(Struct, frozen=True):
    """Complete balance summary across all exchanges following struct-first policy."""
    exchanges: Dict[str, ExchangeBalanceSummary]
    total_exchanges: int
    timestamp: float


class ExchangeMetrics(Struct):
    """Performance metrics for an exchange (msgspec optimized)."""
    connection_time: float = 0.0
    last_price_update: float = 0.0
    price_update_count: int = 0
    order_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    status: ExchangeStatus = ExchangeStatus.DISCONNECTED

#
# class ExchangeEventBus:
#     """Event bus for coordinating events across multiple exchanges."""
#
#     def __init__(self, logger: HFTLoggerInterface):
#         self.logger = logger
#         self._handlers: Dict[str, List[Callable]] = {
#             'book_ticker': [],
#             'order': [],
#             'balance': [],
#             'position': [],
#             'exchange_status': []
#         }
#
#     def subscribe(self, event_type: str, handler: Callable):
#         """Subscribe to events of specific type."""
#         if event_type in self._handlers:
#             self._handlers[event_type].append(handler)
#
#     def unsubscribe(self, event_type: str, handler: Callable):
#         """Unsubscribe from events."""
#         if event_type in self._handlers and handler in self._handlers[event_type]:
#             self._handlers[event_type].remove(handler)
#
#     async def emit(self, event_type: str, data: Any, exchange_key: str = ""):
#         """Emit event to all subscribers."""
#         handlers = self._handlers.get(event_type, [])
#         if handlers:
#             # Execute handlers in parallel for HFT performance
#             tasks = []
#             for handler in handlers:
#                 try:
#                     tasks.append(handler(data, exchange_key))
#                 except Exception as e:
#                     self.logger.error(f"Event handler error: {e}")
#
#             if tasks:
#                 await asyncio.gather(*tasks, return_exceptions=True)


class ExchangeManager:
    """
    Centralized manager for multiple DualExchange instances in arbitrage strategies.
    
    Provides:
    - Lifecycle management for N exchanges
    - Real-time event orchestration
    - Performance monitoring and health checks
    - Automatic error recovery
    - HFT-optimized parallel operations
    """
    
    def __init__(self,
                 symbol: Symbol,
                 exchange_roles: Dict[ArbitrageExchangeType, ExchangeRole],
                 logger: HFTLoggerInterface):
        """Initialize exchange manager.
        
        Args:
            symbol: Trading symbol to manage across exchanges
            exchange_roles: Mapping of role keys to exchange configurations
            logger: HFT logger instance
        """
        self.symbol = symbol
        self.exchange_roles = exchange_roles
        self.logger = logger
        
        # Exchange instances and tracking
        self._exchanges: Dict[ArbitrageExchangeType, DualExchange] = {}
        # self._metrics: Dict[ArbitrageExchangeType, ExchangeMetrics] = {}
        # self._status: Dict[ArbitrageExchangeType, ExchangeStatus] = {}
        
        # Event management
        # self.event_bus = ExchangeEventBus(logger)
        
        # Market data (fresh, no caching per HFT policy)
        # self._book_tickers: Dict[ArbitrageExchangeType, BookTicker] = {}
        # self._active_orders: Dict[ArbitrageExchangeType, List[Order]] = {}
        
        # Balance tracking and monitoring
        # self._current_balances: Dict[ArbitrageExchangeType, List[AssetBalance]] = {}
        # self._balance_alerts_enabled: bool = True
        # self._min_balance_thresholds: Dict[ArbitrageExchangeType, float] = {}  # Per-asset minimum thresholds
        
        # Performance tracking
        self._initialization_time: Optional[float] = None
        # self._last_health_check: float = 0.0
        # self._health_check_interval: float = 10.0  # 10 seconds
    
    async def initialize(self) -> bool:
        """Initialize all exchanges with parallel connection establishment.
        
        Returns:
            bool: True if all exchanges initialized successfully
        """
        start_time = time.time()
        self.logger.info(f"Initializing {len(self.exchange_roles)} exchanges for {self.symbol}")
        
        try:
            # Create DualExchange instances
            for role_key, role_config in self.exchange_roles.items():
                config = get_exchange_config(role_config.exchange_enum.value)
                self._exchanges[role_key] = DualExchange.get_instance(config, self.logger)
                # self._metrics[role_key] = ExchangeMetrics()
                # self._status[role_key] = ExchangeStatus.CONNECTING
            
            # Initialize all exchanges in parallel for HFT performance
            init_tasks = []
            for role_key, exchange in self._exchanges.items():
                init_tasks.append(self._initialize_exchange(role_key, exchange))
            
            results = await asyncio.gather(*init_tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for result in results if result is True)
            total_count = len(results)
            
            self._initialization_time = time.time() - start_time
            
            if success_count == total_count:
                self.logger.info(f"✅ All {total_count} exchanges initialized in {self._initialization_time*1000:.1f}ms")
                # await self._bind_event_handlers()
                return True
            else:
                failed_count = total_count - success_count
                self.logger.error(f"❌ {failed_count}/{total_count} exchanges failed to initialize")
                return False
                
        except Exception as e:
            self.logger.error(f"Exchange manager initialization failed: {e}")
            return False
    
    async def _initialize_exchange(self, role_key: ArbitrageExchangeType, exchange: DualExchange) -> bool:
        """Initialize a single exchange with error handling."""
        try:
            init_start = time.time()
            
            await exchange.initialize(
                symbols=[self.symbol],
                public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                private_channels=[
                    PrivateWebsocketChannelType.ORDER,
                    PrivateWebsocketChannelType.BALANCE
                    # Note: POSITION channel removed - not supported by MEXC, use order fills for position tracking
                ]
            )
            
            # self._metrics[role_key].connection_time = time.time() - init_start
            # self._status[role_key] = ExchangeStatus.CONNECTED
            
            self.logger.debug(f"✅ Exchange {role_key} initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize exchange {role_key}: {e}")
            # self._status[role_key] = ExchangeStatus.ERROR
            # self._metrics[role_key].error_count += 1
            return False
    
    # async def _bind_event_handlers(self):
    #     """Bind WebSocket event handlers for all exchanges."""
    #     binding_tasks = []
    #
    #     for role_key, exchange in self._exchanges.items():
    #         binding_tasks.append(
    #             exchange.bind_handlers(
    #                 on_book_ticker=self._create_book_ticker_handler(role_key),
    #                 on_order=self._create_order_handler(role_key),
    #                 on_balance=self._create_balance_handler(role_key),
    #                 on_position=self._create_position_handler(role_key)
    #             )
    #         )
    #
    #     await asyncio.gather(*binding_tasks)
    #     self.logger.info(f"✅ Event handlers bound for {len(self._exchanges)} exchanges")
    #
    # def _create_book_ticker_handler(self, role_key: ArbitrageExchangeType):
    #     """Create book ticker handler for specific exchange."""
    #     async def handle_book_ticker(book_ticker: BookTicker):
    #         if book_ticker.symbol == self.symbol:
    #             # Update metrics
    #             self._metrics[role_key].last_price_update = time.time()
    #             self._metrics[role_key].price_update_count += 1
    #
    #             # Store fresh data (no caching per HFT policy)
    #             self._book_tickers[role_key] = book_ticker
    #
    #             # Emit to event bus for strategy handlers
    #             await self.event_bus.emit('book_ticker', book_ticker, role_key)
    #
    #     return handle_book_ticker
    #
    # def _create_order_handler(self, role_key: ArbitrageExchangeType):
    #     """Create order handler for specific exchange."""
    #     async def handle_order(order: Order):
    #         if order.symbol == self.symbol:
    #             # Update metrics
    #             self._metrics[role_key].order_count += 1
    #
    #             # Track active orders
    #             if role_key not in self._active_orders:
    #                 self._active_orders[role_key] = []
    #
    #             # Update or add order
    #             existing_orders = self._active_orders[role_key]
    #             for i, existing_order in enumerate(existing_orders):
    #                 if existing_order.order_id == order.order_id:
    #                     existing_orders[i] = order
    #                     break
    #             else:
    #                 existing_orders.append(order)
    #
    #             # Emit to event bus
    #             await self.event_bus.emit('order', order, role_key)
    #
    #     return handle_order
    #
    # def _create_balance_handler(self, role_key: ArbitrageExchangeType):
    #     """Create balance handler with monitoring and alerts."""
    #     async def handle_balance(balance: AssetBalance):
    #         # Update balance cache for validation purposes
    #         if role_key not in self._current_balances:
    #             self._current_balances[role_key] = []
    #
    #         # Update or add balance
    #         balances = self._current_balances[role_key]
    #         for i, existing_balance in enumerate(balances):
    #             if existing_balance.asset == balance.asset:
    #                 balances[i] = balance
    #                 break
    #         else:
    #             balances.append(balance)
    #
    #         # Check for low balance alerts
    #         if self._balance_alerts_enabled:
    #             await self._check_balance_alerts(role_key, balance)
    #
    #         # Emit to event bus for strategy handlers
    #         await self.event_bus.emit('balance', balance, role_key)
    #
    #     return handle_balance
    #
    # def _create_position_handler(self, role_key: ArbitrageExchangeType):
    #     """Create position handler for specific exchange."""
    #     async def handle_position(position: Position):
    #         if position.symbol == self.symbol:
    #             await self.event_bus.emit('position', position, role_key)
    #     return handle_position
    #
    # Public API methods
    #
    def get_exchange(self, role_key: ArbitrageExchangeType) -> Optional[DualExchange]:
        """Get DualExchange instance by role key."""
        return self._exchanges.get(role_key)

    def get_book_ticker(self, role_key: ArbitrageExchangeType, symbol: Symbol) -> Optional[BookTicker]:
        return self._exchanges[role_key].public.book_ticker.get(symbol)

    # def get_all_exchanges(self) -> Dict[str, DualExchange]:
    #     """Get all DualExchange instances."""
    #     return self._exchanges.copy()
    #
    # def get_book_ticker(self, role_key: ArbitrageExchangeType) -> Optional[BookTicker]:
    #     """Get current book ticker for exchange (fresh, not cached)."""
    #     return self._book_tickers.get(role_key)
    #
    # def get_all_book_tickers(self) -> Dict[str, BookTicker]:
    #     """Get all current book tickers."""
    #     return self._book_tickers.copy()
    #
    # def get_active_orders(self, role_key: ArbitrageExchangeType) -> List[Order]:
    #     """Get active orders for exchange."""
    #     return self._active_orders.get(role_key, []).copy()
    #
    # def get_exchange_metrics(self, role_key: ArbitrageExchangeType) -> Optional[ExchangeMetrics]:
    #     """Get performance metrics for exchange."""
    #     return self._metrics.get(role_key)
    #
    # def get_exchange_status(self, role_key: ArbitrageExchangeType) -> Optional[ExchangeStatus]:
    #     """Get connection status for exchange."""
    #     return self._status.get(role_key)
    #
    # def is_all_connected(self) -> bool:
    #     """Check if all exchanges are connected."""
    #     return all(status == ExchangeStatus.CONNECTED for status in self._status.values())
    #
    # def get_connected_count(self) -> int:
    #     """Get number of connected exchanges."""
    #     return sum(1 for status in self._status.values() if status == ExchangeStatus.CONNECTED)
    #
    # # Balance monitoring and alerts
    #
    # async def _check_balance_alerts(self, role_key: ArbitrageExchangeType, balance: AssetBalance):
    #     """Check for low balance conditions and emit alerts."""
    #     try:
    #         asset_name = str(balance.asset)
    #         if asset_name != 'USDT':
    #             return
    #
    #         threshold_key = f"{role_key}_{asset_name}"
    #
    #         # Get or set default threshold
    #         if threshold_key not in self._min_balance_thresholds:
    #             # Default threshold: 10% of a typical base position (configurable)
    #             default_threshold = 10.0  # This should be configurable per strategy
    #             self._min_balance_thresholds[threshold_key] = default_threshold
    #
    #         threshold = self._min_balance_thresholds[threshold_key]
    #         available_balance = float(balance.available)
    #
    #         # Check if balance is below threshold
    #         if available_balance < threshold:
    #             self.logger.warning(
    #                 f"⚠️ Low balance alert: {role_key} {asset_name} = {available_balance:.6f} "
    #                 f"(threshold: {threshold:.6f})"
    #             )
    #
    #             # Emit low balance alert event
    #             alert_data = {
    #                 'role_key': role_key,
    #                 'asset': asset_name,
    #                 'available_balance': available_balance,
    #                 'threshold': threshold,
    #                 'timestamp': time.time()
    #             }
    #             await self.event_bus.emit('low_balance_alert', alert_data)
    #
    #     except Exception as e:
    #         self.logger.error(f"Balance alert check failed: {e}")
    #
    # def set_balance_threshold(self, role_key: ArbitrageExchangeType, asset: str, threshold: float):
    #     """Set minimum balance threshold for alerts."""
    #     threshold_key = f"{role_key}_{asset}"
    #     self._min_balance_thresholds[threshold_key] = threshold
    #     self.logger.info(f"📊 Balance threshold set: {threshold_key} = {threshold:.6f}")
    #
    # def get_current_balances(self, role_key: ArbitrageExchangeType) -> List[AssetBalance]:
    #     """Get current cached balances for an exchange."""
    #     return self._current_balances.get(role_key, []).copy()
    #
    # def get_asset_balance(self, role_key: ArbitrageExchangeType, asset: str) -> Optional[AssetBalance]:
    #     """Get current balance for a specific asset on an exchange."""
    #     balances = self._current_balances.get(role_key, [])
    #     return next((b for b in balances if str(b.asset) == asset), None)
    #
    # def enable_balance_alerts(self, enabled: bool = True):
    #     """Enable or disable balance alerts."""
    #     self._balance_alerts_enabled = enabled
    #     self.logger.info(f"📢 Balance alerts {'enabled' if enabled else 'disabled'}")
    #
    # def get_balance_summary(self) -> BalanceSummaryResponse:
    #     """Get structured summary of all current balances across exchanges."""
    #     exchange_summaries = {}
    #
    #     for role_key, balances in self._current_balances.items():
    #         # Convert list of balances to dict keyed by asset name
    #         balance_dict = {}
    #         for balance in balances:
    #             asset_name = str(balance.asset)
    #             balance_dict[asset_name] = balance
    #
    #         exchange_summaries[role_key] = ExchangeBalanceSummary(
    #             role_key=role_key,
    #             balances=balance_dict
    #         )
    #
    #     return BalanceSummaryResponse(
    #         exchanges=exchange_summaries,
    #         total_exchanges=len(self._exchanges),
    #         timestamp=time.time()
    #     )
    #
    # # Trading operations
    
    async def place_order_parallel(self, orders: Dict[ArbitrageExchangeType, OrderPlacementParams]) -> Dict[ArbitrageExchangeType, Optional[Order]]:
        """Place orders on multiple exchanges in parallel with type-safe parameters.
        
        Args:
            orders: Dict mapping role_key to OrderPlacementParams struct
                   {'role_key': OrderPlacementParams(side=Side.BUY, quantity=100.0, price=50.0)}
        
        Returns:
            Dict mapping role_key to placed Order (or None if failed)
        """
        order_tasks = []
        role_keys = []
        
        for role_key, order_params in orders.items():
            if role_key in self._exchanges:
                # Validate parameters using struct validation
                if not order_params.validate():
                    self.logger.error(f"Invalid order parameters for {role_key}: {order_params}")
                    continue
                    
                exchange = self._exchanges[role_key]
                
                # Choose order type based on parameters
                if order_params.order_type == 'limit':
                    task = exchange.private.place_limit_order(
                        symbol=self.symbol,
                        side=order_params.side,
                        quantity=order_params.quantity,
                        price=order_params.price
                    )
                else:  # market order
                    task = exchange.private.place_market_order(
                        symbol=self.symbol,
                        side=order_params.side,
                        price=order_params.price,
                        quantity=order_params.quantity,
                        # quote_quantity=order_params.quantity*order_params.price,
                        ensure=True
                    )

                order_tasks.append(task)
                role_keys.append(role_key)
        
        results = await asyncio.gather(*order_tasks, return_exceptions=True)
        
        # Map results back to role keys
        placed_orders = {}
        for i, result in enumerate(results):
            role_key = role_keys[i]
            if isinstance(result, Order):
                placed_orders[role_key] = result
                self.logger.info(f"✅ Order placed on {role_key}: {result.order_id} {result}")
            else:
                placed_orders[role_key] = None
                self.logger.error(f"❌ Order failed on {role_key}: {result}")
        
        return placed_orders
    
    async def cancel_all_orders(self) -> Dict[ArbitrageExchangeType, int]:
        """Cancel all active orders across all exchanges.
        
        Returns:
            Dict mapping role_key to number of orders cancelled
        """
        cancel_tasks = []
        role_keys = []
        
        for role_key, exchange in self._exchanges.items():
            task = self._cancel_exchange_orders(role_key, exchange)
            cancel_tasks.append(task)
            role_keys.append(role_key)
        
        results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
        
        cancelled_counts = {}
        for i, result in enumerate(results):
            role_key = role_keys[i]
            cancelled_counts[role_key] = result if isinstance(result, int) else 0
        
        total_cancelled = sum(cancelled_counts.values())
        self.logger.info(f"🛑 Cancelled {total_cancelled} orders across {len(cancelled_counts)} exchanges")
        
        return cancelled_counts
    
    async def _cancel_exchange_orders(self, role_key: ArbitrageExchangeType, exchange: DualExchange) -> int:
        """Cancel all orders for a specific exchange."""
        try:
            # TODO: implement cancel_all_orders
            orders = await exchange.private._orders[self.symbol]
            cancel_tasks = []
            
            for order in orders:
                cancel_tasks.append(
                    exchange.private.cancel_order(self.symbol, order.order_id)
                )
            
            if cancel_tasks:
                await asyncio.gather(*cancel_tasks, return_exceptions=True)

            for order in orders:
                self.logger.info(f"🛑 Cancelled order on {role_key}: {order.order_id} {order}")
                # TODO: sync orders forced way from REST API, in inherited class
            return len(cancel_tasks)
            
        except Exception as e:
            self.logger.warning(f"Failed to cancel orders for {role_key}: {e}")
            return 0

    async def check_connection(self, force_refresh=True):
        if self._exchanges['spot'].is_connected and self._exchanges['futures'].is_connected:
            return True

        if force_refresh:
            await asyncio.sleep(0.25)
            await asyncio.gather(
                self._exchanges['spot'].force_refresh(),
                self._exchanges['futures'].force_refresh()
            )

    
    # Health monitoring
    #
    # async def health_check(self) -> Dict[str, Any]:
    #     """Perform health check on all exchanges."""
    #     current_time = time.time()
    #
    #     if (current_time - self._last_health_check) < self._health_check_interval:
    #         return self._get_cached_health_status()
    #
    #     self._last_health_check = current_time
    #
    #     health_status = {
    #         'overall_status': 'healthy',
    #         'connected_exchanges': self.get_connected_count(),
    #         'total_exchanges': len(self._exchanges),
    #         'exchanges': {}
    #     }
    #
    #     for role_key, metrics in self._metrics.items():
    #         status = self._status.get(role_key, ExchangeStatus.DISCONNECTED)
    #
    #         # Check if price updates are recent (within last 5 seconds)
    #         price_freshness = current_time - metrics.last_price_update if metrics.last_price_update > 0 else float('inf')
    #
    #         exchange_health = {
    #             'status': status.value,
    #             'connection_time_ms': metrics.connection_time * 1000,
    #             'price_updates': metrics.price_update_count,
    #             'price_freshness_seconds': price_freshness,
    #             'orders_processed': metrics.order_count,
    #             'error_count': metrics.error_count,
    #             'avg_latency_ms': metrics.avg_latency_ms
    #         }
    #
    #         # Determine if exchange is healthy
    #         if status != ExchangeStatus.CONNECTED or price_freshness > 30:
    #             exchange_health['healthy'] = False
    #             health_status['overall_status'] = 'degraded'
    #         else:
    #             exchange_health['healthy'] = True
    #
    #         health_status['exchanges'][role_key] = exchange_health
    #
    #     return health_status
    #
    # def _get_cached_health_status(self) -> Dict[str, Any]:
    #     """Get basic health status without full check."""
    #     return {
    #         'overall_status': 'healthy' if self.is_all_connected() else 'degraded',
    #         'connected_exchanges': self.get_connected_count(),
    #         'total_exchanges': len(self._exchanges),
    #         'last_check': self._last_health_check
    #     }
    #
    # Cleanup
    
    async def shutdown(self):
        """Shutdown all exchanges and cleanup resources."""
        self.logger.info(f"Shutting down exchange manager for {self.symbol}")
        
        # Cancel all orders first
        await self.cancel_all_orders()
        
        # Close all exchange connections
        close_tasks = []
        for role_key, exchange in self._exchanges.items():
            close_tasks.append(exchange.close())
            self._status[role_key] = ExchangeStatus.DISCONNECTED
        
        await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # Clear data
        self._book_tickers.clear()
        self._active_orders.clear()
        
        self.logger.info("✅ Exchange manager shutdown completed")
    
    # def get_performance_summary(self) -> Dict[str, Any]:
    #     """Get comprehensive performance summary."""
    #     total_price_updates = sum(m.price_update_count for m in self._metrics.values())
    #     total_orders = sum(m.order_count for m in self._metrics.values())
    #     total_errors = sum(m.error_count for m in self._metrics.values())
    #
    #     return {
    #         'initialization_time_ms': (self._initialization_time or 0) * 1000,
    #         'total_exchanges': len(self._exchanges),
    #         'connected_exchanges': self.get_connected_count(),
    #         'total_price_updates': total_price_updates,
    #         'total_orders_processed': total_orders,
    #         'total_errors': total_errors,
    #         'uptime_seconds': time.time() - (self._initialization_time or time.time()) if self._initialization_time else 0,
    #         'exchanges': {
    #             role_key: {
    #                 'connection_time_ms': metrics.connection_time * 1000,
    #                 'price_updates': metrics.price_update_count,
    #                 'orders': metrics.order_count,
    #                 'errors': metrics.error_count,
    #                 'status': self._status.get(role_key, ExchangeStatus.DISCONNECTED).value
    #             }
    #             for role_key, metrics in self._metrics.items()
    #         }
    #     }


