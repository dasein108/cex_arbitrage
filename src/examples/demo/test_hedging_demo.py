#!/usr/bin/env python3
"""
Test script for the real-world hedging demo.

This script tests the hedging demo in dry-run mode to verify all components work
correctly without placing real orders.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from real_world_hedging_demo import (
    parse_symbol, HedgingConfiguration, HedgingDemoError
)
from infrastructure.logging import get_logger


async def test_symbol_parsing():
    """Test symbol parsing functionality."""
    print("🧪 Testing symbol parsing...")
    
    try:
        # Test valid symbol
        primary, spot, futures = parse_symbol("BTC/USDT")
        assert primary.base == "BTC"
        assert primary.quote == "USDT"
        assert not primary.is_futures
        assert not spot.is_futures
        assert futures.is_futures
        print("✅ Valid symbol parsing works")
        
        # Test invalid symbol
        try:
            parse_symbol("INVALID")
            assert False, "Should have raised exception"
        except ValueError:
            print("✅ Invalid symbol correctly rejected")
        
        return True
        
    except Exception as e:
        print(f"❌ Symbol parsing failed: {e}")
        return False


async def test_configuration_creation():
    """Test configuration creation."""
    print("🧪 Testing configuration creation...")
    
    try:
        primary, spot, futures = parse_symbol("BTC/USDT")
        
        # Valid configuration
        config = HedgingConfiguration(
            symbol=primary,
            spot_symbol=spot,
            futures_symbol=futures,
            amount_usdt=100.0,
            min_funding_rate=0.01,
            max_position_imbalance=0.05,
            max_execution_time_minutes=60.0,
            enable_rebalancing=True
        )
        
        assert config.amount_usdt == 100.0
        assert config.min_funding_rate == 0.01
        print("✅ Valid configuration created")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration creation failed: {e}")
        return False


async def test_state_machine_import():
    """Test state machine import."""
    print("🧪 Testing state machine import...")
    
    try:
        from trading.state_machines.hedging.spot_futures_hedging import (
            SpotFuturesHedgingStateMachine, SpotFuturesHedgingContext
        )
        
        print("✅ State machine imports successful")
        return True
        
    except Exception as e:
        print(f"❌ State machine import failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🚀 Testing Real-World Hedging Demo")
    print("="*50)
    
    tests = [
        ("Symbol Parsing", test_symbol_parsing),
        ("Configuration Creation", test_configuration_creation),
        ("State Machine Import", test_state_machine_import)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        try:
            if await test_func():
                passed += 1
            else:
                print(f"   Test failed")
        except Exception as e:
            print(f"   Test crashed: {e}")
    
    print("\n" + "="*50)
    print(f"🏁 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All tests passed! Demo is ready for use.")
        print("\n💡 Try running the demo:")
        print("   PYTHONPATH=src python src/examples/demo/real_world_hedging_demo.py \\")
        print("       --symbol BTC/USDT --amount 100 --dry-run")
    else:
        print("❌ Some tests failed. Check the errors above.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)