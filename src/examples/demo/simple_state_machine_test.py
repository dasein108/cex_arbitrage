"""
Simple test script for state machine creation without full exchange dependencies.

This script tests just the state machine factory and context creation without
requiring the full exchange infrastructure to be available.
"""

import sys
import os
from typing import Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def test_imports():
    """Test that we can import the state machine components."""
    try:
        from trading.state_machines.base import (
            BaseStrategyStateMachine,
            BaseStrategyContext,
            StrategyResult,
            StrategyState,
            StrategyError,
            StateMachineFactory,
            StrategyType,
            state_machine_factory
        )
        print("✅ Base state machine imports successful")
        return True
    except Exception as e:
        print(f"❌ Base imports failed: {e}")
        return False

def test_strategy_imports():
    """Test that we can import strategy implementations."""
    try:
        from trading.state_machines.hedging import (
            SpotFuturesHedgingStateMachine,
            SpotFuturesHedgingContext,
            FuturesFuturesHedgingStateMachine,
            FuturesFuturesHedgingContext
        )
        from trading.state_machines.market_making import (
            MarketMakingStateMachine,
            MarketMakingContext
        )
        from trading.state_machines.arbitrage import (
            SimpleArbitrageStateMachine,
            SimpleArbitrageContext
        )
        print("✅ Strategy imports successful")
        return True
    except Exception as e:
        print(f"❌ Strategy imports failed: {e}")
        return False

def test_context_creation():
    """Test that we can create context objects."""
    try:
        from trading.state_machines.base import BaseStrategyContext, StrategyState
        
        # Create a simple mock symbol and logger
        class MockSymbol:
            def __init__(self, base, quote, is_futures=False):
                self.base = base
                self.quote = quote
                self.is_futures = is_futures
            def __str__(self):
                return f"{self.base}/{self.quote}"
        
        class MockLogger:
            def info(self, message, **kwargs):
                print(f"INFO: {message}")
            def error(self, message, **kwargs):
                print(f"ERROR: {message}")
            def warning(self, message, **kwargs):
                print(f"WARNING: {message}")
        
        symbol = MockSymbol("BTC", "USDT")
        logger = MockLogger()
        
        # Test base context creation
        context = BaseStrategyContext(
            strategy_name="test_strategy",
            symbol=symbol,
            logger=logger
        )
        
        print(f"✅ Base context created: {context.strategy_name}")
        print(f"   Symbol: {context.symbol}")
        print(f"   State: {context.current_state}")
        return True
        
    except Exception as e:
        print(f"❌ Context creation failed: {e}")
        return False

def test_strategy_context_creation():
    """Test creating specific strategy base."""
    try:
        from trading.state_machines.arbitrage import SimpleArbitrageContext
        
        class MockSymbol:
            def __init__(self, base, quote, is_futures=False):
                self.base = base
                self.quote = quote
                self.is_futures = is_futures
            def __str__(self):
                return f"{self.base}/{self.quote}"
        
        class MockLogger:
            def info(self, message, **kwargs):
                pass
        
        symbol = MockSymbol("BTC", "USDT")
        logger = MockLogger()
        
        # Test arbitrage context creation
        context = SimpleArbitrageContext(
            strategy_name="simple_arbitrage",
            symbol=symbol,
            logger=logger,
            position_size_usdt=100.0,
            min_profit_threshold=0.005
        )
        
        print(f"✅ Arbitrage context created successfully")
        print(f"   Position size: ${context.position_size_usdt}")
        print(f"   Min profit: {context.min_profit_threshold*100:.1f}%")
        return True
        
    except Exception as e:
        print(f"❌ Strategy context creation failed: {e}")
        return False

def test_factory_registration():
    """Test that strategies are properly registered with the factory."""
    try:
        from trading.state_machines.base import state_machine_factory
        
        available_strategies = state_machine_factory.get_available_strategies()
        
        print(f"✅ Factory has {len(available_strategies)} strategies registered:")
        for strategy_type in available_strategies:
            print(f"   - {strategy_type.value}")
        
        return len(available_strategies) > 0
        
    except Exception as e:
        print(f"❌ Factory registration test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Testing State Machine Implementation")
    print("="*50)
    
    tests = [
        ("Import Base Components", test_imports),
        ("Import Strategy Components", test_strategy_imports), 
        ("Create Base Context", test_context_creation),
        ("Create Strategy Context", test_strategy_context_creation),
        ("Test Factory Registration", test_factory_registration)
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
    
    print("\n" + "="*50)
    print(f"🏁 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All tests passed! State machines are working correctly.")
        return True
    else:
        print("❌ Some tests failed. Check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)