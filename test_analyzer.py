#!/usr/bin/env python3
"""
Test script for the enhanced CrossArbitrageCandidateAnalyzer.
This script runs a quick test of the analyzer functionality.
"""

import asyncio
import sys
from datetime import datetime, UTC, timedelta

# Add src to path
sys.path.append('src')

from applications.tools.research.cross_arbitrage_candidate_analyzer import CrossArbitrageCandidateAnalyzer
from exchanges.structs.enums import ExchangeEnum

async def test_analyzer():
    """Test the enhanced analyzer with a limited scope."""
    print("🚀 Testing Enhanced CrossArbitrageCandidateAnalyzer")
    print("=" * 60)
    
    try:
        # Create analyzer
        analyzer = CrossArbitrageCandidateAnalyzer(
            exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES],
            output_dir="test_results"
        )
        
        # Set time range (last 6 hours for quick testing)
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=6)
        
        print(f"📅 Analysis Period: {start_time} to {end_time}")
        print(f"🏢 Exchanges: {[e.value for e in analyzer.exchanges]}")
        
        # Run analysis with limited backtests
        await analyzer.analyze(start_time, end_time, max_backtests=3)
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_analyzer())