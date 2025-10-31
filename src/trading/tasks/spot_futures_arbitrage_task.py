"""
Spot-Futures Arbitrage Task - TaskManager Compatible

Exchange-agnostic arbitrage strategy that extends BaseTradingTask.
Supports arbitrage between any spot and futures exchanges with integrated profit tracking.

Key Features:
- Automatic profit calculation during position updates
- Real-time profit logging on exit operations
- HFT-optimized performance with sub-millisecond execution
- Comprehensive position and profit analytics
"""

import asyncio
import time
import numpy as np
from typing import Optional, Dict, Type, Literal

from trading.tasks.base_arbitrage_task import BaseArbitrageTask
from trading.tasks.base_task import StateHandler
from trading.tasks.arbitrage_task_context import (
    ArbitrageTaskContext,
    TradingParameters,
    ArbitrageOpportunity,
    ValidationResult
)
from exchanges.structs import Symbol, Side, ExchangeEnum, Order
from infrastructure.logging import HFTLoggerInterface, get_logger
from utils import flip_side
from trading.analysis.arbitrage_signals import calculate_arb_signals, Signal
from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer

# Import existing arbitrage components
from trading.task_manager.exchange_manager import (
    ExchangeManager,
    OrderPlacementParams,
    ExchangeRole,
    ArbitrageExchangeType
)


