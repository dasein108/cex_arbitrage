"""
Simplified Delta Arbitrage Live Trading Strategy

This module implements a simplified version of the delta-neutral arbitrage
strategy with dynamic parameter optimization. It's designed as a PoC that
removes complexity while maintaining core arbitrage functionality.
"""

import asyncio
import time
import sys
import os
import pandas as pd
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from exchanges.structs import Symbol, Side, ExchangeEnum
from ..optimization.parameter_optimizer import DeltaArbitrageOptimizer, OptimizationResult
from .strategy_config import DeltaArbitrageConfig
from .arbitrage_context import SimpleDeltaArbitrageContext


@dataclass
class ArbitrageOpportunity:
    """Simple arbitrage opportunity data structure"""
    entry_price_spot: float        # Price to execute on spot exchange
    entry_price_futures: float     # Price to execute on futures exchange
    spread_pct: float              # Spread percentage
    direction: str                 # 'spot_to_futures' or 'futures_to_spot'
    estimated_profit: float        # Estimated profit amount
    confidence: float              # Opportunity confidence (0.0-1.0)
    timestamp: float               # When opportunity was detected


@dataclass
class MockBookTicker:
    """Mock book ticker for testing (simplified structure)"""
    bid_price: float
    ask_price: float
    bid_quantity: float
    ask_quantity: float


