#!/usr/bin/env python3
"""
Simplified Symbol Backtester for Cross-Exchange Arbitrage

Focused on the optimized spike capture strategy (best performing).
Designed for quick symbol testing and parameter optimization.
"""

import pandas as pd
import numpy as np
import asyncio
from datetime import datetime, timedelta, UTC
from pathlib import Path
import sys
import argparse
from typing import Dict, List, Optional
from enum import Enum
from dataclasses import dataclass

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

from config import HftConfig
from exchanges.structs import Symbol
from exchanges.structs.common import AssetName
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from infrastructure.logging import get_logger
from trading.research.cross_arbitrage.multi_candles_source import MultiCandlesSource


class DirectionalAction(Enum):
    LONG_MEXC_SHORT_GATEIO = "long_mexc_short_gateio"
    SHORT_MEXC_LONG_GATEIO = "short_mexc_long_gateio"
    NO_ACTION = "no_action"


class ExitReason(Enum):
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    TIME_STOP = "time_stop"
    CORRELATION_STOP = "correlation_stop"


@dataclass
class Trade:
    """Simplified trade record"""
    entry_idx: int
    exit_idx: int
    entry_time: any
    exit_time: any
    hold_time: int
    entry_spread: float
    exit_spread: float
    raw_pnl_pct: float
    net_pnl_pct: float
    exit_reason: ExitReason
    direction: str
    entry_price_mexc: float
    entry_price_gateio: float
    exit_price_mexc: float
    exit_price_gateio: float


