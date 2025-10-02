"""
Market making strategy state machine.

Implements sophisticated market making with dynamic spreads, multi-level orders,
inventory management, and adaptive pricing based on market conditions.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List

from exchanges.interfaces.composite import BasePrivateComposite, BasePublicComposite
from exchanges.structs import Symbol, Order, Side, SymbolInfo, TimeInForce
from exchanges.utils.exchange_utils import is_order_filled
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


class MarketMakingState(Enum):
    """States specific to market making strategy."""
    CALCULATING_SPREADS = "calculating_spreads"
    PLACING_ORDERS = "placing_orders"
    MONITORING_ORDERS = "monitoring_orders"
    ADJUSTING_SPREADS = "adjusting_spreads"
    ORDER_FILLED = "order_filled"
    INVENTORY_MANAGEMENT = "inventory_management"


@dataclass
class OrderLevel:
    """Represents a single order level in the market making strategy."""
    buy_order: Optional[Order] = None
    sell_order: Optional[Order] = None
    spread_percent: float = 0.0
    quantity: float = 0.0
    distance_from_mid: float = 0.0


@dataclass
class MarketMakingContext(BaseStrategyContext):
    """Context for market making strategy."""
    
    # Exchange connections
    private_exchange: Optional[BasePrivateComposite] = None
    public_exchange: Optional[BasePublicComposite] = None
    
    # Trading parameters
    base_quantity_usdt: float = 0.0
    min_spread_percent: float = 0.001  # 0.1% minimum spread
    max_spread_percent: float = 0.01   # 1% maximum spread
    num_levels: int = 3  # Number of order levels
    level_spacing: float = 0.002  # 0.2% spacing between levels
    
    # Inventory management
    max_inventory_usdt: float = 1000.0
    target_inventory_ratio: float = 0.5  # 50% of max inventory
    inventory_rebalance_threshold: float = 0.8  # 80% of max inventory
    
    # Symbol information
    symbol_info: Optional[SymbolInfo] = None
    
    # Market data
    current_mid_price: float = 0.0
    current_spread: float = 0.0
    market_volatility: float = 0.0
    
    # Order management
    order_levels: List[OrderLevel] = field(default_factory=list)
    filled_orders: List[Order] = field(default_factory=list)
    
    # Inventory tracking
    current_base_inventory: float = 0.0
    current_quote_inventory: float = 0.0
    inventory_ratio: float = 0.5
    
    # Performance tracking
    cycles_completed: int = 0
    total_volume_traded: float = 0.0
    average_spread_captured: float = 0.0


class MarketMakingStateMachine(
    BaseStrategyStateMachine,
    StateTransitionMixin,
    OrderManagementMixin,
    MarketDataMixin,
    PerformanceMonitoringMixin,
    RiskManagementMixin
):
    """
    State machine for market making strategy.
    
    Provides liquidity to the market by continuously placing buy and sell orders
    at calculated spreads around the mid-price, managing inventory and adapting
    to market conditions.
    """
    
    def __init__(self, context: MarketMakingContext):
        super().__init__(context)
        self.context: MarketMakingContext = context
    
    async def _handle_idle(self) -> None:
        """Initialize market making strategy."""
        self.context.logger.info("Initializing market making strategy")
        
        # Get symbol information
        self.context.symbol_info = self.context.public_exchange.symbols_info.get(
            self.context.symbol
        )
        
        if not self.context.symbol_info:
            raise ValueError(f"Missing symbol information for {self.context.symbol}")
        
        # Initialize order levels
        self._initialize_order_levels()
        
        # Update initial inventory
        await self._update_inventory()
        
        self._transition_to_state(StrategyState.ANALYZING)
    
    async def _handle_analyzing(self) -> None:
        """Analyze market conditions and calculate spreads."""
        try:
            # Update market data
            await self._update_market_data()
            
            # Calculate dynamic spreads based on market conditions
            self._calculate_dynamic_spreads()
            
            self.context.logger.info(
                f"Market analysis completed",
                mid_price=self.context.current_mid_price,
                spread=self.context.current_spread,
                volatility=self.context.market_volatility,
                inventory_ratio=self.context.inventory_ratio
            )
            
            self._transition_to_state(StrategyState.EXECUTING)
            
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_executing(self) -> None:
        """Place market making orders."""
        try:
            # Cancel existing orders first
            await self._cancel_existing_orders()
            
            # Place new orders at calculated levels
            await self._place_market_making_orders()
            
            self.context.cycles_completed += 1
            self._transition_to_state(StrategyState.MONITORING)
            
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_monitoring(self) -> None:
        """Monitor orders and market conditions."""
        try:
            # Check for filled orders
            filled_orders = await self._check_filled_orders()
            
            if filled_orders:
                self.context.filled_orders.extend(filled_orders)
                self.context.logger.info(f"{len(filled_orders)} orders filled")
                self._transition_to_state(StrategyState.ADJUSTING)  # Handle fills
                return
            
            # Check if market has moved significantly
            await self._update_market_data()
            
            if self._market_moved_significantly():
                self.context.logger.info("Significant market movement detected")
                self._transition_to_state(StrategyState.ANALYZING)  # Recalculate spreads
            else:
                # Continue monitoring
                await asyncio.sleep(2.0)  # Check every 2 seconds
                
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_adjusting(self) -> None:
        """Handle filled orders and adjust strategy."""
        try:
            # Update inventory after fills
            await self._update_inventory()
            
            # Process filled orders
            for order in self.context.filled_orders:
                await self._process_filled_order(order)
            
            # Clear processed orders
            self.context.filled_orders.clear()
            
            # Check if inventory rebalancing is needed
            if self._inventory_rebalancing_needed():
                self.context.logger.info("Inventory rebalancing required")
                await self._rebalance_inventory()
            
            # Continue with next cycle
            self._transition_to_state(StrategyState.ANALYZING)
            
        except Exception as e:
            self._handle_error(e)
    
    def _initialize_order_levels(self) -> None:
        """Initialize order level structures."""
        self.context.order_levels = []
        
        for i in range(self.context.num_levels):
            level = OrderLevel(
                distance_from_mid=(i + 1) * self.context.level_spacing,
                quantity=self.context.base_quantity_usdt / (i + 1)  # Decreasing quantity per level
            )
            self.context.order_levels.append(level)
    
    async def _update_market_data(self) -> None:
        """Update current market data."""
        # Get current book ticker
        book_ticker = await self._get_current_price(
            self.context.public_exchange,
            self.context.symbol
        )
        
        self.context.current_mid_price = (book_ticker.bid_price + book_ticker.ask_price) / 2
        self.context.current_spread = book_ticker.ask_price - book_ticker.bid_price
        
        # Calculate simple volatility measure (simplified)
        self.context.market_volatility = self.context.current_spread / self.context.current_mid_price
    
    def _calculate_dynamic_spreads(self) -> None:
        """Calculate dynamic spreads based on market conditions and inventory."""
        base_spread = max(
            self.context.min_spread_percent,
            self.context.market_volatility * 2  # Spread proportional to volatility
        )
        
        # Adjust spread based on inventory
        inventory_adjustment = self._calculate_inventory_adjustment()
        
        for level in self.context.order_levels:
            level.spread_percent = min(
                base_spread + inventory_adjustment + level.distance_from_mid,
                self.context.max_spread_percent
            )
    
    def _calculate_inventory_adjustment(self) -> float:
        """Calculate spread adjustment based on current inventory imbalance."""
        # If we have too much base inventory, widen sell spreads and narrow buy spreads
        inventory_imbalance = self.context.inventory_ratio - self.context.target_inventory_ratio
        
        # Scale adjustment by imbalance magnitude
        adjustment = inventory_imbalance * 0.005  # 0.5% max adjustment
        
        return adjustment
    
    async def _cancel_existing_orders(self) -> None:
        """Cancel all existing orders."""
        cancel_tasks = []
        
        for level in self.context.order_levels:
            if level.buy_order:
                cancel_tasks.append(
                    self._cancel_order_safe(self.context.private_exchange, level.buy_order)
                )
            if level.sell_order:
                cancel_tasks.append(
                    self._cancel_order_safe(self.context.private_exchange, level.sell_order)
                )
        
        if cancel_tasks:
            await asyncio.gather(*cancel_tasks, return_exceptions=True)
        
        # Clear order references
        for level in self.context.order_levels:
            level.buy_order = None
            level.sell_order = None
    
    async def _place_market_making_orders(self) -> None:
        """Place buy and sell orders at all levels."""
        order_tasks = []
        
        for level in self.context.order_levels:
            # Calculate prices
            spread_amount = self.context.current_mid_price * level.spread_percent
            buy_price = self.context.current_mid_price - spread_amount
            sell_price = self.context.current_mid_price + spread_amount
            
            # Adjust prices based on inventory
            buy_price, sell_price = self._adjust_prices_for_inventory(buy_price, sell_price)
            
            # Round prices to tick size
            buy_price = self._round_to_tick_size(buy_price)
            sell_price = self._round_to_tick_size(sell_price)
            
            # Calculate quantities
            buy_quantity = level.quantity / buy_price
            sell_quantity = level.quantity / sell_price
            
            # Place orders
            order_tasks.extend([
                self._place_buy_order(level, buy_price, buy_quantity),
                self._place_sell_order(level, sell_price, sell_quantity)
            ])
        
        # Execute all orders concurrently
        await asyncio.gather(*order_tasks, return_exceptions=True)
    
    def _adjust_prices_for_inventory(self, buy_price: float, sell_price: float) -> tuple[float, float]:
        """Adjust order prices based on inventory imbalance."""
        inventory_imbalance = self.context.inventory_ratio - self.context.target_inventory_ratio
        
        # If we have too much inventory, make sells more attractive and buys less attractive
        price_adjustment = inventory_imbalance * self.context.current_mid_price * 0.001  # 0.1% max
        
        adjusted_buy_price = buy_price - price_adjustment
        adjusted_sell_price = sell_price - price_adjustment
        
        return adjusted_buy_price, adjusted_sell_price
    
    def _round_to_tick_size(self, price: float) -> float:
        """Round price to symbol tick size."""
        if not self.context.symbol_info:
            return price
        
        tick_size = self.context.symbol_info.tick
        return round(price / tick_size) * tick_size
    
    async def _place_buy_order(self, level: OrderLevel, price: float, quantity: float) -> None:
        """Place a buy order for a specific level."""
        try:
            level.buy_order = await self.context.private_exchange.place_limit_order(
                symbol=self.context.symbol,
                side=Side.BUY,
                quantity=quantity,
                price=price,
                time_in_force=TimeInForce.GTC
            )
        except Exception as e:
            self.context.logger.warning(f"Failed to place buy order: {e}")
    
    async def _place_sell_order(self, level: OrderLevel, price: float, quantity: float) -> None:
        """Place a sell order for a specific level."""
        try:
            level.sell_order = await self.context.private_exchange.place_limit_order(
                symbol=self.context.symbol,
                side=Side.SELL,
                quantity=quantity,
                price=price,
                time_in_force=TimeInForce.GTC
            )
        except Exception as e:
            self.context.logger.warning(f"Failed to place sell order: {e}")
    
    async def _check_filled_orders(self) -> List[Order]:
        """Check for filled orders across all levels."""
        filled_orders = []
        check_tasks = []
        
        for level in self.context.order_levels:
            if level.buy_order:
                check_tasks.append(
                    self.context.private_exchange.get_order(
                        level.buy_order.symbol, 
                        level.buy_order.order_id
                    )
                )
            if level.sell_order:
                check_tasks.append(
                    self.context.private_exchange.get_order(
                        level.sell_order.symbol,
                        level.sell_order.order_id
                    )
                )
        
        if not check_tasks:
            return filled_orders
        
        order_statuses = await asyncio.gather(*check_tasks, return_exceptions=True)
        
        # Process results
        level_index = 0
        task_index = 0
        
        for level in self.context.order_levels:
            if level.buy_order and task_index < len(order_statuses):
                status = order_statuses[task_index]
                if isinstance(status, Order) and is_order_filled(status):
                    filled_orders.append(status)
                    level.buy_order = None  # Clear filled order
                task_index += 1
            
            if level.sell_order and task_index < len(order_statuses):
                status = order_statuses[task_index]
                if isinstance(status, Order) and is_order_filled(status):
                    filled_orders.append(status)
                    level.sell_order = None  # Clear filled order
                task_index += 1
        
        return filled_orders
    
    def _market_moved_significantly(self) -> bool:
        """Check if market has moved significantly since last update."""
        # This is simplified - in practice, you'd track price history
        # For now, check if spread has changed significantly
        return self.context.market_volatility > 0.01  # 1% volatility threshold
    
    async def _update_inventory(self) -> None:
        """Update current inventory levels."""
        # This would query actual balances from the exchange
        # For now, simplified calculation based on filled orders
        
        base_balance = 0.0
        quote_balance = self.context.base_quantity_usdt * self.context.num_levels
        
        for order in self.context.completed_orders:
            if order.side == Side.BUY:
                base_balance += order.filled_quantity
                quote_balance -= order.filled_quantity * order.average_price
            else:
                base_balance -= order.filled_quantity
                quote_balance += order.filled_quantity * order.average_price
        
        self.context.current_base_inventory = base_balance
        self.context.current_quote_inventory = quote_balance
        
        # Calculate inventory ratio (0 = all quote, 1 = all base)
        total_value = (base_balance * self.context.current_mid_price) + quote_balance
        if total_value > 0:
            self.context.inventory_ratio = (base_balance * self.context.current_mid_price) / total_value
        else:
            self.context.inventory_ratio = 0.5
    
    async def _process_filled_order(self, order: Order) -> None:
        """Process a filled order for performance tracking."""
        self.context.total_volume_traded += order.filled_quantity * order.average_price
        
        # Calculate spread captured (simplified)
        spread_captured = abs(order.average_price - self.context.current_mid_price) / self.context.current_mid_price
        
        # Update running average
        total_orders = len(self.context.completed_orders) + 1
        self.context.average_spread_captured = (
            (self.context.average_spread_captured * (total_orders - 1) + spread_captured) / total_orders
        )
        
        # Add to completed orders
        self.context.completed_orders.append(order)
        
        self.context.logger.info(
            f"Order filled",
            side=order.side.value,
            quantity=order.filled_quantity,
            price=order.average_price,
            spread_captured=spread_captured
        )
    
    def _inventory_rebalancing_needed(self) -> bool:
        """Check if inventory rebalancing is needed."""
        return abs(self.context.inventory_ratio - self.context.target_inventory_ratio) > (
            self.context.inventory_rebalance_threshold - self.context.target_inventory_ratio
        )
    
    async def _rebalance_inventory(self) -> None:
        """Rebalance inventory to target ratio."""
        self.context.logger.info(
            f"Rebalancing inventory",
            current_ratio=self.context.inventory_ratio,
            target_ratio=self.context.target_inventory_ratio
        )
        
        # Simplified rebalancing - place market orders to adjust inventory
        if self.context.inventory_ratio > self.context.target_inventory_ratio:
            # Too much base, sell some
            excess_base = (self.context.inventory_ratio - self.context.target_inventory_ratio) * self.context.current_base_inventory
            
            if excess_base > 0:
                await self._place_limit_sell(
                    self.context.private_exchange,
                    self.context.symbol,
                    excess_base,
                    self.context.current_mid_price * 0.999  # Slightly below mid for quick fill
                )
        else:
            # Too much quote, buy some base
            needed_quote_value = (self.context.target_inventory_ratio - self.context.inventory_ratio) * self.context.current_quote_inventory
            
            if needed_quote_value > 0:
                await self._place_market_buy(
                    self.context.private_exchange,
                    self.context.symbol,
                    needed_quote_value
                )