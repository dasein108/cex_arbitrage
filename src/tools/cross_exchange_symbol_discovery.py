#!/usr/bin/env python3
"""
Cross-Exchange Symbol Discovery Tool

High-performance symbol discovery and arbitrage opportunity analysis across
MEXC Spot, Gate.io Spot, and Gate.io Futures markets.

Architecture:
- Event-driven async processing for parallel exchange queries
- Zero-copy JSON processing with msgspec
- HFT-compliant (no real-time data caching)
- SOLID principles with clear separation of concerns

Performance Target: <30 seconds for complete analysis
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import IntEnum
import msgspec
from msgspec import Struct

# Add parent directory to path for imports (we're now in src/tools)
import sys
import os
project_root = Path(__file__).parent.parent  # Now points to src/
sys.path.insert(0, str(project_root))

# Direct imports from src directory
from exchanges.interface.structs import Symbol, SymbolInfo, AssetName, ExchangeName
from exchanges.mexc.rest.mexc_public import MexcPublicExchange
from exchanges.gateio.rest.gateio_public import GateioPublicExchange  
from exchanges.gateio.rest.gateio_futures_public import GateioPublicFuturesExchange
from common.exceptions import ExchangeAPIError


class MarketType(IntEnum):
    """Market type enumeration for performance"""
    SPOT = 1
    FUTURES = 2


class ExchangeMarket(Struct, frozen=True):
    """Immutable exchange-market pair"""
    exchange: str
    market: MarketType
    
    def __str__(self) -> str:
        market_str = "spot" if self.market == MarketType.SPOT else "futures"
        return f"{self.exchange}_{market_str}"


class SymbolAvailability(Struct):
    """Symbol availability across exchanges"""
    symbol: Symbol
    mexc_spot: bool = False
    gateio_spot: bool = False
    gateio_futures: bool = False
    
    @property
    def exchange_count(self) -> int:
        """Number of exchanges where symbol is available"""
        return sum([self.mexc_spot, self.gateio_spot, self.gateio_futures])
    
    @property
    def is_arbitrage_candidate(self) -> bool:
        """Check if symbol is available on multiple exchanges"""
        return self.exchange_count >= 2


class SymbolMetadata(Struct):
    """Detailed symbol metadata for analysis"""
    symbol: Symbol
    exchanges: Dict[str, Dict[str, Any]]  # exchange_market -> info dict
    min_quote_amount: float  # Minimum across all exchanges
    max_precision: int  # Maximum precision requirement
    fee_range: Tuple[float, float]  # Min and max fees


class DiscoveryResult(Struct):
    """Complete discovery result structure"""
    timestamp: str
    total_symbols: int
    arbitrage_candidates: int
    availability_matrix: Dict[str, Dict[str, bool]]
    metadata: Dict[str, Dict[str, Any]]
    statistics: Dict[str, Any]
    execution_time: float


class OutputFormat(IntEnum):
    """Output format options"""
    SUMMARY = 1
    DETAILED = 2
    FILTERED = 3
    MATRIX = 4


class SymbolDiscoveryEngine:
    """
    High-performance symbol discovery engine.
    
    Responsibilities:
    - Parallel fetching of exchange information
    - Symbol matching and normalization
    - Arbitrage opportunity identification
    - Performance monitoring and optimization
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize discovery engine with optional logger"""
        self.logger = logger or logging.getLogger(__name__)
        self.exchanges: Dict[str, Any] = {}
    
    def _create_exchange_client(self, exchange_market: ExchangeMarket):
        """Factory method to create exchange clients"""
        if exchange_market.exchange == "mexc" and exchange_market.market == MarketType.SPOT:
            return MexcPublicExchange()
        elif exchange_market.exchange == "gateio" and exchange_market.market == MarketType.SPOT:
            return GateioPublicExchange()
        elif exchange_market.exchange == "gateio" and exchange_market.market == MarketType.FUTURES:
            return GateioPublicFuturesExchange()
        else:
            raise ValueError(f"Unsupported exchange/market: {exchange_market}")
    
    async def _fetch_exchange_info(self, exchange_market: ExchangeMarket) -> Dict[Symbol, SymbolInfo]:
        """
        Fetch symbol information from specific exchange/market.
        
        HFT COMPLIANT: Fresh API calls for configuration data.
        """
        try:
            # Create exchange instance on-demand
            exchange_key = str(exchange_market)
            if exchange_key not in self.exchanges:
                self.exchanges[exchange_key] = self._create_exchange_client(exchange_market)
            
            client = self.exchanges[exchange_key]
            start_time = time.perf_counter()
            
            # Fetch exchange info (fresh call per HFT compliance)
            info = await client.get_exchange_info()
            
            elapsed = time.perf_counter() - start_time
            self.logger.info(f"Fetched {len(info)} symbols from {exchange_market} in {elapsed:.2f}s")
            
            return info
            
        except ExchangeAPIError as e:
            self.logger.error(f"Failed to fetch from {exchange_market}: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error fetching from {exchange_market}: {e}")
            return {}
    
    async def discover_symbols(self, filter_major_coins: bool = True) -> DiscoveryResult:
        """
        Perform comprehensive symbol discovery across all exchanges.
        
        Args:
            filter_major_coins: Exclude BTC, ETH, etc. for focused 3-tier analysis
            
        Returns:
            DiscoveryResult with complete analysis
        """
        start_time = time.perf_counter()
        
        # Define exchange/market combinations
        targets = [
            ExchangeMarket(exchange="mexc", market=MarketType.SPOT),
            ExchangeMarket(exchange="gateio", market=MarketType.SPOT),
            ExchangeMarket(exchange="gateio", market=MarketType.FUTURES)
        ]
        
        # Parallel fetch from all exchanges (event-driven architecture)
        tasks = [self._fetch_exchange_info(target) for target in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Map results to exchange/market
        exchange_data: Dict[ExchangeMarket, Dict[Symbol, SymbolInfo]] = {}
        for target, result in zip(targets, results):
            if isinstance(result, Exception):
                self.logger.error(f"Error from {target}: {result}")
                exchange_data[target] = {}
            else:
                exchange_data[target] = result
        
        # Process and analyze symbols
        availability_matrix = self._build_availability_matrix(exchange_data)
        metadata = self._extract_metadata(exchange_data, availability_matrix)
        
        # Apply filters if requested
        if filter_major_coins:
            availability_matrix = self._filter_major_coins(availability_matrix)
            # Update metadata to match filtered symbols
            filtered_metadata = {k: v for k, v in metadata.items() if k in availability_matrix}
            metadata = filtered_metadata
        
        # Calculate statistics
        statistics = self._calculate_statistics(availability_matrix, metadata)
        
        execution_time = time.perf_counter() - start_time
        
        # Convert to serializable format
        availability_dict = {}
        for symbol_key, avail in availability_matrix.items():
            availability_dict[symbol_key] = {
                'mexc_spot': avail.mexc_spot,
                'gateio_spot': avail.gateio_spot,
                'gateio_futures': avail.gateio_futures
            }
        
        # Convert metadata to serializable format
        metadata_dict = {}
        for symbol_key, meta in metadata.items():
            metadata_dict[symbol_key] = {
                'symbol': f"{meta.symbol.base}/{meta.symbol.quote}",
                'min_quote_amount': meta.min_quote_amount,
                'max_precision': meta.max_precision,
                'fee_range': meta.fee_range,
                'exchanges': meta.exchanges
            }
        
        return DiscoveryResult(
            timestamp=datetime.now().isoformat(),
            total_symbols=len(availability_matrix),
            arbitrage_candidates=statistics['arbitrage_candidates'],
            availability_matrix=availability_dict,
            metadata=metadata_dict,
            statistics=statistics,
            execution_time=execution_time
        )
    
    def _build_availability_matrix(self, 
                                  exchange_data: Dict[ExchangeMarket, Dict[Symbol, SymbolInfo]]
                                  ) -> Dict[str, SymbolAvailability]:
        """Build symbol availability matrix across all exchanges"""
        # Collect all unique symbols
        all_symbols: Set[Symbol] = set()
        for symbols in exchange_data.values():
            all_symbols.update(symbols.keys())
        
        # Build availability matrix
        matrix = {}
        for symbol in all_symbols:
            symbol_key = f"{symbol.base}/{symbol.quote}"
            
            # Find exchange markets for mexc and gateio
            mexc_spot_market = ExchangeMarket(exchange="mexc", market=MarketType.SPOT)
            gateio_spot_market = ExchangeMarket(exchange="gateio", market=MarketType.SPOT)
            gateio_futures_market = ExchangeMarket(exchange="gateio", market=MarketType.FUTURES)
            
            availability = SymbolAvailability(
                symbol=symbol,
                mexc_spot=symbol in exchange_data.get(mexc_spot_market, {}),
                gateio_spot=symbol in exchange_data.get(gateio_spot_market, {}),
                gateio_futures=symbol in exchange_data.get(gateio_futures_market, {})
            )
            
            matrix[symbol_key] = availability
        
        return matrix
    
    def _extract_metadata(self,
                         exchange_data: Dict[ExchangeMarket, Dict[Symbol, SymbolInfo]],
                         availability: Dict[str, SymbolAvailability]) -> Dict[str, SymbolMetadata]:
        """Extract detailed metadata for arbitrage candidates"""
        metadata = {}
        
        for symbol_key, avail in availability.items():
            if not avail.is_arbitrage_candidate:
                continue
            
            symbol = avail.symbol
            exchanges_info = {}
            min_quotes = []
            precisions = []
            fees = []
            
            # Collect info from each exchange where symbol is available
            for exchange_market, symbols in exchange_data.items():
                if symbol in symbols:
                    info = symbols[symbol]
                    exchanges_info[str(exchange_market)] = {
                        'base_precision': info.base_precision,
                        'quote_precision': info.quote_precision,
                        'min_quote_amount': info.min_quote_amount,
                        'min_base_amount': info.min_base_amount,
                        'maker_fee': info.maker_commission,
                        'taker_fee': info.taker_commission,
                        'inactive': info.inactive
                    }
                    min_quotes.append(info.min_quote_amount)
                    precisions.append(max(info.base_precision, info.quote_precision))
                    fees.extend([info.maker_commission, info.taker_commission])
            
            if exchanges_info:
                metadata[symbol_key] = SymbolMetadata(
                    symbol=symbol,
                    exchanges=exchanges_info,
                    min_quote_amount=min(min_quotes) if min_quotes else 0,
                    max_precision=max(precisions) if precisions else 0,
                    fee_range=(min(fees) if fees else 0, max(fees) if fees else 0)
                )
        
        return metadata
    
    def _filter_major_coins(self, 
                           availability: Dict[str, SymbolAvailability]
                           ) -> Dict[str, SymbolAvailability]:
        """Filter out major coins for focused 3-tier analysis"""
        # Major coins to exclude
        major_bases = {'BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'SOL', 'DOT', 'DOGE', 
                      'AVAX', 'MATIC', 'LINK', 'UNI', 'ATOM', 'LTC', 'BCH', 'USDT', 'USDC', 'BUSD'}
        
        filtered = {}
        for symbol_key, avail in availability.items():
            if avail.symbol.base not in major_bases:
                filtered[symbol_key] = avail
        
        return filtered
    
    def _calculate_statistics(self,
                            availability: Dict[str, SymbolAvailability],
                            metadata: Dict[str, SymbolMetadata]) -> Dict[str, Any]:
        """Calculate comprehensive statistics"""
        total = len(availability)
        
        # Count by availability
        mexc_only = sum(1 for a in availability.values() 
                       if a.mexc_spot and not a.gateio_spot and not a.gateio_futures)
        gateio_spot_only = sum(1 for a in availability.values()
                              if not a.mexc_spot and a.gateio_spot and not a.gateio_futures)
        gateio_futures_only = sum(1 for a in availability.values()
                                 if not a.mexc_spot and not a.gateio_spot and a.gateio_futures)
        
        # Arbitrage opportunities
        two_way = sum(1 for a in availability.values() if a.exchange_count == 2)
        three_way = sum(1 for a in availability.values() if a.exchange_count == 3)
        
        # Best opportunities (available on all exchanges)
        best_opportunities = [
            symbol_key for symbol_key, avail in availability.items()
            if avail.exchange_count == 3
        ]
        
        return {
            'total_symbols': total,
            'mexc_spot_total': sum(1 for a in availability.values() if a.mexc_spot),
            'gateio_spot_total': sum(1 for a in availability.values() if a.gateio_spot),
            'gateio_futures_total': sum(1 for a in availability.values() if a.gateio_futures),
            'mexc_only': mexc_only,
            'gateio_spot_only': gateio_spot_only,
            'gateio_futures_only': gateio_futures_only,
            'arbitrage_candidates': two_way + three_way,
            'two_way_opportunities': two_way,
            'three_way_opportunities': three_way,
            'best_opportunities': best_opportunities[:20]  # Top 20
        }
    
    async def close(self):
        """Close all exchange connections"""
        for exchange in self.exchanges.values():
            if hasattr(exchange, 'close'):
                try:
                    await exchange.close()
                except Exception as e:
                    self.logger.debug(f"Error closing exchange: {e}")


class OutputManager:
    """
    Manages output generation and file saving.
    
    Responsibilities:
    - Format conversion
    - File management
    - Timestamped output
    """
    
    def __init__(self, output_dir: Path = None):
        """Initialize output manager with directory"""
        self.output_dir = output_dir or Path(__file__).parent / 'output'
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def save_result(self, 
                   result: DiscoveryResult,
                   format: OutputFormat = OutputFormat.DETAILED) -> Path:
        """
        Save discovery result to JSON file.
        
        Returns:
            Path to saved file
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        format_name = format.name.lower()
        filename = f"symbol_discovery_{format_name}_{timestamp}.json"
        filepath = self.output_dir / filename
        
        # Convert to appropriate format
        output_data = self._format_output(result, format)
        
        # Save with standard json for readability
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def _format_output(self, result: DiscoveryResult, format: OutputFormat) -> dict:
        """Format output based on selected format"""
        if format == OutputFormat.SUMMARY:
            return self._format_summary(result)
        elif format == OutputFormat.DETAILED:
            return self._format_detailed(result)
        elif format == OutputFormat.FILTERED:
            return self._format_filtered(result)
        elif format == OutputFormat.MATRIX:
            return self._format_matrix(result)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def _format_summary(self, result: DiscoveryResult) -> dict:
        """Generate summary format"""
        return {
            'timestamp': result.timestamp,
            'execution_time': result.execution_time,
            'statistics': result.statistics,
            'top_opportunities': result.statistics.get('best_opportunities', [])
        }
    
    def _format_detailed(self, result: DiscoveryResult) -> dict:
        """Generate detailed format with all data"""
        return {
            'timestamp': result.timestamp,
            'execution_time': result.execution_time,
            'statistics': result.statistics,
            'availability': result.availability_matrix,
            'metadata': result.metadata
        }
    
    def _format_filtered(self, result: DiscoveryResult) -> dict:
        """Generate filtered format (arbitrage candidates only)"""
        # Filter for arbitrage candidates only
        filtered_availability = {}
        for symbol_key, availability in result.availability_matrix.items():
            # Check if available on multiple exchanges
            count = sum([availability['mexc_spot'], availability['gateio_spot'], availability['gateio_futures']])
            if count >= 2:
                filtered_availability[symbol_key] = availability
        
        return {
            'timestamp': result.timestamp,
            'execution_time': result.execution_time,
            'arbitrage_candidates': len(filtered_availability),
            'opportunities': filtered_availability
        }
    
    def _format_matrix(self, result: DiscoveryResult) -> dict:
        """Generate simple matrix format as specified"""
        return result.availability_matrix