class SimpleDeltaArbitrageStrategy:
    """
    Simplified delta arbitrage strategy with dynamic parameter optimization.
    
    This strategy implements the core arbitrage logic from MexcGateioFuturesStrategy
    but removes complex features to create a clean PoC:
    
    REMOVED COMPLEXITY:
    - Complex rebalancing logic
    - Detailed balance validation  
    - Advanced position tracking
    - Exchange manager integration
    - WebSocket event handling
    
    KEPT ESSENTIALS:
    - Core arbitrage detection
    - Basic order execution simulation
    - Dynamic parameter updates
    - Delta-neutral position management
    """
    
    def __init__(self, 
                 config: DeltaArbitrageConfig,
                 optimizer: DeltaArbitrageOptimizer):
        """
        Initialize simplified delta arbitrage strategy.
        
        Args:
            config: Strategy configuration
            optimizer: Parameter optimizer instance
        """
        self.config = config
        self.optimizer = optimizer
        self.context = SimpleDeltaArbitrageContext(
            symbol=config.symbol,
            parameter_update_interval=config.parameter_update_interval_minutes * 60,
            max_position_hold_time=config.max_position_hold_minutes * 60
        )
        
        # Mock market data (in real implementation, this would come from exchanges)
        self._mock_spot_ticker: Optional[MockBookTicker] = None
        self._mock_futures_ticker: Optional[MockBookTicker] = None
        
        # Market data simulation
        self._market_data_history: List[Dict] = []
        self._simulation_running = False
        
        # Performance tracking
        self._strategy_start_time = 0.0
        self._last_log_time = 0.0
        self._log_interval = 60.0  # Log every minute
        
        print(f"🚀 SimpleDeltaArbitrageStrategy initialized")
        print(f"   • Symbol: {config.symbol}")
        print(f"   • Base position size: {config.base_position_size}")
        print(f"   • Parameter update interval: {config.parameter_update_interval_minutes} minutes")
        print(f"   • Target hit rate: {config.target_hit_rate:.1%}")
    
    async def start(self) -> None:
        """Start the strategy."""
        try:
            print("🔄 Starting SimpleDeltaArbitrageStrategy...")
            
            # Initialize with first parameter optimization
            await self._perform_initial_optimization()
            
            # Start strategy
            self.context.is_active = True
            self._strategy_start_time = time.time()
            
            print("✅ Strategy started successfully")
            print(f"   • Initial entry threshold: {self.context.current_entry_threshold_pct:.4f}%")
            print(f"   • Initial exit threshold: {self.context.current_exit_threshold_pct:.4f}%")
            print(f"   • Initial confidence: {self.context.parameter_confidence_score:.3f}")
            
        except Exception as e:
            print(f"❌ Failed to start strategy: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the strategy."""
        print("🛑 Stopping SimpleDeltaArbitrageStrategy...")
        
        self.context.is_active = False
        self._simulation_running = False
        
        # Close any open positions (in simulation)
        if self.context.is_position_open():
            await self._close_all_positions("Strategy stop")
        
        print("✅ Strategy stopped successfully")
        self._print_final_summary()
    
    async def run_strategy_cycle(self) -> None:
        """
        Run one complete strategy cycle.
        
        This method represents one iteration of the strategy main loop:
        1. Check if parameters need updating
        2. Look for arbitrage opportunities
        3. Execute trades if opportunities found
        4. Manage existing positions
        """
        if not self.context.is_active or self.context.emergency_stop_triggered:
            return
        
        try:
            # 1. Update parameters if needed
            if self.context.should_update_parameters():
                await self._update_parameters()
            
            # 2. Check for opportunities (if not holding positions)
            if self.context.should_check_opportunity():
                self.context.mark_opportunity_checked()
                
                if not self.context.is_position_open():
                    # Look for new opportunities
                    opportunity = await self._identify_arbitrage_opportunity()
                    if opportunity:
                        await self._execute_arbitrage_opportunity(opportunity)
                else:
                    # Manage existing positions
                    await self._manage_existing_positions()
            
            # 3. Periodic logging
            await self._periodic_logging()
            
        except Exception as e:
            print(f"❌ Error in strategy cycle: {e}")
            # Don't stop strategy for individual cycle errors
    
    async def simulate_market_data_feed(self, duration_minutes: int = 60) -> None:
        """
        Simulate market data feed for testing.
        
        This method generates realistic market data and runs the strategy
        against it to demonstrate functionality.
        
        Args:
            duration_minutes: How long to run simulation
        """
        print(f"🎮 Starting market data simulation for {duration_minutes} minutes...")
        
        self._simulation_running = True
        simulation_start = time.time()
        simulation_end = simulation_start + (duration_minutes * 60)
        
        # Generate initial market data
        await self._generate_mock_market_data()
        
        while self._simulation_running and time.time() < simulation_end:
            try:
                # Update mock market data
                await self._update_mock_market_data()
                
                # Run strategy cycle
                await self.run_strategy_cycle()
                
                # Wait for next cycle (simulate real-time)
                await asyncio.sleep(0.1)  # 100ms cycles
                
            except Exception as e:
                print(f"❌ Simulation error: {e}")
                break
        
        self._simulation_running = False
        print("✅ Market data simulation completed")
    
    async def _perform_initial_optimization(self) -> None:
        """Perform initial parameter optimization."""
        print("📈 Performing initial parameter optimization...")
        
        try:
            # Generate some historical data for optimization
            historical_data = await self._generate_historical_data()
            
            # Optimize parameters
            result = await self.optimizer.optimize_parameters(
                historical_data, 
                lookback_hours=self.config.optimization_lookback_hours
            )
            
            # Update context with optimized parameters
            self.context.update_parameters(result)
            
            print(f"✅ Initial optimization completed")
            
        except Exception as e:
            print(f"⚠️ Initial optimization failed, using defaults: {e}")
            # Use default parameters
            default_result = OptimizationResult(
                entry_threshold_pct=0.5,
                exit_threshold_pct=0.1,
                confidence_score=0.3,
                analysis_period_hours=0,
                mean_reversion_speed=0.1,
                spread_volatility=0.2,
                optimization_timestamp=time.time()
            )
            self.context.update_parameters(default_result)
    
    async def _update_parameters(self) -> None:
        """Update strategy parameters using optimizer."""
        print("🔄 Updating strategy parameters...")
        
        try:
            # Get recent market data for optimization
            recent_data = await self._get_recent_market_data()
            
            if len(recent_data) < self.config.min_spread_data_points:
                print(f"⚠️ Insufficient data for optimization: {len(recent_data)} < {self.config.min_spread_data_points}")
                return
            
            # Optimize parameters
            result = await self.optimizer.optimize_parameters(
                recent_data,
                lookback_hours=self.config.optimization_lookback_hours
            )
            
            # Update context
            old_entry = self.context.current_entry_threshold_pct
            old_exit = self.context.current_exit_threshold_pct
            
            self.context.update_parameters(result)
            
            print(f"✅ Parameters updated:")
            print(f"   • Entry: {old_entry:.4f}% → {result.entry_threshold_pct:.4f}%")
            print(f"   • Exit: {old_exit:.4f}% → {result.exit_threshold_pct:.4f}%")
            print(f"   • Confidence: {result.confidence_score:.3f}")
            
        except Exception as e:
            print(f"❌ Parameter update failed: {e}")
    
    async def _identify_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """
        Identify arbitrage opportunities using current market data.
        
        This is a simplified version of the opportunity detection logic
        from the original MexcGateioFuturesStrategy.
        """
        try:
            # Get current market data
            spot_ticker = self._mock_spot_ticker
            futures_ticker = self._mock_futures_ticker
            
            if not spot_ticker or not futures_ticker:
                return None
            
            # Calculate spreads for both directions
            # Direction 1: Buy spot, sell futures
            spot_to_futures_spread = ((futures_ticker.bid_price - spot_ticker.ask_price) / 
                                    spot_ticker.ask_price) * 100
            
            # Direction 2: Buy futures, sell spot  
            futures_to_spot_spread = ((spot_ticker.bid_price - futures_ticker.ask_price) / 
                                    futures_ticker.ask_price) * 100
            
            # Check if any direction meets entry threshold
            entry_threshold = self.context.current_entry_threshold_pct
            
            best_opportunity = None
            
            if spot_to_futures_spread >= entry_threshold:
                best_opportunity = ArbitrageOpportunity(
                    entry_price_spot=spot_ticker.ask_price,
                    entry_price_futures=futures_ticker.bid_price,
                    spread_pct=spot_to_futures_spread,
                    direction='spot_to_futures',
                    estimated_profit=spot_to_futures_spread * self.config.base_position_size / 100,
                    confidence=0.8,
                    timestamp=time.time()
                )
            
            if futures_to_spot_spread >= entry_threshold:
                if (not best_opportunity or 
                    futures_to_spot_spread > best_opportunity.spread_pct):
                    best_opportunity = ArbitrageOpportunity(
                        entry_price_spot=spot_ticker.bid_price,
                        entry_price_futures=futures_ticker.ask_price,
                        spread_pct=futures_to_spot_spread,
                        direction='futures_to_spot',
                        estimated_profit=futures_to_spot_spread * self.config.base_position_size / 100,
                        confidence=0.8,
                        timestamp=time.time()
                    )
            
            if best_opportunity:
                print(f"💰 Arbitrage opportunity detected:")
                print(f"   • Direction: {best_opportunity.direction}")
                print(f"   • Spread: {best_opportunity.spread_pct:.4f}%")
                print(f"   • Estimated profit: {best_opportunity.estimated_profit:.6f}")
            
            return best_opportunity
            
        except Exception as e:
            print(f"❌ Error identifying opportunity: {e}")
            return None
    
    async def _execute_arbitrage_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """
        Execute arbitrage opportunity (simulated).
        
        In a real implementation, this would place actual orders on exchanges.
        For this PoC, we simulate the execution.
        """
        try:
            print(f"🚀 Executing arbitrage opportunity...")
            print(f"   • Direction: {opportunity.direction}")
            print(f"   • Spread: {opportunity.spread_pct:.4f}%")
            
            # Simulate order execution
            position_size = self.config.base_position_size
            
            if opportunity.direction == 'spot_to_futures':
                # Buy spot, sell futures
                self.context.update_positions(
                    spot_position=position_size,
                    futures_position=-position_size,
                    spot_price=opportunity.entry_price_spot,
                    futures_price=opportunity.entry_price_futures
                )
            else:
                # Sell spot, buy futures
                self.context.update_positions(
                    spot_position=-position_size,
                    futures_position=position_size,
                    spot_price=opportunity.entry_price_spot,
                    futures_price=opportunity.entry_price_futures
                )
            
            # Record entry
            entry_fees = self.config.get_total_fees() * position_size / 100
            self.context.total_fees_paid += entry_fees
            
            print(f"✅ Position opened:")
            print(f"   • Spot position: {self.context.spot_position}")
            print(f"   • Futures position: {self.context.futures_position}")
            print(f"   • Delta: {self.context.current_delta}")
            print(f"   • Entry fees: {entry_fees:.6f}")
            
        except Exception as e:
            print(f"❌ Error executing opportunity: {e}")
    
    async def _manage_existing_positions(self) -> None:
        """
        Manage existing positions (check for exit conditions).
        
        This checks if current positions should be closed based on:
        1. Profit target reached
        2. Time limit exceeded
        3. Emergency conditions
        """
        try:
            if not self.context.is_position_open():
                return
            
            # Check time limit
            if self.context.should_close_position_timeout():
                await self._close_all_positions("Time limit exceeded")
                return
            
            # Check profit target
            current_pnl_pct = await self._calculate_current_pnl_pct()
            exit_threshold = self.context.current_exit_threshold_pct
            
            if current_pnl_pct >= exit_threshold:
                await self._close_all_positions("Profit target reached")
                return
            
            # Check emergency stop loss
            emergency_threshold = -self.config.emergency_stop_loss_pct
            if current_pnl_pct <= emergency_threshold:
                self.context.trigger_emergency_stop("Emergency stop loss triggered")
                await self._close_all_positions("Emergency stop loss")
                return
            
        except Exception as e:
            print(f"❌ Error managing positions: {e}")
    
    async def _close_all_positions(self, reason: str) -> None:
        """
        Close all open positions (simulated).
        
        Args:
            reason: Reason for closing positions
        """
        try:
            print(f"🔄 Closing all positions: {reason}")
            
            if not self.context.is_position_open():
                print("⚠️ No positions to close")
                return
            
            # Calculate P&L
            final_pnl_pct = await self._calculate_current_pnl_pct()
            position_size = abs(self.context.spot_position)
            realized_pnl = final_pnl_pct * position_size / 100
            
            # Calculate exit fees
            exit_fees = self.config.get_total_fees() * position_size / 100
            net_pnl = realized_pnl - exit_fees
            
            # Record trade result
            is_winning = net_pnl > 0
            self.context.record_trade_result(realized_pnl, exit_fees, is_winning)
            
            # Reset positions
            self.context.reset_positions()
            
            print(f"✅ Positions closed:")
            print(f"   • Realized P&L: {realized_pnl:.6f}")
            print(f"   • Exit fees: {exit_fees:.6f}")
            print(f"   • Net P&L: {net_pnl:.6f}")
            print(f"   • Trade result: {'✅ WIN' if is_winning else '❌ LOSS'}")
            
        except Exception as e:
            print(f"❌ Error closing positions: {e}")
    
    async def _calculate_current_pnl_pct(self) -> float:
        """Calculate current unrealized P&L percentage."""
        try:
            if not self.context.is_position_open():
                return 0.0
            
            spot_ticker = self._mock_spot_ticker
            futures_ticker = self._mock_futures_ticker
            
            if not spot_ticker or not futures_ticker:
                return 0.0
            
            # Calculate P&L based on current market prices vs entry prices
            spot_pnl = 0.0
            futures_pnl = 0.0
            
            if self.context.spot_position != 0:
                if self.context.spot_position > 0:
                    # Long spot: profit when price goes up
                    spot_pnl = ((spot_ticker.bid_price - self.context.spot_avg_price) / 
                              self.context.spot_avg_price) * 100
                else:
                    # Short spot: profit when price goes down
                    spot_pnl = ((self.context.spot_avg_price - spot_ticker.ask_price) / 
                              self.context.spot_avg_price) * 100
            
            if self.context.futures_position != 0:
                if self.context.futures_position > 0:
                    # Long futures: profit when price goes up
                    futures_pnl = ((futures_ticker.bid_price - self.context.futures_avg_price) / 
                                 self.context.futures_avg_price) * 100
                else:
                    # Short futures: profit when price goes down
                    futures_pnl = ((self.context.futures_avg_price - futures_ticker.ask_price) / 
                                 self.context.futures_avg_price) * 100
            
            # For delta-neutral strategy, we want the spread P&L
            total_pnl_pct = spot_pnl + futures_pnl
            return total_pnl_pct
            
        except Exception as e:
            print(f"❌ Error calculating P&L: {e}")
            return 0.0
    
    async def _periodic_logging(self) -> None:
        """Log strategy status periodically."""
        current_time = time.time()
        if current_time - self._last_log_time >= self._log_interval:
            self._last_log_time = current_time
            
            summary = self.context.get_strategy_summary()
            
            print(f"\n📊 STRATEGY STATUS UPDATE")
            print(f"   • Uptime: {(current_time - self._strategy_start_time) / 60:.1f} minutes")
            print(f"   • Total trades: {summary['performance']['total_trades']}")
            print(f"   • Win rate: {summary['performance']['win_rate']:.1%}")
            print(f"   • Net P&L: {summary['performance']['net_pnl']:.6f}")
            print(f"   • Current delta: {summary['positions']['current_delta']:.2f}")
            print(f"   • Parameter updates: {summary['parameters']['total_updates']}")
            
            if self.context.is_position_open():
                current_pnl = await self._calculate_current_pnl_pct()
                print(f"   • Current position P&L: {current_pnl:.4f}%")
                print(f"   • Position hold time: {summary['positions']['position_hold_time_minutes']:.1f} minutes")
    
    def _print_final_summary(self) -> None:
        """Print final strategy performance summary."""
        summary = self.context.get_strategy_summary()
        
        print(f"\n{'='*60}")
        print(f"STRATEGY FINAL SUMMARY")
        print(f"{'='*60}")
        print(f"Symbol: {summary['symbol']}")
        print(f"Total runtime: {(time.time() - self._strategy_start_time) / 60:.1f} minutes")
        print(f"\nTRADING PERFORMANCE:")
        print(f"• Total trades: {summary['performance']['total_trades']}")
        print(f"• Winning trades: {summary['performance']['winning_trades']}")
        print(f"• Win rate: {summary['performance']['win_rate']:.1%}")
        print(f"• Total P&L: {summary['performance']['total_pnl']:.6f}")
        print(f"• Total fees: {summary['performance']['total_fees']:.6f}")
        print(f"• Net P&L: {summary['performance']['net_pnl']:.6f}")
        print(f"• Average P&L per trade: {summary['performance']['average_pnl']:.6f}")
        print(f"• Max drawdown: {summary['performance']['max_drawdown']:.6f}")
        print(f"\nPARAMETER OPTIMIZATION:")
        print(f"• Total parameter updates: {summary['parameters']['total_updates']}")
        print(f"• Final entry threshold: {summary['parameters']['entry_threshold_pct']:.4f}%")
        print(f"• Final exit threshold: {summary['parameters']['exit_threshold_pct']:.4f}%")
        print(f"• Final confidence: {summary['parameters']['confidence_score']:.3f}")
        print(f"{'='*60}")
    
    # Mock data generation methods (for testing)
    
    async def _generate_historical_data(self) -> 'pd.DataFrame':
        """Generate mock historical data for optimization."""
        import pandas as pd
        import numpy as np
        
        # Generate 24 hours of mock data
        num_points = 288  # 5-minute intervals
        timestamps = pd.date_range(
            start=pd.Timestamp.now() - pd.Timedelta(hours=24),
            periods=num_points,
            freq='5T'
        )
        
        # Generate realistic price data with mean reversion
        base_price = 0.0001
        np.random.seed(42)  # Reproducible for testing
        
        prices = [base_price]
        for i in range(1, num_points):
            # Mean reversion model
            deviation = prices[-1] - base_price
            change = np.random.normal(-0.1 * deviation, 0.00001)
            prices.append(max(0.00001, prices[-1] + change))
        
        prices = np.array(prices)
        spread = prices * 0.002  # 0.2% spread
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'spot_ask_price': prices + spread/2,
            'spot_bid_price': prices - spread/2,
            'fut_ask_price': prices + spread/2 * 1.1,  # Slightly wider futures spread
            'fut_bid_price': prices - spread/2 * 1.1,
        })
        
        return df
    
    async def _get_recent_market_data(self) -> 'pd.DataFrame':
        """Get recent market data from history."""
        import pandas as pd
        
        if len(self._market_data_history) < 50:
            # Generate some data if we don't have enough
            return await self._generate_historical_data()
        
        # Convert recent history to DataFrame
        recent_data = self._market_data_history[-100:]  # Last 100 data points
        
        df = pd.DataFrame(recent_data)
        return df
    
    async def _generate_mock_market_data(self) -> None:
        """Generate initial mock market data."""
        import random
        
        base_spot_price = 0.0001
        base_futures_price = base_spot_price * random.uniform(0.999, 1.001)
        
        self._mock_spot_ticker = MockBookTicker(
            bid_price=base_spot_price * 0.999,
            ask_price=base_spot_price * 1.001,
            bid_quantity=1000.0,
            ask_quantity=1000.0
        )
        
        self._mock_futures_ticker = MockBookTicker(
            bid_price=base_futures_price * 0.999,
            ask_price=base_futures_price * 1.001,
            bid_quantity=500.0,
            ask_quantity=500.0
        )
    
    async def _update_mock_market_data(self) -> None:
        """Update mock market data with realistic price movement."""
        import random
        import numpy as np
        
        if not self._mock_spot_ticker or not self._mock_futures_ticker:
            await self._generate_mock_market_data()
            return
        
        # Simulate correlated price movement with mean reversion
        base_price = 0.0001
        current_spot_mid = (self._mock_spot_ticker.bid_price + self._mock_spot_ticker.ask_price) / 2
        current_futures_mid = (self._mock_futures_ticker.bid_price + self._mock_futures_ticker.ask_price) / 2
        
        # Mean reversion force
        spot_reversion = -0.01 * (current_spot_mid - base_price)
        futures_reversion = -0.01 * (current_futures_mid - base_price)
        
        # Random walk component
        spot_change = np.random.normal(spot_reversion, 0.000005)
        futures_change = np.random.normal(futures_reversion, 0.000005)
        
        # Add some correlation between spot and futures
        correlation_factor = 0.8
        correlated_change = correlation_factor * spot_change
        futures_change = futures_change * (1 - correlation_factor) + correlated_change
        
        # Update prices
        new_spot_mid = max(0.00001, current_spot_mid + spot_change)
        new_futures_mid = max(0.00001, current_futures_mid + futures_change)
        
        # Add bid/ask spread
        spot_spread = new_spot_mid * 0.002
        futures_spread = new_futures_mid * 0.002
        
        self._mock_spot_ticker = MockBookTicker(
            bid_price=new_spot_mid - spot_spread/2,
            ask_price=new_spot_mid + spot_spread/2,
            bid_quantity=random.uniform(500, 2000),
            ask_quantity=random.uniform(500, 2000)
        )
        
        self._mock_futures_ticker = MockBookTicker(
            bid_price=new_futures_mid - futures_spread/2,
            ask_price=new_futures_mid + futures_spread/2,
            bid_quantity=random.uniform(300, 1500),
            ask_quantity=random.uniform(300, 1500)
        )
        
        # Store in history for optimization
        self._market_data_history.append({
            'timestamp': pd.Timestamp.now(),
            'spot_ask_price': self._mock_spot_ticker.ask_price,
            'spot_bid_price': self._mock_spot_ticker.bid_price,
            'fut_ask_price': self._mock_futures_ticker.ask_price,
            'fut_bid_price': self._mock_futures_ticker.bid_price,
        })
        
        # Keep history manageable
        if len(self._market_data_history) > 1000:
            self._market_data_history = self._market_data_history[-500:]