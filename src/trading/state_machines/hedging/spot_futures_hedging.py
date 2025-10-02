"""
Spot/Futures hedging strategy state machine.

Implements delta-neutral hedging between spot and futures positions to capture
funding rate arbitrage while maintaining market-neutral exposure.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Direct imports of real structures and interfaces
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.composite.base_public_composite import BasePublicComposite
from exchanges.structs.common import Symbol, Order, SymbolInfo, AssetBalance, Position
from exchanges.structs.enums import OrderType, OrderStatus, Side
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


class SpotFuturesHedgingState(Enum):
    """States specific to spot/futures hedging strategy."""
    ANALYZING_MARKET = "analyzing_market"
    OPENING_SPOT_POSITION = "opening_spot_position"
    OPENING_FUTURES_HEDGE = "opening_futures_hedge"
    MONITORING_POSITIONS = "monitoring_positions"
    REBALANCING = "rebalancing"
    CLOSING_POSITIONS = "closing_positions"


@dataclass
class SpotFuturesHedgingContext(BaseStrategyContext):
    """Context for spot/futures hedging strategy."""
    
    # Exchange connections
    spot_private_exchange: Optional[BasePrivateComposite] = None
    futures_private_exchange: Optional[BasePrivateComposite] = None
    spot_public_exchange: Optional[BasePublicComposite] = None
    futures_public_exchange: Optional[BasePublicComposite] = None
    
    # Trading parameters
    position_size_usdt: float = 0.0
    target_funding_rate: float = 0.01  # 1% APR minimum
    max_position_imbalance: float = 0.05  # 5% max delta
    
    # Symbol information
    spot_symbol: Optional[Symbol] = None
    futures_symbol: Optional[Symbol] = None

    # Position tracking
    spot_order: Optional[Order] = None
    futures_order: Optional[Order] = None
    current_funding_rate: float = 0.0
    position_delta: float = 0.0  # Current position imbalance
    target_inventory_ratio: float = 0.0  # Target delta neutral ratio
    current_mid_price: float = 0.0  # Current market mid price cache
    
    # Performance tracking
    funding_payments_received: float = 0.0
    rebalance_count: int = 0


class SpotFuturesHedgingStateMachine(
    BaseStrategyStateMachine,
    StateTransitionMixin,
    OrderManagementMixin,
    MarketDataMixin,
    PerformanceMonitoringMixin,
    RiskManagementMixin
):
    """
    State machine for spot/futures hedging strategy.
    
    Maintains delta-neutral positions between spot and futures to capture
    funding rate arbitrage while minimizing directional market risk.
    """
    
    def __init__(self, context: SpotFuturesHedgingContext):
        super().__init__(context)
        self.context: SpotFuturesHedgingContext = context
    
    async def _handle_idle(self) -> None:
        """Initialize strategy and transition to market analysis."""
        self.context.logger.info("Initializing spot/futures hedging strategy")
        
        # Check for existing positions and load them
        await self._load_existing_positions()
        
        # Determine next state based on existing positions
        if self.context.spot_order and self.context.futures_order:
            # Both positions exist, go to monitoring
            self.context.logger.info("Existing hedge positions detected, resuming monitoring")
            self._transition_to_state(StrategyState.MONITORING)
        elif self.context.spot_order or self.context.futures_order:
            # Partial positions exist, complete the hedge
            self.context.logger.info("Partial positions detected, completing hedge setup")
            self._transition_to_state(StrategyState.EXECUTING)
        else:
            # No existing positions, start fresh
            self.context.logger.info("No existing positions, starting fresh analysis")
            self._transition_to_state(StrategyState.ANALYZING)
    
    async def _handle_analyzing(self) -> None:
        """Analyze market conditions and funding rates."""
        try:
            # TODO: disabled
            self._transition_to_state(StrategyState.EXECUTING)
            # Get current funding rate
            # self.context.current_funding_rate = await self._get_current_funding_rate()
            #
            # self.context.logger.info(
            #     f"Current funding rate: {self.context.current_funding_rate:.4f}",
            #     target_rate=self.context.target_funding_rate
            # )
            #
            # # Check if funding rate meets our criteria
            # if abs(self.context.current_funding_rate) >= self.context.target_funding_rate:
            #     self.context.logger.info("Funding rate opportunity detected")
            #     self._transition_to_state(StrategyState.EXECUTING)
            # else:
            #     self.context.logger.info("Funding rate below threshold, waiting...")
            #     await asyncio.sleep(10.0)  # Wait 10 seconds before re-checking
            #
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_executing(self) -> None:
        """Execute the hedging positions."""
        if not self.context.spot_order:
            await self._open_spot_position()
        elif not self.context.futures_order:
            await self._open_futures_hedge()
        else:
            self._transition_to_state(StrategyState.MONITORING)
    
    async def _handle_monitoring(self) -> None:
        """Monitor positions and check for rebalancing needs."""
        try:
            # Update position delta
            await self._calculate_position_delta()
            
            self.context.logger.info(
                f"Position delta: {self.context.position_delta:.4f}",
                max_imbalance=self.context.max_position_imbalance
            )
            
            # Check if rebalancing is needed
            if abs(self.context.position_delta) > self.context.max_position_imbalance:
                self.context.logger.warning("Position imbalance detected, rebalancing needed")
                self._transition_to_state(StrategyState.ADJUSTING)
            else:
                pass
                # # Check funding rate changes
                # current_funding_rate = await self._get_current_funding_rate()
                #
                # # If funding rate becomes unfavorable, close positions
                # if abs(current_funding_rate) < self.context.target_funding_rate * 0.5:
                #     self.context.logger.info("Funding rate no longer attractive, closing positions")
                #     await self._close_all_positions()
                #     self._transition_to_state(StrategyState.COMPLETED)
                # else:
                #     # Continue monitoring
                #     await asyncio.sleep(30.0)  # Check every 30 seconds
                #
        except Exception as e:
            self._handle_error(e)
    
    async def _handle_adjusting(self) -> None:
        """Rebalance positions to maintain delta neutrality."""
        try:
            self.context.logger.info("Rebalancing positions")
            
            # Determine rebalancing action based on delta
            if self.context.position_delta > 0:
                # Too much long exposure, reduce spot or increase futures short
                await self._rebalance_reduce_long()
            else:
                # Too much short exposure, increase spot or reduce futures short
                await self._rebalance_reduce_short()
            
            self.context.rebalance_count += 1
            self._transition_to_state(StrategyState.MONITORING)
            
        except Exception as e:
            self._handle_error(e)
    
    async def _open_spot_position(self) -> None:
        """Open the spot position."""
        self.context.logger.info(f"Opening spot position for {self.context.position_size_usdt} USDT")
        
        # Determine side based on funding rate
        side = Side.BUY if self.context.current_funding_rate > 0 else Side.SELL
        
        if side == Side.BUY:
            self.context.spot_order = await self._place_market_buy(
                self.context.spot_private_exchange,
                self.context.spot_symbol,
                self.context.position_size_usdt
            )
        else:
            # For short positions, we'd need to borrow or use margin
            # Simplified: assume we can place sell orders
            price_info = await self._get_current_price(
                self.context.spot_public_exchange,
                self.context.spot_symbol
            )
            quantity = self.context.position_size_usdt / price_info.bid_price
            
            self.context.spot_order = await self._place_limit_sell(
                self.context.spot_private_exchange,
                self.context.spot_symbol,
                quantity,
                price_info.bid_price
            )
        
        self.context.logger.info(f"Spot order placed: {self.context.spot_order}")
    
    async def _open_futures_hedge(self) -> None:
        """Open the futures hedge position."""
        self.context.logger.info("Opening futures hedge position")
        
        # Calculate hedge size based on spot position
        if not self.context.spot_order:
            raise ValueError("No spot order to hedge against")
        
        # Hedge with opposite side on futures
        futures_side = Side.SELL if self.context.spot_order.side == Side.BUY else Side.BUY
        hedge_quantity = self.context.spot_order.filled_quantity
        
        if futures_side == Side.BUY:
            self.context.futures_order = await self._place_market_buy(
                self.context.futures_private_exchange,
                self.context.futures_symbol,
                hedge_quantity * self.context.spot_order.average_price
            )
        else:
            price_info = await self._get_current_price(
                self.context.futures_public_exchange,
                self.context.futures_symbol
            )
            
            self.context.futures_order = await self._place_limit_sell(
                self.context.futures_private_exchange,
                self.context.futures_symbol,
                hedge_quantity,
                price_info.bid_price
            )
        
        self.context.logger.info(f"Futures hedge order placed: {self.context.futures_order}")
    
    async def _calculate_position_delta(self) -> None:
        """Calculate current position delta (net exposure)."""
        if not self.context.spot_order or not self.context.futures_order:
            self.context.position_delta = 0.0
            return
        
        # Get current prices
        spot_price_info = await self._get_current_price(
            self.context.spot_public_exchange,
            self.context.spot_symbol
        )
        futures_price_info = await self._get_current_price(
            self.context.futures_public_exchange,
            self.context.futures_symbol
        )
        
        # Calculate position values using mid price (bid + ask) / 2
        spot_mid_price = (spot_price_info.bid_price + spot_price_info.ask_price) / 2
        futures_mid_price = (futures_price_info.bid_price + futures_price_info.ask_price) / 2
        
        spot_value = self.context.spot_order.filled_quantity * spot_mid_price
        futures_value = self.context.futures_order.filled_quantity * futures_mid_price
        
        # Update current mid price for futures (used elsewhere)
        self.context.current_mid_price = futures_mid_price
        
        # Apply position direction
        if self.context.spot_order.side == Side.SELL:
            spot_value = -spot_value
        if self.context.futures_order.side == Side.SELL:
            futures_value = -futures_value
        
        # Calculate net delta as percentage of total position
        total_position_value = abs(spot_value) + abs(futures_value)
        self.context.position_delta = (spot_value + futures_value) / total_position_value
    
    async def _get_current_funding_rate(self) -> float:
        # ignore at this moment
        return 0.0
    
    async def _rebalance_reduce_long(self) -> None:
        """Reduce long exposure by adjusting positions."""
        self.context.logger.info("Reducing long exposure")
        
        try:
            # Calculate rebalancing amount (reduce by half of the imbalance)
            imbalance = self.context.position_delta - self.context.target_inventory_ratio
            rebalance_amount = abs(imbalance) * 0.5
            
            if rebalance_amount > 0.01:  # Only rebalance if significant
                # Option 1: Reduce spot position by selling some
                if self.context.spot_order and self.context.spot_order.side == "BUY":
                    sell_quantity = self.context.spot_order.filled_quantity * rebalance_amount
                    price_info = await self._get_current_price(
                        self.context.spot_public_exchange,
                        self.context.spot_symbol
                    )
                    
                    rebalance_order = await self._place_limit_sell(
                        self.context.spot_private_exchange,
                        self.context.spot_symbol,
                        sell_quantity,
                        price_info.bid_price * 0.999  # Slightly below bid for quick fill
                    )
                    
                    self.context.logger.info(
                        f"Rebalance sell order placed",
                        quantity=sell_quantity,
                        price=price_info.bid_price * 0.999,
                        order_id=rebalance_order.order_id
                    )
                
                # Option 2: Increase futures short position
                elif self.context.futures_order:
                    additional_short = self.context.position_size_usdt * rebalance_amount
                    
                    additional_order = await self._place_market_buy(
                        self.context.futures_private_exchange,
                        self.context.futures_symbol,
                        additional_short
                    )
                    
                    self.context.logger.info(
                        f"Additional futures short placed",
                        amount_usdt=additional_short,
                        order_id=additional_order.order_id
                    )
            
        except Exception as e:
            self.context.logger.error(f"Failed to rebalance long exposure: {e}")
            raise
    
    async def _rebalance_reduce_short(self) -> None:
        """Reduce short exposure by adjusting positions."""
        self.context.logger.info("Reducing short exposure")
        
        try:
            # Calculate rebalancing amount (reduce by half of the imbalance)
            imbalance = self.context.target_inventory_ratio - self.context.position_delta
            rebalance_amount = abs(imbalance) * 0.5
            
            if rebalance_amount > 0.01:  # Only rebalance if significant
                # Option 1: Increase spot position by buying more
                additional_buy = self.context.position_size_usdt * rebalance_amount
                
                additional_spot_order = await self._place_market_buy(
                    self.context.spot_private_exchange,
                    self.context.spot_symbol,
                    additional_buy
                )
                
                self.context.logger.info(
                    f"Additional spot buy placed",
                    amount_usdt=additional_buy,
                    order_id=additional_spot_order.order_id
                )
                
                # Option 2: Reduce futures short position by buying back some
                if self.context.futures_order and self.context.futures_order.side == "SELL":
                    buyback_quantity = self.context.futures_order.filled_quantity * rebalance_amount
                    
                    buyback_order = await self._place_market_buy(
                        self.context.futures_private_exchange,
                        self.context.futures_symbol,
                        buyback_quantity * self.context.current_mid_price
                    )
                    
                    self.context.logger.info(
                        f"Futures buyback order placed",
                        quantity=buyback_quantity,
                        order_id=buyback_order.order_id
                    )
            
        except Exception as e:
            self.context.logger.error(f"Failed to rebalance short exposure: {e}")
            raise
    
    async def _close_all_positions(self) -> None:
        """Close all open positions."""
        self.context.logger.info("Closing all positions")
        
        close_orders = []
        
        try:
            # Close spot position
            if self.context.spot_order:
                if self.context.spot_order.side == "BUY":
                    # We bought spot, now sell it
                    spot_price_info = await self._get_current_price(
                        self.context.spot_public_exchange,
                        self.context.spot_symbol
                    )
                    
                    close_spot_order = await self._place_limit_sell(
                        self.context.spot_private_exchange,
                        self.context.spot_symbol,
                        self.context.spot_order.filled_quantity,
                        spot_price_info.bid_price * 0.999  # Quick fill
                    )
                    close_orders.append(close_spot_order)
                    self.context.logger.info(f"Closing spot position: {close_spot_order.order_id}")
            
            # Close futures position
            if self.context.futures_order:
                if self.context.futures_order.side == "SELL":
                    # We sold futures, now buy back to close
                    close_futures_order = await self._place_market_buy(
                        self.context.futures_private_exchange,
                        self.context.futures_symbol,
                        self.context.futures_order.filled_quantity * self.context.current_mid_price
                    )
                    close_orders.append(close_futures_order)
                    self.context.logger.info(f"Closing futures position: {close_futures_order.order_id}")
                elif self.context.futures_order.side == "BUY":
                    # We bought futures, now sell to close
                    futures_price_info = await self._get_current_price(
                        self.context.futures_public_exchange,
                        self.context.futures_symbol
                    )
                    
                    close_futures_order = await self._place_limit_sell(
                        self.context.futures_private_exchange,
                        self.context.futures_symbol,
                        self.context.futures_order.filled_quantity,
                        futures_price_info.bid_price * 0.999  # Quick fill
                    )
                    close_orders.append(close_futures_order)
                    self.context.logger.info(f"Closing futures position: {close_futures_order.order_id}")
            
            # Wait for orders to fill (with timeout)
            for order in close_orders:
                filled_order = await self._wait_for_order_fill(
                    self.context.spot_private_exchange if order.symbol == self.context.spot_symbol 
                    else self.context.futures_private_exchange,
                    order,
                    timeout_seconds=30.0
                )
                
                if filled_order:
                    self.context.completed_orders.append(filled_order)
                    self.context.logger.info(f"Position closed: {filled_order.order_id}")
                else:
                    self.context.logger.warning(f"Close order timeout: {order.order_id}")
            
            # Calculate final profit including funding payments
            total_profit = self._calculate_profit(self.context.spot_order, self.context.futures_order)
            total_profit += self.context.funding_payments_received
            
            self._update_performance_metrics(total_profit)
            
            self.context.logger.info(
                f"All positions closed successfully",
                total_profit=total_profit,
                funding_received=self.context.funding_payments_received,
                rebalances=self.context.rebalance_count,
                close_orders=len(close_orders)
            )
            
        except Exception as e:
            self.context.logger.error(f"Failed to close positions: {e}")
            raise
    
    async def _load_existing_positions(self) -> None:
        """
        Load existing positions and balances to resume strategy if positions exist.
        
        Checks both spot and futures exchanges for existing balances and open orders/positions
        that match our hedging strategy. If found, creates mock Order objects to represent
        existing positions for strategy resumption.
        """
        self.context.logger.info("Checking for existing positions to resume strategy")
        
        try:
            # Get current market prices for position valuation
            spot_price_info = await self._get_current_price(
                self.context.spot_public_exchange,
                self.context.spot_symbol
            )
            futures_price_info = await self._get_current_price(
                self.context.futures_public_exchange,
                self.context.futures_symbol
            )
            
            # Calculate mid prices
            spot_mid_price = (spot_price_info.bid_price + spot_price_info.ask_price) / 2
            futures_mid_price = (futures_price_info.bid_price + futures_price_info.ask_price) / 2
            self.context.current_mid_price = futures_mid_price
            
            # Check spot exchange for existing balance in the base asset
            base_asset = self.context.spot_symbol.base
            spot_balance = await self.context.spot_private_exchange.get_asset_balance(base_asset, force=True)
            
            # Check for open orders on spot exchange
            spot_open_orders = await self.context.spot_private_exchange.get_open_orders(
                self.context.spot_symbol, force=True
            )
            
            # Check futures exchange for existing positions
            futures_positions = None
            if hasattr(self.context.futures_private_exchange, 'positions'):
                futures_positions = self.context.futures_private_exchange.positions.get(
                    self.context.futures_symbol
                )
            
            # Check for open orders on futures exchange
            futures_open_orders = await self.context.futures_private_exchange.get_open_orders(
                self.context.futures_symbol, force=True
            )
            
            # Determine if we have existing hedging positions
            has_spot_position = False
            has_futures_position = False
            
            # Check spot balance (if we have significant balance beyond what we normally hold)
            if spot_balance and spot_balance.total > 0.01:  # Minimum threshold
                self.context.logger.info(
                    f"Found existing spot balance: {spot_balance.total} {base_asset}"
                )
                # Create a mock order to represent the existing balance using current market price
                self.context.spot_order = Order(
                    symbol=self.context.spot_symbol,
                    order_id="existing_balance",
                    side=Side.BUY,
                    order_type=OrderType.MARKET,
                    quantity=spot_balance.total,
                    filled_quantity=spot_balance.total,
                    price=spot_mid_price,
                    average_price=spot_mid_price,
                    status=OrderStatus.FILLED
                )
                has_spot_position = True
            
            # Check spot open orders
            if spot_open_orders:
                self.context.logger.info(f"Found {len(spot_open_orders)} open spot orders")
                # Use the most recent or largest order as our representative order
                largest_order = max(spot_open_orders, key=lambda o: o.quantity)
                self.context.spot_order = largest_order
                has_spot_position = True
            
            # Check futures positions
            if futures_positions and abs(futures_positions.size) > 0.01:
                self.context.logger.info(
                    f"Found existing futures position: {futures_positions.size} {futures_positions.side}"
                )
                # Create a mock order to represent the existing position
                # Convert position side to order side (position side is already BUY/SELL)
                order_side = futures_positions.side
                # Use entry price if available, otherwise use current market price
                position_price = futures_positions.entry_price if futures_positions.entry_price else futures_mid_price
                
                self.context.futures_order = Order(
                    symbol=self.context.futures_symbol,
                    order_id="existing_position",
                    side=order_side,
                    order_type=OrderType.MARKET,
                    quantity=abs(futures_positions.size),
                    filled_quantity=abs(futures_positions.size),
                    price=position_price,
                    average_price=position_price,
                    status=OrderStatus.FILLED
                )
                has_futures_position = True
            
            # Check futures open orders
            if futures_open_orders:
                self.context.logger.info(f"Found {len(futures_open_orders)} open futures orders")
                # Use the most recent or largest order as our representative order
                largest_order = max(futures_open_orders, key=lambda o: o.quantity)
                self.context.futures_order = largest_order
                has_futures_position = True
            
            # Log the result
            if has_spot_position and has_futures_position:
                self.context.logger.info("Complete hedge positions detected - resuming monitoring")
            elif has_spot_position or has_futures_position:
                self.context.logger.info("Partial hedge positions detected - will complete hedge")
            else:
                self.context.logger.info("No existing positions found - starting fresh strategy")
                
        except Exception as e:
            self.context.logger.error(f"Failed to load existing positions: {e}")
            # Don't raise - just proceed with fresh strategy
            self.context.spot_order = None
            self.context.futures_order = None