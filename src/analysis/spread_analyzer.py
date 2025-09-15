#!/usr/bin/env python3
"""
Spread Analyzer

Task 2: Arbitrage analysis engine that processes historical data to identify
profitable opportunities and generates comprehensive performance reports.

Generates CSV report with exact columns:
pair,max_spread,avg_spread,med_spread,spread_>0.3%,count_>0.3%,spread_>0.5%,count_>0.5%,
opportunity_minutes_per_day,avg_duration_seconds,liquidity_score,execution_score,
risk_score,profit_score,composite_rank
"""

import asyncio
import csv
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from msgspec import Struct

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import utility classes
from analysis.utils.data_loader import DataLoader, CandleData
from analysis.utils.spread_calculator import SpreadCalculator, SpreadData
from analysis.utils.metrics import MetricsCalculator


class ArbitrageMetrics(Struct):
    """Complete arbitrage metrics as specified in requirements"""
    pair: str
    max_spread: float
    avg_spread: float
    med_spread: float
    spread_gt_0_3_percent: float        # % of time spread > 0.3%
    count_gt_0_3_percent: int          # Number of 1-min periods > 0.3%
    spread_gt_0_5_percent: float        # % of time spread > 0.5%
    count_gt_0_5_percent: int          # Number of 1-min periods > 0.5%
    opportunity_minutes_per_day: float  # Average opportunity duration per day
    avg_duration_seconds: float        # Average single opportunity duration
    liquidity_score: float             # 0-100, order book depth analysis
    execution_score: float             # 0-100, ease of execution
    risk_score: float                  # 0-100, volatility and correlation risk
    profit_score: float                # 0-100, risk-adjusted profitability
    composite_rank: int                # Overall ranking (1 = best)