class SpotFuturesArbitrageTask(BaseArbitrageTask):
    """
    Exchange-agnostic spot-futures arbitrage strategy with integrated profit tracking.
    
    Extends BaseTradingTask to provide full TaskManager integration while preserving
    all arbitrage logic and performance optimizations. Supports any combination of
    spot and futures exchanges.
    
    Profit Tracking Features:
    - Automatic profit calculation during position updates
    - Real-time profit tracking per exchange (spot/futures)
    - Comprehensive profit logging on exit operations
    - HFT-optimized performance with minimal overhead
    """

    name: str = "SpotFuturesArbitrageTask"

    @property
    def spot_ticker(self):
        return self.exchange_manager.get_exchange('spot').public.book_ticker.get(self.context.symbol)

    @property
    def futures_ticker(self):
        return self.exchange_manager.get_exchange('futures').public.book_ticker.get(self.context.symbol)

    @property
    def spot_vs_futures_spread(self) -> float:
        """Calculate current spot vs futures spread using same formula as backtest."""
        spot_ticker = self.spot_ticker
        futures_ticker = self.futures_ticker
        
        # Use spot ask (buy price) vs futures bid (sell price) for entry opportunity
        spread = (futures_ticker.bid_price - spot_ticker.ask_price) / futures_ticker.bid_price * 100
        return spread
    
    def _calculate_execution_spreads(self) -> Dict[str, float]:
        """Calculate current bid-ask spreads for each exchange in percentage."""
        spreads = {}
        
        # Spot exchange spread
        spot_ticker = self.spot_ticker
        spot_spread = ((spot_ticker.ask_price - spot_ticker.bid_price) / 
                      spot_ticker.ask_price * 100)
        spreads['spot'] = spot_spread
        
        # Futures exchange spread
        futures_ticker = self.futures_ticker
        futures_spread = ((futures_ticker.ask_price - futures_ticker.bid_price) / 
                         futures_ticker.ask_price * 100)
        spreads['futures'] = futures_spread
        
        # Total execution spread (entry + exit costs)
        spreads['total'] = spot_spread + futures_spread
        
        return spreads

    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: ArbitrageTaskContext,
                 spot_exchange: ExchangeEnum,
                 futures_exchange: ExchangeEnum,
                 **kwargs):
        """Initialize exchange-agnostic spot-futures arbitrage strategy."""
        # Initialize base arbitrage task with common setup
        super().__init__(logger, context, spot_exchange, futures_exchange, **kwargs)
        
        # Initialize historical spreads for signal generation with numpy arrays
        self.historical_spreads = {
            'spot_vs_futures': np.array([], dtype=np.float64),  # Spot vs Futures spread
            'execution_spreads': np.array([], dtype=np.float64)  # Combined execution spread
        }
        
        # Signal generation setup
        self._candle_data_loaded = False
        self._spread_check_counter = 0
        self._spread_rejection_counter = 0
        self._last_spread_log_time = asyncio.get_event_loop().time()
        
        # Spread validation parameters  
        self.min_profit_margin = 0.1  # 0.1% minimum profit margin
        self.max_acceptable_spread = 0.2  # 0.2% maximum acceptable total spread

    async def _load_initial_spread_history(self):
        """Load initial spread history from candles once during initialization."""
        if self._candle_data_loaded:
            return
            
        try:
            self.logger.info("📥 Loading initial spread history from candles...")
            
            # Import analyzer here to avoid circular imports
            from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer
            
            analyzer = ArbitrageAnalyzer()
            # Load 7 days of candle data for historical context
            df, _ = await analyzer.run_analysis(self.context.symbol, days=7)
            
            if df.empty:
                self.logger.warning("⚠️ No candle data received from analyzer")
                return
            
            # Extract spot vs futures spread from candle data
            # For spot-futures arbitrage, we use the spread between spot and futures prices
            if 'spot_vs_futures_arb' in df.columns:
                self.historical_spreads['spot_vs_futures'] = df['spot_vs_futures_arb'].values.astype(np.float64)
            else:
                # Calculate from individual exchange data if available
                self.logger.warning("⚠️ No pre-calculated spread column found, using current real-time data only")
                
            loaded_count = len(self.historical_spreads['spot_vs_futures'])
            
            if loaded_count < 50:
                self.logger.warning(f"⚠️ Insufficient historical data: {loaded_count} points (need at least 50)")
            else:
                self.logger.info(f"✅ Loaded {loaded_count} historical spread data points")
            
            self._candle_data_loaded = True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load initial spread history: {e}")
            import traceback
            self.logger.debug(f"Full error traceback: {traceback.format_exc()}")

    def _update_historical_spreads(self):
        """Update historical spreads with current real-time data."""
        try:
            # Calculate current spreads
            current_spot_vs_futures = self.spot_vs_futures_spread
            execution_spreads = self._calculate_execution_spreads()
            current_execution_spread = execution_spreads['total']
            
            # Append to historical data
            self.historical_spreads['spot_vs_futures'] = np.append(
                self.historical_spreads['spot_vs_futures'], 
                current_spot_vs_futures
            )
            self.historical_spreads['execution_spreads'] = np.append(
                self.historical_spreads['execution_spreads'], 
                current_execution_spread
            )
            
            # Keep only recent history (e.g., last 500 periods for signal calculation)
            max_history = 500
            if len(self.historical_spreads['spot_vs_futures']) > max_history:
                self.historical_spreads['spot_vs_futures'] = self.historical_spreads['spot_vs_futures'][-max_history:]
                self.historical_spreads['execution_spreads'] = self.historical_spreads['execution_spreads'][-max_history:]
                
        except Exception as e:
            self.logger.error(f"❌ Error updating historical spreads: {e}")

    async def _validate_spread_profitability(self, signal: Signal = None) -> bool:
        """
        Enhanced spread validation using ArbStats for dynamic thresholds and entry/exit specific logic.
        
        Args:
            signal: Current arbitrage signal for context-specific validation
            
        Returns:
            True if spreads are acceptable for trading, False otherwise
        """
        # Track validation attempts
        self._spread_check_counter += 1
        
        # Get current signal and ArbStats if not provided
        if signal is None:
            signal_result = self._get_current_signal_with_stats()
            signal = signal_result.signal
        else:
            signal_result = self._get_current_signal_with_stats()
        
        # Get current execution spreads and fees
        execution_spreads = self._calculate_execution_spreads()
        total_spread_cost = execution_spreads['total']
        actual_fees = self._calculate_actual_fees()
        
        # Entry/Exit specific validation
        if signal == Signal.ENTER:
            validation_result = self._validate_entry_spreads(
                signal_result, total_spread_cost, actual_fees, execution_spreads
            )
        elif signal == Signal.EXIT:
            validation_result = self._validate_exit_spreads(
                signal_result, total_spread_cost, actual_fees, execution_spreads
            )
        else:  # HOLD
            return False  # Don't trade on HOLD signals
        
        # Update rejection counter
        if not validation_result:
            self._spread_rejection_counter += 1
        
        # Periodic spread monitoring (every 60 seconds)
        current_time = asyncio.get_event_loop().time()
        if current_time - self._last_spread_log_time > 60:
            self._last_spread_log_time = current_time
            rejection_rate = (self._spread_rejection_counter / max(1, self._spread_check_counter)) * 100
            self.logger.info(
                f"📊 Spread monitoring stats: checks={self._spread_check_counter}, "
                f"rejections={self._spread_rejection_counter} ({rejection_rate:.1f}%), "
                f"current_spreads={total_spread_cost:.3f}%",
                spot_spread=f"{execution_spreads['spot']:.3f}%",
                futures_spread=f"{execution_spreads['futures']:.3f}%"
            )
        
        return validation_result

    def _get_current_signal_with_stats(self):
        """Get current arbitrage signal with full ArbStats."""
        if len(self.historical_spreads['spot_vs_futures']) < 50:
            # Return fallback signal for insufficient data
            from trading.analysis.arbitrage_signals import ArbSignal, ArbStats
            return ArbSignal(
                signal=Signal.HOLD,
                mexc_vs_gateio_futures=ArbStats(0, 0, 0, self.spot_vs_futures_spread),
                gateio_spot_vs_futures=ArbStats(0, 0, 0, self._calculate_execution_spreads()['total'])
            )
        
        return calculate_arb_signals(
            mexc_vs_gateio_futures_history=self.historical_spreads['spot_vs_futures'],
            gateio_spot_vs_futures_history=self.historical_spreads['execution_spreads'],
            current_mexc_vs_gateio_futures=self.spot_vs_futures_spread,
            current_gateio_spot_vs_futures=self._calculate_execution_spreads()['total']
        )

    def _calculate_actual_fees(self) -> float:
        """Calculate actual trading fees from exchange configurations."""
        # Get fees from context parameters (these should be set from exchange configs)
        spot_fee = getattr(self.context.params, 'spot_fee', 0.001)  # 0.1% default
        futures_fee = getattr(self.context.params, 'fut_fee', 0.001)  # 0.1% default
        
        # Convert to percentage
        return (spot_fee + futures_fee) * 100

    def _validate_entry_spreads(self, signal_result, total_spread_cost: float, 
                               actual_fees: float, execution_spreads: dict) -> bool:
        """
        Validate spreads for ENTRY signals using dynamic ArbStats thresholds.
        
        For entries, we care most about:
        1. The arbitrage opportunity exceeds statistical entry threshold
        2. Total costs (spreads + fees) don't consume too much of the edge
        3. Current spreads aren't abnormally high
        """
        # Extract ArbStats for dynamic thresholds
        mexc_stats = signal_result.mexc_vs_gateio_futures
        
        # 1. Check if opportunity exceeds dynamic entry threshold (25th percentile of mins)
        entry_edge = abs(mexc_stats.current - mexc_stats.min_25pct)
        
        # 2. Calculate total trading costs
        total_costs = total_spread_cost + actual_fees
        
        # 3. Ensure sufficient profit margin after costs
        net_edge = abs(mexc_stats.current) - total_costs
        required_profit = self.min_profit_margin
        
        # Entry validation logic
        if net_edge < required_profit:
            self.logger.debug(
                f"⚠️ Entry validation failed: net_edge={net_edge:.3f}% < "
                f"required={required_profit:.3f}% | "
                f"opportunity={abs(mexc_stats.current):.3f}%, costs={total_costs:.3f}%",
                entry_threshold=f"{mexc_stats.min_25pct:.3f}%",
                spot_spread=f"{execution_spreads['spot']:.3f}%",
                futures_spread=f"{execution_spreads['futures']:.3f}%",
                fees=f"{actual_fees:.3f}%"
            )
            return False
        
        # 4. Check if current spreads are within acceptable range (relaxed for good opportunities)
        max_spread_multiplier = 2.0 if abs(mexc_stats.current) > abs(mexc_stats.mean) * 1.5 else 1.0
        adjusted_max_spread = self.max_acceptable_spread * max_spread_multiplier
        
        if total_spread_cost > adjusted_max_spread:
            self.logger.debug(
                f"⚠️ Entry validation failed: spreads={total_spread_cost:.3f}% > "
                f"adjusted_max={adjusted_max_spread:.3f}% (multiplier={max_spread_multiplier:.1f})",
                opportunity_quality=f"{abs(mexc_stats.current):.3f}% vs mean {abs(mexc_stats.mean):.3f}%"
            )
            return False
        
        # Success logging
        self.logger.info(
            f"✅ Entry validation passed: net_edge={net_edge:.3f}% > required={required_profit:.3f}%",
            opportunity=f"{abs(mexc_stats.current):.3f}%",
            entry_threshold=f"{mexc_stats.min_25pct:.3f}%",
            costs=f"{total_costs:.3f}%",
            spreads=f"{total_spread_cost:.3f}%",
            fees=f"{actual_fees:.3f}%"
        )
        return True

    def _validate_exit_spreads(self, signal_result, total_spread_cost: float,
                              actual_fees: float, execution_spreads: dict) -> bool:
        """
        Validate spreads for EXIT signals using dynamic ArbStats thresholds.
        
        For exits, we care most about:
        1. We're in a profitable exit zone (above 25th percentile of maxes)
        2. Exit costs don't erode existing profit too much
        3. Better to exit with lower costs than wait for perfect opportunity
        """
        # Extract ArbStats for dynamic thresholds
        gateio_stats = signal_result.gateio_spot_vs_futures
        
        # For exits, be more permissive on spreads since timing is critical
        exit_edge = gateio_stats.current - gateio_stats.max_25pct
        
        # Calculate exit costs (generally should be lower threshold than entry)
        total_costs = total_spread_cost + actual_fees
        
        # For exits, allow higher spread costs if we're in good exit territory
        exit_spread_tolerance = self.max_acceptable_spread * 1.5  # 50% more permissive
        
        if total_spread_cost > exit_spread_tolerance:
            self.logger.debug(
                f"⚠️ Exit validation failed: spreads={total_spread_cost:.3f}% > "
                f"exit_tolerance={exit_spread_tolerance:.3f}%",
                exit_signal_strength=f"{exit_edge:.3f}%",
                exit_threshold=f"{gateio_stats.max_25pct:.3f}%"
            )
            return False
        
        # More permissive profit check for exits (preserve capital, don't optimize for max profit)
        min_exit_profit = self.min_profit_margin * 0.5  # Half the entry requirement
        if exit_edge < min_exit_profit:
            self.logger.debug(
                f"⚠️ Exit validation failed: exit_edge={exit_edge:.3f}% < "
                f"min_exit_profit={min_exit_profit:.3f}%",
                current_signal=f"{gateio_stats.current:.3f}%",
                exit_threshold=f"{gateio_stats.max_25pct:.3f}%"
            )
            return False
        
        # Success logging
        self.logger.info(
            f"✅ Exit validation passed: exit_edge={exit_edge:.3f}% > min={min_exit_profit:.3f}%",
            exit_signal=f"{gateio_stats.current:.3f}%",
            exit_threshold=f"{gateio_stats.max_25pct:.3f}%",
            costs=f"{total_costs:.3f}%",
            spread_tolerance=f"{exit_spread_tolerance:.3f}%"
        )
        return True

    def _check_arbitrage_signal(self) -> Signal:
        """
        Check for arbitrage entry/exit signals using dynamic thresholds.
        
        Returns:
            Signal enum (ENTER, EXIT, or HOLD)
        """
        try:
            # Ensure we have enough historical data
            if len(self.historical_spreads['spot_vs_futures']) < 50:
                return Signal.HOLD
            
            # Generate signal using current market data with historical context
            signal_result = calculate_arb_signals(
                mexc_vs_gateio_futures_history=self.historical_spreads['spot_vs_futures'],
                gateio_spot_vs_futures_history=self.historical_spreads['execution_spreads'],
                current_mexc_vs_gateio_futures=self.spot_vs_futures_spread,
                current_gateio_spot_vs_futures=self._calculate_execution_spreads()['total']
            )
            
            return signal_result.signal
            
        except Exception as e:
            self.logger.error(f"❌ Error checking arbitrage signal: {e}")
            return Signal.HOLD

    async def _should_exit_positions_signal_based(self) -> bool:
        """Check if should exit existing positions using signal-based approach."""
        if not self.context.positions_state.has_positions:
            return False

        # Check for EXIT signal or timeout/profit conditions
        signal = self._check_arbitrage_signal()
        
        # Traditional exit conditions (timeout, profit target)
        traditional_exit = await self._should_exit_positions()
        
        # Exit if signal says EXIT OR traditional conditions are met
        if signal == Signal.EXIT:
            self.logger.info("🔄 EXIT signal detected - closing positions")
            return True
        elif traditional_exit:
            return True
            
        return False

    async def _create_opportunity_from_signal(self) -> Optional[ArbitrageOpportunity]:
        """Create arbitrage opportunity based on current signal and market conditions."""
        try:
            spot_ticker = self.spot_ticker
            futures_ticker = self.futures_ticker
            
            # Calculate current spread (this is our opportunity)
            spread_pct = self.spot_vs_futures_spread
            
            # Calculate max quantity based on available liquidity
            max_quantity = self.round_to_contract_size(
                min(
                    spot_ticker.ask_quantity,
                    futures_ticker.bid_quantity,
                    self.context.single_order_size_usdt / spot_ticker.ask_price
                )
            )
            
            # Ensure meets minimum requirements
            min_spot_qty = self._get_minimum_order_base_quantity('spot')
            min_futures_qty = self._get_minimum_order_base_quantity('futures')
            min_required = max(min_spot_qty, min_futures_qty)
            
            if max_quantity < min_required:
                self.logger.debug(f"📊 Insufficient quantity: {max_quantity:.6f} < {min_required:.6f}")
                return None
            
            return ArbitrageOpportunity(
                direction='enter',
                spread_pct=spread_pct,
                buy_price=spot_ticker.ask_price,   # Buy spot
                sell_price=futures_ticker.bid_price,  # Sell futures
                max_quantity=max_quantity
            )
            
        except Exception as e:
            self.logger.error(f"❌ Error creating opportunity from signal: {e}")
            return None

    def get_unified_state_handlers(self) -> Dict[str, StateHandler]:
        """Provide complete unified state handler mapping.
        
        Includes both base states and arbitrage-specific states using string keys.
        """
        return {
            # Base state handlers
            'idle': self._handle_idle,
            'paused': self._handle_paused,
            'error': self._handle_error,
            'completed': self._handle_complete,
            'cancelled': self._handle_cancelled,
            'executing': self._handle_executing,
            # 'adjusting': self._handle_adjusting,

            # Arbitrage-specific state handlers
            'initializing': self._handle_initializing,
            'monitoring': self._handle_arbitrage_monitoring,
            'analyzing': self._handle_arbitrage_analyzing,
            'error_recovery': self._handle_arbitrage_error_recovery,
        }

    # async def _handle_executing(self):
    #     """Main execution logic - delegates to arbitrage state handlers."""
    #     # Delegate to arbitrage state machine
    #     arbitrage_state = self.context.arbitrage_state
    #
    #     if arbitrage_state == ArbitrageState.INITIALIZING:
    #         await self._handle_arbitrage_initializing()
    #     elif arbitrage_state == ArbitrageState.MONITORING:
    #         await self._handle_arbitrage_monitoring()
    #     elif arbitrage_state == ArbitrageState.ANALYZING:
    #         await self._handle_arbitrage_analyzing()
    #     elif arbitrage_state == ArbitrageState.EXECUTING:
    #         await self._handle_arbitrage_executing()
    #     elif arbitrage_state == ArbitrageState.ERROR_RECOVERY:
    #         await self._handle_arbitrage_error_recovery()
    #     else:
    #         # Default to monitoring
    #         self._transition_arbitrage_state('monitoring')
    #


    async def _handle_arbitrage_monitoring(self):
        """Monitor market and manage positions with real-time spread validation."""
        try:
            await self.exchange_manager.check_connection(True)

            # Load historical spread data once during first run
            await self._load_initial_spread_history()
            
            # Update historical spreads with current real-time data
            self._update_historical_spreads()

            # Check order updates first
            await self._check_order_updates()

            # Check limit orders if enabled
            # if self.context.params.limit_orders_enabled:
            #     await self._check_limit_orders()

            await self._process_imbalance()

            # Check if should exit positions using signal-based approach
            if await self._should_exit_positions_signal_based():
                await self._exit_all_positions()
                return

            # Look for new opportunities using signal-based approach
            if not self.context.positions_state.has_positions:
                # Check arbitrage signal and validate spreads
                signal = self._check_arbitrage_signal()
                spread_valid = await self._validate_spread_profitability(signal)
                
                if signal == Signal.ENTER and spread_valid:
                    # Create opportunity based on current market conditions
                    opportunity = await self._create_opportunity_from_signal()
                    if opportunity:
                        self.logger.info(f"💰 Signal-based opportunity: {opportunity.spread_pct:.4f}% spread")
                        self.evolve_context(current_opportunity=opportunity)
                        self._transition_arbitrage_state('analyzing')
                elif signal == Signal.ENTER and not spread_valid:
                    self.logger.debug("🚫 Entry signal detected but spread validation failed")
                elif signal != Signal.HOLD:
                    self.logger.debug(f"📊 Signal: {signal.value} (not applicable for current state)")

        except Exception as e:
            self.logger.error(f"Monitoring failed: {e}")
            self._transition_arbitrage_state('error_recovery')

    async def _handle_arbitrage_analyzing(self):
        """Analyze current opportunity."""
        if not self.context.current_opportunity:
            self._transition_arbitrage_state('monitoring')
            return

        opportunity = self.context.current_opportunity
        if opportunity.is_fresh():
            self._transition_arbitrage_state('executing')
        else:
            self.logger.info("⚠️ Opportunity no longer fresh")
            self.evolve_context(current_opportunity=None)
            self._transition_arbitrage_state('monitoring')

    async def _handle_executing(self):
        """Execute arbitrage trades."""
        if not self.context.current_opportunity:
            self._transition_arbitrage_state('monitoring')
            return

        try:
            success = await self._enter_positions(self.context.current_opportunity)

            if success:
                self.logger.info("✅ Arbitrage execution successful")
            else:
                self.logger.warning("❌ Arbitrage execution failed")

            self.evolve_context(current_opportunity=None)

        except Exception as e:
            self.logger.error(f"Execution error: {e}")

        self._transition_arbitrage_state('monitoring')



    # Unified utility methods

    def _get_entry_cost_pct(self, buy_price: float, sell_price: float) -> float:
        """Calculate entry cost percentage."""
        return ((buy_price - sell_price) / buy_price) * 100

    async def _identify_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """Identify arbitrage opportunities using backtesting logic."""

        spot_ticker = self.spot_ticker
        futures_ticker = self.futures_ticker

        # Calculate entry cost
        entry_cost_pct = self._get_entry_cost_pct(spot_ticker.ask_price, futures_ticker.bid_price)

        if self._increment_debug_counter():
            print(f'Entry cost {entry_cost_pct:.4f}% ({self.spot_exchange.name} -> {self.futures_exchange.name})')

        # Check if profitable (enter when cost is LOW, not high)
        if entry_cost_pct > self.context.params.max_entry_cost_pct:
            return None

        # Calculate max quantity
        max_quantity = self.round_to_contract_size(
            min(
                spot_ticker.ask_quantity,
                futures_ticker.bid_quantity,
                self.context.single_order_size_usdt / spot_ticker.ask_price
            )
        )

        # Ensure meets minimum requirements
        min_required = max(
            self._get_minimum_order_base_quantity('spot'),
            self._get_minimum_order_base_quantity('futures')
        )

        if max_quantity < min_required:
            return None

        return ArbitrageOpportunity(
            direction='enter',
            spread_pct=entry_cost_pct,
            buy_price=spot_ticker.ask_price,
            sell_price=futures_ticker.bid_price,
            max_quantity=max_quantity
        )

    async def _should_exit_positions(self) -> bool:
        """Check if should exit existing positions."""
        if not self.context.positions_state.has_positions:
            return False

        # Get position details
        spot_pos = self.context.positions_state.positions['spot']
        futures_pos = self.context.positions_state.positions['futures']

        # # Calculate P&L using backtesting logic with fees
        # spot_fee = self.context.params.spot_fee
        # fut_fee = self.context.params.fut_fee
        #
        # # Entry costs (what we paid)
        # entry_spot_cost = spot_pos.price * (1 + spot_fee)  # Bought spot with fee
        # entry_fut_receive = futures_pos.price * (1 - fut_fee)  # Sold futures with fee
        #
        # # Exit revenues (what we get)
        # exit_spot_receive = self.spot_ticker.bid_price * (1 - spot_fee)  # Sell spot with fee
        # exit_fut_cost = self.futures_ticker.ask_price * (1 + fut_fee)  # Buy futures with fee
        #
        # # P&L calculation
        # spot_pnl_pts = exit_spot_receive - entry_spot_cost
        # fut_pnl_pts = entry_fut_receive - exit_fut_cost
        # total_pnl_pts = spot_pnl_pts + fut_pnl_pts
        #
        # # P&L percentage
        # capital = entry_spot_cost
        # net_pnl_pct = (total_pnl_pts / capital) * 100

        net_pnl_pct = self._get_pos_net_pnl(spot_pos.price, futures_pos.price,
                                            self.spot_ticker.bid_price, self.futures_ticker.ask_price)

        # Check exit conditions
        exit_now = False
        if self._increment_debug_counter():
            print(f'{self.context.symbol} Exit pnl {net_pnl_pct:.4f}% spread:'
                  f'spot {self.spot_ticker.spread_percentage:.4f}%, futures {self.futures_ticker.spread_percentage:.4f}%'
                  f' SPOT PNL: {(self.spot_ticker.bid_price - spot_pos.price) / spot_pos.price * 100:.4f}%,'
                  f' FUT PNL: {(futures_pos.price - self.futures_ticker.ask_price) / futures_pos.price * 100:.4f}%')

        # 1. PROFIT TARGET: Exit when profitable
        if net_pnl_pct >= self.context.params.min_profit_pct:
            print(f'{self.context.symbol} Exit pnl {net_pnl_pct:.4f}% spread:'
                  f'spot {self.spot_ticker.spread_percentage:.4f}%, futures {self.futures_ticker.spread_percentage:.4f}%'
                  f' SPOT PNL: {(self.spot_ticker.bid_price - spot_pos.price) / spot_pos.price * 100:.4f}%,'
                  f' FUT PNL: {(futures_pos.price - self.futures_ticker.ask_price) / futures_pos.price * 100:.4f}%')

            exit_now = True
            exit_reason = 'profit_target'
            self.logger.info(
                f"💰 Profit target reached: {net_pnl_pct:.4f}% >= {self.context.params.min_profit_pct:.4f}%")

        # 2. TIMEOUT: Position held too long
        elif self.context.position_start_time:
            hours_held = (time.time() - self.context.position_start_time) / 3600
            if hours_held >= self.context.params.max_hours:
                exit_now = True
                exit_reason = 'timeout'
                self.logger.info(
                    f"🕒 Timeout exit: {hours_held:.2f}h >= {self.context.params.max_hours:.2f}h (P&L: {net_pnl_pct:.4f}%)")

        return exit_now

    async def _process_imbalance(self) -> bool:
        # Check positions and imbalances
        if not self.context.positions_state.has_positions:
            return False
        positions = self.context.positions_state.positions
        delta_base = self.context.positions_state.delta
        min_spot_qty = self._get_minimum_order_base_quantity('spot')
        min_futures_qty = self._get_minimum_order_base_quantity('futures')

        if abs(delta_base) < max(min_spot_qty, min_futures_qty):
            return False

        self.logger.info(f'⚠️ Imbalance detected COINS: {delta_base} SPOT: {positions["spot"]}'
                         f' FUT: {positions["futures"]} ')

        # WRONG:
        # spot_imbalance = delta_base >= min_spot_qty
        # force
        # futures_imbalance_less_ = delta_usdt < 0 and abs(delta_usdt) < min_futures_usdt
        place_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {}

        # if spot_imbalance:
        #     quantity = self._prepare_order_quantity('spot', delta_base)
        #     place_orders['spot'] = OrderPlacementParams(
        #         side=Side.BUY,
        #         quantity=quantity,
        #         price=self.spot_ticker.ask_price
        #     )
        # else:
        # imbalance < minimal futures quantity, force buy spot to reduce imbalance
        if delta_base < 0 and abs(delta_base) >= min_spot_qty:
            quantity = self._prepare_order_quantity('spot', abs(delta_base))
            place_orders['spot'] = OrderPlacementParams(
                side=Side.BUY,
                quantity=quantity,
                price=self.spot_ticker.ask_price
            )
        elif delta_base > 0 and abs(delta_base) >= min_futures_qty:
            quantity = self._prepare_order_quantity('futures', abs(delta_base))
            place_orders['futures'] = OrderPlacementParams(
                side=Side.SELL,
                quantity=quantity,
                price=self.futures_ticker.bid_price
            )
        else:
            self.logger.info('ℹ️ Imbalance detected but below minimums, no correction placed')

        placed_orders = await self.exchange_manager.place_order_parallel(place_orders)

        success = await self._update_active_orders_after_placement(placed_orders)

        if success:
            self.logger.info(f"✅ Delta correction order placed: {[str(o) for o in placed_orders]}")
        else:
            self.logger.error(f"❌ Failed to place delta correction orders {placed_orders}")

        return success

    async def _enter_positions(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute arbitrage trades using unified order preparation."""
        try:
            index_price = self.spot_ticker.ask_price
            # CRITICAL FIX: Convert USDT to coin units before comparison
            order_coin_size = self.context.single_order_size_usdt / index_price

            position_size = min(order_coin_size, opportunity.max_quantity)

            spot_min = self._get_minimum_order_base_quantity('spot')
            futures_min = self._get_minimum_order_base_quantity('futures')
            min_base_qty = max(spot_min, futures_min)

            if position_size < min_base_qty:
                self.logger.error(
                    f"❌ Calculated position size {position_size:.6f} < minimum required {min_base_qty:.6f}")
                return False

            self.logger.info(f"Calculated position size: {position_size:.6f} coins, base: {order_coin_size}, "
                             f"oppo: {opportunity.max_quantity} price: {index_price}")

            # Adjust order sizes to meet exchange minimums
            spot_quantity = self._prepare_order_quantity('spot', position_size)
            futures_quantity = self._prepare_order_quantity('futures', position_size)
            adjusted_quantity = max(spot_quantity, futures_quantity)

            # Ensure adjusted quantities are still equal for delta neutrality
            if abs(spot_quantity - futures_quantity) > 1e-6:
                # Use the larger quantity for both to maintain delta neutrality
                self.logger.info(f"⚖️ Adjusting both quantities to {adjusted_quantity:.6f} for delta neutrality")
                spot_quantity = futures_quantity = adjusted_quantity

            # Convert to OrderPlacementParams
            enter_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {
                'spot': OrderPlacementParams(side=Side.BUY, quantity=spot_quantity, price=opportunity.buy_price),
                'futures': OrderPlacementParams(side=Side.SELL, quantity=futures_quantity, price=opportunity.sell_price)
            }

            # Execute orders in parallel
            self.logger.info(f"🚀 Executing arbitrage trades: {position_size}")
            start_time = time.time()

            placed_orders = await self.exchange_manager.place_order_parallel(enter_orders)

            # Update active orders tracking for successfully placed orders
            success = await self._update_active_orders_after_placement(placed_orders)

            execution_time = (time.time() - start_time) * 1000

            self.logger.info(f"⚡ Order execution completed in {execution_time:.1f}ms,"
                             f" placed orders: {placed_orders}")

            if success:
                entry_cost_pct = self._get_entry_cost_pct(opportunity.buy_price, opportunity.sell_price)
                entry_cost_real_pct = self._get_entry_cost_pct(placed_orders['spot'].price,
                                                               placed_orders['futures'].price)
                entry_cost_diff = entry_cost_real_pct - entry_cost_pct
                self.logger.info(f"✅ Both entry orders placed successfully, "
                                 f"oppo price, buy {opportunity.buy_price}, sell {opportunity.sell_price} qty: {adjusted_quantity} "
                                 f"real price, buy {placed_orders['spot']}, sell {placed_orders['futures']} "
                                 f"enter cost % {entry_cost_pct}:.3f real cost % {entry_cost_real_pct}:.3f "
                                 f"diff % {entry_cost_diff:.3f}")

                # Track position start time
                if self.context.position_start_time is None:
                    self.evolve_context(position_start_time=time.time())
                # TODO: use index price
                position_usdt = max(spot_quantity, futures_quantity) * self.spot_ticker.ask_price
                if position_usdt:
                    self.evolve_context(
                        total_volume_usdt=self.context.total_volume_usdt + position_usdt
                    )
            else:
                # Cancel any successful orders
                await self.exchange_manager.cancel_all_orders()

            return success

        except Exception as e:
            self.logger.error(f"Arbitrage execution error: {e}")
            await self.exchange_manager.cancel_all_orders()
            return False

    def round_to_contract_size(self, qty: float) -> float:
        """Round price based on exchange tick size."""
        symbol_info = self.exchange_manager.get_exchange('futures').public.symbols_info[self.context.symbol]
        return symbol_info.base_to_contracts(qty)

    def get_tick_size(self, exchange_type: ArbitrageExchangeType) -> float:
        """Get tick size based on exchange type."""
        symbol_info = self.exchange_manager.get_exchange(exchange_type).public.symbols_info[self.context.symbol]
        return symbol_info.tick

    def _get_direction_price(self, direction: Literal['enter', 'exit'], exchange_type: ArbitrageExchangeType) -> \
    Optional[float]:
        """Get trade price for entry or exit based on direction and exchange type."""
        if direction == 'enter':
            return self.spot_ticker.ask_price if exchange_type == 'spot' else self.futures_ticker.bid_price
        # elif direction == 'exit':

        return self.spot_ticker.bid_price if exchange_type == 'spot' else self.futures_ticker.ask_price

    async def _exit_all_positions(self):
        """Exit all positions using simplified logic with volume validation."""
        try:
            self.logger.info("🔄 Exiting all positions...")

            # CRITICAL: Validate exit volumes meet minimum requirements
            volume_validation = self._validate_exit_volumes()
            if not volume_validation.valid:
                self.logger.error(f"❌ Exit volume validation failed: {volume_validation.reason}")
                return

            exit_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {}

            # Close spot position (exit is opposite side) with volume validation
            for exchange_role in ['spot', 'futures']:  # type: ArbitrageExchangeType
                pos = self.context.positions_state.positions[exchange_role]
                if pos.has_position:
                    exit_side = flip_side(pos.side)
                    price = self._get_direction_price('exit', 'spot')

                    # Prepare exit quantity with minimum validations
                    exit_quantity = self._prepare_order_quantity('spot', pos.qty)

                    exit_orders[exchange_role] = OrderPlacementParams(
                        side=exit_side,
                        quantity=exit_quantity,
                        price=price
                    )

            if exit_orders:
                placed_orders = await self.exchange_manager.place_order_parallel(exit_orders)

                # Update active orders tracking for exit orders
                success = await self._update_active_orders_after_placement(placed_orders)

                if success:
                    # Log realized profit before clearing positions
                    total_profit = self.context.positions_state.total_realized_profit
                    self.logger.info(f"✅ All exit orders placed successfully - Total profit: ${total_profit:.2f}")
                    # Reset position timing
                    self.evolve_context(position_start_time=None)
                else:
                    self.logger.warning("⚠️ Some exit orders failed")

                return success

        except Exception as e:
            self.logger.error(f"❌ Error exiting positions: {e}")
            return False


    async def _place_limit_orders(self):
        """Place limit orders for profit capture when market opportunity doesn't exist."""
        try:
            # Skip if already have active limit orders
            if self.context.active_limit_orders:
                return

            spot_bid, spot_ask = self.spot_ticker.bid_price, self.spot_ticker.ask_price
            fut_bid, fut_ask = self.futures_ticker.bid_price, self.futures_ticker.ask_price
            
            # Calculate limit profit threshold 
            limit_threshold = self.context.params.min_profit_pct + self.context.params.limit_profit_pct
            
            # Check for enter arbitrage opportunity (buy spot, sell futures)
            if not self.context.positions_state.has_positions:
                # Calculate price for exact limit_profit_pct offset
                # Goal: Find spot price where profit = limit_profit_pct
                # We want: (fut_bid - limit_spot_price) / limit_spot_price * 100 = limit_profit_pct
                # Solving: limit_spot_price = fut_bid / (1 + limit_profit_pct/100)
                # limit_spot_price = fut_bid / (1 + self.context.params.limit_profit_pct / 100)
                
                # Ensure we don't place limit above current ask (would be market order)
                # if limit_spot_price >= spot_ask:
                #     return  # No profitable limit order possible
                #
                limit_spot_price = self.spot_ticker.ask_price - (self.get_tick_size('spot') * 3)  # Place just below current ask
                # Calculate expected profit at this price
                entry_cost_pct = self._get_entry_cost_pct(limit_spot_price, fut_bid)
                # expected_profit_pct = -entry_cost_pct
                
                if self._debug_info_counter <= 1:
                    print(f'{self.context.symbol} Enter limit: target profit {self.context.params.limit_profit_pct:.3f}%, '
                          f'calculated price {limit_spot_price:.6f}, COST: {entry_cost_pct:.4f}%')

                if entry_cost_pct >= limit_threshold:
                    # Place limit buy on spot at calculated price
                    await self._place_single_limit_order('enter', Side.BUY, limit_spot_price)
                    self.logger.info(f"📋 Placing enter limit @{limit_spot_price:.6f}: "
                                   f"expected profit {entry_cost_pct:.4f}% >= threshold {limit_threshold:.4f}%")

            # Check for exit arbitrage opportunity (sell spot, buy futures)
            elif self.context.positions_state.has_positions:
                spot_pos = self.context.positions_state.positions['spot']
                futures_pos = self.context.positions_state.positions['futures']
                
                # Calculate price for exact limit_profit_pct improvement over current market exit
                # Current market exit PnL
                current_market_pnl = self._get_pos_net_pnl(
                    spot_pos.price, futures_pos.price, spot_bid, fut_ask
                )
                
                # Target PnL with limit improvement
                target_pnl = current_market_pnl + self.context.params.limit_profit_pct
                
                # Calculate required spot price for target PnL
                # We need to solve for limit_spot_price where net_pnl = target_pnl
                # For simplicity, add profit percentage to current bid
                # limit_spot_price = spot_bid * (1 + self.context.params.limit_profit_pct / 100)
                limit_spot_price = spot_bid + (self.get_tick_size('spot') * 3)  # Place just below current ask

                # Calculate expected PnL at this price
                net_pnl_pct = self._get_pos_net_pnl(
                    spot_pos.price, futures_pos.price, limit_spot_price, fut_ask
                )

                if self._debug_info_counter <= 1:
                    print(f'{self.context.symbol} Exit limit: target improvement {self.context.params.limit_profit_pct:.3f}%, '
                          f'calculated price {limit_spot_price:.6f}, expected PnL {net_pnl_pct:.4f}%')

                if net_pnl_pct >= limit_threshold:
                    # Place limit sell on spot at calculated price
                    await self._place_single_limit_order('exit', Side.SELL, limit_spot_price)
                    self.logger.info(f"📋 Placing exit limit @{limit_spot_price:.6f}: "
                                   f"expected PnL {net_pnl_pct:.4f}% >= threshold {limit_threshold:.4f}%")
                    
        except Exception as e:
            self.logger.error(f"Error placing limit orders: {e}")

    async def _place_single_limit_order(self, direction: Literal['enter', 'exit'], spot_side: Side, spot_price: float):
        """Place a single limit order on spot. Hedge will be placed when filled."""
        try:
            # Cancel existing limit orders if any
            await self._cancel_limit_orders()
            
            qty_usdt = self.context.single_order_size_usdt
            spot_qty = qty_usdt / spot_price
            
            # Prepare spot limit order using existing pattern
            spot_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {
                'spot': OrderPlacementParams(side=spot_side, quantity=spot_qty, price=spot_price, order_type='limit')
            }
            
            # Place only spot limit order
            placed_orders = await self.exchange_manager.place_order_parallel(spot_orders)
            
            if placed_orders.get('spot'):
                # Track limit orders
                self.evolve_context(
                    active_limit_orders={direction: placed_orders['spot'].order_id},
                    limit_order_prices={direction: spot_price}
                )
                
                self.logger.info(f"📋 Placed {direction} limit order: spot {spot_side.name}@{spot_price:.6f}")
            
        except Exception as e:
            self.logger.error(f"Error placing single limit order: {e}")

    async def _check_limit_orders(self):
        """Check limit orders for fills and price updates."""
        try:
            if not self.context.active_limit_orders:
                return
                
            # Check for fills first - if filled, execute immediate hedge
            await self._check_limit_order_fills()
                
            # Then check if prices need updates based on tolerance percentage
            spot_bid, spot_ask = self.spot_ticker.bid_price, self.spot_ticker.ask_price
            fut_bid, fut_ask = self.futures_ticker.bid_price, self.futures_ticker.ask_price
            
            for direction, order_id in self.context.active_limit_orders.items():
                current_limit_price = self.context.limit_order_prices.get(direction)
                if not current_limit_price:
                    continue
                    
                # Calculate new optimal price based on current market
                new_optimal_price = None
                
                if direction == 'enter' and spot_ask and fut_bid:
                    # Recalculate optimal entry price
                    new_optimal_price = fut_bid / (1 + self.context.params.limit_profit_pct / 100)
                    # Ensure it's still below current ask
                    if new_optimal_price >= spot_ask:
                        new_optimal_price = None  # Can't improve
                        
                elif direction == 'exit' and spot_bid and fut_ask:
                    # Recalculate optimal exit price  
                    new_optimal_price = spot_bid * (1 + self.context.params.limit_profit_pct / 100)
                    # Ensure it's still above current bid
                    if new_optimal_price <= spot_bid:
                        new_optimal_price = None  # Can't improve
                
                # Check if price moved beyond tolerance threshold
                if new_optimal_price:
                    price_change_pct = abs(new_optimal_price - current_limit_price) / current_limit_price * 100
                    
                    if price_change_pct >= self.context.params.limit_profit_tolerance_pct:
                        self.logger.info(f"🔄 Price moved {price_change_pct:.3f}% >= tolerance {self.context.params.limit_profit_tolerance_pct:.3f}%, "
                                       f"updating {direction} limit: {current_limit_price:.6f} -> {new_optimal_price:.6f}")
                        await self._update_limit_order(direction, order_id, new_optimal_price)
                    
        except Exception as e:
            self.logger.error(f"Error checking limit orders: {e}")

    async def _check_limit_order_fills(self):
        """Check if limit orders are filled and execute immediate delta hedge."""
        try:
            for direction, order_id in list(self.context.active_limit_orders.items()):
                # Get order status from exchange
                exchange = self.exchange_manager.get_exchange('spot')
                if not exchange:
                    continue
                    
                # Check if order is filled by looking at active orders
                limit_order =  exchange.private.get_order(order_id)
                
                if not limit_order:
                    # Order not found - likely filled or cancelled
                    await self._handle_limit_order_fill('spot', direction, order_id)
                    
        except Exception as e:
            self.logger.error(f"Error checking limit order fills: {e}")

    async def _handle_limit_order_fill(self, exchange_key: ArbitrageExchangeType,
                                       direction: Literal['enter', 'exit'], order_id: str):
        """Handle limit order fill with immediate delta hedge."""
        try:
            self.logger.info(f"🎯 Limit order filled: {exchange_key} {direction} {order_id}")
            
            # Remove from tracking
            new_limit_orders = self.context.active_limit_orders.copy()
            new_limit_prices = self.context.limit_order_prices.copy()
            del new_limit_orders[direction]
            del new_limit_prices[direction]
            
            self.evolve_context(
                active_limit_orders=new_limit_orders,
                limit_order_prices=new_limit_prices
            )
            
            # Execute immediate delta hedge on futures
            fut_side = Side.SELL if direction == 'enter' else Side.BUY
            qty_usdt = self.context.single_order_size_usdt
            fut_price = self.futures_ticker.ask_price if fut_side == Side.BUY else self.futures_ticker.bid_price
            fut_qty = qty_usdt / fut_price
            
            # Place futures market order for immediate hedge
            fut_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {
                'futures': OrderPlacementParams(side=fut_side, quantity=fut_qty, price=fut_price, order_type='market')
            }
            
            placed_orders = await self.exchange_manager.place_order_parallel(fut_orders)
            
            if placed_orders.get('futures'):
                self.logger.info(f"⚡ Immediate delta hedge: futures {fut_side.name} {fut_qty}@{fut_price:.6f}")
                # Update tracking as normal position
                await self._update_active_orders_after_placement(placed_orders)
            else:
                self.logger.error(f"❌ Failed to place delta hedge for {direction}")
                
        except Exception as e:
            self.logger.error(f"Error handling limit order fill: {e}")

    async def _update_limit_order(self, direction: Literal['enter', 'exit'], order_id: str, new_price: float):
        """Update limit order price."""
        try:
            # Cancel old order using exchange directly
            exchange = self.exchange_manager.get_exchange('spot')
            if exchange:
                o = await exchange.private.cancel_order(self.context.symbol, order_id)
                self._process_order_fill('spot', o)
                if o.filled_quantity > 0:
                    self.logger.info(f"⚠️ Partial fill detected when cancelling limit order {order_id}, processed fill.")
                    return
            
            # Place new order
            spot_side = Side.BUY if direction == 'enter' else Side.SELL
            qty_usdt = self.context.single_order_size_usdt  
            spot_qty = qty_usdt / new_price
            
            spot_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {
                'spot': OrderPlacementParams(side=spot_side, quantity=spot_qty, price=new_price, order_type='limit')
            }
            
            placed_orders = await self.exchange_manager.place_order_parallel(spot_orders)
            
            if placed_orders.get('spot'):
                # Update tracking
                new_limit_orders = self.context.active_limit_orders.copy()
                new_limit_orders[direction] = placed_orders['spot'].order_id
                new_limit_prices = self.context.limit_order_prices.copy()
                new_limit_prices[direction] = new_price
                
                self.evolve_context(
                    active_limit_orders=new_limit_orders,
                    limit_order_prices=new_limit_prices
                )
                
                self.logger.info(f"🔄 Updated {direction} limit order: {new_price:.6f}")
            
        except Exception as e:
            self.logger.error(f"Error updating limit order: {e}")

    async def _cancel_limit_orders(self):
        """Cancel all active limit orders."""
        try:
            exchange = self.exchange_manager.get_exchange('spot')
            if not exchange:
                return

            for direction, order_id in self.context.active_limit_orders.items():
                o = await exchange.private.cancel_order(self.context.symbol, order_id)
                self._process_order_fill('spot', o)

            self.evolve_context(
                active_limit_orders={},
                limit_order_prices={}
            )
            
        except Exception as e:
            self.logger.error(f"Error cancelling limit orders: {e}")

    def _get_pos_net_pnl(self, entry_spot_price: float, entry_fut_price: float,
                         curr_spot_price: float, curr_fut_price: float) -> Optional[float]:
        # Calculate P&L using backtesting logic with fees
        spot_fee = self.context.params.spot_fee
        fut_fee = self.context.params.fut_fee

        # Entry costs (what we paid)
        entry_spot_cost = entry_spot_price * (1 + spot_fee)  # Bought spot with fee
        entry_fut_receive = entry_fut_price * (1 - fut_fee)  # Sold futures with fee

        # Exit revenues (what we get)
        exit_spot_receive = curr_spot_price * (1 - spot_fee)  # Sell spot with fee
        exit_fut_cost = curr_fut_price * (1 + fut_fee)  # Buy futures with fee

        # P&L calculation
        spot_pnl_pts = exit_spot_receive - entry_spot_cost
        fut_pnl_pts = entry_fut_receive - exit_fut_cost
        total_pnl_pts = spot_pnl_pts + fut_pnl_pts

        # P&L percentage
        capital = entry_spot_cost
        net_pnl_pct = (total_pnl_pts / capital) * 100

        return net_pnl_pct

    async def cleanup(self):
        """Clean up strategy resources."""
        # Cancel limit orders and rebalance if needed
        if self.context.params.limit_orders_enabled:
            await self._cancel_limit_orders()
            # do not exit on restart
            # if self.context.positions_state.has_positions:
            #     await self._exit_all_positions()  # Rebalance to delta neutral
            #
        # Call base cleanup
        await super().cleanup()


# Exchange-agnostic factory function
async def create_spot_futures_arbitrage_task(
        symbol: Symbol,
        spot_exchange: ExchangeEnum,
        futures_exchange: ExchangeEnum,
        base_position_size_usdt: float = 100.0,
        max_entry_cost_pct: float = 0.5,
        min_profit_pct: float = 0.1,
        max_hours: float = 6.0,
        logger: Optional[HFTLoggerInterface] = None
) -> SpotFuturesArbitrageTask:
    """Create and initialize spot-futures arbitrage task for any exchange pair."""

    if logger is None:
        logger = get_logger(f'spot_futures_arbitrage.{symbol}.{spot_exchange.name}_{futures_exchange.name}')

    params = TradingParameters(
        max_entry_cost_pct=max_entry_cost_pct,
        min_profit_pct=min_profit_pct,
        max_hours=max_hours,
        limit_orders_enabled=True,
        limit_profit_pct=0.1,
        limit_profit_tolerance_pct=0.1
    )

    context = ArbitrageTaskContext(
        symbol=symbol,
        single_order_size_usdt=base_position_size_usdt,
        params=params,
        arbitrage_state='initializing'
    )

    task = SpotFuturesArbitrageTask(
        logger=logger,
        context=context,
        spot_exchange=spot_exchange,
        futures_exchange=futures_exchange
    )
    await task.start()
    
    # Load initial spread history after exchange connections are established
    await task._load_initial_spread_history()
    
    return task


# Convenience function for MEXC + Gate.io (backward compatibility)
async def create_mexc_gateio_arbitrage_task(
        symbol: Symbol,
        base_position_size_usdt: float = 100.0,
        max_entry_cost_pct: float = 0.5,
        min_profit_pct: float = 0.1,
        max_hours: float = 6.0,
        logger: Optional[HFTLoggerInterface] = None
) -> SpotFuturesArbitrageTask:
    """Create MEXC + Gate.io arbitrage task (convenience function for backward compatibility)."""
    return await create_spot_futures_arbitrage_task(
        symbol=symbol,
        spot_exchange=ExchangeEnum.MEXC,
        futures_exchange=ExchangeEnum.GATEIO_FUTURES,
        base_position_size_usdt=base_position_size_usdt,
        max_entry_cost_pct=max_entry_cost_pct,
        min_profit_pct=min_profit_pct,
        max_hours=max_hours,
        logger=logger
    )
