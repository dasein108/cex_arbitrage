"""
Test script to verify the refactored config management works.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from src.applications.portfolio_rebalancer import (
    BacktestEngine, LiveRebalancer, RebalanceConfig
)


async def test_config_refactoring():
    """Test that the refactored config management works correctly."""
    
    print("=== Testing Refactored Config Management ===\n")
    
    # Test BacktestEngine initialization
    try:
        print("1. Testing BacktestEngine initialization...")
        config = RebalanceConfig(
            upside_threshold=0.40,
            downside_threshold=0.35,
            initial_capital=10000.0
        )
        
        engine = BacktestEngine(
            assets=['BTC', 'ETH'],
            initial_capital=config.initial_capital,
            config=config
        )
        
        print(f"   ✅ BacktestEngine created successfully")
        print(f"   ✅ MEXC config loaded: {engine.mexc_config.name}")
        print(f"   ✅ REST client initialized: {type(engine.rest_client).__name__}")
        
    except Exception as e:
        print(f"   ❌ BacktestEngine failed: {e}")
        return False
    
    # Test LiveRebalancer initialization
    try:
        print("\n2. Testing LiveRebalancer initialization...")
        
        rebalancer = LiveRebalancer(
            assets=['BTC', 'ETH'],
            config=config
        )
        
        print(f"   ✅ LiveRebalancer created successfully")
        print(f"   ✅ MEXC config loaded: {rebalancer.mexc_config.name}")
        print(f"   ✅ DualExchange initialized: {type(rebalancer.exchange).__name__}")
        
    except Exception as e:
        print(f"   ❌ LiveRebalancer failed: {e}")
        return False
    
    # Test configuration access
    try:
        print("\n3. Testing configuration access...")
        print(f"   ✅ Exchange name: {engine.mexc_config.name}")
        print(f"   ✅ Base URL: {engine.mexc_config.base_url}")
        print(f"   ✅ WebSocket URL: {engine.mexc_config.websocket_url}")
        print(f"   ✅ Is futures: {engine.mexc_config.is_futures}")
        
    except Exception as e:
        print(f"   ❌ Configuration access failed: {e}")
        return False
    
    print("\n✅ All tests passed! Config refactoring successful.")
    return True


if __name__ == "__main__":
    print("Portfolio Rebalancer - Config Refactoring Test\n")
    
    try:
        success = asyncio.run(test_config_refactoring())
        if success:
            print("\n🎉 Refactoring complete and working correctly!")
        else:
            print("\n❌ Some tests failed.")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)