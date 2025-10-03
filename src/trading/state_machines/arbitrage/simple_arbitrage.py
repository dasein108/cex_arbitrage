"""
Simple arbitrage strategy state machine.

Implements cross-exchange arbitrage (hedging + swap) by buying on the exchange
with lower prices and selling on the exchange with higher prices to capture
price differences.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from exchanges.interfaces.composite import BasePrivateComposite, BasePublicComposite
from exchanges.structs import Symbol, Order, Side, SymbolInfo
from ..base import (
    BaseStrategyStateMachine,
    BaseStrategyContext,
    StrategyState,
    StateTransitionMixin,
    OrderManagementMixin,
    MarketDataMixin,
    PerformanceMonitoringMixin,
    RiskManagementMixin
)


class SimpleArbitrageState(Enum):
    """States specific to simple arbitrage strategy."""
    SCANNING_OPPORTUNITIES = "scanning_opportunities"
    OPPORTUNITY_DETECTED = "opportunity_detected"
    VALIDATING_OPPORTUNITY = "validating_opportunity"
    EXECUTING_BUY_SIDE = "executing_buy_side"
    EXECUTING_SELL_SIDE = "executing_sell_side"
    MONITORING_EXECUTION = "monitoring_execution"
    PROFIT_REALIZED = "profit_realized"


@dataclass
class SimpleArbitrageContext(BaseStrategyContext):
    """Context for simple arbitrage strategy."""
    
    # Exchange connections
    exchange_a_private: Optional[BasePrivateComposite] = None
    exchange_b_private: Optional[BasePrivateComposite] = None
    exchange_a_public: Optional[BasePublicComposite] = None
    exchange_b_public: Optional[BasePublicComposite] = None
    
    # Trading parameters
    position_size_usdt: float = 0.0
    min_profit_threshold: float = 0.005  # 0.5% minimum profit
    max_execution_time_ms: float = 5000.0  # 5 seconds max execution time
    slippage_tolerance: float = 0.002  # 0.2% slippage tolerance
    
    # Symbols (same symbol on different exchanges)
    symbol_a: Optional[Symbol] = None  # Symbol on exchange A
    symbol_b: Optional[Symbol] = None  # Symbol on exchange B
    symbol_a_info: Optional[SymbolInfo] = None
    symbol_b_info: Optional[SymbolInfo] = None
    
    # Market data
    price_a_bid: float = 0.0
    price_a_ask: float = 0.0
    price_b_bid: float = 0.0
    price_b_ask: float = 0.0
    
    # Arbitrage opportunity
    buy_exchange: str = ""  # "A" or "B"
    sell_exchange: str = ""  # "A" or "B"
    expected_profit_percent: float = 0.0
    expected_profit_usdt: float = 0.0
    
    # Orders
    buy_order: Optional[Order] = None
    sell_order: Optional[Order] = None
    
    # Execution tracking
    execution_start_time: float = 0.0
    buy_execution_time: float = 0.0
    sell_execution_time: float = 0.0
    total_execution_time: float = 0.0
    
    # Performance tracking
    actual_profit_usdt: float = 0.0
    slippage_experienced: float = 0.0
    opportunities_scanned: int = 0
    opportunities_executed: int = 0


class SimpleArbitrageStateMachine(
    BaseStrategyStateMachine,
    StateTransitionMixin,
    OrderManagementMixin,
    MarketDataMixin,
    PerformanceMonitoringMixin,
    RiskManagementMixin
):
    """
    State machine for simple cross-exchange arbitrage.
    
    Scans for price differences between exchanges and executes simultaneous
    buy/sell operations to capture risk-free profit from price discrepancies.
    """
    
    def __init__(self, context: SimpleArbitrageContext):
        super().__init__(context)
        self.context: SimpleArbitrageContext = context
    
    async def _handle_idle(self) -> None:
        """Initialize arbitrage strategy and start scanning."""
        self.context.logger.info("Initializing simple arbitrage strategy")
        
        # Get symbol information
        self.context.symbol_a_info = self.context.exchange_a_public.symbols_info.get(
            self.context.symbol_a
        )
        self.context.symbol_b_info = self.context.exchange_b_public.symbols_info.get(
            self.context.symbol_b
        )
        
        if not self.context.symbol_a_info or not self.context.symbol_b_info:
            raise ValueError("Missing symbol information for exchange A or B")
        
        self.context.logger.info(
            f"Starting arbitrage scanning",
            symbol_a=str(self.context.symbol_a),
            symbol_b=str(self.context.symbol_b),
            min_profit=f"{self.context.min_profit_threshold*100:.2f}%"
        )
        
        self._transition_to_state(StrategyState.ANALYZING)
    
    async def _handle_analyzing(self) -> None:
        """Scan for arbitrage opportunities between exchanges."""
        try:
            # Update prices from both exchanges
            await self._update_exchange_prices()
            
            # Increment scan counter
            self.context.opportunities_scanned += 1
            
            # Detect arbitrage opportunity
            opportunity_found = self._detect_arbitrage_opportunity()
            
            if opportunity_found:
                self.context.logger.info(
                    f"Arbitrage opportunity detected!",
                    buy_exchange=self.context.buy_exchange,
                    sell_exchange=self.context.sell_exchange,
                    expected_profit=f"{self.context.expected_profit_percent*100:.3f}%",
                    expected_profit_usdt=f"${self.context.expected_profit_usdt:.2f}"
                )
                
                self.context.execution_start_time = self._start_performance_timer()
                self._transition_to_state(StrategyState.EXECUTING)
            else:
                # Log current spreads periodically
                if self.context.opportunities_scanned % 100 == 0:
                    self._log_current_spreads()
                
                # Continue scanning with minimal delay
                await asyncio.sleep(0.1)  # 100ms between scans
                
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_executing(self) -> None:
        """Execute the arbitrage trade."""
        if not self.context.buy_order:
            await self._execute_buy_side()
        elif not self.context.sell_order:
            await self._execute_sell_side()
        else:
            self._transition_to_state(StrategyState.MONITORING)
    
    async def _handle_monitoring(self) -> None:
        """Monitor order execution and completion."""
        try:
            # Check if both orders are filled
            both_filled = await self._check_both_orders_filled()
            
            if both_filled:
                self.context.logger.info("Both orders filled, calculating profit")
                await self._calculate_final_profit()
                self._transition_to_state(StrategyState.COMPLETED)
            else:
                # Check for execution timeout
                elapsed_time = self._end_performance_timer(self.context.execution_start_time)
                
                if elapsed_time >= self.context.max_execution_time_ms:
                    self.context.logger.warning("Execution timeout, attempting to close positions")
                    await self._handle_execution_timeout()
                    self._transition_to_state(StrategyState.COMPLETED)
                else:
                    # Continue monitoring
                    await asyncio.sleep(0.1)  # Check every 100ms
                    
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_adjusting(self) -> None:
        """Handle any adjustments needed during execution."""
        # For simple arbitrage, this is typically used for timeout handling
        try:
            await self._handle_execution_timeout()
            self._transition_to_state(StrategyState.COMPLETED)
        except Exception as e:
            self._handle_error(e)
    
    async def _update_exchange_prices(self) -> None:
        """Update current prices from both exchanges."""
        # Get prices concurrently for speed
        price_a_task = self._get_current_price(
            self.context.exchange_a_public,
            self.context.symbol_a
        )
        price_b_task = self._get_current_price(
            self.context.exchange_b_public,
            self.context.symbol_b
        )
        
        price_a_info, price_b_info = await asyncio.gather(price_a_task, price_b_task)
        
        # Store bid/ask prices
        self.context.price_a_bid = price_a_info.bid_price
        self.context.price_a_ask = price_a_info.ask_price
        self.context.price_b_bid = price_b_info.bid_price
        self.context.price_b_ask = price_b_info.ask_price
    
    def _detect_arbitrage_opportunity(self) -> bool:
        """Detect if there's a profitable arbitrage opportunity."""
        # Check both directions
        
        # Direction 1: Buy on A, Sell on B
        profit_a_to_b = (self.context.price_b_bid - self.context.price_a_ask) / self.context.price_a_ask
        
        # Direction 2: Buy on B, Sell on A
        profit_b_to_a = (self.context.price_a_bid - self.context.price_b_ask) / self.context.price_b_ask
        
        # Choose the more profitable direction
        if profit_a_to_b >= self.context.min_profit_threshold:
            self.context.buy_exchange = "A"
            self.context.sell_exchange = "B"
            self.context.expected_profit_percent = profit_a_to_b
            self.context.expected_profit_usdt = profit_a_to_b * self.context.position_size_usdt
            return True
        elif profit_b_to_a >= self.context.min_profit_threshold:
            self.context.buy_exchange = "B"
            self.context.sell_exchange = "A"
            self.context.expected_profit_percent = profit_b_to_a
            self.context.expected_profit_usdt = profit_b_to_a * self.context.position_size_usdt
            return True
        
        return False
    
    def _log_current_spreads(self) -> None:
        """Log current price spreads for monitoring."""
        if (self.context.price_a_ask > 0 and self.context.price_b_bid > 0 and 
            self.context.price_b_ask > 0 and self.context.price_a_bid > 0):
            
            spread_a_to_b = (self.context.price_b_bid - self.context.price_a_ask) / self.context.price_a_ask * 100
            spread_b_to_a = (self.context.price_a_bid - self.context.price_b_ask) / self.context.price_b_ask * 100
            
            self.context.logger.info(
                f"Price scan #{self.context.opportunities_scanned}",
                a_to_b_spread=f"{spread_a_to_b:.3f}%",
                b_to_a_spread=f"{spread_b_to_a:.3f}%",
                threshold=f"{self.context.min_profit_threshold*100:.2f}%"
            )
    
    async def _execute_buy_side(self) -> None:
        """Execute the buy side of the arbitrage."""
        buy_timer = self._start_performance_timer()
        
        if self.context.buy_exchange == "A":
            exchange = self.context.exchange_a_private
            symbol = self.context.symbol_a
        else:
            exchange = self.context.exchange_b_private
            symbol = self.context.symbol_b
        
        self.context.logger.info(f"Executing buy side on exchange {self.context.buy_exchange}")
        
        self.context.buy_order = await self._place_market_buy(
            exchange,
            symbol,
            self.context.position_size_usdt
        )
        
        self.context.buy_execution_time = self._end_performance_timer(buy_timer)
        
        self.context.logger.info(
            f"Buy order executed",
            exchange=self.context.buy_exchange,
            order_id=self.context.buy_order.order_id,
            quantity=self.context.buy_order.filled_quantity,
            price=self.context.buy_order.average_price,
            execution_time_ms=self.context.buy_execution_time
        )
    
    async def _execute_sell_side(self) -> None:
        """Execute the sell side of the arbitrage."""
        sell_timer = self._start_performance_timer()
        
        if self.context.sell_exchange == "A":
            exchange = self.context.exchange_a_private
            symbol = self.context.symbol_a
            target_price = self.context.price_a_bid
        else:
            exchange = self.context.exchange_b_private
            symbol = self.context.symbol_b
            target_price = self.context.price_b_bid
        
        self.context.logger.info(f"Executing sell side on exchange {self.context.sell_exchange}")
        
        # Use the quantity from the buy order
        sell_quantity = self.context.buy_order.filled_quantity
        
        # Place limit order slightly below market for quick fill
        sell_price = target_price * (1 - self.context.slippage_tolerance)
        
        self.context.sell_order = await self._place_limit_sell(
            exchange,
            symbol,
            sell_quantity,
            sell_price
        )
        
        self.context.sell_execution_time = self._end_performance_timer(sell_timer)
        
        self.context.logger.info(
            f"Sell order placed",
            exchange=self.context.sell_exchange,
            order_id=self.context.sell_order.order_id,
            quantity=self.context.sell_order.quantity,
            price=self.context.sell_order.price,
            execution_time_ms=self.context.sell_execution_time
        )
    
    async def _check_both_orders_filled(self) -> bool:
        """Check if both buy and sell orders are completely filled."""
        if not self.context.buy_order or not self.context.sell_order:
            return False
        
        # Check buy order status
        if self.context.buy_exchange == "A":
            buy_exchange = self.context.exchange_a_private
        else:
            buy_exchange = self.context.exchange_b_private
        
        # Check sell order status
        if self.context.sell_exchange == "A":
            sell_exchange = self.context.exchange_a_private
        else:
            sell_exchange = self.context.exchange_b_private
        
        # Get order statuses concurrently
        buy_status_task = buy_exchange.fetch_order(
            self.context.buy_order.symbol,
            self.context.buy_order.order_id
        )
        sell_status_task = sell_exchange.fetch_order(
            self.context.sell_order.symbol,
            self.context.sell_order.order_id
        )
        
        buy_status, sell_status = await asyncio.gather(buy_status_task, sell_status_task)
        
        # Update order references with latest status
        self.context.buy_order = buy_status
        self.context.sell_order = sell_status
        
        from exchanges.utils.exchange_utils import is_order_filled
        return is_order_filled(buy_status) and is_order_filled(sell_status)
    
    async def _calculate_final_profit(self) -> None:
        """Calculate actual profit from the completed arbitrage."""
        if not self.context.buy_order or not self.context.sell_order:
            return
        
        # Calculate costs (buy + fees)
        buy_cost = self.context.buy_order.filled_quantity * self.context.buy_order.average_price
        if self.context.buy_order.fee:
            buy_cost += self.context.buy_order.fee
        
        # Calculate proceeds (sell - fees)
        sell_proceeds = self.context.sell_order.filled_quantity * self.context.sell_order.average_price
        if self.context.sell_order.fee:
            sell_proceeds -= self.context.sell_order.fee
        
        # Calculate actual profit
        self.context.actual_profit_usdt = sell_proceeds - buy_cost
        
        # Calculate slippage
        expected_sell_price = (self.context.price_a_bid if self.context.sell_exchange == "A" 
                             else self.context.price_b_bid)
        actual_sell_price = self.context.sell_order.average_price
        self.context.slippage_experienced = (expected_sell_price - actual_sell_price) / expected_sell_price
        
        # Calculate total execution time
        self.context.total_execution_time = self._end_performance_timer(self.context.execution_start_time)
        
        # Update performance metrics
        self._update_performance_metrics(self.context.actual_profit_usdt)
        self.context.opportunities_executed += 1
        
        # Add orders to completed list
        self.context.completed_orders.extend([self.context.buy_order, self.context.sell_order])
        
        self.context.logger.info(
            f"Arbitrage completed successfully",
            expected_profit_usdt=f"${self.context.expected_profit_usdt:.2f}",
            actual_profit_usdt=f"${self.context.actual_profit_usdt:.2f}",
            slippage=f"{self.context.slippage_experienced*100:.3f}%",
            total_execution_time_ms=self.context.total_execution_time,
            buy_time_ms=self.context.buy_execution_time,
            sell_time_ms=self.context.sell_execution_time
        )
    
    async def _handle_execution_timeout(self) -> None:
        """Handle execution timeout by trying to close positions."""
        self.context.logger.warning("Handling execution timeout")
        
        # Try to cancel unfilled orders and calculate partial profit
        if self.context.buy_order and self.context.sell_order:
            # Both orders placed, check their status
            await self._check_both_orders_filled()
            
            if not self.context.buy_order.filled_quantity:
                # Buy order not filled, cancel it
                try:
                    cancelled_buy = await self._cancel_order_safe(
                        self.context.exchange_a_private if self.context.buy_exchange == "A" 
                        else self.context.exchange_b_private,
                        self.context.buy_order
                    )
                    self.context.buy_order = cancelled_buy
                except Exception as e:
                    self.context.logger.warning(f"Failed to cancel buy order: {e}")
            
            if not self.context.sell_order.filled_quantity:
                # Sell order not filled, cancel it
                try:
                    cancelled_sell = await self._cancel_order_safe(
                        self.context.exchange_a_private if self.context.sell_exchange == "A"
                        else self.context.exchange_b_private,
                        self.context.sell_order
                    )
                    self.context.sell_order = cancelled_sell
                except Exception as e:
                    self.context.logger.warning(f"Failed to cancel sell order: {e}")
        
        # Calculate any partial profit
        if self.context.buy_order and self.context.sell_order:
            await self._calculate_final_profit()