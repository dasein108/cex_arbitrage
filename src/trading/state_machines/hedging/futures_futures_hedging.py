"""
Futures/Futures hedging strategy state machine.

Implements cross-exchange futures arbitrage and calendar spread strategies
to capture price differences between futures contracts on different exchanges
or different expiration dates.
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


class FuturesFuturesHedgingState(Enum):
    """States specific to futures/futures hedging strategy."""
    SCANNING_SPREADS = "scanning_spreads"
    SPREAD_DETECTED = "spread_detected"
    VALIDATING_OPPORTUNITY = "validating_opportunity"
    OPENING_LONG_LEG = "opening_long_leg"
    OPENING_SHORT_LEG = "opening_short_leg"
    MONITORING_SPREAD = "monitoring_spread"
    CLOSING_SPREAD = "closing_spread"


@dataclass
class FuturesFuturesHedgingContext(BaseStrategyContext):
    """Context for futures/futures hedging strategy."""
    
    # Exchange connections
    exchange_a_private: BasePrivateComposite
    exchange_b_private: BasePrivateComposite
    exchange_a_public: BasePublicComposite
    exchange_b_public: BasePublicComposite
    
    # Trading parameters
    position_size_usdt: float
    min_spread_threshold: float = 0.005  # 0.5% minimum spread
    max_spread_threshold: float = 0.02   # 2% maximum spread (too good to be true)
    position_timeout_seconds: float = 300.0  # 5 minutes max holding time
    
    # Symbols
    symbol_a: Symbol  # Long leg
    symbol_b: Symbol  # Short leg
    symbol_a_info: Optional[SymbolInfo] = None
    symbol_b_info: Optional[SymbolInfo] = None
    
    # Position tracking
    long_order: Optional[Order] = None   # Buy on exchange A
    short_order: Optional[Order] = None  # Sell on exchange B
    
    # Market data
    price_a: float = 0.0
    price_b: float = 0.0
    current_spread: float = 0.0
    spread_direction: str = ""  # "a_higher" or "b_higher"
    
    # Performance tracking
    entry_spread: float = 0.0
    exit_spread: float = 0.0
    spread_profit: float = 0.0
    execution_start_time: float = 0.0


class FuturesFuturesHedgingStateMachine(
    BaseStrategyStateMachine,
    StateTransitionMixin,
    OrderManagementMixin,
    MarketDataMixin,
    PerformanceMonitoringMixin,
    RiskManagementMixin
):
    """
    State machine for futures/futures hedging strategy.
    
    Captures price differences between futures contracts on different exchanges
    by simultaneously buying on the cheaper exchange and selling on the expensive one.
    """
    
    def __init__(self, context: FuturesFuturesHedgingContext):
        super().__init__(context)
        self.context: FuturesFuturesHedgingContext = context
    
    async def _handle_idle(self) -> None:
        """Initialize strategy and start spread scanning."""
        self.context.logger.info("Initializing futures/futures hedging strategy")
        
        # Get symbol information
        self.context.symbol_a_info = self.context.exchange_a_public.symbols_info.get(
            self.context.symbol_a
        )
        self.context.symbol_b_info = self.context.exchange_b_public.symbols_info.get(
            self.context.symbol_b
        )
        
        if not self.context.symbol_a_info or not self.context.symbol_b_info:
            raise ValueError("Missing symbol information for exchange A or B")
        
        self._transition_to_state(StrategyState.ANALYZING)
    
    async def _handle_analyzing(self) -> None:
        """Scan for spread opportunities between exchanges."""
        try:
            # Get current prices from both exchanges
            await self._update_current_prices()
            
            # Calculate spread
            self._calculate_spread()
            
            self.context.logger.info(
                f"Current spread: {self.context.current_spread:.4f} ({self.context.spread_direction})",
                price_a=self.context.price_a,
                price_b=self.context.price_b,
                min_threshold=self.context.min_spread_threshold
            )
            
            # Check if spread meets our criteria
            if (abs(self.context.current_spread) >= self.context.min_spread_threshold and 
                abs(self.context.current_spread) <= self.context.max_spread_threshold):
                
                self.context.logger.info("Profitable spread detected!")
                self.context.entry_spread = self.context.current_spread
                self.context.execution_start_time = self._start_performance_timer()
                self._transition_to_state(StrategyState.EXECUTING)
            else:
                # Continue scanning
                await asyncio.sleep(1.0)  # Wait 1 second before next scan
                
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_executing(self) -> None:
        """Execute the spread trade."""
        if not self.context.long_order:
            await self._open_long_leg()
        elif not self.context.short_order:
            await self._open_short_leg()
        else:
            self._transition_to_state(StrategyState.MONITORING)
    
    async def _handle_monitoring(self) -> None:
        """Monitor the spread and look for exit opportunities."""
        try:
            # Update current prices
            await self._update_current_prices()
            self._calculate_spread()
            
            self.context.logger.info(
                f"Monitoring spread: {self.context.current_spread:.4f}",
                entry_spread=self.context.entry_spread,
                spread_change=self.context.current_spread - self.context.entry_spread
            )
            
            # Check for exit conditions
            spread_improvement = self._calculate_spread_improvement()
            time_elapsed = self._end_performance_timer(self.context.execution_start_time)
            
            # Exit if spread has converged sufficiently or timeout
            if (spread_improvement >= 0.002 or  # 0.2% improvement
                time_elapsed >= self.context.position_timeout_seconds * 1000):
                
                self.context.logger.info("Exit conditions met, closing spread")
                self._transition_to_state(StrategyState.ADJUSTING)  # Use adjusting for closing
            else:
                # Continue monitoring
                await asyncio.sleep(2.0)  # Check every 2 seconds
                
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_adjusting(self) -> None:
        """Close the spread positions."""
        try:
            await self._close_spread_positions()
            self._transition_to_state(StrategyState.COMPLETED)
        except Exception as e:
            self._handle_error(e)
    
    async def _update_current_prices(self) -> None:
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
        
        # Use mid-price for spread calculation
        self.context.price_a = (price_a_info.bid_price + price_a_info.ask_price) / 2
        self.context.price_b = (price_b_info.bid_price + price_b_info.ask_price) / 2
    
    def _calculate_spread(self) -> None:
        """Calculate the current spread between exchanges."""
        if self.context.price_a == 0 or self.context.price_b == 0:
            self.context.current_spread = 0.0
            return
        
        # Calculate relative spread
        spread_absolute = self.context.price_a - self.context.price_b
        spread_relative = spread_absolute / min(self.context.price_a, self.context.price_b)
        
        self.context.current_spread = spread_relative
        
        if self.context.price_a > self.context.price_b:
            self.context.spread_direction = "a_higher"
        else:
            self.context.spread_direction = "b_higher"
    
    def _calculate_spread_improvement(self) -> float:
        """Calculate how much the spread has improved since entry."""
        if self.context.entry_spread == 0:
            return 0.0
        
        # Spread improvement means the spread is getting smaller (converging)
        return abs(self.context.entry_spread) - abs(self.context.current_spread)
    
    async def _open_long_leg(self) -> None:
        """Open the long leg of the spread."""
        # Determine which exchange to buy based on spread direction
        if self.context.spread_direction == "b_higher":
            # A is cheaper, buy on A
            exchange = self.context.exchange_a_private
            symbol = self.context.symbol_a
            leg_name = "long (A)"
        else:
            # B is cheaper, buy on B
            exchange = self.context.exchange_b_private
            symbol = self.context.symbol_b
            leg_name = "long (B)"
        
        self.context.logger.info(f"Opening {leg_name} leg")
        
        self.context.long_order = await self._place_market_buy(
            exchange,
            symbol,
            self.context.position_size_usdt
        )
        
        self.context.logger.info(f"Long leg opened: {self.context.long_order}")
    
    async def _open_short_leg(self) -> None:
        """Open the short leg of the spread."""
        # Determine which exchange to sell based on spread direction
        if self.context.spread_direction == "b_higher":
            # B is higher, sell on B
            exchange = self.context.exchange_b_private
            symbol = self.context.symbol_b
            leg_name = "short (B)"
            current_price = self.context.price_b
        else:
            # A is higher, sell on A
            exchange = self.context.exchange_a_private
            symbol = self.context.symbol_a
            leg_name = "short (A)"
            current_price = self.context.price_a
        
        self.context.logger.info(f"Opening {leg_name} leg")
        
        # Calculate quantity based on long order
        if not self.context.long_order:
            raise ValueError("No long order to hedge against")
        
        hedge_quantity = self.context.long_order.filled_quantity
        
        self.context.short_order = await self._place_limit_sell(
            exchange,
            symbol,
            hedge_quantity,
            current_price * 0.999  # Slightly below market for quick fill
        )
        
        self.context.logger.info(f"Short leg opened: {self.context.short_order}")
    
    async def _close_spread_positions(self) -> None:
        """Close both legs of the spread."""
        self.context.logger.info("Closing spread positions")
        
        # Close positions concurrently for speed
        close_tasks = []
        
        if self.context.long_order:
            # Close long position (sell)
            if self.context.spread_direction == "b_higher":
                # Long on A, close by selling on A
                close_tasks.append(self._close_long_on_exchange_a())
            else:
                # Long on B, close by selling on B
                close_tasks.append(self._close_long_on_exchange_b())
        
        if self.context.short_order:
            # Close short position (buy to cover)
            if self.context.spread_direction == "b_higher":
                # Short on B, close by buying on B
                close_tasks.append(self._close_short_on_exchange_b())
            else:
                # Short on A, close by buying on A
                close_tasks.append(self._close_short_on_exchange_a())
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # Calculate final spread profit
        self.context.exit_spread = self.context.current_spread
        self.context.spread_profit = self._calculate_total_spread_profit()
        
        self._update_performance_metrics(self.context.spread_profit)
        
        execution_time = self._end_performance_timer(self.context.execution_start_time)
        
        self.context.logger.info(
            f"Spread trade completed",
            entry_spread=self.context.entry_spread,
            exit_spread=self.context.exit_spread,
            spread_profit=self.context.spread_profit,
            execution_time_ms=execution_time
        )
    
    async def _close_long_on_exchange_a(self) -> None:
        """Close long position on exchange A."""
        price_info = await self._get_current_price(
            self.context.exchange_a_public,
            self.context.symbol_a
        )
        
        await self._place_limit_sell(
            self.context.exchange_a_private,
            self.context.symbol_a,
            self.context.long_order.filled_quantity,
            price_info.bid_price
        )
    
    async def _close_long_on_exchange_b(self) -> None:
        """Close long position on exchange B."""
        price_info = await self._get_current_price(
            self.context.exchange_b_public,
            self.context.symbol_b
        )
        
        await self._place_limit_sell(
            self.context.exchange_b_private,
            self.context.symbol_b,
            self.context.long_order.filled_quantity,
            price_info.bid_price
        )
    
    async def _close_short_on_exchange_a(self) -> None:
        """Close short position on exchange A (buy to cover)."""
        await self._place_market_buy(
            self.context.exchange_a_private,
            self.context.symbol_a,
            self.context.short_order.filled_quantity * self.context.price_a
        )
    
    async def _close_short_on_exchange_b(self) -> None:
        """Close short position on exchange B (buy to cover)."""
        await self._place_market_buy(
            self.context.exchange_b_private,
            self.context.symbol_b,
            self.context.short_order.filled_quantity * self.context.price_b
        )
    
    def _calculate_total_spread_profit(self) -> float:
        """Calculate total profit from the spread trade."""
        if not self.context.long_order or not self.context.short_order:
            return 0.0
        
        # This is a simplified calculation
        # In reality, we'd need to track the closing trades too
        spread_improvement = self._calculate_spread_improvement()
        position_value = self.context.position_size_usdt
        
        return spread_improvement * position_value