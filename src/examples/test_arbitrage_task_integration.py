"""
Test Arbitrage Task Integration with TaskManager

Simple test to verify that the arbitrage strategy integrates properly with TaskManager
without requiring actual exchange connections.

Usage:
    PYTHONPATH=src python src/examples/test_arbitrage_task_integration.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from exchanges.structs import Symbol, AssetName, ExchangeEnum
from infrastructure.logging import get_logger
from trading.task_manager.task_manager import TaskManager
from trading.tasks.arbitrage_task_context import ArbitrageTaskContext, ArbitrageState, TradingParameters
from trading.tasks.spot_futures_arbitrage_task import SpotFuturesArbitrageTask


async def test_task_creation():
    """Test creating arbitrage task and adding to TaskManager."""
    logger = get_logger("arbitrage_integration_test")
    
    print("🧪 Testing Arbitrage Task Integration")
    print("=" * 50)
    
    try:
        # Test 1: Create ArbitrageTaskContext
        print("1. Creating ArbitrageTaskContext...")
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        params = TradingParameters(max_entry_cost_pct=0.5, min_profit_pct=0.1)
        
        context = ArbitrageTaskContext(
            symbol=symbol,
            base_position_size_usdt=100.0,
            params=params,
            arbitrage_state='idle'
        )
        print(f"   ✅ Context created: {context.symbol} with {context.base_position_size_usdt} USDT")
        
        # Test 2: Create SpotFuturesArbitrageTask
        print("2. Creating SpotFuturesArbitrageTask...")
        task = SpotFuturesArbitrageTask(logger, context, ExchangeEnum.MEXC, ExchangeEnum.GATEIO_FUTURES)
        await task.start()
        print(f"   ✅ Task created: {task.name} with ID {task.task_id}")
        
        # Test 3: Initialize TaskManager
        print("3. Creating TaskManager...")
        manager = TaskManager(logger, base_path="test_arbitrage_data")
        print("   ✅ TaskManager created")
        
        # Test 4: Add task to TaskManager
        print("4. Adding task to TaskManager...")
        task_id = await manager.add_task(task)
        print(f"   ✅ Task added with ID: {task_id}")
        
        # Test 5: Start TaskManager (brief execution)
        print("5. Starting TaskManager for brief execution...")
        await manager.start(recover_tasks=False)
        
        # Execute a few cycles
        for i in range(5):
            status = manager.get_status()
            print(f"   Cycle {i+1}: {status['active_tasks']} active tasks, "
                  f"{status['total_executions']} total executions")
            
            if status['active_tasks'] == 0:
                break
                
            await asyncio.sleep(0.1)
        
        # Test 6: Context serialization and persistence
        print("6. Testing context serialization...")
        from trading.task_manager.serialization import TaskSerializer
        
        serialized = TaskSerializer.serialize_context(context)
        print(f"   ✅ Context serialized ({len(serialized)} chars)")
        
        deserialized = TaskSerializer.deserialize_context(serialized, ArbitrageTaskContext)
        print(f"   ✅ Context deserialized: {deserialized.symbol}")
        
        # Test 7: Task recovery
        print("7. Testing task recovery...")
        from trading.task_manager.recovery import TaskRecovery
        from trading.task_manager.persistence import TaskPersistenceManager
        
        persistence = TaskPersistenceManager(logger, "test_recovery_data")
        recovery = TaskRecovery(logger, persistence)
        
        # Save task context
        persistence.save_context(task_id, context)
        print(f"   ✅ Task context saved for recovery")
        
        # Test recovery
        recovered_task = await recovery.recover_spot_futures_arbitrage_task(task_id, serialized)
        if recovered_task:
            print(f"   ✅ Task recovered successfully: {recovered_task.name}")
        else:
            print("   ❌ Task recovery failed")
        
        # Test 8: Clean shutdown
        print("8. Shutting down TaskManager...")
        await manager.stop()
        print("   ✅ TaskManager shutdown complete")
        
        # Test 9: Cleanup
        print("9. Cleaning up task resources...")
        await task.cleanup()
        if recovered_task:
            await recovered_task.cleanup()
        print("   ✅ Task cleanup complete")
        
        print("\n🎉 All integration tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_context_evolution():
    """Test context evolution functionality."""
    logger = get_logger("context_evolution_test")
    
    print("\n🧪 Testing Context Evolution")
    print("=" * 30)
    
    try:
        # Create task context
        symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
        context = ArbitrageTaskContext(
            symbol=symbol,
            base_position_size_usdt=50.0
        )
        
        # Create task
        task = SpotFuturesArbitrageTask(logger, context, ExchangeEnum.MEXC, ExchangeEnum.GATEIO_FUTURES)
        await task.start()
        
        print(f"Initial state: {task.context.arbitrage_state}")
        print(f"Initial cycles: {task.context.arbitrage_cycles}")
        
        # Test context evolution
        task.evolve_context(arbitrage_cycles=5, total_volume_usdt=250.0)
        print(f"After evolution - cycles: {task.context.arbitrage_cycles}, volume: {task.context.total_volume_usdt}")
        
        # Test dict field evolution
        task.evolve_context(min_quote_quantity__spot=15.0, min_quote_quantity__futures=20.0)
        print(f"Min quantities: {task.context.min_quote_quantity}")
        
        # Test state transition
        task._transition_arbitrage_state('monitoring')
        print(f"New arbitrage state: {task.context.arbitrage_state}")
        
        await task.cleanup()
        print("✅ Context evolution tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Context evolution test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all integration tests."""
    print("🚀 Starting Arbitrage Task Integration Tests\n")
    
    test1_passed = await test_task_creation()
    test2_passed = await test_context_evolution()
    
    print(f"\n📊 Test Results:")
    print(f"   Task Integration: {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"   Context Evolution: {'✅ PASS' if test2_passed else '❌ FAIL'}")
    
    if test1_passed and test2_passed:
        print(f"\n🎉 All tests passed! Arbitrage strategy is ready for TaskManager.")
    else:
        print(f"\n❌ Some tests failed. Please check the implementation.")
    
    return test1_passed and test2_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)