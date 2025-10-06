#!/usr/bin/env python3
"""
Delta Neutral Task Test Runner

Standalone test runner for delta neutral task state machine tests.
Can be run directly without pytest for quick testing during development.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src and tests to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure test environment
os.environ['ENVIRONMENT'] = 'test'

from infrastructure.logging import get_logger
from infrastructure.logging.factory import LoggerFactory
from infrastructure.logging.structs import (
    LoggingConfig, ConsoleBackendConfig, PerformanceConfig, RouterConfig
)

# Set up test logging
LoggerFactory._default_config = LoggingConfig(
    environment="test",
    console=ConsoleBackendConfig(enabled=True, min_level="INFO", color=True),
    performance=PerformanceConfig(buffer_size=10, batch_size=1, dispatch_interval=0.001),
    router=RouterConfig(default_backends=["console"])
)

from tests.trading.mocks import DualExchangeMockSystem
from tests.trading.helpers import TestDataFactory, ContextGenerator
from trading.tasks.delta_neutral_task import DeltaNeutralTask, DeltaNeutralState
from trading.struct import TradingStrategyState
from exchanges.structs import Side


async def test_basic_state_machine_flow():
    """Test basic state machine flow from start to completion."""
    print("🧪 Testing basic state machine flow...")
    
    logger = get_logger("test_runner")
    test_symbol = TestDataFactory.DEFAULT_SYMBOL
    
    # Setup mock system
    mock_system = DualExchangeMockSystem()
    await mock_system.setup([test_symbol])
    mock_system.patch_exchange_factory()
    
    try:
        # Create fresh context
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            total_quantity=1.0,
            order_quantity=0.1
        )
        
        # Create and start task
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        print(f"✅ Task started in state: {task.state.name}")
        
        # Execute state machine cycles
        max_cycles = 15
        cycle = 0
        
        while cycle < max_cycles and task.context.state not in [
            TradingStrategyState.COMPLETED, 
            TradingStrategyState.ERROR,
            TradingStrategyState.CANCELLED
        ]:
            old_state = task.state
            result = await task.execute_once()
            cycle += 1
            
            print(f"Cycle {cycle}: {old_state.name} → {task.state.name} "
                  f"(continue: {result.should_continue}, time: {result.execution_time_ms:.2f}ms)")
            
            if not result.should_continue:
                break
            
            # Small delay to prevent tight loop
            await asyncio.sleep(0.01)
        
        # Report results
        print(f"\n📊 Test Results:")
        print(f"Final state: {task.state.name}")
        print(f"Cycles executed: {cycle}")
        print(f"Buy filled: {task.context.filled_quantity[Side.BUY]}")
        print(f"Sell filled: {task.context.filled_quantity[Side.SELL]}")
        print(f"Total orders placed: {mock_system.get_total_orders_placed()}")
        
        # Verify exchanges were initialized
        init_status = mock_system.verify_initialization()
        print(f"Exchange initialization: {init_status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await mock_system.teardown()


async def test_arbitrage_scenario():
    """Test profitable arbitrage scenario."""
    print("\n🧪 Testing arbitrage scenario...")
    
    logger = get_logger("test_arbitrage")
    test_symbol = TestDataFactory.DEFAULT_SYMBOL
    
    # Setup mock system
    mock_system = DualExchangeMockSystem()
    await mock_system.setup([test_symbol])
    mock_system.patch_exchange_factory()
    
    try:
        # Setup profitable arbitrage
        mock_system.setup_profitable_arbitrage(test_symbol, 50000.0, 50100.0)
        
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            total_quantity=0.5,
            order_quantity=0.1
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        print(f"✅ Arbitrage task started")
        
        # Execute several cycles
        for cycle in range(10):
            result = await task.execute_once()
            
            if not result.should_continue:
                break
                
            await asyncio.sleep(0.01)
        
        # Check order placement
        buy_orders = mock_system.get_order_history(Side.BUY)
        sell_orders = mock_system.get_order_history(Side.SELL)
        
        print(f"📊 Arbitrage Results:")
        print(f"Buy orders placed: {len(buy_orders)}")
        print(f"Sell orders placed: {len(sell_orders)}")
        print(f"Final state: {task.state.name}")
        
        success = len(buy_orders) > 0 and len(sell_orders) > 0
        print(f"{'✅' if success else '❌'} Order placement: {'SUCCESS' if success else 'FAILED'}")
        
        return success
        
    except Exception as e:
        print(f"❌ Arbitrage test failed: {e}")
        return False
        
    finally:
        await mock_system.teardown()


async def test_imbalance_rebalancing():
    """Test rebalancing when fills are imbalanced."""
    print("\n🧪 Testing imbalance rebalancing...")
    
    logger = get_logger("test_rebalance")
    test_symbol = TestDataFactory.DEFAULT_SYMBOL
    
    # Setup mock system
    mock_system = DualExchangeMockSystem()
    await mock_system.setup([test_symbol])
    mock_system.patch_exchange_factory()
    
    try:
        # Create imbalanced context
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            total_quantity=1.0,
            filled_quantity={Side.BUY: 0.7, Side.SELL: 0.3}  # Imbalanced
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        print(f"✅ Imbalanced task started")
        print(f"Buy filled: {task.context.filled_quantity[Side.BUY]}")
        print(f"Sell filled: {task.context.filled_quantity[Side.SELL]}")
        
        # Execute cycles to trigger rebalancing
        rebalancing_detected = False
        for cycle in range(15):
            old_state = task.state
            result = await task.execute_once()
            
            if task.state == DeltaNeutralState.REBALANCING:
                rebalancing_detected = True
                print(f"🔄 Rebalancing triggered at cycle {cycle + 1}")
            
            if not result.should_continue:
                break
                
            await asyncio.sleep(0.01)
        
        print(f"📊 Rebalancing Results:")
        print(f"Rebalancing detected: {'✅' if rebalancing_detected else '❌'}")
        print(f"Final state: {task.state.name}")
        
        return rebalancing_detected
        
    except Exception as e:
        print(f"❌ Rebalancing test failed: {e}")
        return False
        
    finally:
        await mock_system.teardown()


async def test_performance():
    """Test execution performance."""
    print("\n🧪 Testing execution performance...")
    
    logger = get_logger("test_performance")
    test_symbol = TestDataFactory.DEFAULT_SYMBOL
    
    # Setup mock system
    mock_system = DualExchangeMockSystem()
    await mock_system.setup([test_symbol])
    mock_system.patch_exchange_factory()
    
    try:
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        # Measure execution times
        execution_times = []
        
        for cycle in range(5):
            import time
            start_time = time.time()
            result = await task.execute_once()
            end_time = time.time()
            
            execution_time_ms = (end_time - start_time) * 1000
            execution_times.append(execution_time_ms)
            
            if not result.should_continue:
                break
        
        avg_time = sum(execution_times) / len(execution_times)
        max_time = max(execution_times)
        
        print(f"📊 Performance Results:")
        print(f"Average execution time: {avg_time:.2f}ms")
        print(f"Maximum execution time: {max_time:.2f}ms")
        print(f"HFT compliant (<100ms): {'✅' if max_time < 100 else '❌'}")
        
        return max_time < 100
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False
        
    finally:
        await mock_system.teardown()


async def main():
    """Run all delta neutral task tests."""
    print("🚀 Starting Delta Neutral Task Tests\n")
    
    tests = [
        ("Basic State Machine", test_basic_state_machine_flow),
        ("Arbitrage Scenario", test_arbitrage_scenario),
        ("Imbalance Rebalancing", test_imbalance_rebalancing),
        ("Performance", test_performance),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print('='*50)
        
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print('='*50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\nResults: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed!")
        return 0
    else:
        print("💥 Some tests failed!")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test runner failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)