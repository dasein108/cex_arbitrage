#!/usr/bin/env python3
"""
Optimized Cross-Exchange Arbitrage Technical Analysis

Addresses the critical issue where entry and exit arbitrage calculations are identical.
Provides separate optimized logic for entry vs exit conditions with enhanced risk management.

Key Optimizations:
1. Separate entry/exit spread calculations reflecting different market dynamics
2. Position-aware P&L tracking with transfer cost consideration
3. Multiple exit criteria: profit target, time decay, stop loss, favorable exit
4. Enhanced risk management with liquidity checks and minimum profitable spread
5. Statistical edge analysis with historical percentile thresholds

Domain-aware implementation respecting separated domain architecture:
- Uses public domain interfaces for market data access
- Maintains domain boundaries between data sources
- HFT-optimized with sub-millisecond performance targets
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Literal, Tuple, Any
from dataclasses import dataclass

from exchanges.structs import Symbol, BookTicker, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data
from infrastructure.logging import HFTLoggerInterface, get_logger


@dataclass
class OptimizedArbitrageThresholds:
    """Enhanced arbitrage thresholds with separate entry/exit calculations."""
    entry_spread: float          # Minimum profitable spread to enter (90th percentile)
    exit_spread: float           # Exit when spread falls below this
    profit_target: float         # Take profit target (e.g., 0.5%)
    stop_loss: float            # Stop loss threshold (e.g., -0.5%)
    max_holding_hours: float    # Maximum position holding time
    mean_entry_spread: float    # Average historical entry spread
    mean_exit_spread: float     # Average historical exit spread
    std_entry_spread: float     # Entry spread standard deviation
    std_exit_spread: float      # Exit spread standard deviation
    min_profitable_spread: float # Minimum spread after all fees
    last_update: datetime
    data_points: int


@dataclass
class PositionState:
    """Track position state for exit calculations."""
    is_open: bool = False
    entry_time: Optional[datetime] = None
    entry_spot_price: Optional[float] = None
    entry_futures_price: Optional[float] = None
    entry_spread: Optional[float] = None
    quantity: Optional[float] = None


class OptimizedCrossArbitrageTA:
    """
    Optimized cross-exchange arbitrage technical analysis.
    
    Addresses the critical issue where entry and exit calculations are identical.
    Provides separate optimized logic for different phases of the arbitrage trade.
    
    Trading Flow:
    1. Entry: Source (MEXC) spot buy → Hedge (Gate.io) futures short
    2. Transfer: Move assets from source to destination exchange (5-10 min)
    3. Exit: Destination (Gate.io) spot sell → Close futures hedge
    
    Domain-aware design:
    - Separates public domain data access (market data)
    - Maintains domain boundaries throughout calculation pipeline
    - Uses HFT-optimized data structures and algorithms
    """
    
    def __init__(
        self,
        symbol: Symbol,
        lookback_hours: int = 24,
        refresh_minutes: int = 15,
        entry_percentile: int = 10,  # Top 10% of spreads for entry
        profit_target: float = 0.5,  # 0.5% profit target
        stop_loss: float = -0.5,     # -0.5% stop loss
        max_holding_hours: float = 2.0,  # 2 hours max hold time
        transfer_cost_pct: float = 0.05,  # 0.05% transfer cost
        trading_fees_pct: float = 0.15,   # 0.15% total trading fees
        logger: Optional[HFTLoggerInterface] = None
    ):
        """Initialize with enhanced configuration parameters."""
        self.symbol = symbol
        self.lookback_hours = lookback_hours
        self.refresh_minutes = refresh_minutes
        self.entry_percentile = entry_percentile
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        self.max_holding_hours = max_holding_hours
        self.transfer_cost_pct = transfer_cost_pct
        self.trading_fees_pct = trading_fees_pct
        self.total_costs_pct = transfer_cost_pct + trading_fees_pct
        
        # Domain-aware logging
        self.logger = logger or get_logger(f'optimized_cross_arbitrage_ta.{symbol}')
        
        # Enhanced data storage (HFT-optimized)
        self.historical_df: Optional[pd.DataFrame] = None
        self.thresholds: Optional[OptimizedArbitrageThresholds] = None
        self.last_refresh: Optional[datetime] = None
        self.position_state = PositionState()
        
        # Performance tracking
        self._calculation_count = 0
        self._signal_history = []
        
        self.logger.info("🚀 OptimizedCrossArbitrageTA initialized",
                        symbol=str(symbol),
                        profit_target=f"{profit_target:.2f}%",
                        total_costs=f"{self.total_costs_pct:.2f}%")
        
    async def initialize(self) -> None:
        """Load initial historical data and calculate enhanced thresholds."""
        self.logger.info("🔄 Initializing OptimizedCrossArbitrageTA", 
                        symbol=str(self.symbol),
                        lookback_hours=self.lookback_hours)
        
        await self.refresh_historical_data()
        
        if self.thresholds:
            self.logger.info("✅ OptimizedCrossArbitrageTA initialized",
                           entry_threshold=f"{self.thresholds.entry_spread:.4f}%",
                           profit_target=f"{self.thresholds.profit_target:.2f}%",
                           data_points=self.thresholds.data_points)
        else:
            self.logger.warning("⚠️ OptimizedCrossArbitrageTA initialized with no thresholds")
            
    async def refresh_historical_data(self) -> None:
        """
        Load historical data and calculate separate entry/exit thresholds.
        
        Enhanced to distinguish between entry and exit market dynamics.
        """
        start_time = datetime.now(timezone.utc)
        end_time = start_time
        start_time = end_time - timedelta(hours=self.lookback_hours)
        
        self.logger.debug("📊 Loading historical data for optimized analysis",
                         start_time=start_time.isoformat(),
                         end_time=end_time.isoformat())
        
        try:
            # Load data for all 3 exchanges in parallel (domain-aware)
            tasks = [
                self._load_exchange_data("mexc", ExchangeEnum.MEXC, start_time, end_time),
                self._load_exchange_data("gateio_spot", ExchangeEnum.GATEIO, start_time, end_time),
                self._load_exchange_data("gateio_futures", ExchangeEnum.GATEIO_FUTURES, start_time, end_time)
            ]
            
            dfs = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter successful results and handle exceptions
            valid_dfs = []
            for i, result in enumerate(dfs):
                if isinstance(result, Exception):
                    exchange_names = ["mexc", "gateio_spot", "gateio_futures"]
                    self.logger.warning(f"Failed to load {exchange_names[i]} data: {result}")
                else:
                    valid_dfs.append(result)
            
            if len(valid_dfs) < 3:
                self.logger.error("❌ Insufficient data sources for optimized arbitrage calculation")
                return
            
            # Merge all dataframes (HFT-optimized)
            self.historical_df = pd.concat(valid_dfs, axis=1).fillna(method='ffill').dropna()
            
            if self.historical_df.empty:
                self.logger.warning("⚠️ No overlapping data found across exchanges")
                return
            
            # Calculate separate entry and exit spreads
            self._calculate_optimized_spreads()
            
            # Update enhanced thresholds
            self._update_optimized_thresholds()
            
            self.last_refresh = datetime.now(timezone.utc)
            
            self.logger.debug("✅ Optimized historical data refreshed",
                             data_points=len(self.historical_df),
                             time_range=f"{self.historical_df.index[0]} to {self.historical_df.index[-1]}")
            
        except Exception as e:
            self.logger.error(f"❌ Error refreshing optimized historical data: {e}")
            
    async def _load_exchange_data(
        self, 
        prefix: str, 
        exchange: ExchangeEnum,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """
        Load and format data for a single exchange.
        
        Domain-aware loading respecting public domain boundaries.
        """
        try:
            # Domain-aware data loading (public domain only)
            df = await get_cached_book_ticker_data(
                exchange=exchange.value,
                symbol_base=self.symbol.base,
                symbol_quote=self.symbol.quote,
                start_time=start_time,
                end_time=end_time
            )
            
            if df.empty:
                self.logger.warning(f"No data available for {exchange.value}")
                return pd.DataFrame()
                
            # Rename columns with exchange prefix (domain-safe)
            df = df.set_index('timestamp')
            for col in ['bid_price', 'ask_price', 'bid_qty', 'ask_qty']:
                if col in df.columns:
                    df[f'{prefix}_{col}'] = df[col]
            
            # Keep only prefixed columns (domain isolation)
            return df[[c for c in df.columns if c.startswith(prefix)]]
            
        except Exception as e:
            self.logger.error(f"Error loading {prefix} data: {e}")
            return pd.DataFrame()
    
    def _calculate_optimized_spreads(self) -> None:
        """
        Calculate separate entry and exit spreads from historical data.
        
        ENTRY PHASE: Buy MEXC spot, hedge with Gate.io futures short
        EXIT PHASE: Sell Gate.io spot, close futures hedge
        
        This addresses the critical issue in the original implementation.
        """
        if self.historical_df is None or self.historical_df.empty:
            return
            
        df = self.historical_df
        
        # === ENTRY SPREAD CALCULATION ===
        # Entry: Buy MEXC spot @ ask, hedge with Gate.io futures short @ bid
        df['entry_spot_cost'] = df['mexc_ask_price']  # Cost to buy on MEXC
        df['entry_futures_revenue'] = df['gateio_futures_bid_price']  # Revenue from shorting futures
        
        # Entry spread (before costs)
        df['entry_spread_raw'] = (
            (df['entry_futures_revenue'] - df['entry_spot_cost']) / 
            df['entry_futures_revenue'] * 100
        )
        
        # Entry spread after costs
        df['entry_spread'] = df['entry_spread_raw'] - self.total_costs_pct
        
        # === EXIT SPREAD CALCULATION ===
        # Exit: Sell Gate.io spot @ bid, close futures short (buy @ ask)
        df['exit_spot_revenue'] = df['gateio_spot_bid_price']  # Revenue from selling spot
        df['exit_futures_cost'] = df['gateio_futures_ask_price']  # Cost to close short
        
        # Exit spread (after transfer to Gate.io)
        df['exit_spread_raw'] = (
            (df['exit_spot_revenue'] - df['exit_futures_cost']) /
            df['exit_spot_revenue'] * 100
        )
        
        # Exit spread after remaining fees (no transfer cost, already paid)
        df['exit_spread'] = df['exit_spread_raw'] - (self.trading_fees_pct * 0.5)  # Only exit fees
        
        # === COMBINED ANALYSIS ===
        # Theoretical round-trip profit if both executed simultaneously
        df['theoretical_profit'] = df['entry_spread'] + df['exit_spread']
        
        # Market efficiency measure (spread compression over time)
        df['spread_efficiency'] = df['entry_spread'] / (df['exit_spread'] + 0.01)  # Avoid div by zero
        
    def _update_optimized_thresholds(self) -> None:
        """
        Calculate enhanced entry/exit thresholds from historical spreads.
        
        Uses separate statistical analysis for entry and exit phases.
        """
        if self.historical_df is None or 'entry_spread' not in self.historical_df:
            return
            
        entry_spreads = self.historical_df['entry_spread'].dropna()
        exit_spreads = self.historical_df['exit_spread'].dropna()
        
        if len(entry_spreads) < 100 or len(exit_spreads) < 100:
            self.logger.warning(f"Insufficient data for thresholds: {len(entry_spreads)} entry, {len(exit_spreads)} exit points")
            return
            
        # Calculate minimum profitable spread (break-even + small buffer)
        min_profitable_spread = self.total_costs_pct + 0.05  # 0.05% buffer
        
        # HFT-optimized percentile calculations
        entry_threshold = max(
            np.percentile(entry_spreads, 100 - self.entry_percentile),
            min_profitable_spread
        )
        
        # Exit threshold: be more aggressive to capture profits
        exit_threshold = np.percentile(exit_spreads, 30)  # 30th percentile for quicker exits
        
        self.thresholds = OptimizedArbitrageThresholds(
            entry_spread=entry_threshold,
            exit_spread=exit_threshold,
            profit_target=self.profit_target,
            stop_loss=self.stop_loss,
            max_holding_hours=self.max_holding_hours,
            mean_entry_spread=entry_spreads.mean(),
            mean_exit_spread=exit_spreads.mean(),
            std_entry_spread=entry_spreads.std(),
            std_exit_spread=exit_spreads.std(),
            min_profitable_spread=min_profitable_spread,
            last_update=datetime.now(timezone.utc),
            data_points=len(entry_spreads)
        )
        
        self.logger.debug("📊 Optimized thresholds updated",
                         entry_spread=f"{self.thresholds.entry_spread:.4f}%",
                         exit_spread=f"{self.thresholds.exit_spread:.4f}%",
                         profit_target=f"{self.thresholds.profit_target:.2f}%",
                         data_points=self.thresholds.data_points)
    
    def should_refresh(self) -> bool:
        """Check if historical data needs refreshing."""
        if self.last_refresh is None:
            return True
            
        elapsed = (datetime.now(timezone.utc) - self.last_refresh).total_seconds() / 60
        return elapsed >= self.refresh_minutes
    
    def calculate_entry_spread(
        self,
        source_book: BookTicker,  # MEXC spot
        hedge_book: BookTicker    # Gate.io futures
    ) -> Dict[str, float]:
        """
        Calculate current entry arbitrage opportunity.
        
        Entry phase: Buy MEXC spot, hedge with Gate.io futures short.
        """
        # Cost to buy on MEXC
        entry_cost = source_book.ask_price
        
        # Revenue from shorting futures
        hedge_revenue = hedge_book.bid_price
        
        # Entry spread calculations
        entry_spread_raw = ((hedge_revenue - entry_cost) / hedge_revenue) * 100
        entry_spread_net = entry_spread_raw - self.total_costs_pct
        
        return {
            'entry_cost': entry_cost,
            'hedge_revenue': hedge_revenue,
            'entry_spread_raw': entry_spread_raw,
            'entry_spread_net': entry_spread_net,
            'liquidity_score': min(source_book.ask_quantity, hedge_book.bid_quantity),
            'timestamp': datetime.now(timezone.utc)
        }
    
    def calculate_exit_spread(
        self,
        dest_book: BookTicker,    # Gate.io spot (after transfer)
        hedge_book: BookTicker    # Gate.io futures
    ) -> Dict[str, float]:
        """
        Calculate current exit arbitrage opportunity.
        
        Exit phase: Sell Gate.io spot, close futures short.
        """
        # Revenue from selling spot
        exit_revenue = dest_book.bid_price
        
        # Cost to close futures short (buy back)
        hedge_close_cost = hedge_book.ask_price
        
        # Exit spread calculations
        exit_spread_raw = ((exit_revenue - hedge_close_cost) / exit_revenue) * 100
        exit_spread_net = exit_spread_raw - (self.trading_fees_pct * 0.5)  # Only exit fees
        
        return {
            'exit_revenue': exit_revenue,
            'hedge_close_cost': hedge_close_cost,
            'exit_spread_raw': exit_spread_raw,
            'exit_spread_net': exit_spread_net,
            'liquidity_score': min(dest_book.bid_quantity, hedge_book.ask_quantity),
            'timestamp': datetime.now(timezone.utc)
        }
    
    def calculate_position_pnl(
        self,
        current_dest_price: float,
        current_futures_price: float
    ) -> Dict[str, float]:
        """
        Calculate current P&L of open arbitrage position.
        
        Considers actual entry prices and all costs paid.
        """
        if not self.position_state.is_open or not self.position_state.entry_spot_price:
            return {'total_pnl_pct': 0.0, 'spot_pnl_pct': 0.0, 'futures_pnl_pct': 0.0}
            
        entry_spot = self.position_state.entry_spot_price
        entry_futures = self.position_state.entry_futures_price
        
        # P&L from spot position (after transfer to Gate.io)
        # We bought at entry_spot, can sell at current_dest_price
        spot_pnl_pct = ((current_dest_price - entry_spot) / entry_spot) * 100
        
        # P&L from futures hedge (we're short, profit when price falls)
        # We sold at entry_futures, need to buy back at current_futures_price
        futures_pnl_pct = ((entry_futures - current_futures_price) / entry_futures) * 100
        
        # Total P&L (costs already deducted at entry)
        total_pnl_pct = spot_pnl_pct + futures_pnl_pct
        
        # Time in position
        hours_held = 0.0
        if self.position_state.entry_time:
            hours_held = (datetime.now(timezone.utc) - self.position_state.entry_time).total_seconds() / 3600
        
        return {
            'total_pnl_pct': total_pnl_pct,
            'spot_pnl_pct': spot_pnl_pct,
            'futures_pnl_pct': futures_pnl_pct,
            'hours_held': hours_held,
            'entry_spread': self.position_state.entry_spread or 0.0
        }
    
    def generate_optimized_signal(
        self,
        source_book: BookTicker,  # MEXC spot
        dest_book: BookTicker,    # Gate.io spot
        hedge_book: BookTicker,   # Gate.io futures
        position_open: bool = False
    ) -> Tuple[Literal['enter', 'exit', 'none'], Dict[str, Any]]:
        """
        Generate optimized trading signals with separate entry/exit logic.
        
        Uses enhanced risk management and multiple exit criteria.
        """
        # Check if we need to refresh historical data
        if self.should_refresh():
            self.logger.debug("📊 Historical data refresh needed")
            # Note: In production, trigger async refresh without blocking
            # asyncio.create_task(self.refresh_historical_data())
        
        signal: Literal['enter', 'exit', 'none'] = 'none'
        result_data = {}
        
        if not position_open:
            # === ENTRY LOGIC ===
            entry_data = self.calculate_entry_spread(source_book, hedge_book)
            entry_spread = entry_data['entry_spread_net']
            
            # Entry conditions
            entry_conditions = []
            
            if self.thresholds:
                # 1. Spread exceeds historical threshold
                if entry_spread > self.thresholds.entry_spread:
                    entry_conditions.append("threshold")
                
                # 2. Spread covers minimum profit requirements
                if entry_spread > self.thresholds.min_profitable_spread:
                    entry_conditions.append("profitable")
                
                # 3. Sufficient liquidity
                if entry_data['liquidity_score'] > 0:
                    entry_conditions.append("liquidity")
                
                # 4. Additional safety checks
                if entry_spread > 0.1:  # Minimum 0.1% after all costs
                    entry_conditions.append("safety")
            
            # Generate entry signal
            if len(entry_conditions) >= 3:  # Need at least 3 conditions
                signal = 'enter'
                
                # Update position state
                self.position_state = PositionState(
                    is_open=True,
                    entry_time=datetime.now(timezone.utc),
                    entry_spot_price=source_book.ask_price,
                    entry_futures_price=hedge_book.bid_price,
                    entry_spread=entry_spread,
                    quantity=min(source_book.ask_quantity, hedge_book.bid_quantity)
                )
                
                self.logger.info(f"📈 Entry signal generated",
                               entry_spread=f"{entry_spread:.4f}%",
                               conditions=entry_conditions)
            
            result_data.update(entry_data)
            result_data['entry_conditions'] = entry_conditions
            
        else:
            # === EXIT LOGIC ===
            exit_data = self.calculate_exit_spread(dest_book, hedge_book)
            position_pnl = self.calculate_position_pnl(dest_book.bid_price, hedge_book.ask_price)
            
            # Exit conditions (any of these triggers exit)
            exit_reasons = []
            
            # 1. Profit target reached
            if position_pnl['total_pnl_pct'] >= self.profit_target:
                exit_reasons.append("profit_target")
            
            # 2. Favorable exit spread
            if self.thresholds and exit_data['exit_spread_net'] > self.thresholds.exit_spread:
                exit_reasons.append("favorable_exit")
            
            # 3. Time limit exceeded
            if position_pnl['hours_held'] >= self.max_holding_hours:
                exit_reasons.append("time_limit")
            
            # 4. Stop loss triggered
            if position_pnl['total_pnl_pct'] <= self.stop_loss:
                exit_reasons.append("stop_loss")
            
            # 5. Spread convergence (market efficiency)
            if exit_data['exit_spread_net'] < -0.1:  # Negative spread
                exit_reasons.append("spread_convergence")
            
            # Generate exit signal
            if exit_reasons:
                signal = 'exit'
                
                # Reset position state
                self.position_state = PositionState(is_open=False)
                
                self.logger.info(f"📉 Exit signal generated",
                               pnl=f"{position_pnl['total_pnl_pct']:.4f}%",
                               reasons=exit_reasons,
                               hours_held=f"{position_pnl['hours_held']:.2f}h")
            
            result_data.update(exit_data)
            result_data.update(position_pnl)
            result_data['exit_reasons'] = exit_reasons
        
        # Performance tracking
        self._calculation_count += 1
        
        # Build comprehensive result
        result_data.update({
            'signal': signal,
            'timestamp': datetime.now(timezone.utc),
            'calculation_count': self._calculation_count,
            'position_open': position_open,
            'thresholds_available': self.thresholds is not None
        })
        
        if self.thresholds:
            result_data['entry_threshold'] = self.thresholds.entry_spread
            result_data['exit_threshold'] = self.thresholds.exit_spread
            result_data['thresholds_age'] = (datetime.now(timezone.utc) - self.thresholds.last_update).total_seconds()
        
        # Track signal history for analysis
        self._signal_history.append({
            'timestamp': datetime.now(timezone.utc),
            'signal': signal,
            'spread': result_data.get('entry_spread_net', result_data.get('exit_spread_net', 0))
        })
        
        # Keep only last 1000 signals for memory efficiency
        if len(self._signal_history) > 1000:
            self._signal_history = self._signal_history[-1000:]
        
        return signal, result_data
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get enhanced performance metrics for HFT compliance monitoring."""
        signal_counts = {}
        if self._signal_history:
            for record in self._signal_history[-100:]:  # Last 100 signals
                signal = record['signal']
                signal_counts[signal] = signal_counts.get(signal, 0) + 1
        
        return {
            'calculation_count': self._calculation_count,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'thresholds_available': self.thresholds is not None,
            'data_points': self.thresholds.data_points if self.thresholds else 0,
            'refresh_interval_minutes': self.refresh_minutes,
            'symbol': str(self.symbol),
            'position_open': self.position_state.is_open,
            'signal_distribution': signal_counts,
            'profit_target': self.profit_target,
            'stop_loss': self.stop_loss,
            'total_costs_pct': self.total_costs_pct,
            'max_holding_hours': self.max_holding_hours
        }
    
    def get_strategy_analytics(self) -> Dict[str, Any]:
        """Get detailed strategy analytics for optimization."""
        if not self.thresholds:
            return {'error': 'No thresholds available'}
        
        # Calculate win rate and performance metrics
        recent_signals = [s for s in self._signal_history if s['signal'] in ['enter', 'exit']]
        
        analytics = {
            'thresholds': {
                'entry_spread': self.thresholds.entry_spread,
                'exit_spread': self.thresholds.exit_spread,
                'profit_target': self.thresholds.profit_target,
                'min_profitable_spread': self.thresholds.min_profitable_spread,
                'mean_entry_spread': self.thresholds.mean_entry_spread,
                'mean_exit_spread': self.thresholds.mean_exit_spread
            },
            'recent_activity': {
                'total_signals': len(recent_signals),
                'enter_signals': len([s for s in recent_signals if s['signal'] == 'enter']),
                'exit_signals': len([s for s in recent_signals if s['signal'] == 'exit']),
                'avg_entry_spread': np.mean([s['spread'] for s in recent_signals if s['signal'] == 'enter']) if recent_signals else 0,
                'avg_exit_spread': np.mean([s['spread'] for s in recent_signals if s['signal'] == 'exit']) if recent_signals else 0
            },
            'configuration': {
                'profit_target': self.profit_target,
                'stop_loss': self.stop_loss,
                'max_holding_hours': self.max_holding_hours,
                'total_costs_pct': self.total_costs_pct,
                'entry_percentile': self.entry_percentile
            },
            'position_state': {
                'is_open': self.position_state.is_open,
                'entry_time': self.position_state.entry_time.isoformat() if self.position_state.entry_time else None,
                'entry_spread': self.position_state.entry_spread
            }
        }
        
        return analytics


