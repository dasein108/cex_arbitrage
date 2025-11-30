"""
MEXC-Gate.io Futures Arbitrage Strategy Signal

This strategy exploits spread differences between MEXC spot and Gate.io futures markets.
The strategy tracks two key spreads that are typically negative, requiring optimal timing
to capture profit opportunities using quantile-based threshold analysis.

Core Trading Logic:
1. Track spreads: mexc_to_gateio_fut (buy MEXC/sell Gate.io futures)
                  gateio_fut_to_mexc (sell MEXC/buy Gate.io futures)  
2. ENTER when spread has minimal difference (closest to zero)
3. EXIT when spread difference is maximum (most negative)
4. Use quantile/percentile analysis for optimal threshold determination
5. Include comprehensive fee modeling and risk management

Performance Requirements:
- HFT-optimized with sub-millisecond signal generation
- Compatible with StrategySignal interface
- Comprehensive backtesting with realistic cost modeling
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from trading.signals_v2.strategy_signal import StrategySignal
from trading.signals_v2.entities import (
    PerformanceMetrics, ArbitrageTrade, TradeEntry, PositionEntry,
    BacktestingParams, ExchangeEnum, Side
)
from trading.data_sources.column_utils import get_column_key


@dataclass
class SpreadMetrics:
    """Comprehensive spread analysis metrics for arbitrage decision making."""
    mexc_to_gateio_fut: float          # MEXC spot to Gate.io futures spread
    gateio_fut_to_mexc: float          # Gate.io futures to MEXC spot spread
    mexc_to_gateio_fut_percentile: float   # Current spread percentile rank
    gateio_fut_to_mexc_percentile: float   # Current spread percentile rank
    volatility: float                   # Spread volatility measure
    favorable_direction: str            # 'mexc_to_fut' or 'fut_to_mexc'
    entry_signal: bool                  # True if conditions met for entry
    exit_signal: bool                   # True if conditions met for exit


@dataclass
class FeeStructure:
    """Comprehensive fee structure for MEXC and Gate.io trading."""
    mexc_spot_maker_fee: float = 0.00      # 0.1% MEXC spot maker fee
    mexc_spot_taker_fee: float = 0.0005      # 0.1% MEXC spot taker fee
    gateio_futures_maker_fee: float = 0.0002  # 0.02% Gate.io futures maker
    gateio_futures_taker_fee: float = 0.0006  # 0.06% Gate.io futures taker
    funding_rate_daily: float = 0.0001      # Expected daily funding cost
    transfer_fee_usd: float = 1.0           # Cross-exchange transfer cost


class MexcGateioFuturesArbitrageSignal(StrategySignal):
    """
    Advanced arbitrage strategy between MEXC spot and Gate.io futures markets.
    
    This strategy uses quantile-based analysis to identify optimal entry and exit
    points for cross-exchange arbitrage opportunities with comprehensive risk management.
    """
    name = "MEXC-Gate.io Futures Arbitrage"
    def __init__(
        self,
        entry_quantile: float = 0.70,           # 70th percentile for entry threshold
        exit_quantile: float = 0.20,            # 20th percentile for exit threshold
        historical_window_hours: int = 24,      # Lookback period for analysis
        min_spread_threshold: float = 0.0015,   # Minimum spread to consider (0.15% > 0.11% fees + profit margin)
        position_size_usd: float = 1000.0,      # Position size in USD
        max_daily_trades: int = 50,             # Trade frequency limit
        volatility_adjustment: bool = True,      # Enable adaptive thresholds
        risk_limit_pct: float = 0.05,          # Maximum portfolio risk (5%)
        fee_structure: Optional[FeeStructure] = None
    ):
        """
        Initialize the MEXC-Gate.io futures arbitrage strategy.
        
        Args:
            entry_quantile: Percentile threshold for entry (0.70-0.80 recommended)
            exit_quantile: Percentile threshold for exit (0.15-0.25 recommended)  
            historical_window_hours: Hours of history for quantile calculation
            min_spread_threshold: Additional profit margin above fees (0.15% = 0.11% fees + 0.04% profit)
            position_size_usd: Size of each arbitrage position
            max_daily_trades: Maximum trades per day for risk control
            volatility_adjustment: Enable dynamic threshold adjustment
            risk_limit_pct: Maximum portfolio exposure
            fee_structure: Custom fee structure (uses defaults if None)
        """
        self.entry_quantile = entry_quantile
        self.exit_quantile = exit_quantile
        self.historical_window_hours = historical_window_hours
        self.min_spread_threshold = min_spread_threshold
        self.position_size_usd = position_size_usd
        self.max_daily_trades = max_daily_trades
        self.volatility_adjustment = volatility_adjustment
        self.risk_limit_pct = risk_limit_pct
        self.fee_structure = fee_structure or FeeStructure()
        
        # Dynamic column keys for data consistency with backtesting framework
        self.col_mexc_bid = get_column_key(ExchangeEnum.MEXC, 'bid_price')
        self.col_mexc_ask = get_column_key(ExchangeEnum.MEXC, 'ask_price')
        self.col_gateio_fut_bid = get_column_key(ExchangeEnum.GATEIO_FUTURES, 'bid_price')
        self.col_gateio_fut_ask = get_column_key(ExchangeEnum.GATEIO_FUTURES, 'ask_price')
        
        # Internal state for tracking
        self._spread_history: List[SpreadMetrics] = []
        self._active_positions: List[PositionEntry] = []
        self._daily_trade_count: Dict[str, int] = {}
        
        # Performance optimization - numpy arrays for fast calculations
        self._mexc_to_fut_history = np.array([], dtype=np.float64)
        self._fut_to_mexc_history = np.array([], dtype=np.float64)
        self.analysis_results = {}

    def calculate_spread_metrics(self, df: pd.DataFrame, timestamp: datetime) -> SpreadMetrics:
        """
        Calculate comprehensive spread metrics for arbitrage decision making.
        
        Args:
            df: DataFrame with MEXC spot and Gate.io futures price data
            timestamp: Current timestamp for analysis
            
        Returns:
            SpreadMetrics with current spread analysis
        """
        # Get current prices (assume df has required columns)
        mexc_bid = df.loc[timestamp, self.col_mexc_bid] if timestamp in df.index else 0
        mexc_ask = df.loc[timestamp, self.col_mexc_ask] if timestamp in df.index else 0
        gateio_fut_bid = df.loc[timestamp, self.col_gateio_fut_bid] if timestamp in df.index else 0
        gateio_fut_ask = df.loc[timestamp, self.col_gateio_fut_ask] if timestamp in df.index else 0
        
        if any(price <= 0 for price in [mexc_bid, mexc_ask, gateio_fut_bid, gateio_fut_ask]):
            # Return neutral metrics if data is missing
            return SpreadMetrics(
                mexc_to_gateio_fut=0, gateio_fut_to_mexc=0,
                mexc_to_gateio_fut_percentile=50, gateio_fut_to_mexc_percentile=50,
                volatility=0, favorable_direction='none', entry_signal=False, exit_signal=False
            )
        
        # Calculate spreads including trading fees
        total_fees = (self.fee_structure.mexc_spot_taker_fee + 
                     self.fee_structure.gateio_futures_taker_fee)
        
        # MEXC to Gate.io futures spread (buy MEXC, sell Gate.io futures)
        mexc_to_fut_spread = ((gateio_fut_bid - mexc_ask) / mexc_ask) - total_fees
        
        # Gate.io futures to MEXC spread (sell MEXC, buy Gate.io futures) 
        fut_to_mexc_spread = ((mexc_bid - gateio_fut_ask) / gateio_fut_ask) - total_fees
        
        # Update historical arrays for efficient percentile calculation
        self._mexc_to_fut_history = np.append(self._mexc_to_fut_history, mexc_to_fut_spread)
        self._fut_to_mexc_history = np.append(self._fut_to_mexc_history, fut_to_mexc_spread)
        
        # Maintain rolling window
        max_history_length = self.historical_window_hours * 12  # 5-minute intervals
        if len(self._mexc_to_fut_history) > max_history_length:
            self._mexc_to_fut_history = self._mexc_to_fut_history[-max_history_length:]
            self._fut_to_mexc_history = self._fut_to_mexc_history[-max_history_length:]
        
        # Calculate percentiles for current spreads
        mexc_to_fut_percentile = (
            np.searchsorted(np.sort(self._mexc_to_fut_history), mexc_to_fut_spread) / 
            len(self._mexc_to_fut_history) * 100
            if len(self._mexc_to_fut_history) > 10 else 50
        )
        
        fut_to_mexc_percentile = (
            np.searchsorted(np.sort(self._fut_to_mexc_history), fut_to_mexc_spread) /
            len(self._fut_to_mexc_history) * 100 
            if len(self._fut_to_mexc_history) > 10 else 50
        )
        
        # Calculate spread volatility for adaptive thresholds
        volatility = (np.std(self._mexc_to_fut_history) + np.std(self._fut_to_mexc_history)) / 2
        
        # Determine favorable direction and signals
        favorable_direction = 'mexc_to_fut' if mexc_to_fut_spread > fut_to_mexc_spread else 'fut_to_mexc'
        
        # Entry signal: spread is favorable (high percentile = closest to zero)
        entry_threshold = self.entry_quantile * 100
        if self.volatility_adjustment:
            # Adjust threshold based on volatility
            entry_threshold *= (1 + volatility * 10)  # Increase threshold in volatile periods
        
        # Calculate total trading fees for both directions
        total_fees = self.fee_structure.mexc_spot_taker_fee + self.fee_structure.gateio_futures_taker_fee
        
        # Entry signal logic for fee-adjusted arbitrage:
        # MEXC to Futures direction: Buy MEXC spot, Sell Gate.io futures
        # Profitable when: gateio_fut_bid - mexc_ask > total_fees
        mexc_to_fut_profitable = mexc_to_fut_spread > (total_fees + self.min_spread_threshold)
        mexc_to_fut_signal = mexc_to_fut_percentile >= entry_threshold and mexc_to_fut_profitable
        
        # Futures to MEXC direction: Buy Gate.io futures, Sell MEXC spot  
        # Profitable when: mexc_bid - gateio_fut_ask > total_fees
        fut_to_mexc_profitable = fut_to_mexc_spread > (total_fees + self.min_spread_threshold) 
        fut_to_mexc_signal = fut_to_mexc_percentile >= entry_threshold and fut_to_mexc_profitable
        
        entry_signal = mexc_to_fut_signal or fut_to_mexc_signal
        
        # Exit signal: spread is unfavorable (low percentile = most negative)
        exit_threshold = self.exit_quantile * 100
        exit_signal = (
            mexc_to_fut_percentile <= exit_threshold or fut_to_mexc_percentile <= exit_threshold
        )
        
        return SpreadMetrics(
            mexc_to_gateio_fut=mexc_to_fut_spread,
            gateio_fut_to_mexc=fut_to_mexc_spread,
            mexc_to_gateio_fut_percentile=mexc_to_fut_percentile,
            gateio_fut_to_mexc_percentile=fut_to_mexc_percentile,
            volatility=volatility,
            favorable_direction=favorable_direction,
            entry_signal=entry_signal,
            exit_signal=exit_signal
        )
    
    def _check_daily_trade_limit(self, timestamp: datetime) -> bool:
        """Check if daily trade limit has been reached."""
        date_key = timestamp.strftime('%Y-%m-%d')
        current_count = self._daily_trade_count.get(date_key, 0)
        return current_count < self.max_daily_trades
    
    def _increment_daily_trade_count(self, timestamp: datetime):
        """Increment daily trade counter."""
        date_key = timestamp.strftime('%Y-%m-%d')
        self._daily_trade_count[date_key] = self._daily_trade_count.get(date_key, 0) + 1
    
    def _execute_arbitrage_trade(
        self, 
        timestamp: datetime, 
        spread_metrics: SpreadMetrics,
        df: pd.DataFrame
    ) -> Optional[PositionEntry]:
        """
        Execute arbitrage trade based on spread analysis.
        
        Args:
            timestamp: Current timestamp
            spread_metrics: Current spread metrics
            df: Market data DataFrame
            
        Returns:
            PositionEntry if trade executed, None otherwise
        """
        if not self._check_daily_trade_limit(timestamp):
            return None
        
        # Get current prices
        mexc_bid = df.loc[timestamp, self.col_mexc_bid]
        mexc_ask = df.loc[timestamp, self.col_mexc_ask]
        gateio_fut_bid = df.loc[timestamp, self.col_gateio_fut_bid]
        gateio_fut_ask = df.loc[timestamp, self.col_gateio_fut_ask]
        
        # Calculate position size in base currency
        if spread_metrics.favorable_direction == 'mexc_to_fut':
            # Buy MEXC, sell Gate.io futures
            base_qty = self.position_size_usd / mexc_ask
            
            mexc_trade = TradeEntry(
                exchange=ExchangeEnum.MEXC,
                side=Side.BUY,
                price=mexc_ask,
                qty=base_qty,
                fee_pct=self.fee_structure.mexc_spot_taker_fee * 100,
                slippage_pct=0.05
            )
            
            gateio_trade = TradeEntry(
                exchange=ExchangeEnum.GATEIO_FUTURES,
                side=Side.SELL,
                price=gateio_fut_bid,
                qty=base_qty,
                fee_pct=self.fee_structure.gateio_futures_taker_fee * 100,
                slippage_pct=0.05
            )
        else:
            # Sell MEXC, buy Gate.io futures
            base_qty = self.position_size_usd / mexc_bid
            
            mexc_trade = TradeEntry(
                exchange=ExchangeEnum.MEXC,
                side=Side.SELL,
                price=mexc_bid,
                qty=base_qty,
                fee_pct=self.fee_structure.mexc_spot_taker_fee * 100,
                slippage_pct=0.05
            )
            
            gateio_trade = TradeEntry(
                exchange=ExchangeEnum.GATEIO_FUTURES,
                side=Side.BUY,
                price=gateio_fut_ask,
                qty=base_qty,
                fee_pct=self.fee_structure.gateio_futures_taker_fee * 100,
                slippage_pct=0.05
            )
        
        # Create position entry
        position = PositionEntry(entry_time=timestamp)
        position.add_arbitrage_trade(timestamp, [mexc_trade, gateio_trade])
        
        # Add funding cost for futures position
        daily_funding_usd = self.position_size_usd * self.fee_structure.funding_rate_daily
        position.total_transfer_fees += daily_funding_usd
        
        self._increment_daily_trade_count(timestamp)
        return position
    
    def backtest(self, df: pd.DataFrame) -> PerformanceMetrics:
        """
        Execute comprehensive backtest of MEXC-Gate.io futures arbitrage strategy.
        
        This method implements realistic trading simulation including:
        - Quantile-based entry/exit thresholds
        - Comprehensive fee modeling (spot + futures + funding)
        - Risk management (daily limits, position sizing)
        - Realistic execution costs and slippage
        
        Args:
            df: DataFrame containing historical market data with columns:
                - {self.col_mexc_bid}, {self.col_mexc_ask}
                - {self.col_gateio_fut_bid}, {self.col_gateio_fut_ask}
                - timestamp index
                
        Returns:
            PerformanceMetrics with comprehensive performance analysis
        """
        if df.empty:
            return PerformanceMetrics()

        self.analyze_signals(df)
        # Validate required columns
        required_columns = [self.col_mexc_bid, self.col_mexc_ask, self.col_gateio_fut_bid, self.col_gateio_fut_ask]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # Initialize tracking variables
        self._spread_history = []
        self._active_positions = []
        self._daily_trade_count = {}
        self._mexc_to_fut_history = np.array([], dtype=np.float64)
        self._fut_to_mexc_history = np.array([], dtype=np.float64)
        
        master_position = PositionEntry(entry_time=df.index[0])
        initial_capital = 10000.0  # Default initial capital for backtesting
        
        # Process each timestamp
        for timestamp in df.index:
            try:
                # Calculate spread metrics
                spread_metrics = self.calculate_spread_metrics(df, timestamp)
                self._spread_history.append(spread_metrics)
                
                # Check for entry signals
                if spread_metrics.entry_signal and len(self._mexc_to_fut_history) > 50:
                    position = self._execute_arbitrage_trade(timestamp, spread_metrics, df)
                    if position:
                        self._active_positions.append(position)
                        # Add trades to master position for performance calculation
                        for arb_timestamp, trades in position.arbitrage_trades.items():
                            master_position.add_arbitrage_trade(arb_timestamp, trades)
                        master_position.total_transfer_fees += position.total_transfer_fees
                
                # Note: Exit logic would be implemented for live trading
                # For this arbitrage strategy, each trade is self-contained
                
            except Exception as e:
                # Log error and continue (robust backtesting)
                print(f"Error processing timestamp {timestamp}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Calculate final performance metrics
        performance = master_position.get_performance_metrics(initial_capital)
        
        # Add strategy-specific metrics
        if self._spread_history:
            avg_mexc_to_fut_spread = np.mean([s.mexc_to_gateio_fut for s in self._spread_history])
            avg_fut_to_mexc_spread = np.mean([s.gateio_fut_to_mexc for s in self._spread_history])
            avg_volatility = np.mean([s.volatility for s in self._spread_history])
            
            # Enhance performance metrics with strategy insights
            total_opportunities = sum(1 for s in self._spread_history if s.entry_signal)
            total_samples = len(self._spread_history)
            opportunity_rate = (total_opportunities / total_samples * 100) if total_samples > 0 else 0
            
            # Add custom metrics via extended attributes
            performance.strategy_metrics = {
                'avg_mexc_to_fut_spread': avg_mexc_to_fut_spread,
                'avg_fut_to_mexc_spread': avg_fut_to_mexc_spread,
                'avg_volatility': avg_volatility,
                'opportunity_rate_pct': opportunity_rate,
                'total_opportunities': total_opportunities,
                'entry_quantile_used': self.entry_quantile,
                'exit_quantile_used': self.exit_quantile
            }
        
        return performance
    
    def get_current_signal(self, df: pd.DataFrame, timestamp: datetime) -> Dict[str, any]:
        """
        Generate current trading signal for live trading.
        
        Args:
            df: Current market data DataFrame  
            timestamp: Current timestamp
            
        Returns:
            Dictionary with signal information for live trading
        """
        spread_metrics = self.calculate_spread_metrics(df, timestamp)
        
        return {
            'timestamp': timestamp,
            'entry_signal': spread_metrics.entry_signal,
            'exit_signal': spread_metrics.exit_signal,
            'favorable_direction': spread_metrics.favorable_direction,
            'mexc_to_fut_spread': spread_metrics.mexc_to_gateio_fut,
            'fut_to_mexc_spread': spread_metrics.gateio_fut_to_mexc,
            'mexc_to_fut_percentile': spread_metrics.mexc_to_gateio_fut_percentile,
            'fut_to_mexc_percentile': spread_metrics.gateio_fut_to_mexc_percentile,
            'spread_volatility': spread_metrics.volatility,
            'daily_trades_remaining': self.max_daily_trades - self._daily_trade_count.get(
                timestamp.strftime('%Y-%m-%d'), 0
            ),
            'position_size_usd': self.position_size_usd,
            'min_spread_threshold': self.min_spread_threshold
        }

    def apply_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply strategy signals to historical data for backtesting.
        
        Args:
            df: Historical market data DataFrame
            
        Returns:
            DataFrame with added signal columns for backtesting
        """
        df_result = df.copy()
        
        # Calculate spreads in basis points
        df_result['mexc_to_fut_spread'] = (
            (df_result[self.col_mexc_ask] - df_result[self.col_gateio_fut_bid]) / 
            df_result[self.col_mexc_ask] * 10000  # Convert to basis points
        )
        
        df_result['fut_to_mexc_spread'] = (
            (df_result[self.col_gateio_fut_ask] - df_result[self.col_mexc_bid]) / 
            df_result[self.col_gateio_fut_ask] * 10000  # Convert to basis points
        )
        
        # Initialize signal columns
        df_result['entry_signal'] = False
        df_result['exit_signal'] = False
        df_result['favorable_direction'] = 'none'
        
        # Process each timestamp to build up historical data and generate signals
        for i, (timestamp, row) in enumerate(df_result.iterrows()):
            # Calculate spread metrics for current timestamp
            spread_metrics = self.calculate_spread_metrics(df_result.iloc[:i+1], timestamp)
            
            # Apply signals
            df_result.loc[timestamp, 'entry_signal'] = spread_metrics.entry_signal
            df_result.loc[timestamp, 'exit_signal'] = spread_metrics.exit_signal
            df_result.loc[timestamp, 'favorable_direction'] = spread_metrics.favorable_direction
            
            # Add percentile information
            df_result.loc[timestamp, 'mexc_to_fut_percentile'] = spread_metrics.mexc_to_gateio_fut_percentile
            df_result.loc[timestamp, 'fut_to_mexc_percentile'] = spread_metrics.gateio_fut_to_mexc_percentile
            df_result.loc[timestamp, 'volatility'] = spread_metrics.volatility
        
        return df_result

    def analyze_signals(self, df: pd.DataFrame) -> dict:
        """
        Analyze spread distributions and signal generation thresholds.
        
        Provides detailed analysis of spread quantiles and threshold effectiveness
        for debugging signal generation issues.
        
        Args:
            df: Market data DataFrame with spread calculations
            
        Returns:
            Dictionary with comprehensive spread analysis
        """
        # First apply signals to get spread columns
        df_with_signals = self.apply_signals(df)
        
        # Calculate spreads if not already present
        if 'mexc_to_fut_spread' not in df_with_signals.columns:
            df_with_signals['mexc_to_fut_spread'] = (
                (df_with_signals[self.col_mexc_ask] - df_with_signals[self.col_gateio_fut_bid]) / 
                df_with_signals[self.col_mexc_ask] * 10000  # Convert to basis points
            )
        
        if 'fut_to_mexc_spread' not in df_with_signals.columns:
            df_with_signals['fut_to_mexc_spread'] = (
                (df_with_signals[self.col_gateio_fut_ask] - df_with_signals[self.col_mexc_bid]) / 
                df_with_signals[self.col_gateio_fut_ask] * 10000  # Convert to basis points
            )
        
        quantile_perc = [0.20, 0.5, 0.75, 0.8, 0.85, 0.9, 0.95, 0.97, 0.99]
        
        results = {}
        
        # Analyze MEXC to Futures direction
        mexc_to_fut_spreads = df_with_signals['mexc_to_fut_spread'].dropna()
        if len(mexc_to_fut_spreads) > 0:
            mexc_to_fut_quantiles = mexc_to_fut_spreads.quantile(quantile_perc)
            entry_threshold_80 = mexc_to_fut_quantiles[0.8]  # Entry quantile threshold
            exit_threshold_20 = mexc_to_fut_quantiles[0.2]   # Exit quantile threshold
            
            profitable_spreads = mexc_to_fut_spreads[mexc_to_fut_spreads > entry_threshold_80]
            
            mexc_to_fut_analysis = {
                'spread_stats': {
                    'count': len(mexc_to_fut_spreads),
                    'mean': mexc_to_fut_spreads.mean(),
                    'std': mexc_to_fut_spreads.std(),
                    'min': mexc_to_fut_spreads.min(),
                    'max': mexc_to_fut_spreads.max()
                },
                'quantiles': {f'q{int(q*100)}': v for q, v in mexc_to_fut_quantiles.items()},
                'entry_threshold_80pct': entry_threshold_80,
                'exit_threshold_20pct': exit_threshold_20,
                'profitable_opportunities': {
                    'count': len(profitable_spreads),
                    'percentage': len(profitable_spreads) / len(mexc_to_fut_spreads) * 100,
                    'avg_spread': profitable_spreads.mean() if len(profitable_spreads) > 0 else 0
                }
            }
            results['mexc_to_futures'] = mexc_to_fut_analysis
        
        # Analyze Futures to MEXC direction
        fut_to_mexc_spreads = df_with_signals['fut_to_mexc_spread'].dropna()
        if len(fut_to_mexc_spreads) > 0:
            fut_to_mexc_quantiles = fut_to_mexc_spreads.quantile(quantile_perc)
            entry_threshold_80 = fut_to_mexc_quantiles[0.8]
            exit_threshold_20 = fut_to_mexc_quantiles[0.2]
            
            profitable_spreads = fut_to_mexc_spreads[fut_to_mexc_spreads > entry_threshold_80]
            
            fut_to_mexc_analysis = {
                'spread_stats': {
                    'count': len(fut_to_mexc_spreads),
                    'mean': fut_to_mexc_spreads.mean(),
                    'std': fut_to_mexc_spreads.std(),
                    'min': fut_to_mexc_spreads.min(),
                    'max': fut_to_mexc_spreads.max()
                },
                'quantiles': {f'q{int(q*100)}': v for q, v in fut_to_mexc_quantiles.items()},
                'entry_threshold_80pct': entry_threshold_80,
                'exit_threshold_20pct': exit_threshold_20,
                'profitable_opportunities': {
                    'count': len(profitable_spreads),
                    'percentage': len(profitable_spreads) / len(fut_to_mexc_spreads) * 100,
                    'avg_spread': profitable_spreads.mean() if len(profitable_spreads) > 0 else 0
                }
            }
            results['futures_to_mexc'] = fut_to_mexc_analysis
        
        # Analyze signal generation
        entry_signals = df_with_signals['entry_signal'].sum() if 'entry_signal' in df_with_signals.columns else 0
        exit_signals = df_with_signals['exit_signal'].sum() if 'exit_signal' in df_with_signals.columns else 0
        
        results['signal_analysis'] = {
            'total_rows': len(df_with_signals),
            'entry_signals': entry_signals,
            'exit_signals': exit_signals,
            'entry_signal_rate': entry_signals / len(df_with_signals) * 100 if len(df_with_signals) > 0 else 0,
            'exit_signal_rate': exit_signals / len(df_with_signals) * 100 if len(df_with_signals) > 0 else 0
        }
        
        # Add strategy configuration for context
        results['strategy_config'] = {
            'entry_quantile': self.entry_quantile,
            'exit_quantile': self.exit_quantile,
            'position_size_usd': self.position_size_usd,
            'historical_window_hours': self.historical_window_hours,
            'max_daily_trades': self.max_daily_trades,
            'min_spread_threshold': self.min_spread_threshold,
            'volatility_adjustment': self.volatility_adjustment
        }
        
        self.analysis_results = results
        return results


def create_mexc_gateio_futures_strategy(
    entry_quantile: float = 0.80,
    exit_quantile: float = 0.20, 
    position_size_usd: float = 1000.0,
    **kwargs
) -> MexcGateioFuturesArbitrageSignal:
    """
    Convenience factory function for creating MEXC-Gate.io futures arbitrage strategy.
    
    Args:
        entry_quantile: Percentile for entry threshold (0.75-0.85 recommended)
        exit_quantile: Percentile for exit threshold (0.15-0.25 recommended)
        position_size_usd: Position size for each arbitrage trade
        **kwargs: Additional parameters for strategy customization
        
    Returns:
        Configured MexcGateioFuturesArbitrageSignal instance
    """
    return MexcGateioFuturesArbitrageSignal(
        entry_quantile=entry_quantile,
        exit_quantile=exit_quantile,
        position_size_usd=position_size_usd,
        **kwargs
    )