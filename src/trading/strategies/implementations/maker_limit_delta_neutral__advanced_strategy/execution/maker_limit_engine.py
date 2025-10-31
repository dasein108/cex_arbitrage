"""
Market Making Engine with Limit Order Management

Core market making engine that manages limit order placement, updates, and fill detection.
Optimized for HFT performance with sub-50ms order operations and efficient fill monitoring.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from enum import Enum

from exchanges.structs import BookTicker, Side, Order, OrderStatus, OrderType, TimeInForce
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.config.maker_limit_config import MakerLimitConfig
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.dynamic_offset_calculator import OffsetResult
from infrastructure.logging import HFTLoggerInterface


class OrderUpdateAction(Enum):
    """Order update action types"""
    NO_UPDATE = "NO_UPDATE"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_UPDATED = "ORDER_UPDATED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_FAILED = "ORDER_FAILED"


@dataclass
class OrderPlacementParams:
    """Parameters for placing an order"""
    symbol: str
    side: Side
    quantity: float
    price: float
    order_type: OrderType = OrderType.LIMIT
    time_in_force: TimeInForce = TimeInForce.GTC


@dataclass
class SideUpdateResult:
    """Result of updating orders for one side"""
    action: OrderUpdateAction
    order: Optional[Order] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    price_deviation: float = 0.0


@dataclass
class MakerUpdateResult:
    """Result of updating maker orders"""
    action: str
    timestamp: float
    side_results: Dict[str, SideUpdateResult]
    total_execution_time_ms: float = 0.0


@dataclass
class OrderFillEvent:
    """Order fill event for hedge execution"""
    side: Side
    order: Order
    fill_price: float
    fill_quantity: float
    timestamp: float
    partial_fill: bool = False
    remaining_quantity: float = 0.0


class MakerLimitEngine:
    """Core market making engine with limit order management"""
    
    def __init__(self, spot_exchange: BasePrivateComposite, 
                 config: MakerLimitConfig, logger: HFTLoggerInterface):
        self.spot_exchange = spot_exchange
        self.config = config
        self.logger = logger
        
        # Order tracking
        self.active_orders: Dict[Side, Order] = {}
        self.pending_orders: Set[str] = set()  # Orders being placed/cancelled
        self.last_book_update = 0
        self.last_order_check = 0
        
        # Performance tracking
        self.order_operations_count = 0
        self.fill_events_count = 0
        self.average_execution_time = 0.0
        
        # Order management state
        self.order_update_threshold = config.order_update_threshold
        self.max_pending_time = 5.0  # Max time to wait for order confirmation
        
        # Fill tracking for performance
        self.recent_fills: List[OrderFillEvent] = []
        self.fill_check_interval = 0.1  # Check fills every 100ms
        
    async def update_limit_orders(self, current_book: BookTicker, 
                                offset_results: Dict[Side, OffsetResult],
                                should_trade: bool) -> MakerUpdateResult:
        """Update limit orders based on current market conditions"""
        
        update_start_time = time.time()
        
        if not should_trade:
            # Cancel all orders if trading is halted
            cancel_result = await self._cancel_all_orders()
            return MakerUpdateResult(
                action="ORDERS_CANCELLED",
                timestamp=update_start_time,
                side_results={'cancel_all': cancel_result},
                total_execution_time_ms=(time.time() - update_start_time) * 1000
            )
        
        # Update orders for both sides
        side_results = {}
        
        for side in [Side.BUY, Side.SELL]:
            if side in offset_results:
                result = await self._update_side_order(
                    side, current_book, offset_results[side]
                )
                side_results[side.name] = result
        
        total_time = (time.time() - update_start_time) * 1000
        
        # Log performance warning if slow
        if total_time > self.config.max_loop_time_ms:
            self.logger.warning(f"Slow order update: {total_time:.2f}ms")
        
        return MakerUpdateResult(
            action="ORDERS_UPDATED",
            timestamp=update_start_time,
            side_results=side_results,
            total_execution_time_ms=total_time
        )
    
    async def _update_side_order(self, side: Side, current_book: BookTicker, 
                               offset_result: OffsetResult) -> SideUpdateResult:
        """Update order for specific side with HFT optimization"""
        
        operation_start_time = time.time()
        
        try:
            existing_order = self.active_orders.get(side)
            target_price = offset_result.target_price
            
            # Check if update is needed
            if existing_order and not self._needs_order_update(existing_order, target_price):
                return SideUpdateResult(
                    action=OrderUpdateAction.NO_UPDATE,
                    execution_time_ms=(time.time() - operation_start_time) * 1000,
                    price_deviation=0.0
                )
            
            # Cancel existing order if present
            if existing_order:
                await self._cancel_order_fast(existing_order.order_id)
                if side in self.active_orders:
                    del self.active_orders[side]
            
            # Calculate order quantity
            order_quantity = self._calculate_order_quantity(target_price)
            
            # Place new order
            order_params = OrderPlacementParams(
                symbol=str(self.config.symbol),
                side=side,
                quantity=order_quantity,
                price=target_price,
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC
            )
            
            new_order = await self._place_order_fast(order_params)
            
            if new_order:
                self.active_orders[side] = new_order
                execution_time = (time.time() - operation_start_time) * 1000
                
                self.logger.info(f"Placed {side.name} limit order", extra={
                    'price': target_price,
                    'quantity': order_quantity,
                    'offset_ticks': offset_result.offset_ticks,
                    'order_id': new_order.order_id,
                    'execution_time_ms': execution_time,
                    'safety_score': offset_result.safety_score
                })
                
                return SideUpdateResult(
                    action=OrderUpdateAction.ORDER_PLACED,
                    order=new_order,
                    execution_time_ms=execution_time
                )
            else:
                raise Exception("Order placement returned None")
                
        except Exception as e:
            execution_time = (time.time() - operation_start_time) * 1000
            error_msg = f"Failed to update {side.name} order: {e}"
            
            self.logger.error(error_msg, extra={
                'side': side.name,
                'target_price': target_price,
                'execution_time_ms': execution_time
            })
            
            return SideUpdateResult(
                action=OrderUpdateAction.ORDER_FAILED,
                error=error_msg,
                execution_time_ms=execution_time
            )
    
    async def check_order_fills(self) -> List[OrderFillEvent]:
        """Check for order fills with efficient polling"""
        
        current_time = time.time()
        
        # Rate limit fill checks
        if current_time - self.last_order_check < self.fill_check_interval:
            return []
        
        self.last_order_check = current_time
        fill_events = []
        
        # Check each active order
        for side, order in list(self.active_orders.items()):
            try:
                updated_order = await self.spot_exchange.get_order_status(order.order_id)
                
                if updated_order.status == OrderStatus.FILLED:
                    fill_event = OrderFillEvent(
                        side=side,
                        order=updated_order,
                        fill_price=updated_order.average_price or updated_order.price,
                        fill_quantity=updated_order.filled_quantity,
                        timestamp=current_time,
                        partial_fill=False
                    )
                    fill_events.append(fill_event)
                    
                    # Remove filled order from tracking
                    del self.active_orders[side]
                    self.fill_events_count += 1
                    
                    self.logger.info(f"Order filled: {side.name}", extra={
                        'fill_price': updated_order.average_price or updated_order.price,
                        'fill_quantity': updated_order.filled_quantity,
                        'order_id': updated_order.order_id,
                        'total_fills': self.fill_events_count
                    })
                    
                elif updated_order.status == OrderStatus.PARTIALLY_FILLED:
                    # Handle partial fills
                    if updated_order.filled_quantity > order.filled_quantity:
                        fill_quantity = updated_order.filled_quantity - order.filled_quantity
                        fill_event = OrderFillEvent(
                            side=side,
                            order=updated_order,
                            fill_price=updated_order.average_price or updated_order.price,
                            fill_quantity=fill_quantity,
                            timestamp=current_time,
                            partial_fill=True,
                            remaining_quantity=updated_order.quantity - updated_order.filled_quantity
                        )
                        fill_events.append(fill_event)
                        
                        # Update tracked order
                        self.active_orders[side] = updated_order
                        self.fill_events_count += 1
                        
                        self.logger.info(f"Partial fill: {side.name}", extra={
                            'fill_price': updated_order.average_price or updated_order.price,
                            'fill_quantity': fill_quantity,
                            'remaining_quantity': updated_order.quantity - updated_order.filled_quantity,
                            'order_id': updated_order.order_id
                        })
                
                elif updated_order.status in [OrderStatus.CANCELLED, OrderStatus.REJECTED]:
                    # Remove cancelled/rejected orders
                    if side in self.active_orders:
                        del self.active_orders[side]
                    
                    self.logger.warning(f"Order {updated_order.status.name}: {side.name}", extra={
                        'order_id': updated_order.order_id,
                        'status': updated_order.status.name
                    })
                    
            except Exception as e:
                self.logger.error(f"Error checking order status for {side.name}: {e}")
        
        # Track recent fills for performance analysis
        if fill_events:
            self.recent_fills.extend(fill_events)
            # Keep only last 100 fills
            if len(self.recent_fills) > 100:
                self.recent_fills = self.recent_fills[-100:]
        
        return fill_events
    
    def _needs_order_update(self, existing_order: Order, target_price: float) -> bool:
        """Check if order needs updating based on price deviation"""
        price_deviation = abs(existing_order.price - target_price) / target_price
        return price_deviation >= self.order_update_threshold
    
    def _calculate_order_quantity(self, price: float) -> float:
        """Calculate order quantity based on position size and price"""
        # Base quantity from USD position size
        base_quantity = self.config.position_size_usd / price
        
        # Round to reasonable precision (typically 6 decimal places)
        return round(base_quantity, 6)
    
    async def _place_order_fast(self, params: OrderPlacementParams) -> Optional[Order]:
        """Fast order placement with error handling"""
        try:
            self.order_operations_count += 1
            
            # Track pending order
            temp_order_id = f"pending_{int(time.time() * 1000)}"
            self.pending_orders.add(temp_order_id)
            
            # Place order
            order = await self.spot_exchange.place_order(
                symbol=params.symbol,
                side=params.side,
                order_type=params.order_type,
                quantity=params.quantity,
                price=params.price,
                time_in_force=params.time_in_force
            )
            
            # Remove from pending
            self.pending_orders.discard(temp_order_id)
            
            return order
            
        except Exception as e:
            self.pending_orders.discard(temp_order_id)
            raise e
    
    async def _cancel_order_fast(self, order_id: str):
        """Fast order cancellation"""
        try:
            await self.spot_exchange.cancel_order(order_id)
        except Exception as e:
            self.logger.warning(f"Order cancellation failed: {e}")
    
    async def _cancel_all_orders(self) -> SideUpdateResult:
        """Cancel all active orders quickly"""
        cancel_start_time = time.time()
        cancelled_count = 0
        
        try:
            # Cancel all active orders in parallel
            cancel_tasks = []
            for side, order in list(self.active_orders.items()):
                cancel_tasks.append(self._cancel_order_fast(order.order_id))
            
            if cancel_tasks:
                await asyncio.gather(*cancel_tasks, return_exceptions=True)
                cancelled_count = len(cancel_tasks)
            
            # Clear tracking
            self.active_orders.clear()
            
            execution_time = (time.time() - cancel_start_time) * 1000
            
            self.logger.info(f"Cancelled {cancelled_count} orders", extra={
                'execution_time_ms': execution_time
            })
            
            return SideUpdateResult(
                action=OrderUpdateAction.ORDER_CANCELLED,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution_time = (time.time() - cancel_start_time) * 1000
            
            self.logger.error(f"Error cancelling orders: {e}", extra={
                'execution_time_ms': execution_time
            })
            
            return SideUpdateResult(
                action=OrderUpdateAction.ORDER_FAILED,
                error=str(e),
                execution_time_ms=execution_time
            )
    
    def get_active_order_count(self) -> int:
        """Get number of active orders"""
        return len(self.active_orders)
    
    def get_active_orders_summary(self) -> Dict[str, any]:
        """Get summary of active orders"""
        summary = {}
        for side, order in self.active_orders.items():
            summary[side.name] = {
                'order_id': order.order_id,
                'price': order.price,
                'quantity': order.quantity,
                'filled_quantity': order.filled_quantity,
                'status': order.status.name if order.status else 'UNKNOWN'
            }
        return summary
    
    def get_performance_stats(self) -> Dict[str, any]:
        """Get engine performance statistics"""
        return {
            'order_operations_count': self.order_operations_count,
            'fill_events_count': self.fill_events_count,
            'active_orders': len(self.active_orders),
            'pending_orders': len(self.pending_orders),
            'recent_fills': len(self.recent_fills),
            'average_execution_time_ms': self.average_execution_time,
            'fill_check_interval': self.fill_check_interval
        }
    
    async def cleanup(self):
        """Cleanup function to cancel all orders on shutdown"""
        if self.active_orders:
            self.logger.info("Cleaning up: cancelling all active orders")
            await self._cancel_all_orders()