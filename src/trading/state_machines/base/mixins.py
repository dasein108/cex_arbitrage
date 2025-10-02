"""
Common mixins for state machine trading strategies.

Provides reusable functionality that can be mixed into specific strategy
implementations for common operations like order management, market data
handling, and performance monitoring.
"""

import asyncio
import time
from typing import Optional, Dict, Any, TYPE_CHECKING

# Direct imports of real interfaces
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.composite.base_public_composite import BasePublicComposite
from exchanges.structs.common import Symbol, Order, BookTicker
from exchanges.structs.enums import Side
from exchanges.utils.exchange_utils import is_order_filled


class StateTransitionMixin:
    """Mixin for safe state transitions with validation and logging."""
    
    def _validate_transition(self, from_state, to_state) -> bool:
        """Validate if a state transition is allowed."""
        # Override in specific strategies for custom validation
        return True
    
    def _transition_with_validation(self, new_state) -> None:
        """Transition to new state with validation."""
        if hasattr(self, 'context') and hasattr(self.context, 'current_state'):
            if self._validate_transition(self.context.current_state, new_state):
                self._transition_to_state(new_state)
            else:
                raise ValueError(f"Invalid transition from {self.context.current_state} to {new_state}")


class OrderManagementMixin:
    """Mixin for common order management operations."""
    
    async def _place_market_buy(
        self, 
        private_exchange: BasePrivateComposite,
        symbol: Symbol, 
        quote_quantity: float
    ) -> Order:
        """Place a market buy order with error handling."""
        try:
            order = await private_exchange.place_market_order(
                symbol=symbol,
                side=Side.BUY,
                quote_quantity=quote_quantity,
                ensure=True
            )
            return order
        except Exception as e:
            if hasattr(self, '_handle_error'):
                self._handle_error(e)
            raise
    
    async def _place_limit_sell(
        self,
        private_exchange: BasePrivateComposite,
        symbol: Symbol,
        quantity: float,
        price: float
    ) -> Order:
        """Place a limit sell order with error handling."""
        try:
            order = await private_exchange.place_limit_order(
                symbol=symbol,
                side=Side.SELL,
                quantity=quantity,
                price=price
            )
            return order
        except Exception as e:
            if hasattr(self, '_handle_error'):
                self._handle_error(e)
            raise
    
    async def _cancel_order_safe(
        self,
        private_exchange: BasePrivateComposite,
        order: Order
    ) -> Order:
        """Safely cancel an order with fill detection."""
        try:
            cancelled_order = await private_exchange.cancel_order(
                order.symbol,
                order.order_id
            )
            return cancelled_order
        except Exception as e:
            # Check if order was filled during cancellation attempt
            try:
                order_status = await private_exchange.get_order(order.symbol, order.order_id)
                if is_order_filled(order_status):
                    return order_status
            except:
                pass
            
            if hasattr(self, '_handle_error'):
                self._handle_error(e)
            raise
    
    async def _wait_for_order_fill(
        self,
        private_exchange: BasePrivateComposite,
        order: Order,
        timeout_seconds: float = 30.0,
        check_interval: float = 0.1
    ) -> Optional[Order]:
        """Wait for order to fill with timeout."""
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            try:
                order_status = await private_exchange.get_order(order.symbol, order.order_id)
                if is_order_filled(order_status):
                    return order_status
                await asyncio.sleep(check_interval)
            except Exception as e:
                if hasattr(self, 'context') and hasattr(self.context, 'logger'):
                    self.context.logger.warning(f"Error checking order status: {e}")
                await asyncio.sleep(check_interval)
        
        return None  # Timeout


class MarketDataMixin:
    """Mixin for market data operations."""
    
    async def _get_current_price(
        self,
        public_exchange: BasePublicComposite,
        symbol: Symbol
    ) -> BookTicker:
        """Get current market price with error handling."""
        try:
            book_ticker = await public_exchange.get_book_ticker(symbol)
            return book_ticker
        except Exception as e:
            if hasattr(self, '_handle_error'):
                self._handle_error(e)
            raise
    
    async def _get_spread_info(
        self,
        public_exchange: BasePublicComposite,
        symbol: Symbol
    ) -> Dict[str, float]:
        """Get spread information for a symbol."""
        try:
            book_ticker = await public_exchange.get_book_ticker(symbol)
            spread = book_ticker.ask_price - book_ticker.bid_price
            spread_percent = (spread / book_ticker.bid_price) * 100
            
            return {
                'bid_price': book_ticker.bid_price,
                'ask_price': book_ticker.ask_price,
                'spread_absolute': spread,
                'spread_percent': spread_percent,
                'mid_price': (book_ticker.bid_price + book_ticker.ask_price) / 2
            }
        except Exception as e:
            if hasattr(self, '_handle_error'):
                self._handle_error(e)
            raise


class PerformanceMonitoringMixin:
    """Mixin for performance tracking and metrics."""
    
    def _start_performance_timer(self) -> float:
        """Start a performance timer."""
        return time.time()
    
    def _end_performance_timer(self, start_time: float) -> float:
        """End performance timer and return duration in milliseconds."""
        return (time.time() - start_time) * 1000
    
    def _calculate_profit(self, buy_order: Order, sell_order: Order) -> float:
        """Calculate profit from buy/sell order pair."""
        if not (is_order_filled(buy_order) and is_order_filled(sell_order)):
            return 0.0
        
        # Calculate total cost (including fees)
        buy_cost = buy_order.filled_quantity * buy_order.average_price
        if buy_order.fee:
            buy_cost += buy_order.fee
        
        # Calculate total proceeds (minus fees)
        sell_proceeds = sell_order.filled_quantity * sell_order.average_price
        if sell_order.fee:
            sell_proceeds -= sell_order.fee
        
        return sell_proceeds - buy_cost
    
    def _update_performance_metrics(self, profit: float) -> None:
        """Update context performance metrics."""
        if hasattr(self, 'context'):
            self.context.total_profit_usdt += profit
            self.context.execution_count += 1


class RiskManagementMixin:
    """Mixin for risk management operations."""
    
    def _validate_order_size(
        self,
        symbol: Symbol,
        quantity: float,
        max_position_usdt: float = 1000.0
    ) -> bool:
        """Validate order size against risk limits."""
        # Basic size validation - can be enhanced with symbol-specific rules
        return quantity > 0 and (quantity * 100) <= max_position_usdt  # Assuming ~$100 per unit
    
    def _validate_price_reasonable(
        self,
        current_price: float,
        order_price: float,
        max_deviation_percent: float = 5.0
    ) -> bool:
        """Validate that order price is reasonable compared to current market."""
        deviation = abs(order_price - current_price) / current_price * 100
        return deviation <= max_deviation_percent
    
    def _check_maximum_exposure(
        self,
        current_positions_usdt: float,
        new_position_usdt: float,
        max_total_exposure_usdt: float = 5000.0
    ) -> bool:
        """Check if new position would exceed maximum exposure limits."""
        total_exposure = current_positions_usdt + new_position_usdt
        return total_exposure <= max_total_exposure_usdt
    
    def _emergency_exit_required(
        self,
        current_loss_usdt: float,
        max_loss_usdt: float = 100.0
    ) -> bool:
        """Determine if emergency exit is required due to losses."""
        return current_loss_usdt >= max_loss_usdt