class SymbolBacktester:
    """
    Streamlined backtester focused on spike capture and mean reversion strategies.
    
    Supports both real market data loading and synthetic test data.
    This consolidates the best-performing logic from the research phase
    into a clean, production-ready implementation for symbol testing.
    """
    
    def __init__(self, 
                 trading_fees: Dict[str, float] = None,
                 slippage_estimate: float = 0.02):
        """
        Initialize with realistic trading costs and real data loading capability
        
        Args:
            trading_fees: Dict with 'mexc', 'gateio' fees (default: maker/taker optimal)
            slippage_estimate: Estimated slippage per leg (default: 0.02%)
        """
        if trading_fees is None:
            trading_fees = {
                'mexc': 0.00,     # Maker fees (can be achieved with limit orders)
                'gateio': 0.10,   # Taker fees (market orders)
            }
        
        self.mexc_fee = trading_fees['mexc']
        self.gateio_fee = trading_fees['gateio']
        self.slippage_estimate = slippage_estimate
        
        # Total cost per round-trip (critical for profitability)
        self.total_cost = self.mexc_fee + self.gateio_fee + 2 * slippage_estimate
        
        # Initialize real data components
        self.config = HftConfig()
        self.logger = get_logger("SymbolBacktester")
        self.candles_source = MultiCandlesSource()
        
        # Exchanges for real data loading
        self.exchanges = [
            ExchangeEnum.MEXC,
            ExchangeEnum.GATEIO,
            ExchangeEnum.GATEIO_FUTURES
        ]
        
        print(f"💰 Trading costs configured:")
        print(f"   MEXC fee: {self.mexc_fee:.3f}%")
        print(f"   Gate.io fee: {self.gateio_fee:.3f}%")
        print(f"   Slippage estimate: {self.slippage_estimate:.3f}%")
        print(f"   Total round-trip cost: {self.total_cost:.3f}%")
    
    def _determine_directional_action(self, 
                                    mexc_move: float, 
                                    gateio_move: float, 
                                    differential: float,
                                    min_differential: float,
                                    min_single_move: float) -> DirectionalAction:
        """
        Determine optimal directional action based on price movements
        
        Key Logic (FIXED from original):
        - If MEXC moves up more than Gate.io → SHORT MEXC, LONG Gate.io
        - If Gate.io moves up more than MEXC → LONG MEXC, SHORT Gate.io
        """
        
        # Check minimum thresholds
        if abs(differential) < min_differential:
            return DirectionalAction.NO_ACTION
            
        if max(abs(mexc_move), abs(gateio_move)) < min_single_move:
            return DirectionalAction.NO_ACTION
        
        # Determine direction based on differential
        if differential > 0:
            # MEXC moved up more than Gate.io
            # Expectation: MEXC will revert down, Gate.io will catch up
            # Action: SHORT MEXC, LONG Gate.io
            return DirectionalAction.SHORT_MEXC_LONG_GATEIO
        else:
            # Gate.io moved up more than MEXC  
            # Expectation: Gate.io will revert down, MEXC will catch up
            # Action: LONG MEXC, SHORT Gate.io
            return DirectionalAction.LONG_MEXC_SHORT_GATEIO
    
    def _calculate_directional_pnl(self, position: Dict, mexc_price: float, gateio_price: float) -> float:
        """
        Calculate P&L for directional position
        
        Accounts for the actual direction of the position:
        - LONG_MEXC_SHORT_GATEIO: profit when MEXC outperforms Gate.io
        - SHORT_MEXC_LONG_GATEIO: profit when Gate.io outperforms MEXC
        """
        
        mexc_return = (mexc_price - position['mexc_entry_price']) / position['mexc_entry_price'] * 100
        gateio_return = (gateio_price - position['gateio_entry_price']) / position['gateio_entry_price'] * 100
        
        if position['action'] == DirectionalAction.LONG_MEXC_SHORT_GATEIO:
            # Profit when MEXC outperforms Gate.io
            pnl = mexc_return - gateio_return
        else:  # SHORT_MEXC_LONG_GATEIO
            # Profit when Gate.io outperforms MEXC  
            pnl = gateio_return - mexc_return
        
        return pnl

    async def load_real_data(self, symbol_str: str, hours: int = 24, 
                           timeframe: KlineInterval = KlineInterval.MINUTE_5) -> pd.DataFrame:
        """
        Load real market data from exchanges
        
        Args:
            symbol_str: Symbol as string (e.g., "QUBIC_USDT") 
            hours: Hours of historical data to load
            timeframe: Candle timeframe (MINUTE_1, MINUTE_5, etc.)
            
        Returns:
            DataFrame with OHLCV data from all exchanges
        """
        
        # Parse symbol
        base, quote = symbol_str.split('_')
        symbol = Symbol(base=AssetName(base), quote=AssetName(quote))
        
        # Time range
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=hours)
        
        self.logger.info(f"📊 Loading real candle data for {symbol}")
        self.logger.info(f"   Timeframe: {timeframe.value}")
        self.logger.info(f"   Period: {start_time} to {end_time} ({hours}h)")
        
        try:
            df = await self.candles_source.get_multi_candles_df(
                exchanges=self.exchanges,
                symbol=symbol,
                date_to=end_time,
                hours=hours,
                timeframe=timeframe
            )
            
            if df.empty:
                self.logger.warning(f"⚠️ No candle data available for {symbol}")
                return pd.DataFrame()
            
            # Process data similar to spot_spot_arbitrage_analyzer.py
            self._process_real_data(df)
            
            self.logger.info(f"✅ Loaded real data: {len(df)} candles")
            return df
            
        except Exception as e:
            self.logger.error(f"❌ Error loading real data: {e}")
            return pd.DataFrame()
    
    def _process_real_data(self, df: pd.DataFrame) -> None:
        """Process real candle data to add required columns for strategies"""
        
        # Column names based on exchange enums
        mexc_c_col = f'{ExchangeEnum.MEXC.value}_close'
        gateio_c_col = f'{ExchangeEnum.GATEIO.value}_close'
        gateio_fut_c_col = f'{ExchangeEnum.GATEIO_FUTURES.value}_close'
        
        mexc_h_col = f'{ExchangeEnum.MEXC.value}_high'
        gateio_h_col = f'{ExchangeEnum.GATEIO.value}_high'
        gateio_fut_h_col = f'{ExchangeEnum.GATEIO_FUTURES.value}_high'
        
        mexc_l_col = f'{ExchangeEnum.MEXC.value}_low'
        gateio_l_col = f'{ExchangeEnum.GATEIO.value}_low'
        gateio_fut_l_col = f'{ExchangeEnum.GATEIO_FUTURES.value}_low'
        
        def diff_perc(col1, col2):
            denom = df[col2]
            num = df[col1] - denom
            pct = num.div(denom).mul(100)
            # avoid division-by-zero and replace NaN/inf with 0
            pct = pct.where(denom != 0, 0).fillna(0)
            return pct
        
        # Basic spread calculations
        df['mexc_vs_gateio_pct'] = diff_perc(mexc_c_col, gateio_c_col)
        df['mexc_vs_gateio_fut_pct'] = diff_perc(mexc_c_col, gateio_fut_c_col)
        df['gateio_vs_gateio_fut_pct'] = diff_perc(gateio_c_col, gateio_fut_c_col)
        
        # Store column names for strategies
        df.attrs['mexc_c_col'] = mexc_c_col
        df.attrs['gateio_c_col'] = gateio_c_col
        df.attrs['gateio_futures_c_col'] = gateio_fut_c_col
        df.attrs['mexc_h_col'] = mexc_h_col
        df.attrs['mexc_l_col'] = mexc_l_col
        df.attrs['gateio_h_col'] = gateio_h_col
        df.attrs['gateio_l_col'] = gateio_l_col
        
        # Technical indicators for mean reversion
        window = 20
        df['spread_mean'] = df['mexc_vs_gateio_pct'].rolling(window).mean()
        df['spread_std'] = df['mexc_vs_gateio_pct'].rolling(window).std()
        df['spread_z_score'] = (df['mexc_vs_gateio_pct'] - df['spread_mean']) / df['spread_std']
        df['spread_velocity'] = df['mexc_vs_gateio_pct'].diff()
        
        # Rolling correlation
        df['rolling_corr'] = df[mexc_c_col].rolling(window).corr(df[gateio_c_col])
        
        # Volatility indicators  
        df['mexc_range'] = (df[mexc_h_col] - df[mexc_l_col]) / df[mexc_c_col] * 100
        df['gateio_range'] = (df[gateio_h_col] - df[gateio_l_col]) / df[gateio_c_col] * 100
        
        self.logger.info(f"📊 Real data processed:")
        self.logger.info(f"   Spread range: {df['mexc_vs_gateio_pct'].min():.3f}% to {df['mexc_vs_gateio_pct'].max():.3f}%")
        self.logger.info(f"   Correlation: {df['rolling_corr'].mean():.3f} avg")
    
    def backtest_mean_reversion(self, 
                              df: pd.DataFrame,
                              entry_z_threshold: float = 1.5,
                              exit_z_threshold: float = 0.5,
                              stop_loss_pct: float = 0.5,
                              max_hold_minutes: int = 120,
                              symbol: str = "UNKNOWN") -> Dict:
        """
        Backtest mean reversion strategy (profitable for QUBIC)
        
        Strategy:
        - Enter: When spread Z-score > threshold and spread contracting
        - Exit: When spread returns to mean or stop-loss hit
        - Logic: Assumes spreads revert to historical mean
        """
        
        print(f"\n🎯 Backtesting Mean Reversion for {symbol}")
        print(f"   Entry Z-threshold: {entry_z_threshold}")
        print(f"   Exit Z-threshold: {exit_z_threshold}")
        print(f"   Stop loss: {stop_loss_pct}%")
        print(f"   Max hold time: {max_hold_minutes} minutes")
        
        # Ensure required columns exist
        if 'spread_z_score' not in df.columns:
            # Add technical indicators
            window = 20
            df['spread_mean'] = df['mexc_vs_gateio_pct'].rolling(window=window).mean()
            df['spread_std'] = df['mexc_vs_gateio_pct'].rolling(window=window).std()
            df['spread_z_score'] = (df['mexc_vs_gateio_pct'] - df['spread_mean']) / df['spread_std']
            df['spread_velocity'] = df['mexc_vs_gateio_pct'].diff()
            
        if 'rolling_corr' not in df.columns:
            # Add correlation
            mexc_col = df.attrs.get('mexc_c_col', 'mexc_close')
            gateio_col = df.attrs.get('gateio_c_col', 'gateio_close')
            df['rolling_corr'] = df[mexc_col].rolling(20).corr(df[gateio_col])
        
        # Get column names
        mexc_c_col = df.attrs.get('mexc_c_col', 'mexc_close')
        gateio_c_col = df.attrs.get('gateio_c_col', 'gateio_close')
        
        # Position tracking
        position = None
        trades = []
        
        for idx in range(len(df)):
            if idx < 20:  # Skip until indicators are ready
                continue
                
            row = df.iloc[idx]
            
            # Skip if any critical data is missing
            if pd.isna(row['spread_z_score']) or pd.isna(row['spread_mean']):
                continue
            
            current_spread = row['mexc_vs_gateio_pct']
            z_score = row['spread_z_score']
            spread_velocity = row.get('spread_velocity', 0)
            rolling_corr = row.get('rolling_corr', 1.0)
            
            # ENTRY LOGIC
            if position is None:
                # Enter when spread is wide and starting to contract
                entry_signal = (
                    abs(z_score) > entry_z_threshold and
                    spread_velocity < 0 and  # Spread contracting (converging)
                    rolling_corr > 0.7  # Venues still correlated
                )
                
                if entry_signal:
                    position = {
                        'entry_idx': idx,
                        'entry_time': row.name if hasattr(row, 'name') else idx,
                        'entry_spread': current_spread,
                        'entry_z_score': z_score,
                        'entry_price_mexc': row[mexc_c_col],
                        'entry_price_gateio': row[gateio_c_col],
                        'direction': 'long' if current_spread > 0 else 'short',  # Long MEXC if it's expensive
                    }
                    
            # EXIT LOGIC
            else:
                hold_time = idx - position['entry_idx']
                spread_change = current_spread - position['entry_spread']
                
                # Profit target: spread returned to mean
                profit_target = abs(z_score) < exit_z_threshold
                
                # Stop loss: spread moved against us
                stop_loss = abs(spread_change) > stop_loss_pct
                
                # Time stop: held too long
                time_stop = hold_time > max_hold_minutes
                
                # Correlation breakdown: venues decorrelated
                correlation_stop = rolling_corr < 0.6
                
                exit_signal = profit_target or stop_loss or time_stop or correlation_stop
                
                if exit_signal:
                    # Calculate P&L
                    # If we longed MEXC (expecting it to fall relative to gateio):
                    # PnL = entry_spread - exit_spread - costs
                    raw_pnl = position['entry_spread'] - current_spread
                    
                    # Adjust for direction
                    if position['direction'] == 'short':
                        raw_pnl = -raw_pnl
                    
                    net_pnl = raw_pnl - (self.mexc_fee + self.gateio_fee + self.slippage_estimate * 2)
                    
                    # Determine exit reason
                    exit_reason = ExitReason.PROFIT_TARGET if profit_target else \
                                 ExitReason.STOP_LOSS if stop_loss else \
                                 ExitReason.TIME_STOP if time_stop else \
                                 ExitReason.CORRELATION_STOP
                    
                    # Record trade
                    trade = Trade(
                        entry_idx=position['entry_idx'],
                        exit_idx=idx,
                        entry_time=position['entry_time'],
                        exit_time=row.name if hasattr(row, 'name') else idx,
                        hold_time=hold_time,
                        entry_spread=position['entry_spread'],
                        exit_spread=current_spread,
                        raw_pnl_pct=raw_pnl,
                        net_pnl_pct=net_pnl,
                        exit_reason=exit_reason,
                        direction=position['direction'],
                        entry_price_mexc=position['entry_price_mexc'],
                        entry_price_gateio=position['entry_price_gateio'],
                        exit_price_mexc=row[mexc_c_col],
                        exit_price_gateio=row[gateio_c_col]
                    )
                    trades.append(trade)
                    position = None
        
        # Calculate metrics
        return self._calculate_metrics(trades, symbol)
    
    def backtest_optimized_spike_capture(self, 
                                        df: pd.DataFrame,
                                        min_differential: float = 0.15,
                                        min_single_move: float = 0.1,
                                        max_hold_minutes: int = 10,
                                        profit_target_multiplier: float = 0.4,
                                        momentum_exit_threshold: float = 1.5,
                                        symbol: str = "UNKNOWN") -> Dict:
        """
        Optimized spike capture strategy - the best performer from research
        
        This strategy captures directional spikes by:
        1. Detecting when one exchange moves significantly more than another
        2. Taking counter-directional position to capture the differential
        3. Exiting when profit target is hit or conditions change
        
        Args:
            df: DataFrame with mexc_close, gateio_close columns
            min_differential: Minimum price move difference to trigger (%)
            min_single_move: Minimum single exchange move required (%)
            max_hold_minutes: Maximum hold time
            profit_target_multiplier: Target = differential * this multiplier
            momentum_exit_threshold: Exit when momentum reversal exceeds this
            symbol: Symbol being backtested (for logging)
        """
        
        print(f"\n🎯 Backtesting Optimized Spike Capture for {symbol}")
        print(f"   Min differential: {min_differential:.2f}%")
        print(f"   Min single move: {min_single_move:.2f}%") 
        print(f"   Max hold time: {max_hold_minutes} minutes")
        print(f"   Profit target: {profit_target_multiplier:.1f}x differential")
        print(f"   Momentum exit threshold: {momentum_exit_threshold:.1f}x")
        
        # Get column names (flexible for different data sources)
        mexc_c_col = df.attrs.get('mexc_c_col', 'mexc_close')
        gateio_c_col = df.attrs.get('gateio_c_col', 'gateio_close')
        
        # Prepare data
        df = df.copy()
        df['mexc_pct_change'] = df[mexc_c_col].pct_change() * 100
        df['gateio_pct_change'] = df[gateio_c_col].pct_change() * 100
        df['price_differential'] = df['mexc_pct_change'] - df['gateio_pct_change']
        
        trades = []
        position = None
        
        for idx, row in df.iterrows():
            if pd.isna(row['mexc_pct_change']) or pd.isna(row['gateio_pct_change']):
                continue
            
            current_time = idx if isinstance(idx, int) else idx
            mexc_move = row['mexc_pct_change']
            gateio_move = row['gateio_pct_change']
            differential = row['price_differential']
            
            # === ENTRY LOGIC ===
            if position is None:
                action = self._determine_directional_action(
                    mexc_move, gateio_move, differential,
                    min_differential, min_single_move
                )
                
                if action != DirectionalAction.NO_ACTION:
                    # Calculate expected profit and target
                    expected_profit = abs(differential) * profit_target_multiplier
                    
                    position = {
                        'entry_idx': current_time,
                        'action': action,
                        'mexc_entry_price': row[mexc_c_col],
                        'gateio_entry_price': row[gateio_c_col],
                        'entry_differential': differential,
                        'expected_profit': expected_profit,
                        'profit_target': expected_profit,
                        'entry_time': current_time
                    }
                    
                    continue
            
            # === EXIT LOGIC ===
            if position is not None:
                hold_time = current_time - position['entry_time']
                
                # Calculate current P&L
                actual_pnl = self._calculate_directional_pnl(position, row[mexc_c_col], row[gateio_c_col])
                
                # Exit conditions (optimized from research)
                profit_target_hit = actual_pnl >= position['profit_target']
                time_limit_hit = hold_time >= max_hold_minutes
                stop_loss_hit = actual_pnl < -position['expected_profit'] * 1.0
                
                # Less aggressive momentum reversal (key optimization)
                current_differential = row['price_differential']
                momentum_reversal = (
                    abs(current_differential - position['entry_differential']) > 
                    abs(position['entry_differential']) * momentum_exit_threshold
                )
                
                # Exit decision logic
                should_exit = profit_target_hit or time_limit_hit or stop_loss_hit
                
                # For spike scenarios, be more patient with momentum reversals
                if momentum_reversal and abs(position['entry_differential']) > 0.3:
                    should_exit = should_exit or (hold_time >= max_hold_minutes * 0.8)
                elif momentum_reversal:
                    should_exit = True
                
                if should_exit:
                    # Final P&L calculation
                    gross_pnl = actual_pnl
                    net_pnl = gross_pnl - self.total_cost
                    
                    # Determine exit reason
                    if profit_target_hit:
                        exit_reason = ExitReason.PROFIT_TARGET
                    elif stop_loss_hit:
                        exit_reason = ExitReason.STOP_LOSS
                    elif momentum_reversal:
                        exit_reason = ExitReason.CORRELATION_STOP
                    else:
                        exit_reason = ExitReason.TIME_STOP
                    
                    # Calculate spreads for analysis
                    entry_spread = ((position['mexc_entry_price'] - position['gateio_entry_price']) / 
                                  position['gateio_entry_price']) * 100
                    exit_spread = ((row[mexc_c_col] - row[gateio_c_col]) / row[gateio_c_col]) * 100
                    
                    trade = Trade(
                        entry_idx=position['entry_idx'],
                        exit_idx=current_time,
                        entry_time=position['entry_time'],
                        exit_time=current_time,
                        hold_time=hold_time,
                        entry_spread=entry_spread,
                        exit_spread=exit_spread,
                        raw_pnl_pct=gross_pnl,
                        net_pnl_pct=net_pnl,
                        exit_reason=exit_reason,
                        direction=position['action'].value,
                        entry_price_mexc=position['mexc_entry_price'],
                        entry_price_gateio=position['gateio_entry_price'],
                        exit_price_mexc=row[mexc_c_col],
                        exit_price_gateio=row[gateio_c_col],
                    )
                    
                    trades.append(trade)
                    position = None
        
        return self._calculate_metrics(trades, symbol)
    
    def _calculate_metrics(self, trades: List[Trade], symbol: str) -> Dict:
        """Calculate comprehensive performance metrics"""
        
        if not trades:
            return {
                'symbol': symbol,
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl_pct': 0,
                'avg_pnl_pct': 0,
                'max_pnl_pct': 0,
                'min_pnl_pct': 0,
                'avg_hold_time': 0,
                'sharpe_ratio': 0,
                'trades_df': pd.DataFrame()
            }
        
        # Convert trades to DataFrame for analysis
        trades_data = []
        for trade in trades:
            trades_data.append({
                'entry_idx': trade.entry_idx,
                'exit_idx': trade.exit_idx,
                'hold_time': trade.hold_time,
                'entry_spread': trade.entry_spread,
                'exit_spread': trade.exit_spread,
                'raw_pnl_pct': trade.raw_pnl_pct,
                'net_pnl_pct': trade.net_pnl_pct,
                'exit_reason': trade.exit_reason.value,
                'direction': trade.direction,
            })
        
        trades_df = pd.DataFrame(trades_data)
        
        # Calculate metrics
        total_trades = len(trades)
        winning_trades = len(trades_df[trades_df['net_pnl_pct'] > 0])
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = trades_df['net_pnl_pct'].sum()
        avg_pnl = trades_df['net_pnl_pct'].mean()
        max_pnl = trades_df['net_pnl_pct'].max()
        min_pnl = trades_df['net_pnl_pct'].min()
        avg_hold_time = trades_df['hold_time'].mean()
        
        # Sharpe ratio calculation
        pnl_std = trades_df['net_pnl_pct'].std()
        sharpe_ratio = (avg_pnl / pnl_std) if pnl_std > 0 else 0
        
        return {
            'symbol': symbol,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl_pct': total_pnl,
            'avg_pnl_pct': avg_pnl,
            'max_pnl_pct': max_pnl,
            'min_pnl_pct': min_pnl,
            'avg_hold_time': avg_hold_time,
            'sharpe_ratio': sharpe_ratio,
            'trades_df': trades_df
        }
    
    def create_test_data(self, symbol: str = "TEST", periods: int = 1000, spike_frequency: int = 100) -> pd.DataFrame:
        """
        Create realistic test data for strategy validation
        
        Args:
            symbol: Symbol name for testing
            periods: Number of data points
            spike_frequency: How often to inject spikes (every N periods)
        """
        print(f"📊 Creating test data for {symbol}: {periods} periods")
        
        # Create timestamps
        timestamps = pd.date_range(start='2024-01-01', periods=periods, freq='1min')
        
        # Base prices with correlated random walk
        mexc_base = 100.0
        gateio_base = 100.0
        
        mexc_prices = []
        gateio_prices = []
        
        for i in range(periods):
            # Normal correlated movement
            mexc_change = np.random.normal(0, 0.1)
            gateio_change = mexc_change * 0.8 + np.random.normal(0, 0.05)
            
            # Inject spikes periodically
            if i % spike_frequency == 50:
                spike_magnitude = np.random.uniform(0.3, 1.0)
                if np.random.random() > 0.5:
                    mexc_change += spike_magnitude
                    gateio_change += spike_magnitude * 0.6
                else:
                    gateio_change += spike_magnitude
                    mexc_change += spike_magnitude * 0.6
            
            mexc_price = mexc_base + mexc_change
            gateio_price = gateio_base + gateio_change
            
            mexc_prices.append(mexc_price)
            gateio_prices.append(gateio_price)
            
            mexc_base = mexc_price
            gateio_base = gateio_price
        
        # Create DataFrame
        df = pd.DataFrame({
            'timestamp': timestamps,
            'mexc_close': mexc_prices,
            'gateio_close': gateio_prices,
        })
        
        # Add futures prices (slightly lower due to funding rate effect)
        df['gateio_futures_close'] = df['gateio_close'] * 0.999
        
        # Calculate spread columns needed for strategies
        df['mexc_vs_gateio_pct'] = ((df['mexc_close'] - df['gateio_close']) / df['gateio_close']) * 100
        df['mexc_vs_gateio_fut_pct'] = ((df['mexc_close'] - df['gateio_futures_close']) / df['gateio_futures_close']) * 100
        df['gateio_vs_gateio_fut_pct'] = ((df['gateio_close'] - df['gateio_futures_close']) / df['gateio_futures_close']) * 100
        
        # Set attributes for column identification
        df.attrs['mexc_c_col'] = 'mexc_close'
        df.attrs['gateio_c_col'] = 'gateio_close'
        df.attrs['gateio_futures_c_col'] = 'gateio_futures_close'
        
        print(f"✅ Test data created: {len(df)} rows")
        print(f"   MEXC price range: ${min(mexc_prices):.2f} - ${max(mexc_prices):.2f}")
        print(f"   Gate.io price range: ${min(gateio_prices):.2f} - ${max(gateio_prices):.2f}")
        
        return df


