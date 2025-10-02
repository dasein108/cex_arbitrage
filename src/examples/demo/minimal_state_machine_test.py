"""
Minimal test for state machine core functionality without exchange dependencies.

This test directly imports only the core state machine components to verify
the implementation works without requiring the full exchange infrastructure.
"""

import sys
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any
import asyncio
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Mock the exchange dependencies to avoid import issues
class MockSymbol:
    def __init__(self, base: str, quote: str, is_futures: bool = False):
        self.base = base
        self.quote = quote
        self.is_futures = is_futures
    
    def __str__(self):
        return f"{self.base}/{self.quote}"

class MockOrder:
    def __init__(self, order_id: str, symbol, side: str, quantity: float, price: float):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.filled_quantity = quantity
        self.price = price
        self.average_price = price
        self.fee = 0.0

class MockLogger:
    def info(self, message: str, **kwargs):
        print(f"INFO: {message}")
    def error(self, message: str, **kwargs):
        print(f"ERROR: {message}")
    def warning(self, message: str, **kwargs):
        print(f"WARNING: {message}")

# Test the core state machine components directly
def test_core_components():
    """Test core state machine components without exchange dependencies."""
    try:
        # Test enums and basic structures
        from trading.state_machines.base.base_state_machine import (
            StrategyState, StrategyResult, StrategyError, BaseStrategyContext
        )
        
        # Test that we can create basic enums
        state = StrategyState.IDLE
        print(f"✅ Created StrategyState: {state.value}")
        
        # Test context creation
        symbol = MockSymbol("BTC", "USDT")
        logger = MockLogger()
        
        context = BaseStrategyContext(
            strategy_name="test_strategy",
            symbol=symbol,
            logger=logger
        )
        
        print(f"✅ Created BaseStrategyContext: {context.strategy_name}")
        
        # Test result creation
        result = StrategyResult(
            strategy_name="test",
            symbol=symbol,
            success=True,
            profit_usdt=10.5,
            execution_time_ms=1500.0
        )
        
        print(f"✅ Created StrategyResult: ${result.profit_usdt} profit")
        
        return True
        
    except Exception as e:
        print(f"❌ Core components test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_factory_components():
    """Test factory components."""
    try:
        from trading.state_machines.base.factory import StrategyType, StateMachineFactory
        
        # Test enum creation
        strategy_type = StrategyType.SIMPLE_ARBITRAGE
        print(f"✅ Created StrategyType: {strategy_type.value}")
        
        # Test factory creation
        factory = StateMachineFactory()
        print(f"✅ Created StateMachineFactory")
        
        return True
        
    except Exception as e:
        print(f"❌ Factory components test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_mixins():
    """Test mixin components."""
    try:
        from trading.state_machines.base.mixins import (
            StateTransitionMixin,
            PerformanceMonitoringMixin,
            RiskManagementMixin
        )
        
        print(f"✅ Imported mixins successfully")
        
        # Test performance monitoring mixin
        class TestClass(PerformanceMonitoringMixin):
            pass
        
        test_obj = TestClass()
        start_time = test_obj._start_performance_timer()
        time.sleep(0.001)  # 1ms
        duration = test_obj._end_performance_timer(start_time)
        
        print(f"✅ Performance timing works: {duration:.1f}ms")
        
        return True
        
    except Exception as e:
        print(f"❌ Mixins test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run minimal tests."""
    print("🧪 Minimal State Machine Core Tests")
    print("="*40)
    
    tests = [
        ("Core Components", test_core_components),
        ("Factory Components", test_factory_components),
        ("Mixins", test_mixins)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        if test_func():
            passed += 1
    
    print("\n" + "="*40)
    print(f"🏁 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ Core state machine components are working!")
    else:
        print("❌ Some core components failed.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)