"""Order Processing Mixin for Trading Tasks.

Provides abstract methods and common patterns for processing order execution results.
Breaking down complex order processing into focused, testable methods.
"""
from abc import ABC, abstractmethod
from typing import Optional

from exchanges.structs import Order
from exchanges.structs.common import Side
from utils.exchange_utils import is_order_done


class OrderProcessingMixin(ABC):
    """Mixin for order execution processing.
    
    This mixin defines a common pattern for processing order execution results
    across different trading tasks. It breaks down complex processing into
    focused methods that follow single responsibility principle.
    
    The main coordination method `process_order_execution_base` orchestrates
    the processing flow, while abstract methods allow tasks to implement
    their specific logic.
    """
    
    async def process_order_execution_base(self, order: Order, exchange_side: Optional[Side] = None):
        """Main coordinator for order execution processing.
        
        This method provides the common flow for processing order execution:
        1. Check if order is completed (filled/cancelled)
        2. If completed: handle the completion and clear order state
        3. If active: update the active order state
        
        Args:
            order: Order to process
            exchange_side: Side of the exchange (for dual exchange tasks)
        """
        if is_order_done(order):
            await self._handle_completed_order(order, exchange_side)
            self._clear_order_state(exchange_side)
        else:
            self._update_active_order_state(order, exchange_side)
    
    @abstractmethod
    async def _handle_completed_order(self, order: Order, exchange_side: Optional[Side] = None):
        """Handle completed order fills and updates.
        
        This method should:
        - Update filled quantities and average prices
        - Log completion information
        - Update context with final order state
        
        Args:
            order: Completed order to handle
            exchange_side: Side of the exchange (for dual exchange tasks)
        """
        pass
    
    @abstractmethod
    def _clear_order_state(self, exchange_side: Optional[Side] = None):
        """Clear order state after completion.
        
        This method should:
        - Clear current order references
        - Update context to remove order_id
        - Clean up any order-specific state
        
        Args:
            exchange_side: Side of the exchange (for dual exchange tasks)
        """
        pass
    
    @abstractmethod
    def _update_active_order_state(self, order: Order, exchange_side: Optional[Side] = None):
        """Update state for active (unfilled) orders.
        
        This method should:
        - Update current order reference
        - Sync order_id in context
        - Track any partial fills
        
        Args:
            order: Active order to track
            exchange_side: Side of the exchange (for dual exchange tasks)
        """
        pass
    
    def _should_process_order_fills(self, order: Order) -> bool:
        """Check if order has fills to process.
        
        Args:
            order: Order to check
            
        Returns:
            True if order has quantity filled, False otherwise
        """
        return order.filled_quantity > 0
    
    def _log_order_completion(self, order: Order, tag: str = "", **extra_fields):
        """Log order completion with consistent format.
        
        Args:
            order: Completed order
            tag: Additional tag for logging
            **extra_fields: Additional fields to log
        """
        # This method assumes the inheriting class has 'logger' and '_tag' attributes
        if hasattr(self, 'logger') and hasattr(self, '_tag'):
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.info(f"✅ Order completed {tag_str}",
                           order_id=order.order_id,
                           side=order.side.name,
                           filled_quantity=order.filled_quantity,
                           price=order.price,
                           **extra_fields)