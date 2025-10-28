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

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from applications.tools.candles_downloader import CandlesDownloader
from exchanges.structs.enums import ExchangeEnum


class ArbitrageAnalyzer:
    """
    Simple arbitrage analyzer for MEXC → Gate.io delta-neutral strategies.
    
    Calculates 4 arbitrage opportunities and finds optimal entry/exit points
    accounting for trading fees and market spreads.
    """
    
    SPREAD_BPS = 5  # 0.05% spread assumption for bid/ask simulation
    TOTAL_FEES = 0.25  # 0.1% + 0.05% + 0.05% total fees
    
    def __init__(self, cache_dir: str = "cache", exchanges: Optional[List[ExchangeEnum]] = None):
        """Initialize analyzer with configurable cache directory."""
        self.exchanges = exchanges or [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]

        self.cache_dir = Path(__file__).parent / cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self.downloader = CandlesDownloader(output_dir=str(self.cache_dir))
    
    async def run_analysis(self, symbol: str, days: int = 7) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Run complete arbitrage analysis for given symbol and time period.
        
        Args:
            symbol: Trading symbol (e.g., "BTC_USDT")
            days: Number of days to analyze
            
        Returns:
            Tuple of (dataframe with all calculations, analysis results dict)
        """
        print(f"🚀 Starting arbitrage analysis for {symbol} ({days} days)")
        
        # Download candle data
        df = await self._download_and_merge_data(symbol, days)
        
        # Simulate bid/ask prices
        df = self._simulate_bid_ask_prices(df)
        
        # Calculate arbitrage opportunities
        df = self._calculate_arbitrage_metrics(df)
        
        # Perform statistical analysis
        results = self._analyze_profitability(df)
        results['symbol'] = symbol
        results['days_analyzed'] = days
        results['total_periods'] = len(df)
        
        # Save results
        output_file = self.cache_dir / f"{symbol}_arbitrage_analysis_{days}d.csv"
        df.to_csv(output_file, index=False)
        print(f"💾 Results saved to: {output_file}")
        
        return df, results
    
    async def _download_and_merge_data(self, symbol: str, days: int) -> pd.DataFrame:
        """Download candles from all 3 exchanges and merge by timestamp."""
        print(f"📥 Downloading {symbol} candles from 3 exchanges...")
        

        dfs = {}
        for exchange in self.exchanges:
            try:
                prefix = exchange.value.lower()
                csv_path = await self.downloader.download_candles(
                    exchange=exchange,
                    symbol=symbol,
                    timeframe="5m",
                    days=days
                )
                
                df = pd.read_csv(csv_path)
                df['timestamp'] = pd.to_datetime(df['datetime'])
                df = df.set_index('timestamp')
                
                # Rename columns with exchange prefix
                price_cols = ['open', 'high', 'low', 'close', 'volume']
                for col in price_cols:
                    df[f"{prefix}_{col}"] = df[col]
                
                dfs[prefix] = df[[f"{prefix}_{col}" for col in price_cols]]
                print(f"✅ {exchange.value}: {len(df)} candles")
                
            except Exception as e:
                print(f"❌ Failed to download {exchange.value}: {e}")
                raise
        
        # Merge all dataframes by timestamp
        merged_df = pd.concat(dfs.values(), axis=1)
        merged_df = merged_df.fillna(method='ffill').dropna()
        
        print(f"🔀 Merged data: {len(merged_df)} aligned periods")
        return merged_df.reset_index()
    
    def _simulate_bid_ask_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """Simulate bid/ask prices from close prices using spread assumption."""
        spread_factor = self.SPREAD_BPS / 10000  # Convert bps to decimal
        
        for exchange in self.exchanges:
            prefix = exchange.value.lower()
            close_col = f"{prefix}_close"
            if close_col in df.columns:
                df[f"{prefix}_bid_price"] = df[close_col] * (1 - spread_factor)
                df[f"{prefix}_ask_price"] = df[close_col] * (1 + spread_factor)
        
        return df
    
    def _calculate_arbitrage_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate the 4 arbitrage opportunities as specified."""
        
        # 1. MEXC vs Gate.io Futures (market order)
        df['mexc_vs_gateio_futures_arb'] = (
            (df['gateio_futures_bid_price'] - df['mexc_spot_ask_price']) / 
            df['gateio_futures_bid_price'] * 100
        )
        
        # 2. Gate.io Spot vs Futures
        df['gateio_spot_vs_futures_arb'] = (
            (df['gateio_spot_bid_price'] - df['gateio_futures_ask_price']) / 
            df['gateio_spot_bid_price'] * 100
        )
        
        # Calculate total arbitrage sum
        df['total_arbitrage_sum'] = (
            df['mexc_vs_gateio_futures_arb'] + df['gateio_spot_vs_futures_arb']
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
            'mexc_futures_arb_stats': self._metric_stats(df, 'mexc_vs_gateio_futures_arb'),
            'spot_futures_arb_stats': self._metric_stats(df, 'gateio_spot_vs_futures_arb'),
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
        analyzer = ArbitrageAnalyzer()
        
        # Quick test with 1 day of data
        try:
            df, results = await analyzer.run_analysis("F_USDT", days=1)
            print(analyzer.format_report(results))
            
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
    
    asyncio.run(main())