# Factory function for easy initialization
async def create_optimized_cross_arbitrage_ta(
    symbol: Symbol,
    lookback_hours: int = 24,
    profit_target: float = 0.5,
    max_holding_hours: float = 2.0,
    logger: Optional[HFTLoggerInterface] = None
) -> OptimizedCrossArbitrageTA:
    """Create and initialize optimized cross-arbitrage TA."""
    
    ta = OptimizedCrossArbitrageTA(
        symbol=symbol,
        lookback_hours=lookback_hours,
        profit_target=profit_target,
        max_holding_hours=max_holding_hours,
        logger=logger
    )
    
    await ta.initialize()
    return ta


# Example usage and testing
async def example_optimized_usage():
    """Demonstrate optimized cross-arbitrage TA usage."""
    
    # Initialize optimized TA module
    ta = await create_optimized_cross_arbitrage_ta(
        symbol=Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        lookback_hours=24,
        profit_target=0.5,  # 0.5% profit target
        max_holding_hours=2.0  # 2 hours max
    )
    
    # Mock market data for demonstration
    from decimal import Decimal
    
    # Example 1: Entry evaluation
    source_book = BookTicker(  # MEXC spot
        symbol=ta.symbol,
        bid_price=50000.0, ask_price=50001.0,
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=datetime.now(timezone.utc)
    )
    
    dest_book = BookTicker(  # Gate.io spot
        symbol=ta.symbol,
        bid_price=49999.0, ask_price=50000.0,
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=datetime.now(timezone.utc)
    )
    
    hedge_book = BookTicker(  # Gate.io futures
        symbol=ta.symbol,
        bid_price=50020.0, ask_price=50021.0,  # Premium to spot for entry opportunity
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Generate entry signal
    signal, data = ta.generate_optimized_signal(
        source_book=source_book,
        dest_book=dest_book,
        hedge_book=hedge_book,
        position_open=False
    )
    
    print(f"Entry evaluation: {signal}")
    print(f"Entry spread: {data.get('entry_spread_net', 0):.4f}%")
    print(f"Entry conditions: {data.get('entry_conditions', [])}")
    
    # Example 2: Exit evaluation (simulate open position)
    if signal == 'enter':
        ta.position_state.is_open = True
        ta.position_state.entry_time = datetime.now(timezone.utc)
        ta.position_state.entry_spot_price = 50001.0
        ta.position_state.entry_futures_price = 50020.0
        ta.position_state.entry_spread = data['entry_spread_net']
        
        # Simulate market movement
        hedge_book_exit = BookTicker(  # Futures price moved down (profit for short)
            symbol=ta.symbol,
            bid_price=50000.0, ask_price=50001.0,  # Lower than entry
            bid_quantity=10.0, ask_quantity=10.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        exit_signal, exit_data = ta.generate_optimized_signal(
            source_book=source_book,
            dest_book=dest_book,
            hedge_book=hedge_book_exit,
            position_open=True
        )
        
        print(f"\nExit evaluation: {exit_signal}")
        print(f"Position P&L: {exit_data.get('total_pnl_pct', 0):.4f}%")
        print(f"Exit reasons: {exit_data.get('exit_reasons', [])}")
    
    # Get strategy analytics
    analytics = ta.get_strategy_analytics()
    print(f"\nStrategy Analytics:")
    print(f"Entry threshold: {analytics['thresholds']['entry_spread']:.4f}%")
    print(f"Profit target: {analytics['thresholds']['profit_target']:.2f}%")
    print(f"Total costs: {analytics['configuration']['total_costs_pct']:.2f}%")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_optimized_usage())