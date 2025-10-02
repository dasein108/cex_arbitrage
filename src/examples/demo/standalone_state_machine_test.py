"""
Standalone test for state machine core functionality using protocols.

This test uses the protocol-based implementation to verify state machines work
independently of the full exchange infrastructure.
"""

import sys
import os
import asyncio

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def test_protocol_imports():
    """Test that we can import protocol-based components."""
    try:
        from trading.state_machines.base.protocols import (
            SimpleSymbol, SimpleOrder, SimpleLogger,
            SymbolProtocol, OrderProtocol, LoggerProtocol
        )
        print("✅ Protocol imports successful")
        
        # Test creating simple objects
        symbol = SimpleSymbol("BTC", "USDT")
        order = SimpleOrder("test_1", symbol, "BUY", 1.0, 50000.0)
        logger = SimpleLogger("test")
        
        print(f"✅ Created test objects: {symbol}, {order}")
        
        return True
    except Exception as e:
        print(f"❌ Protocol imports failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_base_components():
    """Test base state machine components."""
    try:
        from trading.state_machines.base.base_state_machine import (
            StrategyState, StrategyResult, BaseStrategyContext
        )
        from trading.state_machines.base.protocols import SimpleSymbol, SimpleLogger
        
        # Test state creation
        state = StrategyState.IDLE
        print(f"✅ Created state: {state.value}")
        
        # Test context creation
        symbol = SimpleSymbol("BTC", "USDT")
        logger = SimpleLogger("test")
        
        context = BaseStrategyContext(
            strategy_name="test_strategy",
            symbol=symbol,
            logger=logger
        )
        print(f"✅ Created context: {context.strategy_name}")
        
        # Test result creation
        result = StrategyResult(
            strategy_name="test",
            symbol=symbol,
            success=True,
            profit_usdt=10.5
        )
        print(f"✅ Created result: ${result.profit_usdt}")
        
        return True
        
    except Exception as e:
        print(f"❌ Base components failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_factory_standalone():
    """Test factory components in standalone mode."""
    try:
        from trading.state_machines.base.factory import StrategyType, StateMachineFactory
        
        # Test enum
        strategy_type = StrategyType.SIMPLE_ARBITRAGE
        print(f"✅ Created strategy type: {strategy_type.value}")
        
        # Test factory
        factory = StateMachineFactory()
        print(f"✅ Created factory")
        
        # Test getting available strategies (should be empty initially)
        strategies = factory.get_available_strategies()
        print(f"✅ Available strategies: {len(strategies)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Factory test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_mixins_standalone():
    """Test mixin components in standalone mode."""
    try:
        from trading.state_machines.base.mixins import (
            PerformanceMonitoringMixin, RiskManagementMixin
        )
        
        # Test performance mixin
        class TestPerformance(PerformanceMonitoringMixin):
            pass
        
        perf = TestPerformance()
        start = perf._start_performance_timer()
        import time
        time.sleep(0.001)  # 1ms
        duration = perf._end_performance_timer(start)
        print(f"✅ Performance mixin works: {duration:.1f}ms")
        
        # Test risk management mixin
        class TestRisk(RiskManagementMixin):
            pass
        
        risk = TestRisk()
        valid = risk._validate_order_size(None, 1.0, 1000.0)
        print(f"✅ Risk mixin works: order valid = {valid}")
        
        return True
        
    except Exception as e:
        print(f"❌ Mixins test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_mock_arbitrage_context():
    """Test creating arbitrage context with mock data."""
    try:
        # Import strategy context
        from trading.state_machines.arbitrage.simple_arbitrage import SimpleArbitrageContext
        from trading.state_machines.base.protocols import SimpleSymbol, SimpleLogger
        
        # Create mock objects
        symbol = SimpleSymbol("BTC", "USDT")
        logger = SimpleLogger("arbitrage_test")
        
        # Create context with all optional fields
        context = SimpleArbitrageContext(
            strategy_name="simple_arbitrage",
            symbol=symbol,
            logger=logger,
            position_size_usdt=100.0,
            min_profit_threshold=0.005
        )
        
        print(f"✅ Created arbitrage context:")
        print(f"   Strategy: {context.strategy_name}")
        print(f"   Symbol: {context.symbol}")
        print(f"   Position size: ${context.position_size_usdt}")
        print(f"   Min profit: {context.min_profit_threshold*100:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ Mock arbitrage context failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all standalone tests."""
    print("🧪 Standalone State Machine Tests (Protocol-based)")
    print("="*55)
    
    tests = [
        ("Protocol Imports", test_protocol_imports),
        ("Base Components", test_base_components),
        ("Factory Standalone", test_factory_standalone),
        ("Mixins Standalone", test_mixins_standalone),
        ("Mock Arbitrage Context", lambda: asyncio.run(test_mock_arbitrage_context()))
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        try:
            if test_func():
                passed += 1
            else:
                print(f"   Test failed")
        except Exception as e:
            print(f"   Test crashed: {e}")
    
    print("\n" + "="*55)
    print(f"🏁 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All standalone tests passed! State machines work independently!")
        print("\n💡 Next steps:")
        print("   - Add real exchange connections for full functionality")
        print("   - Run integration tests with exchange infrastructure")
        print("   - Test complete strategy execution cycles")
    else:
        print("❌ Some standalone tests failed.")
        print("   Check the errors above for debugging information.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)