class DiscoveryCLI:
    """
    Command-line interface for symbol discovery tool.
    
    Provides user-friendly interface with progress indicators.
    """
    
    def __init__(self):
        """Initialize CLI with logging configuration"""
        self._setup_logging()
        self.engine = SymbolDiscoveryEngine(self.logger)
        self.output_manager = OutputManager()
    
    def _setup_logging(self):
        """Configure logging for CLI"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger('SymbolDiscovery')
    
    async def run(self,
                 output_format: OutputFormat = OutputFormat.DETAILED,
                 filter_major: bool = True,
                 save_output: bool = True) -> None:
        """
        Run symbol discovery with specified options.
        
        Args:
            output_format: Output format selection
            filter_major: Filter major coins for 3-tier focus
            save_output: Save results to file
        """
        try:
            self.logger.info("Starting cross-exchange symbol discovery...")
            self.logger.info(f"Options: format={output_format.name}, filter_major={filter_major}")
            
            # Run discovery
            result = await self.engine.discover_symbols(filter_major_coins=filter_major)
            
            # Display summary
            self._display_summary(result)
            
            # Save output if requested
            if save_output:
                filepath = self.output_manager.save_result(result, output_format)
                self.logger.info(f"Results saved to: {filepath}")
            
            # Close connections
            await self.engine.close()
            
            self.logger.info(f"Discovery completed in {result.execution_time:.2f} seconds")
            
        except Exception as e:
            self.logger.error(f"Discovery failed: {e}")
            await self.engine.close()
            raise
    
    def _display_summary(self, result: DiscoveryResult) -> None:
        """Display result summary to console"""
        stats = result.statistics
        
        print("\n" + "="*60)
        print("SYMBOL DISCOVERY RESULTS")
        print("="*60)
        print(f"Execution Time: {result.execution_time:.2f} seconds")
        print(f"Timestamp: {datetime.fromisoformat(result.timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
        print("\nEXCHANGE COVERAGE:")
        print(f"  MEXC Spot: {stats['mexc_spot_total']} symbols")
        print(f"  Gate.io Spot: {stats['gateio_spot_total']} symbols")
        print(f"  Gate.io Futures: {stats['gateio_futures_total']} symbols")
        print(f"  Total Unique: {stats['total_symbols']} symbols")
        print("\nEXCLUSIVE SYMBOLS:")
        print(f"  MEXC Only: {stats['mexc_only']}")
        print(f"  Gate.io Spot Only: {stats['gateio_spot_only']}")
        print(f"  Gate.io Futures Only: {stats['gateio_futures_only']}")
        print("\nARBITRAGE OPPORTUNITIES:")
        print(f"  Two-Way: {stats['two_way_opportunities']} symbols")
        print(f"  Three-Way: {stats['three_way_opportunities']} symbols")
        print(f"  Total Candidates: {stats['arbitrage_candidates']} symbols")
        
        if stats.get('best_opportunities'):
            print("\nTOP OPPORTUNITIES (Available on all exchanges):")
            for symbol in stats['best_opportunities'][:10]:
                print(f"    • {symbol}")
        print("="*60 + "\n")


# Main entry point
async def main():
    """Main entry point for CLI tool"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Cross-Exchange Symbol Discovery Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings (detailed output, filter major coins)
  python cross_exchange_symbol_discovery.py
  
  # Generate summary only
  python cross_exchange_symbol_discovery.py --format summary
  
  # Include major coins in analysis
  python cross_exchange_symbol_discovery.py --no-filter-major
  
  # Generate simple matrix format
  python cross_exchange_symbol_discovery.py --format matrix
        """
    )
    
    parser.add_argument(
        '--format',
        type=str,
        choices=['summary', 'detailed', 'filtered', 'matrix'],
        default='detailed',
        help='Output format (default: detailed)'
    )
    
    parser.add_argument(
        '--no-filter-major',
        action='store_true',
        help='Include major coins (BTC, ETH, etc.) in analysis'
    )
    
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Do not save output to file'
    )
    
    args = parser.parse_args()
    
    # Map format string to enum
    format_map = {
        'summary': OutputFormat.SUMMARY,
        'detailed': OutputFormat.DETAILED,
        'filtered': OutputFormat.FILTERED,
        'matrix': OutputFormat.MATRIX
    }
    
    cli = DiscoveryCLI()
    await cli.run(
        output_format=format_map[args.format],
        filter_major=not args.no_filter_major,
        save_output=not args.no_save
    )


if __name__ == '__main__':
    asyncio.run(main())