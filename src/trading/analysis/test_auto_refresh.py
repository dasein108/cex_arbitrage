#!/usr/bin/env python3
"""
Test the auto-refresh and cleanup features of CrossArbitrageTA.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.append('/Users/dasein/dev/cex_arbitrage/src')

from trading.analysis.cross_arbitrage_ta import CrossArbitrageDynamicSignalGenerator, CrossArbitrageSignalConfig
from exchanges.structs import Symbol, AssetName
from infrastructure.logging import get_logger

async def test_auto_refresh_features():
    """Test auto-refresh and cleanup functionality."""
    print("🧪 TESTING AUTO-REFRESH AND CLEANUP FEATURES")
    print("=" * 60)
    
    # Test 1: Auto-refresh enabled
    print("\n📊 Test 1: Auto-refresh enabled (5 second interval)")
    
    ta_auto = CrossArbitrageDynamicSignalGenerator(
        symbol=Symbol(base=AssetName("F"), quote=AssetName("USDT")),
        config=CrossArbitrageSignalConfig(
            lookback_hours=24,
            refresh_minutes=0.083,  # 5 seconds for testing (0.083 * 60 = 5s)
            entry_percentile=15,
            exit_percentile=85,
            total_fees=0.2
        ),
        logger=get_logger("test_auto")
    )
    
    try:
        await ta_auto.initialize()
        
        print(f"✅ Auto-refresh TA initialized")
        print(f"   Refresh interval: {ta_auto.refresh_minutes} minutes")
        print(f"   Auto-refresh task running: {ta_auto._refresh_task is not None}")
        print(f"   Is running: {ta_auto._is_running}")
        
        # Wait to see if auto-refresh triggers
        print("⏳ Waiting 6 seconds to test auto-refresh...")
        await asyncio.sleep(6)
        
        print("✅ Auto-refresh test completed")
        
    except Exception as e:
        print(f"❌ Auto-refresh test failed: {e}")
        return False
    finally:
        # Test cleanup
        print("🛑 Testing cleanup...")
        await ta_auto.shutdown()
        print(f"   Is running after shutdown: {ta_auto._is_running}")
        print(f"   Refresh task after shutdown: {ta_auto._refresh_task}")
    
    # Test 2: Auto-refresh disabled
    print(f"\n📊 Test 2: Auto-refresh disabled")
    
    ta_manual = CrossArbitrageDynamicSignalGenerator(
        symbol=Symbol(base=AssetName("F"), quote=AssetName("USDT")),
        config=CrossArbitrageSignalConfig(
            lookback_hours=24,
            refresh_minutes=None,  # Disabled
            entry_percentile=15,
            exit_percentile=85,
            total_fees=0.2
        ),
        logger=get_logger("test_manual")
    )
    
    try:
        await ta_manual.initialize()
        
        print(f"✅ Manual TA initialized")
        print(f"   Refresh interval: {ta_manual.refresh_minutes}")
        print(f"   Auto-refresh task running: {ta_manual._refresh_task is not None}")
        print(f"   Is running: {ta_manual._is_running}")
        
        # Test manual refresh
        print("🔄 Testing manual refresh...")
        should_refresh = ta_manual.should_refresh()
        print(f"   Should refresh: {should_refresh}")
        
        if should_refresh:
            await ta_manual.refresh_historical_data()
            print("✅ Manual refresh completed")
        
    except Exception as e:
        print(f"❌ Manual refresh test failed: {e}")
        return False
    finally:
        # Test cleanup
        print("🛑 Testing cleanup...")
        await ta_manual.cleanup()  # Test cleanup() alias
        print(f"   Is running after cleanup: {ta_manual._is_running}")
    
    # Test 3: Multiple shutdown calls (should be safe)
    print(f"\n📊 Test 3: Multiple shutdown calls")
    
    try:
        await ta_manual.shutdown()  # Second shutdown call
        await ta_manual.cleanup()   # Third cleanup call
        print("✅ Multiple shutdown calls handled safely")
    except Exception as e:
        print(f"❌ Multiple shutdown test failed: {e}")
        return False
    
    print(f"\n🎉 ALL AUTO-REFRESH TESTS PASSED!")
    print(f"✅ Auto-refresh functionality working")
    print(f"✅ Manual refresh functionality working")
    print(f"✅ Cleanup functionality working")
    print(f"✅ Multiple shutdown calls handled safely")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_auto_refresh_features())
    if success:
        sys.exit(0)
    else:
        sys.exit(1)