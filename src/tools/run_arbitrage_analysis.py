#!/usr/bin/env python3
"""
Complete Arbitrage Analysis Pipeline (LEGACY)

⚠️  DEPRECATED: This script combines multiple steps into one.
    For better workflow control, use the individual scripts:

    1. python cross_exchange_symbol_discovery.py  # Find symbols
    2. python arbitrage_data_fetcher.py           # Download data  
    3. python arbitrage_analyzer.py               # Analyze spreads

This legacy script is maintained for backward compatibility but may be
removed in future versions. Use the individual scripts for new workflows.

Usage:
    python run_arbitrage_analysis.py --help
    python run_arbitrage_analysis.py --test  # Quick test with limited data
    python run_arbitrage_analysis.py         # Full analysis
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add src to path (now we're in src/tools, so go up one level)
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from analysis.collect_arbitrage_data import ArbitrageDataPipeline
from analysis.spread_analyzer import SpreadAnalyzer


async def run_complete_pipeline(
    discovery_file: str = "output/symbol_discovery_detailed_20250913_102849.json",
    data_dir: str = "data/arbitrage",
    output_file: str = "output/arbitrage_analysis_report.csv",
    days: int = 7,
    max_symbols: int = None,
    skip_collection: bool = False
) -> bool:
    """
    Run the complete arbitrage analysis pipeline.
    
    Args:
        discovery_file: Path to symbol discovery results
        data_dir: Directory for collected data
        output_file: Output CSV report filename
        days: Number of days of historical data
        max_symbols: Maximum symbols to process (for testing)
        skip_collection: Skip data collection if data already exists
        
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
    if not Path(discovery_file).is_absolute():
        discovery_file = str(Path.cwd() / discovery_file)
    if not Path(data_dir).is_absolute():
        data_dir = str(Path.cwd() / data_dir)
    if not Path(output_file).is_absolute():
        output_file = str(Path.cwd() / output_file)
    
    try:
        # Phase 1: Data Collection (Task 1)
        if not skip_collection:
            logger.info("=" * 60)
            logger.info("PHASE 1: DATA COLLECTION")
            logger.info("=" * 60)
            
            pipeline = ArbitrageDataPipeline(output_dir=data_dir)
            
            collection_results = await pipeline.collect_data_for_analysis(
                discovery_file=discovery_file,
                days=days,
                max_symbols=max_symbols
            )
            
            if collection_results['success_rate'] < 50:
                logger.warning(f"Low success rate: {collection_results['success_rate']:.1f}%")
                logger.warning("Proceeding with available data...")
        else:
            logger.info("Skipping data collection (using existing data)")
        
        # Phase 2: Analysis & Reporting (Task 2)
        logger.info("=" * 60)
        logger.info("PHASE 2: ARBITRAGE ANALYSIS")
        logger.info("=" * 60)
        
        analyzer = SpreadAnalyzer(data_dir=data_dir)
        
        # Analyze all available symbols
        results = analyzer.analyze_all_symbols(max_symbols=max_symbols)
        
        if not results:
            logger.error("No arbitrage opportunities found")
            return False
        
        # Generate CSV report
        output_path = analyzer.generate_csv_report(results, output_file)
        
        # Generate summary statistics
        summary = analyzer.generate_summary_stats(results)
        
        # Display final results
        logger.info("=" * 60)
        logger.info("ARBITRAGE ANALYSIS COMPLETED")
        logger.info("=" * 60)
        logger.info(f"📊 Total opportunities analyzed: {summary['total_opportunities']}")
        logger.info(f"🚀 High profit opportunities (≥70): {summary['high_profit_opportunities']}")
        logger.info(f"⚡ Medium profit opportunities (40-69): {summary['medium_profit_opportunities']}")
        logger.info(f"📈 Average profit score: {summary['avg_profit_score']:.1f}")
        logger.info(f"💰 Average max spread: {summary['avg_max_spread']:.3f}%")
        logger.info(f"📄 Report saved to: {output_path}")
        
        # Display top 3 opportunities
        if len(results) >= 3:
            logger.info("\n🎯 TOP 3 OPPORTUNITIES:")
            for i, metrics in enumerate(results[:3], 1):
                logger.info(
                    f"  {i}. {metrics.pair} - "
                    f"Profit: {metrics.profit_score:.1f}, "
                    f"Max Spread: {metrics.max_spread:.3f}%, "
                    f"Freq >0.3%: {metrics.spread_gt_0_3_percent:.1f}%"
                )
        
        logger.info(f"\n✅ Pipeline completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return False


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Complete Arbitrage Analysis Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full analysis (7 days of data)
  python run_arbitrage_analysis.py
  
  # Quick test with limited symbols (3 days)
  python run_arbitrage_analysis.py --test
  
  # Use existing data, skip collection
  python run_arbitrage_analysis.py --skip-collection
  
  # Custom parameters
  python run_arbitrage_analysis.py --days 14 --max-symbols 10 --output test_report.csv
        """
    )
    
    parser.add_argument(
        '--discovery-file',
        default="output/symbol_discovery_detailed_20250913_102849.json",
        help='Path to symbol discovery results JSON'
    )
    
    parser.add_argument(
        '--data-dir',
        default="data/arbitrage",
        help='Directory for collected historical data'
    )
    
    parser.add_argument(
        '--output',
        default="output/arbitrage_analysis_report.csv",
        help='Output CSV report filename'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days of historical data (default: 7)'
    )
    
    parser.add_argument(
        '--max-symbols',
        type=int,
        help='Maximum symbols to process (useful for testing)'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Quick test mode (3 days data, max 5 symbols)'
    )
    
    parser.add_argument(
        '--skip-collection',
        action='store_true',
        help='Skip data collection, use existing data'
    )
    
    args = parser.parse_args()
    
    # Resolve paths based on current working directory
    
    # If paths don't start with /, they are relative - make them relative to CWD
    if not args.discovery_file.startswith('/'):
        args.discovery_file = str(Path.cwd() / args.discovery_file)
    if not args.data_dir.startswith('/'):
        args.data_dir = str(Path.cwd() / args.data_dir)
    if not args.output.startswith('/'):
        args.output = str(Path.cwd() / args.output)
    
    # Test mode settings
    if args.test:
        args.days = 3
        args.max_symbols = 5
        args.output = str(Path.cwd() / "output/test_arbitrage_report.csv")
        print("🧪 Running in test mode (3 days, 5 symbols max)")
    
    # Run the pipeline
    success = asyncio.run(run_complete_pipeline(
        discovery_file=args.discovery_file,
        data_dir=args.data_dir,
        output_file=args.output,
        days=args.days,
        max_symbols=args.max_symbols,
        skip_collection=args.skip_collection
    ))
    
    if success:
        print("\n🎉 Arbitrage analysis pipeline completed successfully!")
        print(f"📄 Check your report: {args.output}")
    else:
        print("\n💥 Pipeline failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()