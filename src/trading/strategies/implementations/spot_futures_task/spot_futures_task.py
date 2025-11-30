"""
Simplified Spot-Futures Strategy Task

A minimalistic arbitrage strategy that extends BaseMultiSpotFuturesArbitrageTask
with focus on simple market-market execution and optimal threshold calculation.

This strategy integrates the fee-adjusted threshold logic from mexc_gateio_futures_arbitrage_signal.py
while maintaining the architectural patterns from the base multi-spot-futures strategy framework.

Key Features:
- Simple market-market order execution (no complex limit order logic)
- Fee-adjusted spread calculations with quantile-based thresholds
- Dynamic threshold optimization based on volatility
- Minimal configuration and straightforward arbitrage execution
- Integration with separated domain architecture
"""

import asyncio
import numpy as np
from collections import deque
from typing import Dict, Optional, Type, List
from datetime import datetime, timezone, timedelta

from db.models import Symbol
from exchanges.structs import ExchangeEnum, BookTicker, Order
from exchanges.structs.common import Side
from exchanges.structs.enums import KlineInterval
from infrastructure.logging import HFTLoggerInterface
from trading.strategies.implementations.base_strategy.pnl_tracker import PositionChange
from trading.strategies.implementations.base_strategy.position_manager import PositionManager
from trading.strategies.structs import MarketData

from trading.strategies.implementations.base_strategy.base_multi_spot_futures_strategy import (
    BaseMultiSpotFuturesArbitrageTask,
    BaseMultiSpotFuturesTaskContext
)
from trading.data_sources.column_utils import get_column_key
from trading.data_sources.book_ticker.book_ticker_source import BookTickerDbSource
from utils.logging_utils import disable_default_exchange_logging


class SpotFuturesTaskContext(BaseMultiSpotFuturesTaskContext, kw_only=True):
    """
    Minimal context for simplified spot-futures arbitrage strategy.
    
    Contains only essential parameters for threshold-based market execution
    without the complexity of limit order management or complex arbitrage setups.
    """
    name: str = "spot_futures_task"
    
    # Quantile-based threshold parameters (integrated from signal logic)
    entry_quantile: float = 0.75          # 75th percentile for entry threshold
    exit_quantile: float = 0.25           # 25th percentile for exit threshold
    min_spread_threshold: float = 0.0015  # Minimum spread above fees (0.15%)
    
    # Fee structure (simplified)
    spot_taker_fee: float = 0.0005        # 0.05% default spot taker fee
    futures_taker_fee: float = 0.0006     # 0.06% default futures taker fee
    
    # Strategy parameters
    historical_window_hours: int = 24     # Hours of history for quantile calculation
    volatility_adjustment: bool = True    # Enable adaptive thresholds based on volatility
    max_daily_trades: int = 50           # Trade frequency limit for risk management


