#!/usr/bin/env python3
"""
SpreadAnalyzer - Arbitrage Spread Analysis Engine

Analyzes price spreads between exchanges to identify arbitrage opportunities.
Provides comprehensive metrics and scoring for profitable trading opportunities.

Key Features:
- Calculates multi-dimensional arbitrage metrics
- Generates comprehensive scoring system
- Exports analysis results to CSV reports
- Provides statistical analysis and insights

Usage:
    from spread_analyzer import SpreadAnalyzer
    
    analyzer = SpreadAnalyzer(data_dir="data/arbitrage")
    results = analyzer.analyze_all_symbols()
    analyzer.generate_csv_report(results, "report.csv")
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import glob

from infrastructure.logging.factory import get_logger


@dataclass
class ArbitrageMetrics:
    """Comprehensive arbitrage metrics for a trading pair."""
    pair: str
    max_spread: float
    avg_spread: float
    med_spread: float
    spread_gt_0_3_percent: float
    spread_gt_0_5_percent: float
    count_gt_0_3_percent: int
    count_gt_0_5_percent: int
    opportunity_minutes_per_day: float
    avg_duration_seconds: float
    liquidity_score: float
    execution_score: float
    risk_score: float
    profit_score: float
    total_data_points: int
    exchanges: List[str]


class SpreadAnalyzer:
    """
    Advanced spread analysis engine for cryptocurrency arbitrage opportunities.
    
    Analyzes historical candles data from multiple exchanges to identify
    profitable arbitrage opportunities with comprehensive scoring.
    """
    
    def __init__(self, data_dir: str = "data/arbitrage"):
        """
        Initialize the SpreadAnalyzer.
        
        Args:
            data_dir: Directory containing collected candles data files
        """
        self.data_dir = Path(data_dir)
        self.logger = get_logger("SpreadAnalyzer")
        
        # Analysis configuration
        self.min_data_points = 100  # Minimum data points for reliable analysis
        self.spread_thresholds = {
            'low': 0.1,      # 0.1% - minimum spread for consideration
            'medium': 0.3,   # 0.3% - profitable spread threshold
            'high': 0.5      # 0.5% - high profit spread threshold
        }
        
        # Scoring weights for profit score calculation
        self.scoring_weights = {
            'max_spread': 0.25,
            'frequency': 0.35,
            'duration': 0.15,
            'liquidity': 0.15,
            'risk': 0.10
        }
    
    def discover_available_symbols(self) -> List[str]:
        """
        Discover symbols with available data for analysis.
        
        Returns:
            List of symbol pairs with sufficient data
        """
        self.logger.info(f"🔍 Discovering available symbols in: {self.data_dir}")
        
        if not self.data_dir.exists():
            self.logger.warning(f"Data directory does not exist: {self.data_dir}")
            return []
        
        # Find all CSV files matching exchange pattern
        csv_files = list(self.data_dir.glob("*_USDT_1m_*.csv"))
        
        if not csv_files:
            self.logger.warning("No CSV files found in data directory")
            return []
        
        # Extract unique symbols from filenames
        symbols = set()
        for file_path in csv_files:
            # Parse filename like: GATEIO_FUTURES_BTC_USDT_1m_20250919_20250922.csv
            filename = file_path.stem
            parts = filename.split('_')
            
            if len(parts) >= 4 and parts[-3] == '1m':
                # Extract base currency (e.g., BTC from BTC_USDT)
                base_idx = -4
                quote_idx = -3
                if base_idx < len(parts) and quote_idx < len(parts):
                    base = parts[base_idx]
                    quote = parts[quote_idx - 1]  # USDT is before 1m
                    symbol = f"{base}/{quote}"
                    symbols.add(symbol)
        
        available_symbols = sorted(list(symbols))
        self.logger.info(f"📊 Found {len(available_symbols)} symbols with data")
        
        return available_symbols
    
    def load_symbol_data(self, symbol: str) -> Optional[Dict[str, pd.DataFrame]]:
        """
        Load data for a specific symbol from all available exchanges.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            
        Returns:
            Dictionary mapping exchange names to DataFrames, or None if insufficient data
        """
        base, quote = symbol.split('/')
        search_pattern = f"*_{base}_{quote}_1m_*.csv"
        
        files = list(self.data_dir.glob(search_pattern))
        
        if len(files) < 2:
            self.logger.debug(f"Insufficient data files for {symbol}: {len(files)} files found")
            return None
        
        exchange_data = {}
        
        for file_path in files:
            try:
                # Extract exchange name from filename
                filename = file_path.stem
                parts = filename.split('_')
                exchange_name = '_'.join(parts[:2])  # e.g., "GATEIO_FUTURES"
                
                # Load CSV data
                df = pd.read_csv(file_path)
                
                # Validate required columns
                required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                if not all(col in df.columns for col in required_cols):
                    self.logger.warning(f"Missing columns in {file_path}")
                    continue
                
                # Convert timestamp and set as index
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp').sort_index()
                
                # Validate data quality
                if len(df) < self.min_data_points:
                    self.logger.debug(f"Insufficient data points for {symbol} on {exchange_name}: {len(df)}")
                    continue
                
                exchange_data[exchange_name] = df
                
            except Exception as e:
                self.logger.warning(f"Failed to load {file_path}: {e}")
                continue
        
        if len(exchange_data) < 2:
            self.logger.debug(f"Insufficient exchanges for {symbol}: {len(exchange_data)} exchanges")
            return None
        
        return exchange_data
    
    def calculate_spreads(self, exchange_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Calculate spreads between exchanges for the given data.
        
        Args:
            exchange_data: Dictionary mapping exchange names to price data
            
        Returns:
            DataFrame with spread calculations
        """
        # Align all exchange data to common timestamps
        all_exchanges = list(exchange_data.keys())
        
        # Use close prices for spread calculation
        price_data = {}
        for exchange, df in exchange_data.items():
            price_data[exchange] = df['close']
        
        # Combine all price data
        combined_prices = pd.DataFrame(price_data)
        
        # Forward fill small gaps, drop rows with any NaN
        combined_prices = combined_prices.fillna(method='ffill', limit=5)
        combined_prices = combined_prices.dropna()
        
        if len(combined_prices) < self.min_data_points:
            return pd.DataFrame()
        
        # Calculate spreads between all exchange pairs
        spread_results = []
        
        for i in range(len(all_exchanges)):
            for j in range(i + 1, len(all_exchanges)):
                exchange_a = all_exchanges[i]
                exchange_b = all_exchanges[j]
                
                price_a = combined_prices[exchange_a]
                price_b = combined_prices[exchange_b]
                
                # Calculate percentage spread
                spread = abs(price_a - price_b) / ((price_a + price_b) / 2) * 100
                
                spread_results.append({
                    'timestamp': combined_prices.index,
                    'exchange_pair': f"{exchange_a}_{exchange_b}",
                    'spread_pct': spread
                })
        
        if not spread_results:
            return pd.DataFrame()
        
        # Create final spread DataFrame
        spread_df = pd.DataFrame({
            'timestamp': spread_results[0]['timestamp']
        })
        
        # Add all spread columns
        for result in spread_results:
            spread_df[result['exchange_pair']] = result['spread_pct'].values
        
        # Calculate maximum spread across all exchange pairs
        spread_cols = [col for col in spread_df.columns if col != 'timestamp']
        spread_df['max_spread'] = spread_df[spread_cols].max(axis=1)
        spread_df['avg_spread'] = spread_df[spread_cols].mean(axis=1)
        
        return spread_df
    
    def analyze_symbol(self, symbol: str) -> Optional[ArbitrageMetrics]:
        """
        Perform comprehensive arbitrage analysis for a single symbol.
        
        Args:
            symbol: Trading pair symbol to analyze
            
        Returns:
            ArbitrageMetrics object with analysis results, or None if analysis failed
        """
        self.logger.debug(f"Analyzing symbol: {symbol}")
        
        # Load symbol data
        exchange_data = self.load_symbol_data(symbol)
        if not exchange_data:
            return None
        
        # Calculate spreads
        spread_df = self.calculate_spreads(exchange_data)
        if spread_df.empty:
            return None
        
        # Calculate core spread metrics
        max_spread = spread_df['max_spread'].max()
        avg_spread = spread_df['max_spread'].mean()
        med_spread = spread_df['max_spread'].median()
        
        # Calculate opportunity frequencies
        gt_0_3_mask = spread_df['max_spread'] > self.spread_thresholds['medium']
        gt_0_5_mask = spread_df['max_spread'] > self.spread_thresholds['high']
        
        count_gt_0_3 = gt_0_3_mask.sum()
        count_gt_0_5 = gt_0_5_mask.sum()
        total_points = len(spread_df)
        
        spread_gt_0_3_percent = (count_gt_0_3 / total_points) * 100 if total_points > 0 else 0
        spread_gt_0_5_percent = (count_gt_0_5 / total_points) * 100 if total_points > 0 else 0
        
        # Calculate opportunity duration metrics
        opportunity_minutes_per_day = (count_gt_0_3 / total_points) * 1440 if total_points > 0 else 0  # 1440 min/day
        
        # Estimate average duration (simplified)
        avg_duration_seconds = 60.0  # Assume 1-minute minimum duration for now
        
        # Calculate scoring components
        liquidity_score = min(100, len(exchange_data) * 20)  # More exchanges = better liquidity
        execution_score = max(0, 100 - (avg_spread * 20))    # Lower average spread = better execution
        risk_score = min(100, max_spread * 10)               # Higher max spread = higher risk
        
        # Calculate composite profit score
        profit_score = self._calculate_profit_score(
            max_spread, spread_gt_0_3_percent, opportunity_minutes_per_day,
            liquidity_score, risk_score
        )
        
        # Create metrics object
        metrics = ArbitrageMetrics(
            pair=symbol,
            max_spread=max_spread,
            avg_spread=avg_spread,
            med_spread=med_spread,
            spread_gt_0_3_percent=spread_gt_0_3_percent,
            spread_gt_0_5_percent=spread_gt_0_5_percent,
            count_gt_0_3_percent=count_gt_0_3,
            count_gt_0_5_percent=count_gt_0_5,
            opportunity_minutes_per_day=opportunity_minutes_per_day,
            avg_duration_seconds=avg_duration_seconds,
            liquidity_score=liquidity_score,
            execution_score=execution_score,
            risk_score=risk_score,
            profit_score=profit_score,
            total_data_points=total_points,
            exchanges=list(exchange_data.keys())
        )
        
        return metrics
    
    def _calculate_profit_score(self, max_spread: float, frequency_pct: float, 
                              minutes_per_day: float, liquidity_score: float, 
                              risk_score: float) -> float:
        """
        Calculate composite profit score using weighted components.
        
        Args:
            max_spread: Maximum observed spread percentage
            frequency_pct: Percentage of time with profitable spreads
            minutes_per_day: Minutes per day with opportunities
            liquidity_score: Liquidity assessment score
            risk_score: Risk assessment score
            
        Returns:
            Composite profit score (0-100)
        """
        # Normalize components to 0-100 scale
        spread_component = min(100, max_spread * 50)        # Max spread contribution
        frequency_component = frequency_pct                  # Already 0-100
        duration_component = min(100, minutes_per_day / 10)  # Duration contribution
        liquidity_component = liquidity_score               # Already 0-100
        risk_component = 100 - risk_score                   # Invert risk (lower risk = higher score)
        
        # Calculate weighted average
        profit_score = (
            spread_component * self.scoring_weights['max_spread'] +
            frequency_component * self.scoring_weights['frequency'] +
            duration_component * self.scoring_weights['duration'] +
            liquidity_component * self.scoring_weights['liquidity'] +
            risk_component * self.scoring_weights['risk']
        )
        
        return round(profit_score, 1)
    
    def analyze_all_symbols(self, max_symbols: Optional[int] = None, 
                          incremental_output: Optional[str] = None) -> List[ArbitrageMetrics]:
        """
        Analyze all available symbols for arbitrage opportunities.
        
        Args:
            max_symbols: Maximum number of symbols to analyze
            incremental_output: Optional file path for incremental results
            
        Returns:
            List of ArbitrageMetrics sorted by profit score (descending)
        """
        symbols = self.discover_available_symbols()
        
        if max_symbols:
            symbols = symbols[:max_symbols]
        
        self.logger.info(f"📊 Analyzing {len(symbols)} symbols for arbitrage opportunities")
        
        results = []
        incremental_file = None
        
        if incremental_output:
            # Prepare incremental CSV file
            incremental_file = open(incremental_output, 'w')
            incremental_file.write("pair,max_spread,avg_spread,spread_gt_0_3_percent,opportunity_minutes_per_day,profit_score\n")
        
        try:
            for i, symbol in enumerate(symbols, 1):
                self.logger.info(f"🔍 [{i}/{len(symbols)}] Analyzing {symbol}...")
                
                metrics = self.analyze_symbol(symbol)
                
                if metrics:
                    results.append(metrics)
                    self.logger.info(f"✅ {symbol}: Profit Score {metrics.profit_score:.1f}, Max Spread {metrics.max_spread:.3f}%")
                    
                    # Write incremental results
                    if incremental_file:
                        incremental_file.write(f"{metrics.pair},{metrics.max_spread:.3f},{metrics.avg_spread:.3f},"
                                             f"{metrics.spread_gt_0_3_percent:.1f},{metrics.opportunity_minutes_per_day:.1f},"
                                             f"{metrics.profit_score:.1f}\n")
                        incremental_file.flush()
                else:
                    self.logger.warning(f"❌ {symbol}: Analysis failed (insufficient data)")
        
        finally:
            if incremental_file:
                incremental_file.close()
        
        # Sort by profit score (descending)
        results.sort(key=lambda x: x.profit_score, reverse=True)
        
        self.logger.info(f"✅ Analysis completed: {len(results)} symbols analyzed")
        
        return results
    
    def generate_csv_report(self, results: List[ArbitrageMetrics], output_file: str) -> str:
        """
        Generate a comprehensive CSV report from analysis results.
        
        Args:
            results: List of ArbitrageMetrics to include in report
            output_file: Output CSV file path
            
        Returns:
            Path to generated report file
        """
        # Ensure output directory exists
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert results to DataFrame
        data = []
        for metrics in results:
            data.append({
                'rank': len(data) + 1,
                'pair': metrics.pair,
                'max_spread_%': metrics.max_spread,
                'avg_spread_%': metrics.avg_spread,
                'median_spread_%': metrics.med_spread,
                'spread_>0.3%_freq_%': metrics.spread_gt_0_3_percent,
                'spread_>0.5%_freq_%': metrics.spread_gt_0_5_percent,
                'opportunity_count_0.3%': metrics.count_gt_0_3_percent,
                'opportunity_count_0.5%': metrics.count_gt_0_5_percent,
                'opportunity_minutes_per_day': metrics.opportunity_minutes_per_day,
                'avg_duration_seconds': metrics.avg_duration_seconds,
                'liquidity_score': metrics.liquidity_score,
                'execution_score': metrics.execution_score,
                'risk_score': metrics.risk_score,
                'profit_score': metrics.profit_score,
                'total_data_points': metrics.total_data_points,
                'exchanges': '|'.join(metrics.exchanges),
                'num_exchanges': len(metrics.exchanges)
            })
        
        df = pd.DataFrame(data)
        df.to_csv(output_path, index=False, float_format='%.3f')
        
        self.logger.info(f"📄 CSV report generated: {output_path}")
        
        return str(output_path)
    
    def generate_summary_stats(self, results: List[ArbitrageMetrics]) -> Dict[str, Any]:
        """
        Generate summary statistics from analysis results.
        
        Args:
            results: List of ArbitrageMetrics to summarize
            
        Returns:
            Dictionary with summary statistics
        """
        if not results:
            return {}
        
        profit_scores = [r.profit_score for r in results]
        max_spreads = [r.max_spread for r in results]
        
        summary = {
            'total_opportunities': len(results),
            'high_profit_opportunities': len([r for r in results if r.profit_score >= 70]),
            'medium_profit_opportunities': len([r for r in results if 40 <= r.profit_score < 70]),
            'low_profit_opportunities': len([r for r in results if 1 <= r.profit_score < 40]),
            'avg_profit_score': np.mean(profit_scores),
            'max_profit_score': max(profit_scores),
            'min_profit_score': min(profit_scores),
            'avg_max_spread': np.mean(max_spreads),
            'best_symbol': results[0].pair if results else None,
            'best_profit_score': results[0].profit_score if results else 0
        }
        
        return summary