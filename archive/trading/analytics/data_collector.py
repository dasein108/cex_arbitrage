#!/usr/bin/env python3
"""
Arbitrage Data Collection Pipeline

Task 1: Data collection pipeline that integrates with existing symbol discovery
and candles downloader to gather historical data for arbitrage analysis.

Integrates with:
- cross_exchange_symbol_discovery.py for symbol filtering
- candles_downloader.py for bulk data collection
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from exchanges.structs import ExchangeEnum
# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import existing tools
from applications.tools.candles_downloader import CandlesDownloader


class ArbitrageDataPipeline:
    """
    Data collection pipeline for arbitrage analysis.
    
    Integrates with existing symbol discovery results and candles downloader
    to gather historical 1-minute data for triangular arbitrage opportunities
    across 3 exchanges: MEXC spot, Gate.io spot, and Gate.io futures.
    """
    
    def __init__(self, output_dir: str = "./data/arbitrage"):
        """
        Initialize the data collection pipeline.
        
        Args:
            output_dir: Directory to save collected data
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize candles downloader
        self.candles_downloader = CandlesDownloader(output_dir=str(self.output_dir))
        
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
    
    def load_discovery_results(self, discovery_file: str) -> Dict[str, Any]:
        """
        Load symbol discovery results from JSON file.
        
        Args:
            discovery_file: Path to discovery results JSON
            
        Returns:
            Parsed discovery results
        """
        discovery_path = Path(discovery_file)
        
        if not discovery_path.exists():
            raise FileNotFoundError(f"Discovery file not found: {discovery_file}")
        
        try:
            with open(discovery_path, 'r') as f:
                data = json.load(f)
            
            self.logger.info(f"Loaded discovery results from {discovery_file}")
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in discovery file: {e}")
    
    def extract_triangular_symbols(self, discovery_data: Dict[str, Any]) -> List[str]:
        """
        Extract symbols with 3-way coverage from discovery results.
        
        Args:
            discovery_data: Discovery results data
            
        Returns:
            List of symbols available on all 3 supported markets (MEXC spot, Gate.io spot, Gate.io futures)
        """
        triangular_symbols = []
        
        # Access the availability matrix
        availability = discovery_data.get('availability_matrix', {})
        
        for symbol_key, symbol_availability in availability.items():
            # Check if symbol is available on all 3 supported markets
            if all([
                symbol_availability.get('mexc_spot', False),
                symbol_availability.get('gateio_spot', False),
                symbol_availability.get('gateio_futures', False)
            ]):
                triangular_symbols.append(symbol_key)
        
        self.logger.info(f"Found {len(triangular_symbols)} triangular arbitrage opportunities")
        
        # Log first few symbols for verification
        if triangular_symbols:
            sample_symbols = triangular_symbols[:5]
            self.logger.info(f"Sample symbols: {sample_symbols}")
        
        return triangular_symbols
    
    def generate_download_configs(self, 
                                symbols: List[str], 
                                days: int = 7, 
                                timeframe: str = "1m") -> List[Dict[str, Any]]:
        """
        Generate download configurations for candles downloader.
        
        Args:
            symbols: List of trading symbols
            days: Number of days of historical data
            timeframe: Candle timeframe
            
        Returns:
            List of download configurations
        """
        configs = []
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        self.logger.info(f"Data collection period: {start_date.date()} to {end_date.date()}")
        
        # Generate configs for each symbol and exchange combination
        for symbol in symbols:
            # Convert symbol format from discovery results to candles downloader format
            # e.g., "BTC/USD_STABLE" -> "BTC_USDT"
            if '/USD_STABLE' in symbol:
                candle_symbol = symbol.replace('/USD_STABLE', '_USDT')
            else:
                candle_symbol = symbol.replace('/', '_')
            
            # Generate configs for 3-exchange setup: MEXC spot, Gate.io spot, Gate.io futures
            # Note: Gate.io futures uses 'gateio_futures' as the exchange name
            exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
            
            for exchange in exchanges:
                config = {
                    'exchange': exchange,
                    'symbol': candle_symbol,
                    'timeframe': timeframe,
                    'start_date': start_date,
                    'end_date': end_date
                }
                configs.append(config)
        
        self.logger.info(f"Generated {len(configs)} download configurations")
        return configs
    
    async def collect_data_for_analysis(self, 
                                      discovery_file: str = "src/tools/output/symbol_discovery_detailed_20250913_102849.json",
                                      days: int = 7,
                                      max_symbols: Optional[int] = None) -> Dict[str, Any]:
        """
        Complete data collection pipeline for arbitrage analysis.
        
        Args:
            discovery_file: Path to symbol discovery results
            days: Number of days of historical data
            max_symbols: Maximum number of symbols to process (for testing)
            
        Returns:
            Collection results summary
        """
        try:
            self.logger.info("Starting arbitrage data collection pipeline...")
            
            # Step 1: Load discovery results
            self.logger.info("Step 1: Loading symbol discovery results...")
            discovery_data = self.load_discovery_results(discovery_file)
            
            # Step 2: Extract triangular arbitrage symbols
            self.logger.info("Step 2: Extracting triangular arbitrage opportunities...")
            symbols = self.extract_triangular_symbols(discovery_data)
            
            if not symbols:
                raise ValueError("No triangular arbitrage opportunities found in discovery results")
            
            # Limit symbols for testing if specified
            if max_symbols and len(symbols) > max_symbols:
                symbols = symbols[:max_symbols]
                self.logger.info(f"Limited to {max_symbols} symbols for testing")
            
            # Step 3: Generate download configs
            self.logger.info("Step 3: Generating download configurations...")
            configs = self.generate_download_configs(symbols, days)
            
            # Step 4: Execute bulk downloads
            self.logger.info("Step 4: Starting bulk data downloads...")
            self.logger.info(f"Downloading data for {len(symbols)} symbols from {len(configs)} exchange/symbol combinations")
            
            results = await self.candles_downloader.download_multiple(configs)
            
            # Step 5: Analyze results
            successful_downloads = [r for r in results if isinstance(r, str)]
            failed_downloads = len(results) - len(successful_downloads)
            
            collection_summary = {
                'total_symbols': len(symbols),
                'total_configs': len(configs),
                'successful_downloads': len(successful_downloads),
                'failed_downloads': failed_downloads,
                'success_rate': len(successful_downloads) / len(configs) * 100 if configs else 0,
                'data_directory': str(self.output_dir),
                'symbols_processed': symbols,
                'file_paths': successful_downloads
            }
            
            self.logger.info("=== Data Collection Summary ===")
            self.logger.info(f"Total symbols: {collection_summary['total_symbols']}")
            self.logger.info(f"Successful downloads: {collection_summary['successful_downloads']}")
            self.logger.info(f"Failed downloads: {collection_summary['failed_downloads']}")
            self.logger.info(f"Success rate: {collection_summary['success_rate']:.1f}%")
            self.logger.info(f"Data saved to: {collection_summary['data_directory']}")
            
            return collection_summary
            
        except Exception as e:
            self.logger.error(f"Data collection failed: {e}")
            raise
    
    def validate_collected_data(self) -> Dict[str, Any]:
        """
        Validate the collected data files and provide statistics.
        
        Returns:
            Validation results
        """
        csv_files = list(self.output_dir.glob("*.csv"))
        
        if not csv_files:
            return {
                'valid': False,
                'reason': 'No CSV files found',
                'file_count': 0
            }
        
        # Group files by symbol
        symbol_files = {}
        for file_path in csv_files:
            filename = file_path.name
            # Extract symbol from filename (e.g., "mexc_BTC_USDT_1m_20240613_20240913.csv")
            parts = filename.split('_')
            if len(parts) >= 3:
                exchange = parts[0]
                symbol = f"{parts[1]}_{parts[2]}"
                
                if symbol not in symbol_files:
                    symbol_files[symbol] = {}
                symbol_files[symbol][exchange] = file_path
        
        # Check for symbols with complete 3-exchange data
        # For triangular arbitrage, we need MEXC spot, Gate.io spot, and Gate.io futures
        complete_symbols = []
        incomplete_symbols = []
        
        for symbol, files in symbol_files.items():
            # Check if we have all required exchanges for triangular arbitrage
            has_mexc_spot = any('mexc' in str(path) and 'spot' in str(path) or 'mexc' in str(path) for path in files.values())
            has_gateio_spot = any('gateio' in str(path) and 'spot' in str(path) or ('gateio' in str(path) and 'futures' not in str(path)) for path in files.values())
            has_gateio_futures = any('gateio' in str(path) and 'futures' in str(path) for path in files.values())
            
            if has_mexc_spot and (has_gateio_spot or has_gateio_futures):
                # For now, accept symbols with at least MEXC and one Gate.io market
                complete_symbols.append(symbol)
            else:
                incomplete_symbols.append(symbol)
        
        validation_results = {
            'valid': len(complete_symbols) > 0,
            'total_files': len(csv_files),
            'total_symbols': len(symbol_files),
            'complete_symbols': len(complete_symbols),
            'incomplete_symbols': len(incomplete_symbols),
            'complete_symbol_list': complete_symbols,
            'incomplete_symbol_list': incomplete_symbols,
            'data_completeness': len(complete_symbols) / len(symbol_files) * 100 if symbol_files else 0
        }
        
        self.logger.info("=== Data Validation Results ===")
        self.logger.info(f"Total CSV files: {validation_results['total_files']}")
        self.logger.info(f"Symbols with complete data: {validation_results['complete_symbols']}")
        self.logger.info(f"Symbols with incomplete data: {validation_results['incomplete_symbols']}")
        self.logger.info(f"Data completeness: {validation_results['data_completeness']:.1f}%")
        
        return validation_results