class SpotFuturesStrategyTask(BaseMultiSpotFuturesArbitrageTask[SpotFuturesTaskContext]):
    """
    Simplified spot-futures arbitrage strategy focused on market-market execution.
    
    This strategy removes the complex limit order logic from inventory_spot_strategy
    and instead implements simple market execution when fee-adjusted spread thresholds
    are met, using quantile-based threshold optimization from the signal framework.
    
    Architecture:
    - Extends BaseMultiSpotFuturesArbitrageTask for 1 spot + 1 futures pattern  
    - Uses fee-adjusted spread calculations with quantile-based entry/exit
    - Implements only market-market order execution (no limit orders)
    - Maintains delta hedge management from base class
    """
    
    name = "spot_futures_task"

    @property
    def context_class(self) -> Type[SpotFuturesTaskContext]:
        """Return the spot-futures task context class."""
        return SpotFuturesTaskContext

    def __init__(self,
                 context: SpotFuturesTaskContext,
                 logger: HFTLoggerInterface = None,
                 **kwargs):
        """Initialize simplified spot-futures arbitrage task."""
        super().__init__(context, logger, **kwargs)

        # Disable exchange logging for cleaner output
        disable_default_exchange_logging()

        # Initialize position managers mappings (simplified from inventory strategy)
        self._pos: Dict[ExchangeEnum, PositionManager] = {}
        
        # Dynamic column keys for market data (integrated from signal)
        if len(self.context.spot_settings) > 0:
            self.spot_exchange = self.context.spot_settings[0].exchange
        if self.context.hedge_settings:
            self.futures_exchange = self.context.hedge_settings.exchange
            
        # Initialize spread history for quantile calculations (optimized with deque for HFT performance)
        max_history_length = self.context.historical_window_hours * 12  # 5-minute intervals
        self._spread_history: deque = deque(maxlen=max_history_length)
        self._daily_trade_count: Dict[str, int] = {}
        
        # Current arbitrage state (simplified)
        self._current_favorable_direction: Optional[str] = None
        self._last_signal_time: Optional[datetime] = None
        
        # Historical data loading
        self._historical_data_loaded: bool = False

    async def start(self):
        """Initialize strategy with position manager mappings."""
        await super().start()
        
        # Create simplified position manager mappings
        if len(self._spot_managers) > 0:
            self._pos[self.spot_exchange] = self._spot_managers[0]
        if self.hedge_manager:
            self._pos[self.futures_exchange] = self.hedge_manager
        
        # Load initial spread history from database for immediate threshold calculations
        await self._load_initial_spread_history()

    async def stop(self):
        """Handle strategy shutdown."""
        await super().stop()

    def get_spot_book_ticker(self) -> BookTicker:
        """Get current spot book ticker."""
        return self._spot_ex[0].public.book_ticker[self.context.symbol]

    def get_futures_book_ticker(self) -> BookTicker:
        """Get current futures book ticker."""
        return self._hedge_ex.public.book_ticker[self.context.symbol]

    async def _load_initial_spread_history(self):
        """
        Load initial spread history from database book ticker snapshots.
        
        This provides historical context for quantile-based threshold calculations
        similar to mexc_gateio_futures_arbitrage_signal.py preloading.
        """
        try:
            if self._historical_data_loaded:
                return

            self.logger.info("📊 Loading initial spread history from database...")
            
            # Create BookTickerDbSource for historical data
            db_source = BookTickerDbSource()
            
            # Define exchanges to load data for
            exchanges = [self.spot_exchange, self.futures_exchange]
            
            # Load historical data (use same timeframe as signal uses for backtesting)
            end_time = datetime.now(timezone.utc)
            # start_time = end_time - timedelta(hours=self.context.historical_window_hours)
            
            # Get multi-exchange data for both spot and futures
            df = await db_source.get_multi_exchange_data(
                exchanges=exchanges, 
                symbol=self.context.symbol, 
                hours=self.context.historical_window_hours,
                date_to=end_time,
                timeframe=KlineInterval.MINUTE_1 # 5-minute intervals for good granularity
            )
            
            if df.empty:
                self.logger.warning("⚠️ No historical book ticker data found in database")
                return
            
            self.logger.info(f"📈 Loaded {len(df)} historical data points")
            
            # Generate dynamic column keys for consistency
            spot_bid_col = get_column_key(self.spot_exchange, 'bid_price')
            spot_ask_col = get_column_key(self.spot_exchange, 'ask_price')
            futures_bid_col = get_column_key(self.futures_exchange, 'bid_price')
            futures_ask_col = get_column_key(self.futures_exchange, 'ask_price')
            
            # Check if required columns exist
            required_cols = [spot_bid_col, spot_ask_col, futures_bid_col, futures_ask_col]
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                self.logger.warning(f"⚠️ Missing columns in historical data: {missing_cols}")
                return
            
            # Calculate historical fee-adjusted spreads
            total_fees = self.context.spot_taker_fee + self.context.futures_taker_fee
            
            # Spot to Futures: Buy spot, sell futures
            # Profitable when: futures_bid - spot_ask > total_fees  
            spot_to_futures_spreads = ((df[futures_bid_col] - df[spot_ask_col]) / 
                                       df[spot_ask_col]) - total_fees
            
            # Futures to Spot: Buy futures, sell spot
            # Profitable when: spot_bid - futures_ask > total_fees
            futures_to_spot_spreads = ((df[spot_bid_col] - df[futures_ask_col]) / 
                                       df[futures_ask_col]) - total_fees
            
            # Use maximum spread for simplified history tracking (similar to signal logic)
            historical_spreads = np.maximum(spot_to_futures_spreads, futures_to_spot_spreads)
            
            # Filter out NaN values and convert to list
            valid_spreads = historical_spreads.dropna().tolist()
            
            if len(valid_spreads) > 0:
                # Initialize deque with recent data (deque will automatically limit to maxlen)
                recent_data = valid_spreads[-self.context.historical_window_hours * 60:]  # Keep recent data
                self._spread_history.extend(recent_data)
                self.logger.info(f"✅ Initialized spread history with {len(self._spread_history)} data points")
                self.logger.info(f"📊 Spread range: {min(self._spread_history):.4f}% to {max(self._spread_history):.4f}%")
            else:
                self.logger.warning("⚠️ No valid spread data calculated from historical book tickers")
            
            self._historical_data_loaded = True
            
        except Exception as e:
            self.logger.error(f"❌ Error loading initial spread history: {e}")
            import traceback
            traceback.print_exc()

    @property
    def spot_position_qty(self) -> float:
        """Get current spot position quantity."""
        if self.spot_exchange in self._pos:
            return self._pos[self.spot_exchange].qty
        return 0.0

    @property 
    def futures_position_qty(self) -> float:
        """Get current futures position quantity (short positions are negative)."""
        if self.futures_exchange in self._pos:
            return self._pos[self.futures_exchange].qty
        return 0.0

    def calculate_fee_adjusted_spreads(self) -> Dict[str, float]:
        """
        Calculate fee-adjusted spreads for both arbitrage directions.
        
        Integrated from mexc_gateio_futures_arbitrage_signal.py logic (lines 145-154)
        
        Returns:
            Dictionary with spread calculations for both directions
        """
        spot_ticker = self.get_spot_book_ticker()
        futures_ticker = self.get_futures_book_ticker()
        
        if not spot_ticker or not futures_ticker:
            return {'spot_to_futures': 0.0, 'futures_to_spot': 0.0}

        # Calculate total trading fees for both directions
        total_fees = self.context.spot_taker_fee + self.context.futures_taker_fee
        
        # Spot to Futures direction: Buy spot, sell futures
        # Profitable when: futures_bid - spot_ask > total_fees
        spot_to_futures_spread = ((futures_ticker.bid_price - spot_ticker.ask_price) / 
                                  spot_ticker.ask_price) - total_fees
        
        # Futures to Spot direction: Buy futures, sell spot  
        # Profitable when: spot_bid - futures_ask > total_fees
        futures_to_spot_spread = ((spot_ticker.bid_price - futures_ticker.ask_price) / 
                                  futures_ticker.ask_price) - total_fees
        
        return {
            'spot_to_futures': spot_to_futures_spread,
            'futures_to_spot': futures_to_spot_spread
        }

    def update_spread_history(self, spreads: Dict[str, float]) -> Dict[str, float]:
        """
        Update spread history and calculate percentiles for threshold decisions.
        
        Integrated from signal logic (lines 156-177) with simplified single-spread tracking.
        Optimized with deque for O(1) append operations in HFT environments.
        
        Args:
            spreads: Current spread calculations
            
        Returns:
            Dictionary with percentile information for decision making
        """
        # Use the maximum spread for history tracking (simplified approach)
        current_max_spread = max(spreads['spot_to_futures'], spreads['futures_to_spot'])
        self._spread_history.append(current_max_spread)  # O(1) append with automatic size limiting
        
        # Calculate percentiles for current spreads (need sufficient history)
        if len(self._spread_history) < 50:
            return {'percentile_rank': 50.0, 'volatility': 0.0, 'sufficient_history': False}
        
        sorted_history = sorted(self._spread_history)
        percentile_rank = (np.searchsorted(sorted_history, current_max_spread) / 
                          len(sorted_history) * 100)
        
        volatility = np.std(self._spread_history)
        
        return {
            'percentile_rank': percentile_rank,
            'volatility': volatility,
            'sufficient_history': True
        }

    def should_enter_arbitrage(self, spreads: Dict[str, float], percentile_info: Dict[str, float]) -> Dict[str, any]:
        """
        Determine if arbitrage entry conditions are met using quantile-based logic.
        
        Integrated from signal logic (lines 185-204) with fee-adjusted profitability checks.
        
        Args:
            spreads: Current fee-adjusted spread calculations
            percentile_info: Percentile and volatility information
            
        Returns:
            Dictionary with entry decision and direction information
        """
        if not percentile_info['sufficient_history']:
            return {'should_enter': False, 'direction': None, 'reason': 'insufficient_history'}

        # Calculate entry threshold with volatility adjustment
        entry_threshold = self.context.entry_quantile * 100
        if self.context.volatility_adjustment:
            # Increase threshold in volatile periods (from signal line 188)
            entry_threshold *= (1 + percentile_info['volatility'] * 10)

        # Check if current spread percentile meets entry threshold
        if percentile_info['percentile_rank'] < entry_threshold:
            return {'should_enter': False, 'direction': None, 'reason': 'below_entry_threshold'}

        # Determine profitable direction and check minimum spread threshold
        total_fees = self.context.spot_taker_fee + self.context.futures_taker_fee
        
        spot_to_futures_profitable = (spreads['spot_to_futures'] > 
                                      total_fees + self.context.min_spread_threshold)
        futures_to_spot_profitable = (spreads['futures_to_spot'] > 
                                      total_fees + self.context.min_spread_threshold)
        
        if spot_to_futures_profitable:
            return {'should_enter': True, 'direction': 'spot_to_futures', 'reason': 'profitable_spread'}
        elif futures_to_spot_profitable:
            return {'should_enter': True, 'direction': 'futures_to_spot', 'reason': 'profitable_spread'}
        else:
            return {'should_enter': False, 'direction': None, 'reason': 'spread_below_min_threshold'}

    def should_exit_arbitrage(self, percentile_info: Dict[str, float]) -> bool:
        """
        Determine if arbitrage exit conditions are met.
        
        Args:
            percentile_info: Current percentile information
            
        Returns:
            True if should exit current positions
        """
        if not percentile_info['sufficient_history']:
            return False
            
        exit_threshold = self.context.exit_quantile * 100
        return percentile_info['percentile_rank'] <= exit_threshold

    def _check_daily_trade_limit(self) -> bool:
        """Check if daily trade limit has been reached."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        current_count = self._daily_trade_count.get(today, 0)
        return current_count < self.context.max_daily_trades

    def _increment_daily_trade_count(self):
        """Increment daily trade counter."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        self._daily_trade_count[today] = self._daily_trade_count.get(today, 0) + 1

    async def execute_market_arbitrage(self, direction: str) -> bool:
        """
        Execute market-market arbitrage trade in the specified direction.
        
        This is the core simplified execution logic - only market orders, no limit orders.
        
        Args:
            direction: 'spot_to_futures' or 'futures_to_spot'
            
        Returns:
            True if execution initiated successfully
        """
        try:
            if not self._check_daily_trade_limit():
                self.logger.info("Daily trade limit reached, skipping arbitrage")
                return False

            # Calculate trade quantity
            trade_qty = self.context.order_qty or (self.context.total_quantity * 0.1)
            
            if direction == 'spot_to_futures':
                # Buy spot, sell futures
                spot_side = Side.BUY
                futures_side = Side.SELL
                
                # Validate spot can buy more
                if self.spot_position_qty + trade_qty > self.context.total_quantity:
                    self.logger.info("Spot position would exceed total quantity limit")
                    return False
                    
            elif direction == 'futures_to_spot':
                # Sell spot, buy futures  
                spot_side = Side.SELL
                futures_side = Side.BUY
                
                # Validate spot has inventory to sell
                spot_manager = self._pos[self.spot_exchange]
                min_sell_qty = spot_manager.get_min_base_qty(Side.SELL)
                if self.spot_position_qty < min_sell_qty:
                    self.logger.info("Insufficient spot position to sell")
                    return False
                    
                trade_qty = min(trade_qty, self.spot_position_qty)
            else:
                return False

            # Execute both legs simultaneously (market-market execution)
            self.logger.info(f"🔄 Executing {direction} arbitrage: qty={trade_qty}")
            
            tasks = [
                self._pos[self.spot_exchange].place_market_order(side=spot_side, quantity=trade_qty),
                self._pos[self.futures_exchange].place_market_order(side=futures_side, quantity=trade_qty)
            ]
            
            await asyncio.gather(*tasks)
            self._increment_daily_trade_count()
            self._current_favorable_direction = direction
            self._last_signal_time = datetime.now(timezone.utc)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error executing market arbitrage: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def manage_delta_hedge(self):
        """
        Manage delta hedge using base class implementation.
        
        Reuses the delta hedge logic from BaseMultiSpotFuturesArbitrageTask
        """
        delta = self.spot_position_qty - abs(self.futures_position_qty)

        if abs(delta) < self._hedge_ex.public.get_min_base_quantity(self.context.symbol):
            return False

        self.logger.info(f"⚖️ Detected position imbalance: delta={delta:.8f}, "
                         f"spot={self.spot_position_qty}, futures={self.futures_position_qty}")

        book_ticker = self._hedge_ex.public.book_ticker[self.context.symbol]
        price = book_ticker.ask_price if delta < 0 else book_ticker.bid_price
        side = Side.SELL if delta > 0 else Side.BUY
        self.logger.info(f"⚖️ Re-balance futures: side={side.name}, qty={abs(delta):.8f} at price={price:.8f}")

        await self.hedge_manager.place_order(side=side, price=price, quantity=abs(delta), is_market=True)
        return True

    async def _on_order_filled_callback(self, order: Order, change: PositionChange):
        """
        Handle order fill events with simplified logic.
        
        Unlike the complex inventory strategy, this just logs fills and manages delta hedge.
        """
        self.logger.info(f"✅ {order.exchange.name} Order filled: {order} -> {self.status()}")
        
        # Skip hedge fills for callback processing
        if order.exchange == self.futures_exchange:
            return
            
        # After spot fills, check if we need delta hedge rebalancing
        await self.manage_delta_hedge()

    async def _manage_positions(self):
        """
        Core position management with simplified threshold-based logic.
        
        This replaces the complex _manage_arbitrage logic from inventory strategy
        with simple threshold-based decision making using fee-adjusted spreads.
        """
        try:
            # Calculate current fee-adjusted spreads
            spreads = self.calculate_fee_adjusted_spreads()
            percentile_info = self.update_spread_history(spreads)
            
            # Determine if we should enter new arbitrage
            entry_decision = self.should_enter_arbitrage(spreads, percentile_info)
            
            if entry_decision['should_enter']:
                executed = await self.execute_market_arbitrage(entry_decision['direction'])
                if executed:
                    self.logger.info(f"🔥 Entered arbitrage: {entry_decision['direction']} "
                                   f"(reason: {entry_decision['reason']})")
            
            # Check for exit conditions (if we have active positions)
            elif (self.spot_position_qty > 0 and abs(self.futures_position_qty) > 0 and
                  self.should_exit_arbitrage(percentile_info)):
                
                # Simple exit: close positions toward target allocation
                if self.spot_position_qty > self.context.total_quantity * 0.5:
                    # Reduce spot position
                    reduce_qty = min(self.spot_position_qty * 0.5, self.context.order_qty or 1.0)
                    await self._pos[self.spot_exchange].place_market_order(Side.SELL, reduce_qty)
                    self.logger.info(f"🔻 Exiting arbitrage: reducing spot position by {reduce_qty}")

            # Always manage delta hedge
            await self.manage_delta_hedge()
            
        except Exception as e:
            self.logger.error(f"❌ Error managing positions: {e}")
            import traceback
            traceback.print_exc()

    def status(self) -> str:
        """Generate status string for logging."""
        return (f"SPOT ({self.spot_exchange.name}): {self.spot_position_qty:.8f}, "
                f"FUTURES ({self.futures_exchange.name}): {self.futures_position_qty:.8f}")


