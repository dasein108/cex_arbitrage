#!/usr/bin/env python3
"""
Arbitrage Data Fetcher

Standalone script for fetching historical candles data for arbitrage analysis.
Uses symbol discovery results to download candles from multiple exchanges.

Key Features:
- Integrates with cross_exchange_symbol_discovery.py output
- Downloads 1-minute candles for specified time period
- Rate-limited batch processing to prevent API throttling
- Saves data in unified CSV format for analysis

Usage:
    python arbitrage_data_fetcher.py --help
    python arbitrage_data_fetcher.py --days 3                    # Default 3 days
    python arbitrage_data_fetcher.py --days 7 --max-symbols 10   # Custom parameters
    python arbitrage_data_fetcher.py --discovery-file custom.json
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

# Import ArbitrageDataPipeline from local implementation
from arbitrage_data_pipeline import ArbitrageDataPipeline


async def fetch_arbitrage_data(
    discovery_file: str = "output/symbol_discovery_detailed_20250913_102849.json",
    data_dir: str = "data/arbitrage",
    days: int = 3,
    max_symbols: int = None,
    validate_only: bool = False
) -> bool:
    """
    Fetch historical candles data for arbitrage analysis.
    
    Args:
        discovery_file: Path to symbol discovery results JSON
        data_dir: Directory to save collected data
        days: Number of days of historical data to collect
        max_symbols: Maximum symbols to process (for testing)
        validate_only: Only validate existing data without collecting new data
        
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
    
    # Initialize data pipeline
    pipeline = ArbitrageDataPipeline(output_dir=data_dir)
    
    if validate_only:
        logger.info("=" * 60)
        logger.info("VALIDATING EXISTING DATA")
        logger.info("=" * 60)
        
        validation_results = pipeline.validate_collected_data()
        
        if validation_results['valid']:
            logger.info("✅ Data validation passed")
            logger.info(f"📊 Complete symbols: {validation_results['complete_symbols']}")
            logger.info(f"📈 Data completeness: {validation_results['data_completeness']:.1f}%")
            
            if validation_results['complete_symbol_list']:
                logger.info("🎯 Available symbols for analysis:")
                for symbol in validation_results['complete_symbol_list'][:10]:  # Show first 10
                    logger.info(f"   - {symbol}")
                if len(validation_results['complete_symbol_list']) > 10:
                    logger.info(f"   ... and {len(validation_results['complete_symbol_list']) - 10} more")
        else:
            logger.error("❌ Data validation failed")
            logger.error(f"Reason: {validation_results.get('reason', 'Unknown')}")
            return False
        
        return True
    
    try:
        logger.info("=" * 60)
        logger.info("ARBITRAGE DATA COLLECTION")
        logger.info("=" * 60)
        logger.info(f"📂 Discovery file: {discovery_file}")
        logger.info(f"💾 Data directory: {data_dir}")
        logger.info(f"📅 Collection period: {days} days")
        if max_symbols:
            logger.info(f"🔢 Max symbols: {max_symbols} (testing mode)")
        
        # Execute data collection
        collection_results = await pipeline.collect_data_for_analysis(
            discovery_file=discovery_file,
            days=days,
            max_symbols=max_symbols
        )
        
        # Evaluate results
        success_rate = collection_results['success_rate']
        
        logger.info("=" * 60)
        logger.info("DATA COLLECTION COMPLETED")
        logger.info("=" * 60)
        logger.info(f"📊 Total symbols processed: {collection_results['total_symbols']}")
        logger.info(f"✅ Successful downloads: {collection_results['successful_downloads']}")
        logger.info(f"❌ Failed downloads: {collection_results['failed_downloads']}")
        logger.info(f"📈 Success rate: {success_rate:.1f}%")
        logger.info(f"💾 Data saved to: {collection_results['data_directory']}")
        
        if success_rate >= 80:
            logger.info("🎉 Excellent success rate! Data ready for analysis.")
        elif success_rate >= 50:
            logger.info("⚠️ Moderate success rate. Some symbols may be missing.")
        else:
            logger.warning("🔥 Low success rate. Check network connectivity and API limits.")
        
        # Show sample collected symbols
        if collection_results['symbols_processed']:
            logger.info("🎯 Sample collected symbols:")
            sample_size = min(5, len(collection_results['symbols_processed']))
            for symbol in collection_results['symbols_processed'][:sample_size]:
                logger.info(f"   - {symbol}")
        
        logger.info(f"\n📄 Ready for analysis! Run: python arbitrage_analyzer.py --data-dir {data_dir}")
        
        return True
        
    except Exception as e:
        logger.error(f"💥 Data collection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """CLI entry point for arbitrage data fetcher."""
    parser = argparse.ArgumentParser(
        description="Fetch historical candles data for arbitrage analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch 3 days of data (default)
  python arbitrage_data_fetcher.py
  
  # Fetch 7 days with custom symbol limit
  python arbitrage_data_fetcher.py --days 7 --max-symbols 10
  
  # Use custom discovery file
  python arbitrage_data_fetcher.py --discovery-file my_symbols.json
  
  # Validate existing data without downloading
  python arbitrage_data_fetcher.py --validate-only
  
  # Custom data directory
  python arbitrage_data_fetcher.py --data-dir ./my_data --days 5

Workflow:
  1. Run: python cross_exchange_symbol_discovery.py  (generates symbol list)
  2. Run: python arbitrage_data_fetcher.py           (downloads candles data) 
  3. Run: python arbitrage_analyzer.py               (performs spread analysis)
        """
    )
    
    parser.add_argument(
        '--discovery-file',
        default="output/symbol_discovery_detailed_20250913_102849.json",
        help='Path to symbol discovery results JSON file'
    )
    
    parser.add_argument(
        '--data-dir',
        default="data/arbitrage",
        help='Output directory for collected data (default: data/arbitrage)'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=3,
        help='Number of days of historical data to collect (default: 3)'
    )
    
    parser.add_argument(
        '--max-symbols',
        type=int,
        help='Maximum number of symbols to process (useful for testing)'
    )
    
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate existing data without collecting new data'
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
    
    print("🚀 Arbitrage Data Fetcher")
    print("=" * 40)
    
    if not args.validate_only:
        print(f"📅 Collecting {args.days} days of historical data...")
        if args.max_symbols:
            print(f"🔢 Limited to {args.max_symbols} symbols (testing mode)")
    else:
        print("🔍 Validating existing data...")
    
    # Run data collection
    success = asyncio.run(fetch_arbitrage_data(
        discovery_file=args.discovery_file,
        data_dir=args.data_dir,
        days=args.days,
        max_symbols=args.max_symbols,
        validate_only=args.validate_only
    ))
    
    if success:
        if not args.validate_only:
            print("\n🎉 Data collection completed successfully!")
            print("📊 Data ready for arbitrage analysis.")
            print("➡️  Next step: python arbitrage_analyzer.py")
        else:
            print("\n✅ Data validation completed successfully!")
    else:
        print("\n💥 Data collection failed!")
        print("🔍 Check logs above for error details.")
        sys.exit(1)


if __name__ == "__main__":
    main()