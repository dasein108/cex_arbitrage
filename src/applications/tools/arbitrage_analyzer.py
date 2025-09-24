#!/usr/bin/env python3
"""
Arbitrage Spread Analyzer

Standalone script for analyzing collected arbitrage data and generating reports.
Analyzes spread patterns between exchanges to identify profitable opportunities.

Key Features:
- Analyzes collected candles data from arbitrage_data_fetcher.py
- Calculates comprehensive arbitrage metrics and scoring
- Generates CSV reports with rankings and statistics
- Provides detailed opportunity analysis and insights

Usage:
    python arbitrage_analyzer.py --help
    python arbitrage_analyzer.py                           # Default analysis
    python arbitrage_analyzer.py --max-symbols 10          # Limit analysis scope
    python arbitrage_analyzer.py --output custom_report.csv
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from trading.analytics.spread_analyzer import SpreadAnalyzer


def analyze_arbitrage_opportunities(
    data_dir: str = "data/arbitrage",
    output_file: str = "output/arbitrage_analysis_report.csv",
    max_symbols: int = None,
    min_profit_score: float = 0.0,
    show_details: bool = False,
    incremental: bool = False
) -> bool:
    """
    Analyze arbitrage opportunities from collected data.
    
    Args:
        data_dir: Directory containing collected candles data
        output_file: Output CSV report filename
        max_symbols: Maximum symbols to analyze (for testing)
        min_profit_score: Minimum profit score threshold for reporting
        show_details: Show detailed analysis for each symbol
        incremental: Write results incrementally to CSV for immediate observation
        
    Returns:
        True if successful, False otherwise
    """
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Resolve paths relative to current working directory
    if not Path(data_dir).is_absolute():
        data_dir = str(Path.cwd() / data_dir)
    if not Path(output_file).is_absolute():
        output_file = str(Path.cwd() / output_file)
    
    try:
        logger.info("=" * 60)
        logger.info("ARBITRAGE SPREAD ANALYSIS")
        logger.info("=" * 60)
        logger.info(f"📂 Data directory: {data_dir}")
        logger.info(f"📄 Output report: {output_file}")
        if max_symbols:
            logger.info(f"🔢 Max symbols: {max_symbols} (testing mode)")
        if min_profit_score > 0:
            logger.info(f"📊 Min profit score: {min_profit_score}")
        
        # Initialize analyzer
        analyzer = SpreadAnalyzer(data_dir=data_dir)
        
        # Check data availability
        available_symbols = analyzer.discover_available_symbols()
        if not available_symbols:
            logger.error("❌ No data found for analysis")
            logger.error(f"Check that data exists in: {data_dir}")
            logger.error("Run: python arbitrage_data_fetcher.py first")
            return False
        
        logger.info(f"📊 Found data for {len(available_symbols)} symbols")
        
        # Prepare incremental output path if requested
        incremental_output = None
        if incremental:
            # Use a temporary incremental file
            incremental_output = output_file.replace('.csv', '_incremental.csv')
            logger.info(f"📝 Incremental mode enabled: {incremental_output}")
        
        # Analyze all available symbols
        logger.info("🔍 Starting spread analysis...")
        results = analyzer.analyze_all_symbols(
            max_symbols=max_symbols, 
            incremental_output=incremental_output
        )
        
        if not results:
            logger.error("❌ No arbitrage opportunities found")
            logger.error("This could mean:")
            logger.error("  - Insufficient data for analysis")
            logger.error("  - No profitable spreads detected")
            logger.error("  - Data quality issues")
            return False
        
        # Filter results by minimum profit score if specified
        if min_profit_score > 0:
            filtered_results = [r for r in results if r.profit_score >= min_profit_score]
            logger.info(f"🎯 Filtered to {len(filtered_results)} opportunities with profit score ≥ {min_profit_score}")
            results = filtered_results
        
        if not results:
            logger.warning(f"⚠️ No opportunities meet minimum profit score of {min_profit_score}")
            return False
        
        # Generate CSV report
        logger.info("📄 Generating CSV report...")
        output_path = analyzer.generate_csv_report(results, output_file)
        
        # Generate summary statistics
        summary = analyzer.generate_summary_stats(results)
        
        # Display analysis results
        logger.info("=" * 60)
        logger.info("ARBITRAGE ANALYSIS COMPLETED")
        logger.info("=" * 60)
        logger.info(f"📊 Total opportunities analyzed: {summary['total_opportunities']}")
        logger.info(f"🚀 High profit opportunities (≥70): {summary['high_profit_opportunities']}")
        logger.info(f"⚡ Medium profit opportunities (40-69): {summary['medium_profit_opportunities']}")
        logger.info(f"📈 Low profit opportunities (1-39): {summary['low_profit_opportunities']}")
        logger.info(f"💰 Average profit score: {summary['avg_profit_score']:.1f}")
        logger.info(f"📏 Average max spread: {summary['avg_max_spread']:.3f}%")
        logger.info(f"📄 Report saved to: {output_path}")
        
        # Note about incremental output
        if incremental:
            logger.info(f"📝 Incremental results were saved to: {incremental_output}")
            logger.info("   ℹ️  The incremental file shows results as they were computed")
            logger.info("   ℹ️  The final report has proper ranking and sorting")
        
        # Display top opportunities
        top_count = min(10, len(results))
        if top_count > 0:
            logger.info(f"\n🎯 TOP {top_count} ARBITRAGE OPPORTUNITIES:")
            for i, metrics in enumerate(results[:top_count], 1):
                logger.info(
                    f"  {i:2d}. {metrics.pair:15s} - "
                    f"Profit: {metrics.profit_score:5.1f}, "
                    f"Max Spread: {metrics.max_spread:6.3f}%, "
                    f"Freq >0.3%: {metrics.spread_gt_0_3_percent:5.1f}%"
                )
        
        # Show detailed analysis if requested
        if show_details and len(results) <= 5:
            logger.info(f"\n📋 DETAILED ANALYSIS:")
            for metrics in results:
                logger.info(f"\n  Symbol: {metrics.pair}")
                logger.info(f"    Max Spread: {metrics.max_spread:.3f}%")
                logger.info(f"    Avg Spread: {metrics.avg_spread:.3f}%")
                logger.info(f"    Median Spread: {metrics.med_spread:.3f}%")
                logger.info(f"    Opportunities >0.3%: {metrics.spread_gt_0_3_percent:.1f}% ({metrics.count_gt_0_3_percent} times)")
                logger.info(f"    Opportunities >0.5%: {metrics.spread_gt_0_5_percent:.1f}% ({metrics.count_gt_0_5_percent} times)")
                logger.info(f"    Opportunity minutes/day: {metrics.opportunity_minutes_per_day:.1f}")
                logger.info(f"    Avg duration: {metrics.avg_duration_seconds:.0f}s")
                logger.info(f"    Liquidity score: {metrics.liquidity_score:.1f}")
                logger.info(f"    Execution score: {metrics.execution_score:.1f}")
                logger.info(f"    Risk score: {metrics.risk_score:.1f}")
                logger.info(f"    Final profit score: {metrics.profit_score:.1f}")
        
        # Provide actionable insights
        logger.info(f"\n💡 INSIGHTS:")
        if summary['high_profit_opportunities'] > 0:
            logger.info(f"   🎯 {summary['high_profit_opportunities']} high-value opportunities detected!")
            logger.info(f"   💰 Focus on symbols with profit score ≥70 for best returns")
        
        if summary['avg_max_spread'] > 0.5:
            logger.info(f"   📈 Strong spread patterns detected (avg {summary['avg_max_spread']:.3f}%)")
        elif summary['avg_max_spread'] > 0.3:
            logger.info(f"   📊 Moderate spread opportunities available")
        else:
            logger.info(f"   📉 Limited spread opportunities in current data")
        
        top_symbol = results[0] if results else None
        if top_symbol and top_symbol.opportunity_minutes_per_day > 60:
            logger.info(f"   ⏰ Best symbol ({top_symbol.pair}) has {top_symbol.opportunity_minutes_per_day:.0f} min/day of opportunities")
        
        logger.info(f"\n✅ Analysis completed successfully!")
        logger.info(f"📊 Open report: {output_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"💥 Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """CLI entry point for arbitrage analyzer."""
    parser = argparse.ArgumentParser(
        description="Analyze arbitrage opportunities from collected data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze all available data
  python arbitrage_analyzer.py
  
  # Limit analysis to top symbols
  python arbitrage_analyzer.py --max-symbols 20
  
  # Filter by minimum profit score
  python arbitrage_analyzer.py --min-profit-score 30
  
  # Custom output file
  python arbitrage_analyzer.py --output my_analysis.csv
  
  # Show detailed analysis (for small datasets)
  python arbitrage_analyzer.py --max-symbols 5 --details
  
  # Full analysis with custom data directory
  python arbitrage_analyzer.py --data-dir ./my_data --output ./reports/analysis.csv

Workflow:
  1. Run: python cross_exchange_symbol_discovery.py  (generates symbol list)
  2. Run: python arbitrage_data_fetcher.py           (downloads candles data) 
  3. Run: python arbitrage_analyzer.py               (performs spread analysis)

Report Columns:
  - pair: Trading pair symbol
  - max_spread: Maximum spread percentage observed
  - avg_spread: Average spread percentage
  - spread_>0.3%: Percentage of time spread exceeded 0.3%
  - opportunity_minutes_per_day: Minutes per day with profitable spreads
  - profit_score: Composite profitability ranking (0-100)
        """
    )
    
    parser.add_argument(
        '--data-dir',
        default="data/arbitrage",
        help='Directory containing collected candles data (default: data/arbitrage)'
    )
    
    parser.add_argument(
        '--output',
        default="output/arbitrage_analysis_report.csv",
        help='Output CSV report filename (default: output/arbitrage_analysis_report.csv)'
    )
    
    parser.add_argument(
        '--max-symbols',
        type=int,
        help='Maximum number of symbols to analyze (useful for testing)'
    )
    
    parser.add_argument(
        '--min-profit-score',
        type=float,
        default=0.0,
        help='Minimum profit score threshold for reporting (default: 0.0)'
    )
    
    parser.add_argument(
        '--details',
        action='store_true',
        help='Show detailed analysis for each symbol (recommended for ≤5 symbols)'
    )
    
    parser.add_argument(
        '--incremental',
        action='store_true',
        help='Write results incrementally to CSV for immediate observation'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("📊 Arbitrage Spread Analyzer")
    print("=" * 40)
    
    if args.max_symbols:
        print(f"🔢 Analyzing up to {args.max_symbols} symbols...")
    else:
        print("🔍 Analyzing all available symbols...")
    
    if args.min_profit_score > 0:
        print(f"📊 Filtering by minimum profit score: {args.min_profit_score}")
    
    # Run analysis
    success = analyze_arbitrage_opportunities(
        data_dir=args.data_dir,
        output_file=args.output,
        max_symbols=args.max_symbols,
        min_profit_score=args.min_profit_score,
        show_details=args.details,
        incremental=args.incremental
    )
    
    if success:
        print("\n🎉 Arbitrage analysis completed successfully!")
        print(f"📄 Report saved to: {args.output}")
        print("💡 Review the CSV report for detailed arbitrage opportunities.")
    else:
        print("\n💥 Analysis failed!")
        print("🔍 Check logs above for error details.")
        print("💡 Ensure data was collected first: python arbitrage_data_fetcher.py")
        sys.exit(1)


if __name__ == "__main__":
    main()