def create_spot_futures_strategy_task(
    symbol: Symbol,
    spot_exchange: ExchangeEnum,
    futures_exchange: ExchangeEnum,
    order_qty: float,
    total_quantity: float,
    entry_quantile: float = 0.75,
    exit_quantile: float = 0.25,
    **kwargs
) -> SpotFuturesStrategyTask:
    """
    Factory function for creating simplified spot-futures arbitrage strategy.
    
    Args:
        symbol: Trading symbol
        spot_exchange: Exchange for spot trading
        futures_exchange: Exchange for futures trading
        order_qty: Size of each arbitrage trade
        total_quantity: Maximum total position size
        entry_quantile: Percentile threshold for entry (0.70-0.80 recommended)
        exit_quantile: Percentile threshold for exit (0.20-0.30 recommended)
        **kwargs: Additional context parameters
        
    Returns:
        Configured SpotFuturesStrategyTask instance
    """
    spot_settings = [MarketData(exchange=spot_exchange)]
    hedge_settings = MarketData(exchange=futures_exchange)

    context = SpotFuturesTaskContext(
        symbol=symbol,
        order_qty=order_qty,
        total_quantity=total_quantity,
        spot_settings=spot_settings,
        hedge_settings=hedge_settings,
        entry_quantile=entry_quantile,
        exit_quantile=exit_quantile,
        **kwargs
    )
    
    return SpotFuturesStrategyTask(context=context)