#!/usr/bin/env python3
"""
Test State Management in BaseTradingTask

Tests that state and order_id are properly managed in context:
- State transitions update context.state
- Order ID tracking in context.order_id
- Task ID auto-generation in context.task_id
- Context serialization/deserialization
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure immediate logging for dev environment
os.environ['ENVIRONMENT'] = 'dev'

from infrastructure.logging import get_logger
from infrastructure.logging.factory import LoggerFactory
from infrastructure.logging.structs import (
    LoggingConfig, ConsoleBackendConfig, PerformanceConfig, RouterConfig
)

# Set up immediate logging config
LoggerFactory._default_config = LoggingConfig(
    environment="dev",
    console=ConsoleBackendConfig(enabled=True, min_level="DEBUG", color=True),
    performance=PerformanceConfig(buffer_size=100, batch_size=1, dispatch_interval=0.001),
    router=RouterConfig(default_backends=["console"])
)

from config.config_manager import get_exchange_config
from exchanges.structs.common import Symbol, AssetName, Side
from trading.tasks.iceberg_task import IcebergTask, IcebergTaskContext
from trading.struct import TradingStrategyState


async def test_state_management():
    """Test state and order_id management in context."""
    logger = get_logger("state_test")
    logger.info("🧪 Testing state management in trading tasks")
    
    config = get_exchange_config("gateio_spot")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    
    # Test 1: Context initialization
    logger.info("=== Test 1: Context Initialization ===")
    
    context = IcebergTaskContext(
        symbol=symbol,
        side=Side.BUY,
        total_quantity=10.0,
        order_quantity=2.0
    )
    
    task = IcebergTask(config=config, logger=logger, context=context)
    
    # Verify initial state
    assert task.state == TradingStrategyState.NOT_STARTED, f"Expected NOT_STARTED, got {task.state}"
    assert task.context.state == TradingStrategyState.NOT_STARTED, f"Expected NOT_STARTED in context, got {task.context.state}"
    assert task.order_id is None, f"Expected None order_id, got {task.order_id}"
    assert task.task_id != "", f"Expected auto-generated task_id, got empty string"
    
    logger.info("✅ Initial state verified", 
                state=task.state.name, 
                task_id=task.task_id,
                order_id=task.order_id)
    
    # Test 2: State transitions
    logger.info("=== Test 2: State Transitions ===")
    
    await task.start()
    assert task.state == TradingStrategyState.IDLE, f"Expected IDLE after start, got {task.state}"
    assert task.context.state == TradingStrategyState.IDLE, f"Expected IDLE in context, got {task.context.state}"
    
    logger.info("✅ State transition verified", state=task.state.name)
    
    # Test 3: Order ID management
    logger.info("=== Test 3: Order ID Management ===")
    
    # Simulate setting order_id
    task.evolve_context(order_id="test_order_123")
    assert task.order_id == "test_order_123", f"Expected test_order_123, got {task.order_id}"
    assert task.context.order_id == "test_order_123", f"Expected test_order_123 in context, got {task.context.order_id}"
    
    logger.info("✅ Order ID management verified", order_id=task.order_id)
    
    # Test 4: Context serialization
    logger.info("=== Test 4: Context Serialization ===")
    
    # Save context
    saved_data = task.save_context()
    logger.info("Context serialized", data_length=len(saved_data))
    
    # Create new task and restore context
    new_context = IcebergTaskContext(symbol=symbol, side=Side.SELL)  # Dummy initial context
    new_task = IcebergTask(config=config, logger=logger, context=new_context)
    
    # Restore context
    new_task.restore_context(saved_data)
    
    # Verify restored state
    assert new_task.state == task.state, f"Expected {task.state}, got {new_task.state}"
    assert new_task.order_id == task.order_id, f"Expected {task.order_id}, got {new_task.order_id}"
    assert new_task.task_id == task.task_id, f"Expected {task.task_id}, got {new_task.task_id}"
    assert new_task.context.side == task.context.side, f"Expected {task.context.side}, got {new_task.context.side}"
    
    logger.info("✅ Context serialization verified", 
                restored_state=new_task.state.name,
                restored_order_id=new_task.order_id,
                restored_task_id=new_task.task_id)
    
    # Test 5: Context evolution
    logger.info("=== Test 5: Context Evolution ===")
    
    original_task_id = task.task_id
    task.evolve_context(
        state=TradingStrategyState.EXECUTING,
        order_id="new_order_456",
        total_quantity=15.0
    )
    
    assert task.state == TradingStrategyState.EXECUTING, f"Expected EXECUTING, got {task.state}"
    assert task.order_id == "new_order_456", f"Expected new_order_456, got {task.order_id}"
    assert task.context.total_quantity == 15.0, f"Expected 15.0, got {task.context.total_quantity}"
    assert task.task_id == original_task_id, f"Task ID should not change, got {task.task_id}"
    
    logger.info("✅ Context evolution verified", 
                state=task.state.name,
                order_id=task.order_id,
                total_quantity=task.context.total_quantity)
    
    logger.info("🎉 All state management tests passed!")
    
    # Small delay to ensure logging is flushed
    await asyncio.sleep(0.01)


if __name__ == "__main__":
    print("🚀 Starting state management tests...")
    try:
        asyncio.run(test_state_management())
        print("✅ All tests completed successfully!")
    except Exception as e:
        print(f"❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)