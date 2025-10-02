"""
Spot/Futures hedging strategy state machine.

Implements delta-neutral hedging between spot and futures positions to capture
funding rate arbitrage while maintaining market-neutral exposure.
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
    spot_symbol_info: Optional[SymbolInfo] = None
    futures_symbol_info: Optional[SymbolInfo] = None
    
    # Position tracking
    spot_order: Optional[Order] = None
    futures_order: Optional[Order] = None
    current_funding_rate: float = 0.0
    position_delta: float = 0.0  # Current position imbalance
    
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
        
        # Get symbol information
        self.context.spot_symbol_info = self.context.spot_public_exchange.symbols_info.get(
            self.context.spot_symbol
        )
        self.context.futures_symbol_info = self.context.futures_public_exchange.symbols_info.get(
            self.context.futures_symbol
        )
        
        if not self.context.spot_symbol_info or not self.context.futures_symbol_info:
            raise ValueError("Missing symbol information for spot or futures")
        
        self._transition_to_state(StrategyState.ANALYZING)
    
    async def _handle_analyzing(self) -> None:
        """Analyze market conditions and funding rates."""
        try:
            # Get current funding rate
            self.context.current_funding_rate = await self._get_current_funding_rate()
            
            self.context.logger.info(
                f"Current funding rate: {self.context.current_funding_rate:.4f}",
                target_rate=self.context.target_funding_rate
            )
            
            # Check if funding rate meets our criteria
            if abs(self.context.current_funding_rate) >= self.context.target_funding_rate:
                self.context.logger.info("Funding rate opportunity detected")
                self._transition_to_state(StrategyState.EXECUTING)
            else:
                self.context.logger.info("Funding rate below threshold, waiting...")
                await asyncio.sleep(10.0)  # Wait 10 seconds before re-checking
                
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
                # Check funding rate changes
                current_funding_rate = await self._get_current_funding_rate()
                
                # If funding rate becomes unfavorable, close positions
                if abs(current_funding_rate) < self.context.target_funding_rate * 0.5:
                    self.context.logger.info("Funding rate no longer attractive, closing positions")
                    await self._close_all_positions()
                    self._transition_to_state(StrategyState.COMPLETED)
                else:
                    # Continue monitoring
                    await asyncio.sleep(30.0)  # Check every 30 seconds
                    
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
        
        # Calculate position values
        spot_value = self.context.spot_order.filled_quantity * spot_price_info.mid_price
        futures_value = self.context.futures_order.filled_quantity * futures_price_info.mid_price
        
        # Apply position direction
        if self.context.spot_order.side == Side.SELL:
            spot_value = -spot_value
        if self.context.futures_order.side == Side.SELL:
            futures_value = -futures_value
        
        # Calculate net delta as percentage of total position
        total_position_value = abs(spot_value) + abs(futures_value)
        self.context.position_delta = (spot_value + futures_value) / total_position_value
    
    async def _get_current_funding_rate(self) -> float:
        """Get current funding rate from futures exchange."""
        # This would need to be implemented based on the specific exchange API
        # For now, return a mock value
        return 0.015  # 1.5% funding rate
    
    async def _rebalance_reduce_long(self) -> None:
        """Reduce long exposure by adjusting positions."""
        self.context.logger.info("Reducing long exposure")
        # Implementation would adjust position sizes
        # For now, just log the action
        await asyncio.sleep(1.0)
    
    async def _rebalance_reduce_short(self) -> None:
        """Reduce short exposure by adjusting positions."""
        self.context.logger.info("Reducing short exposure")
        # Implementation would adjust position sizes
        # For now, just log the action
        await asyncio.sleep(1.0)
    
    async def _close_all_positions(self) -> None:
        """Close all open positions."""
        self.context.logger.info("Closing all positions")
        
        # Close spot position
        if self.context.spot_order:
            # Implementation would close the spot position
            pass
        
        # Close futures position
        if self.context.futures_order:
            # Implementation would close the futures position
            pass
        
        # Calculate final profit including funding payments
        total_profit = self._calculate_profit(self.context.spot_order, self.context.futures_order)
        total_profit += self.context.funding_payments_received
        
        self._update_performance_metrics(total_profit)
        
        self.context.logger.info(
            f"Positions closed",
            total_profit=total_profit,
            funding_received=self.context.funding_payments_received,
            rebalances=self.context.rebalance_count
        )