class SpreadAnalyzer:
    """
    High-performance arbitrage analysis engine.
    
    Processes historical candlestick data to calculate spreads between exchanges
    and generate comprehensive performance metrics for trading opportunities.
    
    Features:
    - Memory-efficient streaming processing
    - Sub-millisecond spread calculations
    - Comprehensive statistical analysis
    - Risk and execution scoring
    """
    
    def __init__(self, data_dir: str):
        """
        Initialize spread analyzer.
        
        Args:
            data_dir: Directory containing historical CSV data
        """
        self.data_dir = Path(data_dir)
        
        # Initialize components
        self.data_loader = DataLoader(str(self.data_dir))
        self.spread_calculator = SpreadCalculator()
        self.metrics_calculator = MetricsCalculator()
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        if not self.data_dir.exists():
            raise ValueError(f"Data directory does not exist: {data_dir}")
    
    def discover_available_symbols(self) -> List[str]:
        """
        Discover symbols that have data from both MEXC and Gate.io.
        
        Returns:
            List of symbols with complete data
        """
        # Find all CSV files
        csv_files = list(self.data_dir.glob("*.csv"))
        
        # Group by symbol
        symbol_files = {}
        for file_path in csv_files:
            filename = file_path.name
            
            # Extract symbol from filename (e.g., "mexc_BTC_USDT_1m_20240613_20240913.csv")
            parts = filename.split('_')
            if len(parts) >= 3:
                exchange = parts[0]
                symbol = f"{parts[1]}_{parts[2]}"
                
                if symbol not in symbol_files:
                    symbol_files[symbol] = set()
                symbol_files[symbol].add(exchange)
        
        # Find symbols with both exchanges
        complete_symbols = [
            symbol for symbol, exchanges in symbol_files.items()
            if 'mexc' in exchanges and 'gateio' in exchanges
        ]
        
        self.logger.info(f"Found {len(complete_symbols)} symbols with complete data")
        return sorted(complete_symbols)
    
    def analyze_symbol(self, symbol: str, chunk_size: int = 10000) -> Optional[ArbitrageMetrics]:
        """
        Analyze arbitrage opportunities for a single symbol.
        
        Args:
            symbol: Trading symbol (e.g., "BTC_USDT")
            chunk_size: Chunk size for memory-efficient processing
            
        Returns:
            ArbitrageMetrics or None if analysis failed
        """
        try:
            self.logger.info(f"Analyzing {symbol}...")
            
            # Find data files
            files = self.data_loader.find_symbol_files(symbol)
            
            if not files['mexc'] or not files['gateio']:
                self.logger.warning(f"Missing data files for {symbol}")
                return None
            
            # Process data in chunks for memory efficiency
            all_spreads = []
            mexc_candles_sample = []
            gateio_candles_sample = []
            
            mexc_chunks = self.data_loader.load_candle_data(files['mexc'], chunk_size)
            gateio_chunks = self.data_loader.load_candle_data(files['gateio'], chunk_size)
            
            # Process chunks in parallel
            for mexc_chunk, gateio_chunk in zip(mexc_chunks, gateio_chunks):
                # Store sample for liquidity analysis
                if len(mexc_candles_sample) < 1000:
                    mexc_candles_sample.extend(mexc_chunk[:100])
                if len(gateio_candles_sample) < 1000:
                    gateio_candles_sample.extend(gateio_chunk[:100])
                
                # Synchronize timestamps
                synchronized_pairs = self.data_loader.synchronize_timestamps(mexc_chunk, gateio_chunk)
                
                if not synchronized_pairs:
                    continue
                
                # Calculate spreads
                chunk_spreads = self.spread_calculator.calculate_batch_spreads(synchronized_pairs)
                all_spreads.extend(chunk_spreads)
            
            if not all_spreads:
                self.logger.warning(f"No valid spreads calculated for {symbol}")
                return None
            
            # Calculate analysis period in days
            if all_spreads:
                start_time = min(s.timestamp for s in all_spreads)
                end_time = max(s.timestamp for s in all_spreads)
                analysis_days = (end_time - start_time) / (1000 * 60 * 60 * 24)  # Convert ms to days
            else:
                analysis_days = 7  # Default 7 days
            
            # Calculate all metrics
            metrics_dict = self.metrics_calculator.calculate_all_metrics(
                symbol=symbol,
                spreads=all_spreads,
                mexc_candles=mexc_candles_sample,
                gateio_candles=gateio_candles_sample,
                analysis_days=int(analysis_days)
            )
            
            # Convert to structured format
            metrics = ArbitrageMetrics(
                pair=metrics_dict['pair'],
                max_spread=round(metrics_dict['max_spread'], 4),
                avg_spread=round(metrics_dict['avg_spread'], 4),
                med_spread=round(metrics_dict['med_spread'], 4),
                spread_gt_0_3_percent=round(metrics_dict['spread_>0.3%'], 2),
                count_gt_0_3_percent=metrics_dict['count_>0.3%'],
                spread_gt_0_5_percent=round(metrics_dict['spread_>0.5%'], 2),
                count_gt_0_5_percent=metrics_dict['count_>0.5%'],
                opportunity_minutes_per_day=round(metrics_dict['opportunity_minutes_per_day'], 1),
                avg_duration_seconds=round(metrics_dict['avg_duration_seconds'], 1),
                liquidity_score=round(metrics_dict['liquidity_score'], 1),
                execution_score=round(metrics_dict['execution_score'], 1),
                risk_score=round(metrics_dict['risk_score'], 1),
                profit_score=round(metrics_dict['profit_score'], 1),
                composite_rank=metrics_dict['composite_rank']
            )
            
            self.logger.info(f"✅ {symbol}: profit_score={metrics.profit_score}, spreads={len(all_spreads)}")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Failed to analyze {symbol}: {e}")
            return None
    
    def analyze_all_symbols(self, max_symbols: Optional[int] = None, 
                           incremental_output: Optional[str] = None) -> List[ArbitrageMetrics]:
        """
        Analyze all available symbols with optional incremental CSV output.
        
        Args:
            max_symbols: Maximum number of symbols to analyze (for testing)
            incremental_output: Path to CSV file for incremental results (write as we go)
            
        Returns:
            List of ArbitrageMetrics for all analyzed symbols
        """
        symbols = self.discover_available_symbols()
        
        if max_symbols and len(symbols) > max_symbols:
            symbols = symbols[:max_symbols]
            self.logger.info(f"Limited analysis to {max_symbols} symbols for testing")
        
        self.logger.info(f"Analyzing {len(symbols)} symbols...")
        
        # Initialize incremental CSV writer if requested
        csv_writer = None
        csv_file = None
        if incremental_output:
            output_path = Path(incremental_output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # CSV headers
            headers = [
                'pair', 'max_spread', 'avg_spread', 'med_spread',
                'spread_>0.3%', 'count_>0.3%', 'spread_>0.5%', 'count_>0.5%',
                'opportunity_minutes_per_day', 'avg_duration_seconds',
                'liquidity_score', 'execution_score', 'risk_score',
                'profit_score', 'composite_rank'
            ]
            
            csv_file = open(output_path, 'w', newline='', encoding='utf-8')
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(headers)
            csv_file.flush()  # Ensure header is written immediately
            
            self.logger.info(f"📝 Writing incremental results to: {incremental_output}")
        
        results = []
        for i, symbol in enumerate(symbols, 1):
            self.logger.info(f"Progress: {i}/{len(symbols)} - {symbol}")
            
            metrics = self.analyze_symbol(symbol)
            if metrics:
                results.append(metrics)
                
                # Write to incremental CSV if enabled
                if csv_writer:
                    row = [
                        metrics.pair,
                        metrics.max_spread,
                        metrics.avg_spread,
                        metrics.med_spread,
                        metrics.spread_gt_0_3_percent,
                        metrics.count_gt_0_3_percent,
                        metrics.spread_gt_0_5_percent,
                        metrics.count_gt_0_5_percent,
                        metrics.opportunity_minutes_per_day,
                        metrics.avg_duration_seconds,
                        metrics.liquidity_score,
                        metrics.execution_score,
                        metrics.risk_score,
                        metrics.profit_score,
                        1  # Temporary rank, will be updated after all analysis
                    ]
                    csv_writer.writerow(row)
                    csv_file.flush()  # Flush immediately to see results
                    self.logger.info(f"💾 Saved to CSV: {metrics.pair} (profit_score={metrics.profit_score:.1f})")
        
        # Close incremental CSV file
        if csv_file:
            csv_file.close()
            self.logger.info(f"✅ Incremental CSV completed: {incremental_output}")
        
        # Rank opportunities by profit score
        if results:
            # Convert to dict format for ranking
            metrics_dicts = [
                {
                    'pair': m.pair,
                    'max_spread': m.max_spread,
                    'avg_spread': m.avg_spread,
                    'med_spread': m.med_spread,
                    'spread_>0.3%': m.spread_gt_0_3_percent,
                    'count_>0.3%': m.count_gt_0_3_percent,
                    'spread_>0.5%': m.spread_gt_0_5_percent,
                    'count_>0.5%': m.count_gt_0_5_percent,
                    'opportunity_minutes_per_day': m.opportunity_minutes_per_day,
                    'avg_duration_seconds': m.avg_duration_seconds,
                    'liquidity_score': m.liquidity_score,
                    'execution_score': m.execution_score,
                    'risk_score': m.risk_score,
                    'profit_score': m.profit_score,
                    'composite_rank': m.composite_rank
                }
                for m in results
            ]
            
            # Rank by profit score
            ranked_metrics = self.metrics_calculator.rank_opportunities(metrics_dicts)
            
            # Convert back to ArbitrageMetrics
            results = [
                ArbitrageMetrics(
                    pair=m['pair'],
                    max_spread=m['max_spread'],
                    avg_spread=m['avg_spread'],
                    med_spread=m['med_spread'],
                    spread_gt_0_3_percent=m['spread_>0.3%'],
                    count_gt_0_3_percent=m['count_>0.3%'],
                    spread_gt_0_5_percent=m['spread_>0.5%'],
                    count_gt_0_5_percent=m['count_>0.5%'],
                    opportunity_minutes_per_day=m['opportunity_minutes_per_day'],
                    avg_duration_seconds=m['avg_duration_seconds'],
                    liquidity_score=m['liquidity_score'],
                    execution_score=m['execution_score'],
                    risk_score=m['risk_score'],
                    profit_score=m['profit_score'],
                    composite_rank=m['composite_rank']
                )
                for m in ranked_metrics
            ]
        
        self.logger.info(f"Successfully analyzed {len(results)} symbols")
        return results
    
    def generate_csv_report(self, 
                          metrics_list: List[ArbitrageMetrics], 
                          output_file: str = "arbitrage_analysis_report.csv") -> str:
        """
        Generate CSV report with exact specified columns.
        
        Args:
            metrics_list: List of arbitrage metrics
            output_file: Output CSV filename
            
        Returns:
            Path to generated CSV file
        """
        output_path = Path(output_file)
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # CSV header as specified in requirements
        headers = [
            'pair',
            'max_spread',
            'avg_spread', 
            'med_spread',
            'spread_>0.3%',
            'count_>0.3%',
            'spread_>0.5%',
            'count_>0.5%',
            'opportunity_minutes_per_day',
            'avg_duration_seconds',
            'liquidity_score',
            'execution_score',
            'risk_score',
            'profit_score',
            'composite_rank'
        ]
        
        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(headers)
                
                # Write data rows
                for metrics in metrics_list:
                    row = [
                        metrics.pair,
                        metrics.max_spread,
                        metrics.avg_spread,
                        metrics.med_spread,
                        metrics.spread_gt_0_3_percent,
                        metrics.count_gt_0_3_percent,
                        metrics.spread_gt_0_5_percent,
                        metrics.count_gt_0_5_percent,
                        metrics.opportunity_minutes_per_day,
                        metrics.avg_duration_seconds,
                        metrics.liquidity_score,
                        metrics.execution_score,
                        metrics.risk_score,
                        metrics.profit_score,
                        metrics.composite_rank
                    ]
                    writer.writerow(row)
            
            self.logger.info(f"CSV report generated: {output_path}")
            self.logger.info(f"Report contains {len(metrics_list)} arbitrage opportunities")
            
            # Display top opportunities
            if metrics_list:
                self.logger.info("\n=== TOP 5 ARBITRAGE OPPORTUNITIES ===")
                for i, metrics in enumerate(metrics_list[:5], 1):
                    self.logger.info(
                        f"{i}. {metrics.pair} - "
                        f"Profit Score: {metrics.profit_score}, "
                        f"Max Spread: {metrics.max_spread}%, "
                        f"Avg Duration: {metrics.avg_duration_seconds}s"
                    )
            
            return str(output_path)
            
        except Exception as e:
            self.logger.error(f"Failed to generate CSV report: {e}")
            raise
    
    def generate_summary_stats(self, metrics_list: List[ArbitrageMetrics]) -> Dict[str, Any]:
        """
        Generate summary statistics for the analysis.
        
        Args:
            metrics_list: List of arbitrage metrics
            
        Returns:
            Summary statistics dictionary
        """
        if not metrics_list:
            return {'total_opportunities': 0}
        
        # Extract key metrics
        profit_scores = [m.profit_score for m in metrics_list]
        max_spreads = [m.max_spread for m in metrics_list]
        avg_spreads = [m.avg_spread for m in metrics_list]
        
        # Count opportunities by quality
        high_profit = len([m for m in metrics_list if m.profit_score >= 70])
        medium_profit = len([m for m in metrics_list if 40 <= m.profit_score < 70])
        low_profit = len([m for m in metrics_list if m.profit_score < 40])
        
        return {
            'total_opportunities': len(metrics_list),
            'high_profit_opportunities': high_profit,
            'medium_profit_opportunities': medium_profit,
            'low_profit_opportunities': low_profit,
            'avg_profit_score': sum(profit_scores) / len(profit_scores),
            'max_profit_score': max(profit_scores),
            'avg_max_spread': sum(max_spreads) / len(max_spreads),
            'highest_max_spread': max(max_spreads),
            'avg_avg_spread': sum(avg_spreads) / len(avg_spreads),
            'opportunities_above_0_3_percent': len([m for m in metrics_list if m.spread_gt_0_3_percent > 0])
        }


# CLI cex for manual execution
async def main():
    """CLI entry point for spread analysis"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analyze arbitrage opportunities from historical data"
    )
    
    parser.add_argument(
        '--data-dir',
        default="./data/arbitrage",
        help='Directory containing historical CSV data'
    )
    
    parser.add_argument(
        '--output',
        default="arbitrage_analysis_report.csv",
        help='Output CSV filename'
    )
    
    parser.add_argument(
        '--max-symbols',
        type=int,
        help='Maximum number of symbols to analyze (for testing)'
    )
    
    parser.add_argument(
        '--symbol',
        help='Analyze single symbol only'
    )
    
    args = parser.parse_args()
    
    # Initialize analyzer
    analyzer = SpreadAnalyzer(data_dir=args.data_dir)
    
    try:
        if args.symbol:
            # Analyze single symbol
            print(f"Analyzing {args.symbol}...")
            metrics = analyzer.analyze_symbol(args.symbol)
            
            if metrics:
                print("✅ Analysis completed")
                print(f"Profit Score: {metrics.profit_score}")
                print(f"Max Spread: {metrics.max_spread}%")
                print(f"Opportunities >0.3%: {metrics.spread_gt_0_3_percent}%")
                
                # Generate single-symbol report
                analyzer.generate_csv_report([metrics], args.output)
            else:
                print("❌ Analysis failed")
        else:
            # Analyze all symbols
            print("Starting comprehensive arbitrage analysis...")
            results = analyzer.analyze_all_symbols(max_symbols=args.max_symbols)
            
            if results:
                # Generate CSV report
                output_path = analyzer.generate_csv_report(results, args.output)
                
                # Display summary
                summary = analyzer.generate_summary_stats(results)
                print("\n=== ANALYSIS SUMMARY ===")
                print(f"Total opportunities: {summary['total_opportunities']}")
                print(f"High profit (≥70): {summary['high_profit_opportunities']}")
                print(f"Medium profit (40-69): {summary['medium_profit_opportunities']}")
                print(f"Low profit (<40): {summary['low_profit_opportunities']}")
                print(f"Average profit score: {summary['avg_profit_score']:.1f}")
                print(f"Average max spread: {summary['avg_max_spread']:.3f}%")
                print(f"\n✅ Report saved to: {output_path}")
            else:
                print("❌ No opportunities found")
                
    except Exception as e:
        print(f"❌ Analysis failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())