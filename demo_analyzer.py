#!/usr/bin/env python3
"""
Demonstration of the Enhanced CrossArbitrageCandidateAnalyzer.
This script shows the complete 3-stage analysis pipeline.
"""

import asyncio
import sys
from datetime import datetime, UTC, timedelta

# Add src to path
sys.path.append('src')

from applications.tools.research.cross_arbitrage_candidate_analyzer import CrossArbitrageCandidateAnalyzer
from exchanges.structs.enums import ExchangeEnum

async def main():
    """Demonstrate the complete arbitrage analysis pipeline."""
    print("🚀 Enhanced Arbitrage Candidate Analysis Demo")
    print("=" * 60)
    
    # Create analyzer
    analyzer = CrossArbitrageCandidateAnalyzer(
        exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES],
        output_dir="demo_results"
    )
    
    # Configure analysis period (last 6 hours for demo)
    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=6)
    
    print(f"📅 Analysis Period: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"🏢 Exchanges: {[e.value for e in analyzer.exchanges]}")
    print(f"📁 Output Directory: {analyzer.output_dir}")
    print()
    
    try:
        # Run the complete analysis with limited backtests for demo
        await analyzer.analyze(start_time, end_time, max_backtests=5)
        
        print("\n🎉 Demo completed successfully!")
        print("\n📋 Check the following files:")
        print(f"   • demo_results/arbitrage_candidates.json - Final ranked candidates")
        print(f"   • demo_results/screening_results.json - All screening results")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())