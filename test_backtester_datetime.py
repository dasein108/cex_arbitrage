#!/usr/bin/env python3
"""
Test script to verify datetime functionality in the strategy backtester.
"""

import asyncio
from datetime import datetime, timedelta
from src.trading.analysis.strategy_backtester import backtest_mexc_gateio_strategy
from exchanges.structs.common import Symbol, AssetName


async def test_datetime_functionality():
    """Test that the backtester works with datetime objects."""
    print("🧪 Testing Strategy Backtester with datetime objects")
    print("=" * 60)
    
    try:
        # Create symbol using available data
        symbol = Symbol(base=AssetName('NEIROETH'), quote=AssetName('USDT'))
        
        # Use datetime objects directly
        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)
        
        print(f"Symbol: {symbol.base}/{symbol.quote}")
        print(f"Start Date: {start_date}")
        print(f"End Date: {end_date}")
        print(f"Date Type: {type(start_date)} (should be datetime)")
        
        # Test the convenience function with datetime objects
        print("\n🚀 Running backtest with datetime objects...")
        results = await backtest_mexc_gateio_strategy(
            symbol=symbol,
            start_date=start_date,  # datetime object
            end_date=end_date,      # datetime object
            entry_threshold_pct=0.1,
            exit_threshold_pct=0.03,
            base_position_size=100.0
        )
        
        print("✅ Backtest completed successfully with datetime objects!")
        print(f"📊 Results: {results.total_trades} trades, {results.total_return_pct:.2f}% return")
        print(f"🎯 Type checking passed - datetime objects accepted")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_datetime_functionality())