def test_symbol_backtester():
    """Quick test of the symbol backtester"""
    
    print("🚀 SYMBOL BACKTESTER TEST")
    print("=" * 60)
    
    # Initialize backtester
    backtester = SymbolBacktester()
    
    # Create test data
    df = backtester.create_test_data(symbol="TEST_USDT", periods=500)
    
    # Run backtest
    results = backtester.backtest_optimized_spike_capture(
        df,
        min_differential=0.15,
        min_single_move=0.1,
        max_hold_minutes=10,
        profit_target_multiplier=0.4,
        symbol="TEST_USDT"
    )
    
    # Display results
    print("\n📊 BACKTEST RESULTS:")
    print("=" * 60)
    print(f"Symbol: {results['symbol']}")
    print(f"Total Trades: {results['total_trades']}")
    print(f"Win Rate: {results['win_rate']:.1f}%")
    print(f"Total P&L: {results['total_pnl_pct']:.3f}%")
    print(f"Average P&L: {results['avg_pnl_pct']:.3f}%")
    print(f"Best Trade: {results['max_pnl_pct']:.3f}%")
    print(f"Worst Trade: {results['min_pnl_pct']:.3f}%")
    print(f"Average Hold Time: {results['avg_hold_time']:.1f} minutes")
    print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    
    # Profitability check
    if results['total_pnl_pct'] > 0:
        print(f"\n✅ STRATEGY IS PROFITABLE!")
        print(f"   Net profit after all costs: {results['total_pnl_pct']:.3f}%")
    else:
        print(f"\n❌ Strategy shows losses: {results['total_pnl_pct']:.3f}%")
    
    return results


if __name__ == "__main__":
    """Main entry point for quick testing"""
    
    parser = argparse.ArgumentParser(description='Symbol Backtester')
    parser.add_argument('--symbol', type=str, default='TEST_USDT',
                       help='Symbol to test (default: TEST_USDT)')
    parser.add_argument('--periods', type=int, default=1000,
                       help='Number of periods for test data (default: 1000)')
    parser.add_argument('--quick', action='store_true',
                       help='Quick test mode')
    
    args = parser.parse_args()
    
    print(f"🎯 Testing symbol: {args.symbol}")
    print(f"📈 Data periods: {args.periods}")
    
    # Run test
    test_symbol_backtester()
    
    print("\n🎯 NEXT STEPS:")
    print("1. Replace test data with real market data")
    print("2. Test on multiple symbols")
    print("3. Optimize parameters for each symbol")
    print("4. Implement live trading integration")