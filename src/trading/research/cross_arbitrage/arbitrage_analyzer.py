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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import sys
import os

from db import initialize_database_manager

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from trading.research.cross_arbitrage.book_ticker_source import CandlesBookTickerSource, BookTickerDbSource
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from exchanges.structs import Symbol, AssetName


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
                 tf: KlineInterval = KlineInterval.MINUTE_5):
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
        results = self._analyze_profitability(df)
        results['symbol'] = symbol
        results['days_analyzed'] = days
        results['total_periods'] = len(df)
        
        # Analysis completed
        print(f"💾 Analysis completed: {len(df)} periods analyzed")
        
        return df, results
    
    async def _download_and_merge_data(self, symbol: Symbol, days: int) -> pd.DataFrame:
        """Download book ticker data using modern BookTickerSource architecture."""
        print(f"📥 Loading {symbol} book ticker data from 3 exchanges...")
        

        # Use BookTickerSource for data loading
        df = await self.book_ticker_source.get_multi_exchange_data(
            exchanges=self.exchanges,
            symbol=symbol,
            hours=days * 24,
            timeframe=self.tf
        )

        len_before = len(df)

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
        
        # Calculate total arbitrage sum
        df['total_arbitrage_sum'] = (
            df[AnalyzerKeys.mexc_vs_gateio_futures_arb] + df[AnalyzerKeys.gateio_spot_vs_futures_arb]
        )
        
        # Apply fees
        df['total_arbitrage_sum_fees'] = df['total_arbitrage_sum'] - self.TOTAL_FEES
        
        # Mark profitable periods
        df['is_profitable'] = df['total_arbitrage_sum_fees'] > 0
        
        return df
    
    def _analyze_profitability(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Perform statistical analysis to find optimal entry/exit points."""
        profitable_df = df[df['is_profitable']]
        
        results = {
            # Overall profitability
            'profitability_pct': len(profitable_df) / len(df) * 100,
            'avg_profit_when_profitable': profitable_df['total_arbitrage_sum_fees'].mean() if len(profitable_df) > 0 else 0,
            'max_profit': df['total_arbitrage_sum_fees'].max(),
            'min_profit': df['total_arbitrage_sum_fees'].min(),

            # Entry point analysis (percentiles of total arbitrage sum)
            'entry_thresholds': {
                '25th_percentile': df['total_arbitrage_sum'].quantile(0.25),
                '10th_percentile': df['total_arbitrage_sum'].quantile(0.10),
                '5th_percentile': df['total_arbitrage_sum'].quantile(0.05),
            },

            # Individual arbitrage metrics
            'mexc_futures_arb_stats': self._metric_stats(df, AnalyzerKeys.mexc_vs_gateio_futures_arb),
            'spot_futures_arb_stats': self._metric_stats(df, AnalyzerKeys.gateio_spot_vs_futures_arb),
            'total_arb_stats': self._metric_stats(df, 'total_arbitrage_sum_fees'),
        }
        
        # Profitable streak analysis
        results['profitable_streaks'] = self._analyze_streaks(df['is_profitable'])

        return results
    
    def _metric_stats(self, df: pd.DataFrame, column: str) -> Dict[str, float]:
        """Calculate basic statistics for a metric column."""
        return {
            'mean': df[column].mean(),
            'std': df[column].std(),
            'min': df[column].min(),
            'max': df[column].max(),
            'median': df[column].median(),
        }
    
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