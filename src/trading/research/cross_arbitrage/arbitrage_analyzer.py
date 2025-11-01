#!/usr/bin/env python3
"""
Arbitrage Analysis Tool

Analyzes arbitrage opportunities between MEXC spot, Gate.io spot, and Gate.io futures
using 5-minute candle data. Calculates optimal entry/exit points for delta-neutral 
arbitrage strategies.

Usage:
    analyzer = ArbitrageAnalyzer()
    df, results = await analyzer.run_analysis("BTC_USDT", days=7)
    print(analyzer.format_report(results))
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Union
import sys
import os

from db import initialize_database_manager

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from trading.research.cross_arbitrage.book_ticker_source import CandlesBookTickerSource, BookTickerDbSource
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from exchanges.structs import Symbol, AssetName
from trading.analysis.arbitrage_signals import calculate_arb_signals


class AnalyzerKeys:
    """Static keys for column names and arbitrage calculations."""
    
    # Exchange column keys
    mexc_bid = f'{ExchangeEnum.MEXC.value}_bid_price'
    mexc_ask = f'{ExchangeEnum.MEXC.value}_ask_price'
    gateio_spot_bid = f'{ExchangeEnum.GATEIO.value}_bid_price'
    gateio_spot_ask = f'{ExchangeEnum.GATEIO.value}_ask_price'
    gateio_futures_bid = f'{ExchangeEnum.GATEIO_FUTURES.value}_bid_price'
    gateio_futures_ask = f'{ExchangeEnum.GATEIO_FUTURES.value}_ask_price'
    
    # Arbitrage calculation keys
    mexc_vs_gateio_futures_arb = f'{ExchangeEnum.MEXC.value}_vs_{ExchangeEnum.GATEIO_FUTURES.value}_arb'
    gateio_spot_vs_futures_arb = f'{ExchangeEnum.GATEIO.value}_vs_{ExchangeEnum.GATEIO_FUTURES.value}_arb'


class ArbitrageAnalyzer:
    """
    Simple arbitrage analyzer for MEXC → Gate.io delta-neutral strategies.
    
    Calculates 4 arbitrage opportunities and finds optimal entry/exit points
    accounting for trading fees and market spreads.
    """
    
    # Remove SPREAD_BPS - now handled by BookTickerSource
    TOTAL_FEES = 0.25  # 0.1% + 0.05% + 0.05% total fees
    
    def __init__(self, exchanges: Optional[List[ExchangeEnum]] = None, use_db_book_tickers = False,
                 tf: Union[KlineInterval, int] = KlineInterval.MINUTE_5):
        """Initialize analyzer with modern BookTickerSource."""
        self.tf = tf
        self.exchanges = exchanges or [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
        self.book_ticker_source = BookTickerDbSource() if use_db_book_tickers else  CandlesBookTickerSource()
    
    async def run_analysis(self, symbol: Symbol, days: int = 7,
                           df_data: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Run complete arbitrage analysis for given symbol and time period.
        
        Args:
            symbol: Trading symbol (e.g., "BTC_USDT")
            days: Number of days to analyze
            
        Returns:
            Tuple of (dataframe with all calculations, analysis results dict)
        """
        print(f"🚀 Starting arbitrage analysis for {symbol} ({days} days)")
        
        # Load data using BookTickerSource (includes bid/ask prices)
        if df_data is not None:
            df = df_data
            print(f"💾 Using provided dataframe with {len(df)} periods")
        else:
            df = await self._download_and_merge_data(symbol, days)

        # Calculate arbitrage opportunities
        df = self._calculate_arbitrage_metrics(df)
        
        # Perform statistical analysis

        # Analysis completed
        print(f"💾 Analysis completed: {len(df)} periods analyzed")
        
        return df, {}
    
    async def _download_and_merge_data(self, symbol: Symbol, days: int) -> pd.DataFrame:
        """Download book ticker data using modern BookTickerSource architecture."""
        print(f"📥 Loading {symbol} book ticker data from 3 exchanges...")
        

        # Use BookTickerSource for data loading
        df = await self.book_ticker_source.get_multi_exchange_data(
            exchanges=self.exchanges,
            symbol=symbol,
            hours=round(days * 24),
            timeframe=self.tf
        )

        len_before = len(df)
        # df.fillna(method='ffill', inplace=True)

        df.dropna(inplace=True)

        print(f"🔀 Loaded data: {len(df)}(with nan: {len_before}) aligned periods")



        return df
    
    def _validate_required_columns(self, df: pd.DataFrame) -> None:
        """Validate that all required columns exist in the dataframe."""
        required_columns = [
            AnalyzerKeys.mexc_ask,
            AnalyzerKeys.mexc_bid,
            AnalyzerKeys.gateio_spot_bid,
            AnalyzerKeys.gateio_spot_ask,
            AnalyzerKeys.gateio_futures_bid,
            AnalyzerKeys.gateio_futures_ask
        ]
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
    
    def _calculate_arbitrage_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate arbitrage opportunities using AnalyzerKeys."""
        
        # Validate required columns exist
        self._validate_required_columns(df)
        
        # 1. MEXC vs Gate.io Futures arbitrage
        df[AnalyzerKeys.mexc_vs_gateio_futures_arb] = (
            (df[AnalyzerKeys.gateio_futures_bid] - df[AnalyzerKeys.mexc_ask]) / 
            df[AnalyzerKeys.gateio_futures_bid] * 100
        )
        
        # 2. Gate.io Spot vs Futures arbitrage
        df[AnalyzerKeys.gateio_spot_vs_futures_arb] = (
            (df[AnalyzerKeys.gateio_spot_bid] - df[AnalyzerKeys.gateio_futures_ask]) / 
            df[AnalyzerKeys.gateio_spot_bid] * 100
        )
        
        df = self.add_arb_signals_with_pnl(df)
        return df

    def add_arb_signals_with_pnl(
            self,
            df: pd.DataFrame,
            window_size: int = 10,
            total_fees: float = 0.0025,  # 0.25% total fees
            lookback_periods: int = 500,  # Fixed lookback like hedged backtest
            min_history: int = 50,  # Minimum periods before trading
    ) -> pd.DataFrame:
        """
        Add arbitrage signals with bidirectional position tracking and P&L calculation.
        Uses unified logic for both MEXC_TO_GATEIO and GATEIO_TO_MEXC directions.

        Args:
            df: DataFrame with price and arb columns
            window_size: Rolling window size for statistics (default: 10)
            total_fees: Total trading fees (default: 0.25%)
            lookback_periods: Fixed lookback period for percentile calculation (default: 500)
            min_history: Minimum periods before generating signals (default: 50)

        Returns:
            DataFrame with signals, positions, and P&L for both directions
        """
        mexc_col = AnalyzerKeys.mexc_vs_gateio_futures_arb
        gateio_col = AnalyzerKeys.gateio_spot_vs_futures_arb

        # Initialize unified signal columns for bidirectional trading
        df['signal'] = 'HOLD'
        df['direction'] = 'NONE'
        df['mexc_gateio_min_25pct'] = np.nan
        df['gateio_spot_max_25pct'] = np.nan
        df['mexc_gateio_mean'] = np.nan
        df['gateio_spot_mean'] = np.nan

        # Calculate signals using unified methodology from hedged backtest
        for i in range(len(df)):
            # Skip if insufficient history
            if i < min_history:
                continue
                
            # Get historical data (fixed lookback period like hedged backtest)
            start_idx = max(0, i - lookback_periods)
            mexc_history = df[mexc_col].iloc[start_idx:i+1].values
            gateio_history = df[gateio_col].iloc[start_idx:i+1].values
            
            # Use unified signal detection like hedged backtest
            if len(mexc_history) >= min_history:
                signal_result = calculate_arb_signals(
                    mexc_vs_gateio_futures_history=mexc_history,
                    gateio_spot_vs_futures_history=gateio_history,
                    current_mexc_vs_gateio_futures=df.iloc[i][mexc_col],
                    current_gateio_spot_vs_futures=df.iloc[i][gateio_col],
                    window_size=window_size
                )
                
                # Store statistics
                df.iloc[i, df.columns.get_loc('mexc_gateio_min_25pct')] = signal_result.mexc_vs_gateio_futures.min_25pct
                df.iloc[i, df.columns.get_loc('gateio_spot_max_25pct')] = signal_result.gateio_spot_vs_futures.max_25pct
                df.iloc[i, df.columns.get_loc('mexc_gateio_mean')] = signal_result.mexc_vs_gateio_futures.mean
                df.iloc[i, df.columns.get_loc('gateio_spot_mean')] = signal_result.gateio_spot_vs_futures.mean
                
                # Determine signal and direction using unified logic
                if signal_result.signal.value == 'ENTER':
                    # Choose direction based on spread magnitude (like hedged backtest)
                    mexc_spread_magnitude = abs(signal_result.mexc_vs_gateio_futures.current)
                    gateio_spread_magnitude = abs(signal_result.gateio_spot_vs_futures.current)
                    
                    if mexc_spread_magnitude >= gateio_spread_magnitude:
                        # MEXC spread is larger, go MEXC_TO_GATEIO
                        df.iloc[i, df.columns.get_loc('signal')] = 'ENTER'
                        df.iloc[i, df.columns.get_loc('direction')] = 'MEXC_TO_GATEIO'
                    else:
                        # Gate.io spread is larger, go GATEIO_TO_MEXC
                        df.iloc[i, df.columns.get_loc('signal')] = 'ENTER'
                        df.iloc[i, df.columns.get_loc('direction')] = 'GATEIO_TO_MEXC'
                elif signal_result.signal.value == 'EXIT':
                    df.iloc[i, df.columns.get_loc('signal')] = 'EXIT'
                    # Direction remains same as current position

        # --- Unified Bidirectional Position Tracking and P&L Calculation ---
        df['position_open'] = False
        df['source_spot_entry'] = np.nan
        df['hedge_futures_entry'] = np.nan
        df['dest_spot_exit'] = np.nan
        df['hedge_futures_exit'] = np.nan
        df['trade_pnl'] = 0.0
        df['cumulative_pnl'] = 0.0

        position_open = False
        position_direction = None
        source_spot_entry = 0.0
        hedge_futures_entry = 0.0
        cumulative_pnl = 0.0

        for idx in df.index:
            signal = df.loc[idx, 'signal']
            direction = df.loc[idx, 'direction']

            if signal == 'ENTER' and not position_open:
                # Open unified position based on direction
                position_direction = direction
                
                if direction == 'MEXC_TO_GATEIO':
                    # Buy MEXC spot, Sell Gate.io futures
                    source_spot_entry = df.loc[idx, AnalyzerKeys.mexc_ask]
                    hedge_futures_entry = df.loc[idx, AnalyzerKeys.gateio_futures_bid]
                elif direction == 'GATEIO_TO_MEXC':
                    # Buy Gate.io spot, Sell Gate.io futures
                    source_spot_entry = df.loc[idx, AnalyzerKeys.gateio_spot_ask]
                    hedge_futures_entry = df.loc[idx, AnalyzerKeys.gateio_futures_bid]

                df.loc[idx, 'position_open'] = True
                df.loc[idx, 'source_spot_entry'] = source_spot_entry
                df.loc[idx, 'hedge_futures_entry'] = hedge_futures_entry
                position_open = True

            elif signal == 'EXIT' and position_open:
                # Close unified position based on current direction
                if position_direction == 'MEXC_TO_GATEIO':
                    # Transfer complete: Sell Gate.io spot, Buy Gate.io futures
                    dest_spot_exit = df.loc[idx, AnalyzerKeys.gateio_spot_bid]
                    hedge_futures_exit = df.loc[idx, AnalyzerKeys.gateio_futures_ask]
                elif position_direction == 'GATEIO_TO_MEXC':
                    # Transfer complete: Sell MEXC spot, Buy Gate.io futures
                    dest_spot_exit = df.loc[idx, AnalyzerKeys.mexc_bid]
                    hedge_futures_exit = df.loc[idx, AnalyzerKeys.gateio_futures_ask]

                # THREE-EXCHANGE DELTA-NEUTRAL P&L CALCULATION
                # Gate.io Futures always provides hedging reference
                # Calculate actual position values for proper delta-neutral P&L
                
                # Spot leg P&L: Exit price vs Entry price (percentage)
                spot_leg_pnl_pct = (dest_spot_exit - source_spot_entry) / source_spot_entry
                
                # Futures hedge P&L: We sold futures at entry, buy back at exit
                futures_leg_pnl_pct = (hedge_futures_entry - hedge_futures_exit) / hedge_futures_entry
                
                # Total delta-neutral P&L (both legs combined)
                gross_pnl_pct = spot_leg_pnl_pct + futures_leg_pnl_pct
                trade_pnl = gross_pnl_pct - total_fees

                df.loc[idx, 'dest_spot_exit'] = dest_spot_exit
                df.loc[idx, 'hedge_futures_exit'] = hedge_futures_exit
                df.loc[idx, 'trade_pnl'] = trade_pnl * 100  # Convert to percentage
                cumulative_pnl += trade_pnl * 100
                df.loc[idx, 'cumulative_pnl'] = cumulative_pnl

                position_open = False
                position_direction = None

            # Forward fill position state
            if position_open:
                df.loc[idx, 'position_open'] = True
                df.loc[idx, 'direction'] = position_direction
                df.loc[idx, 'source_spot_entry'] = source_spot_entry
                df.loc[idx, 'hedge_futures_entry'] = hedge_futures_entry

            # Forward fill cumulative P&L
            df.loc[idx, 'cumulative_pnl'] = cumulative_pnl

        return df

    def _analyze_streaks(self, is_profitable: pd.Series) -> Dict[str, Any]:
        """Analyze consecutive profitable periods."""
        streaks = []
        current_streak = 0
        
        for profitable in is_profitable:
            if profitable:
                current_streak += 1
            else:
                if current_streak > 0:
                    streaks.append(current_streak)
                current_streak = 0
        
        if current_streak > 0:
            streaks.append(current_streak)
        
        if not streaks:
            return {'count': 0, 'avg_length': 0, 'max_length': 0}
        
        return {
            'count': len(streaks),
            'avg_length': sum(streaks) / len(streaks),
            'max_length': max(streaks),
            'total_profitable_periods': sum(streaks)
        }
    
    def format_report(self, results: Dict[str, Any]) -> str:
        """Format analysis results into a readable report."""
        symbol = results['symbol']
        days = results['days_analyzed']
        
        report = f"""