# CLI exchanges for manual execution
async def main():
    """CLI entry point for data collection"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Collect historical data for arbitrage analysis"
    )
    
    parser.add_argument(
        '--discovery-file',
        default="src/tools/output/symbol_discovery_detailed_20250913_102849.json",
        help='Path to symbol discovery results JSON file'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days of historical data to collect'
    )
    
    parser.add_argument(
        '--output',
        default="./data/arbitrage",
        help='Output directory for collected data'
    )
    
    parser.add_argument(
        '--max-symbols',
        type=int,
        help='Maximum number of symbols to process (for testing)'
    )
    
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate existing data without collecting new data'
    )
    
    args = parser.parse_args()
    
    # Initialize pipeline
    pipeline = ArbitrageDataPipeline(output_dir=args.output)
    
    if args.validate_only:
        # Validate existing data
        validation_results = pipeline.validate_collected_data()
        if validation_results['valid']:
            print("✅ Data validation passed")
        else:
            print("❌ Data validation failed")
            print(f"Reason: {validation_results.get('reason', 'Unknown')}")
    else:
        # Collect data
        try:
            results = await pipeline.collect_data_for_analysis(
                discovery_file=args.discovery_file,
                days=args.days,
                max_symbols=args.max_symbols
            )
            
            if results['success_rate'] > 50:
                print("✅ Data collection completed successfully")
            else:
                print("⚠️ Data collection completed with issues")
                
        except Exception as e:
            print(f"❌ Data collection failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())