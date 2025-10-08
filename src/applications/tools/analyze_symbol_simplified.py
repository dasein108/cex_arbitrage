#!/usr/bin/env python3
"""
Historical Spread Analysis Tool

Streamlined tool for analyzing historical arbitrage spreads
across trading symbols and exchanges.

Usage Examples:
    # Analyze NEIROETH historical data
    python analyze_symbol_simplified.py --symbol NEIROETH --quote USDT
    
    # Analyze BTC with custom time period
    python analyze_symbol_simplified.py --symbol BTC --quote USDT --hours 48
    
    # Analyze with custom exchanges
    python analyze_symbol_simplified.py --symbol ETH --quote USDT --exchanges GATEIO_SPOT,MEXC_SPOT
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# Add paths for imports from project root
current_dir = Path(__file__).parent  # /Users/dasein/dev/cex_arbitrage/src/applications/tools/
project_root = current_dir.parent.parent.parent  # /Users/dasein/dev/cex_arbitrage/
src_path = project_root / "src"

sys.path.insert(0, str(src_path))

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

# Import from same directory/package
try:
    from .data_fetcher import MultiSymbolDataFetcher
    from .spread_analyzer_simplified import SpreadAnalyzer
except ImportError:
    from data_fetcher import MultiSymbolDataFetcher
    from spread_analyzer_simplified import SpreadAnalyzer

# Setup simplified logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class HistoricalAnalyzer:
    """Streamlined historical spread analyzer."""
    
    DEFAULT_EXCHANGES = {
        'GATEIO_SPOT': 'GATEIO_SPOT',
        'GATEIO_FUTURES': 'GATEIO_FUTURES',
        'MEXC_SPOT': 'MEXC_SPOT'
    }
    
    def __init__(self, symbol: Symbol, exchanges: Optional[Dict[str, str]] = None):
        self.symbol = symbol
        self.exchanges = exchanges or self.DEFAULT_EXCHANGES
        self.symbol_str = f"{symbol.base}/{symbol.quote}"
        
        # Initialize components
        self.data_fetcher = MultiSymbolDataFetcher(symbol, self.exchanges)
        self.spread_analyzer = SpreadAnalyzer(self.data_fetcher)
        
        logger.info(f"Historical analyzer initialized for {self.symbol_str}")
        logger.info(f"Exchanges: {list(self.exchanges.keys())}")
    
    async def initialize(self) -> bool:
        """Initialize the analyzer."""
        logger.info("Initializing analyzer...")
        success = await self.data_fetcher.initialize()
        
        if success:
            logger.info("Analyzer initialized successfully")
            health = await self.data_fetcher.health_check()
            logger.info(f"Health check: {health}")
            
            if not health['latest_data_available']:
                logger.warning("No recent data available - results may be limited")
        else:
            logger.error("Failed to initialize analyzer")
        
        return success
    
    async def analyze_historical_performance(
        self,
        hours_back: int = 24,
        spread_type: str = 'auto'
    ) -> Dict:
        """Analyze historical performance and patterns."""
        logger.info(f"Analyzing {hours_back}h historical performance for {self.symbol_str}...")
        
        try:
            # Get historical statistics with auto-fallback
            stats = await self.spread_analyzer.get_historical_statistics(
                hours_back=hours_back, 
                spread_type=spread_type
            )
            
            if not stats:
                return {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'symbol': self.symbol_str,
                    'error': 'No historical data available',
                    'status': 'no_data'
                }
            
            # Get volatility metrics
            try:
                volatility = await self.spread_analyzer.get_volatility_metrics()
            except Exception as e:
                logger.warning(f"Could not get volatility metrics: {e}")
                volatility = {}
            
            results = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'symbol': self.symbol_str,
                'analysis_period': {
                    'hours_back': hours_back,
                    'spread_type': spread_type,
                    'period_start': stats.period_start.isoformat(),
                    'period_end': stats.period_end.isoformat(),
                    'sample_count': stats.sample_count
                },
                'historical_statistics': {
                    'mean_spread_pct': round(stats.mean_spread, 4),
                    'median_spread_pct': round(stats.median_spread, 4),
                    'std_deviation': round(stats.std_deviation, 4),
                    'min_spread_pct': round(stats.min_spread, 4),
                    'max_spread_pct': round(stats.max_spread, 4),
                    'percentiles': {
                        'p25': round(stats.p25, 4),
                        'p75': round(stats.p75, 4),
                        'p90': round(stats.p90, 4),
                        'p95': round(stats.p95, 4),
                        'p99': round(stats.p99, 4)
                    }
                },
                'market_analysis': {
                    'trend_direction': stats.trend_direction,
                    'volatility_regime': stats.volatility_regime,
                    'profitable_opportunities': stats.profitable_opportunities,
                    'opportunity_rate_per_hour': round(stats.opportunity_rate, 2)
                },
                'volatility_metrics': volatility,
                'recommendations': self._generate_recommendations(stats)
            }
            
            logger.info(f"Historical analysis complete:")
            logger.info(f"  • Opportunity rate: {stats.opportunity_rate:.2f}/hour")
            logger.info(f"  • Mean spread: {stats.mean_spread:.4f}%")
            logger.info(f"  • Volatility regime: {stats.volatility_regime}")
            
            return results
            
        except Exception as e:
            logger.error(f"Historical analysis failed: {e}")
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'symbol': self.symbol_str,
                'error': str(e),
                'status': 'failed'
            }
    
    def _generate_recommendations(self, stats) -> list[str]:
        """Generate trading recommendations based on analysis."""
        recommendations = []
        
        if stats.opportunity_rate > 2.0:
            recommendations.append("HIGH ACTIVITY: Strong arbitrage potential with frequent opportunities")
        elif stats.opportunity_rate < 0.5:
            recommendations.append("LOW ACTIVITY: Limited arbitrage opportunities, consider other symbols")
        
        if stats.volatility_regime == 'high':
            recommendations.append("HIGH VOLATILITY: Use smaller position sizes and tighter risk management")
        elif stats.volatility_regime == 'low':
            recommendations.append("LOW VOLATILITY: Stable conditions, suitable for larger positions")
        
        if stats.trend_direction == 'expanding':
            recommendations.append("EXPANDING SPREADS: Increasing arbitrage opportunities expected")
        elif stats.trend_direction == 'contracting':
            recommendations.append("CONTRACTING SPREADS: Decreasing arbitrage potential")
        
        if stats.mean_spread > 0.2:
            recommendations.append("WIDE SPREADS: Excellent profit potential with proper execution")
        elif stats.mean_spread < 0.05:
            recommendations.append("NARROW SPREADS: Requires HFT execution for profitability")
        
        return recommendations or ["NEUTRAL: Standard market conditions, proceed with normal strategy"]


def parse_exchanges(exchange_str: str) -> Dict[str, str]:
    """Parse comma-separated exchange string."""
    if not exchange_str:
        return None
    
    exchanges = {}
    for i, exchange in enumerate(exchange_str.split(',')):
        key = f"EXCHANGE_{i+1}"
        exchanges[key] = exchange.strip().upper()
    
    return exchanges


async def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Historical Spread Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic historical analysis
  python analyze_symbol_simplified.py --symbol NEIROETH --quote USDT
  
  # Extended time period
  python analyze_symbol_simplified.py --symbol BTC --quote USDT --hours 48
  
  # Custom exchanges
  python analyze_symbol_simplified.py --symbol ETH --quote USDT --exchanges GATEIO_SPOT,MEXC_SPOT
        """
    )
    
    # Core arguments
    parser.add_argument('--symbol', required=True, help='Base symbol to analyze (e.g., NEIROETH, BTC)')
    parser.add_argument('--quote', default='USDT', help='Quote currency (default: USDT)')
    parser.add_argument('--hours', type=int, default=24, help='Hours of historical data (default: 24)')
    parser.add_argument('--exchanges', help='Comma-separated exchange list (e.g., GATEIO_SPOT,MEXC_SPOT)')
    parser.add_argument('--spread-type', default='auto', help='Spread type for analysis (default: auto)')
    
    # Output options
    parser.add_argument('--output', choices=['json', 'pretty'], default='pretty', help='Output format')
    parser.add_argument('--save', help='Save results to file')
    
    args = parser.parse_args()
    
    try:
        # Create symbol
        symbol = Symbol(base=AssetName(args.symbol.upper()), quote=AssetName(args.quote.upper()))
        exchanges = parse_exchanges(args.exchanges)
        
        # Initialize analyzer
        analyzer = HistoricalAnalyzer(symbol, exchanges)
        
        if not await analyzer.initialize():
            logger.error("Failed to initialize analyzer")
            return 1
        
        # Perform historical analysis
        results = await analyzer.analyze_historical_performance(
            hours_back=args.hours,
            spread_type=args.spread_type
        )
        
        # Output results
        if args.output == 'json':
            output = json.dumps(results, indent=2, default=str)
        else:
            output = format_historical_results(results)
        
        print(output)
        
        # Save to file if requested
        if args.save:
            with open(args.save, 'w') as f:
                if args.output == 'json':
                    json.dump(results, f, indent=2, default=str)
                else:
                    f.write(output)
            logger.info(f"Results saved to {args.save}")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Analysis interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def format_historical_results(results: Dict) -> str:
    """Format historical analysis results."""
    output = []
    output.append(f"HISTORICAL PERFORMANCE ANALYSIS")
    output.append(f"{'='*50}")
    output.append(f"Symbol: {results['symbol']}")
    output.append(f"Timestamp: {results['timestamp']}")
    
    # Handle error cases
    if 'error' in results:
        output.append("")
        output.append(f"ERROR: {results['error']}")
        output.append(f"Status: {results.get('status', 'unknown')}")
        return "\n".join(output)
    
    # Handle successful analysis
    if 'analysis_period' not in results:
        output.append("")
        output.append("ERROR: Missing analysis period data")
        return "\n".join(output)
        
    output.append(f"Period: {results['analysis_period']['hours_back']} hours")
    output.append(f"Samples: {results['analysis_period']['sample_count']}")
    output.append("")
    
    stats = results['historical_statistics']
    output.append(f"SPREAD STATISTICS")
    output.append(f"Mean Spread: {stats['mean_spread_pct']}%")
    output.append(f"Median Spread: {stats['median_spread_pct']}%")
    output.append(f"Range: {stats['min_spread_pct']}% - {stats['max_spread_pct']}%")
    output.append(f"Std Deviation: {stats['std_deviation']}%")
    output.append("")
    
    output.append(f"PERCENTILES")
    percentiles = stats['percentiles']
    output.append(f"25th: {percentiles['p25']}%")
    output.append(f"75th: {percentiles['p75']}%")
    output.append(f"90th: {percentiles['p90']}%")
    output.append(f"95th: {percentiles['p95']}%")
    output.append(f"99th: {percentiles['p99']}%")
    output.append("")
    
    market = results['market_analysis']
    output.append(f"MARKET ANALYSIS")
    output.append(f"Trend: {market['trend_direction']}")
    output.append(f"Volatility Regime: {market['volatility_regime']}")
    output.append(f"Opportunities per Hour: {market['opportunity_rate_per_hour']}")
    output.append(f"Profitable Opportunities: {market['profitable_opportunities']}")
    output.append("")
    
    output.append(f"RECOMMENDATIONS")
    for rec in results['recommendations']:
        output.append(f"• {rec}")
    
    return "\n".join(output)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)