🎯 ARBITRAGE ANALYSIS REPORT - {symbol} ({days} days)
{'='*60}

📊 OVERALL PROFITABILITY:
  • Profitable periods: {results['profitability_pct']:.1f}%
  • Average profit when profitable: {results['avg_profit_when_profitable']:.3f}%
  • Max profit observed: {results['max_profit']:.3f}%
  • Min profit observed: {results['min_profit']:.3f}%

🚀 OPTIMAL ENTRY POINTS (Total Arbitrage Sum):
  • Conservative (25th percentile): {results['entry_thresholds']['25th_percentile']:.3f}%
  • Aggressive (10th percentile): {results['entry_thresholds']['10th_percentile']:.3f}%
  • Very Aggressive (5th percentile): {results['entry_thresholds']['5th_percentile']:.3f}%

📈 INDIVIDUAL METRICS:
  MEXC → Gate.io Futures Arbitrage:
    Mean: {results['mexc_futures_arb_stats']['mean']:.3f}% | Std: {results['mexc_futures_arb_stats']['std']:.3f}%

  Gate.io Spot vs Futures Arbitrage:  
    Mean: {results['spot_futures_arb_stats']['mean']:.3f}% | Std: {results['spot_futures_arb_stats']['std']:.3f}%

  Total Arbitrage (After Fees):
    Mean: {results['total_arb_stats']['mean']:.3f}% | Std: {results['total_arb_stats']['std']:.3f}%

⏱️  PROFITABLE STREAKS:
  • Number of profitable streaks: {results['profitable_streaks']['count']}
  • Average streak length: {results['profitable_streaks']['avg_length']:.1f} periods
  • Longest streak: {results['profitable_streaks']['max_length']} periods

💡 STRATEGY RECOMMENDATIONS:
  1. Enter positions when total arbitrage > {results['entry_thresholds']['10th_percentile']:.3f}%
  2. Exit when arbitrage approaches 0% or turns negative
  3. Average holding period: ~{results['profitable_streaks']['avg_length']:.0f} × 5min = {results['profitable_streaks']['avg_length']*5:.0f} minutes
  
⚠️  RISK FACTORS:
  • Assumes {self.SPREAD_BPS} bps spread | {self.TOTAL_FEES}% total fees
  • Based on simulated bid/ask from close prices
  • Historical analysis - future results may vary
"""
        return report


if __name__ == "__main__":
    async def main():
        await initialize_database_manager()  # Ensure DB manager is initialized
        analyzer = ArbitrageAnalyzer()
        
        # Quick test with 1 day of data
        try:
            df, results = await analyzer.run_analysis("F_USDT", days=1)
            print(analyzer.format_report(results))
            
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
    
    asyncio.run(main())