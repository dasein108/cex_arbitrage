#!/usr/bin/env python3
"""
Balance Sync Demo

Demonstrates how to set up and use the balance synchronization system
for monitoring account balances across multiple exchanges.

This example shows:
1. Creating private exchange instances
2. Setting up balance sync task
3. Registering exchanges with the sync system
4. Running the sync task with TaskManager
5. Monitoring sync performance and statistics
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict

from infrastructure.logging import HFTLoggerFactory
from trading.tasks.balance_sync_task import BalanceSyncTask, BalanceSyncTaskContext
from trading.task_manager.task_manager import TaskManager
from trading.utils.balance_sync_utils import (
    setup_balance_sync_for_exchanges,
    BalanceSyncManager,
    get_balance_sync_stats_summary
)
from exchanges.structs import ExchangeEnum
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from config.config_manager import HftConfig
from exchanges.exchange_factory import get_composite_implementation


async def demo_basic_balance_sync():
    """Basic balance sync demo with manual setup."""
    
    print("🚀 Balance Sync Demo - Basic Setup")
    print("=" * 50)
    
    # Initialize logger
    logger = HFTLoggerFactory.get_logger("balance_sync_demo")
    
    # Initialize configuration
    config_manager = HftConfig()
    
    # Create private exchange instances (using factory)
    private_exchanges: Dict[ExchangeEnum, BasePrivateComposite] = {}
    
    exchange_configs = [
        ExchangeEnum.MEXC,
        ExchangeEnum.GATEIO,
        # Add more exchanges as needed
    ]
    
    print(f"📡 Creating private exchange instances for {len(exchange_configs)} exchanges...")
    
    for exchange_enum in exchange_configs:
        try:
            # Get exchange config
            exchange_config = config_manager.get_exchange_config(exchange_enum.value)
            
            # Create private composite exchange
            private_exchange = get_composite_implementation(
                exchange_config, 
                is_private=True
            )
            
            private_exchanges[exchange_enum] = private_exchange
            print(f"✅ Created private exchange: {exchange_enum.name}")
            
        except Exception as e:
            print(f"❌ Failed to create {exchange_enum.name} private exchange: {e}")
            continue
    
    if not private_exchanges:
        print("❌ No private exchanges created. Check your API credentials in config.")
        return
    
    print(f"\n💾 Setting up balance sync for {len(private_exchanges)} exchanges...")
    
    # Set up balance sync task
    balance_sync_task = await setup_balance_sync_for_exchanges(
        logger=logger,
        private_exchanges=private_exchanges,
        sync_interval_seconds=30.0,  # Sync every 30 seconds for demo
        task_manager=None  # Manual execution for demo
    )
    
    print(f"✅ Balance sync task created: {balance_sync_task.task_id}")
    
    # Start the task
    await balance_sync_task.start()
    
    print(f"\n🔄 Running balance sync for 3 minutes...")
    print("   (Press Ctrl+C to stop early)")
    
    try:
        # Run for 3 minutes with status updates
        start_time = datetime.now()
        cycles = 0
        
        while (datetime.now() - start_time).seconds < 180:  # 3 minutes
            # Execute one cycle
            result = await balance_sync_task.execute_once()
            cycles += 1
            
            # Print status every 5 cycles
            if cycles % 5 == 0:
                stats = balance_sync_task.get_sync_stats()
                print(f"📊 Cycle {cycles}: "
                      f"{stats['successful_syncs']} successful, "
                      f"{stats['failed_syncs']} failed, "
                      f"last: {stats['last_sync_balances_count']} balances")
            
            # Wait for next execution time
            await asyncio.sleep(result.next_delay)
            
            # Stop if task completed
            if not result.should_continue:
                break
    
    except KeyboardInterrupt:
        print("\n⏹️  Balance sync stopped by user")
    
    # Stop the task
    await balance_sync_task.stop()
    
    # Print final statistics
    print(f"\n📈 Final Statistics:")
    print(get_balance_sync_stats_summary(balance_sync_task))


async def demo_task_manager_integration():
    """Demo balance sync with TaskManager integration."""
    
    print("\n🚀 Balance Sync Demo - TaskManager Integration")
    print("=" * 55)
    
    # Initialize components
    logger = HFTLoggerFactory.get_logger("balance_sync_taskmanager_demo")
    config_manager = HftConfig()
    
    # Create TaskManager
    task_manager = TaskManager(logger, base_path="demo_task_data")
    
    # Create BalanceSyncManager for high-level management
    balance_sync_manager = BalanceSyncManager(logger, task_manager)
    
    # Create private exchanges (simplified for demo)
    private_exchanges: Dict[ExchangeEnum, BasePrivateComposite] = {}
    
    exchange_configs = [ExchangeEnum.MEXC]  # Single exchange for demo simplicity
    
    for exchange_enum in exchange_configs:
        try:
            exchange_config = config_manager.get_exchange_config(exchange_enum.value)
            private_exchange = get_composite_implementation(exchange_config, is_private=True)
            private_exchanges[exchange_enum] = private_exchange
            print(f"✅ Created private exchange: {exchange_enum.name}")
        except Exception as e:
            print(f"❌ Failed to create {exchange_enum.name} private exchange: {e}")
    
    if not private_exchanges:
        print("❌ No private exchanges created for TaskManager demo")
        return
    
    # Create balance sync group
    print(f"\n💾 Creating balance sync group with TaskManager...")
    
    task_id = await balance_sync_manager.create_sync_group(
        group_name="demo_group",
        private_exchanges=private_exchanges,
        sync_interval_seconds=20.0  # 20 seconds for demo
    )
    
    print(f"✅ Created balance sync group with task ID: {task_id}")
    
    # Start TaskManager
    print(f"\n🎯 Starting TaskManager execution...")
    await task_manager.start()
    
    try:
        # Run for 2 minutes
        print("🔄 Running TaskManager for 2 minutes...")
        await asyncio.sleep(120)
        
    except KeyboardInterrupt:
        print("\n⏹️  TaskManager stopped by user")
    
    # Stop everything
    await task_manager.stop()
    
    # Print final summary
    print(f"\n📊 TaskManager Summary:")
    print(balance_sync_manager.get_summary())
    
    # Clean up
    await balance_sync_manager.remove_sync_group("demo_group")


async def demo_error_handling():
    """Demo balance sync error handling and recovery."""
    
    print("\n🚀 Balance Sync Demo - Error Handling")
    print("=" * 45)
    
    logger = HFTLoggerFactory.get_logger("balance_sync_error_demo")
    
    # Create a balance sync task with invalid exchange (to trigger errors)
    context = BalanceSyncTaskContext(
        exchange_enums=[ExchangeEnum.MEXC],  # Valid enum but no exchange instance
        sync_interval_seconds=10.0,
        task_id=f"error_demo_{int(datetime.now().timestamp())}"
    )
    
    balance_sync_task = BalanceSyncTask(
        logger=logger,
        context=context,
        private_exchanges={}  # Empty - will cause errors
    )
    
    await balance_sync_task.start()
    
    print("🔄 Running balance sync with intentional errors...")
    
    try:
        # Run a few cycles to see error handling
        for i in range(5):
            result = await balance_sync_task.execute_once()
            
            stats = balance_sync_task.get_sync_stats()
            print(f"Cycle {i+1}: "
                  f"Success: {stats['successful_syncs']}, "
                  f"Failed: {stats['failed_syncs']}, "
                  f"Error: {stats['last_error']}")
            
            await asyncio.sleep(result.next_delay)
            
            if not result.should_continue:
                break
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    await balance_sync_task.stop()
    
    print("✅ Error handling demo completed")


async def main():
    """Run all balance sync demos."""
    
    print("🎯 CEX Arbitrage - Balance Sync System Demo")
    print("=" * 50)
    print("This demo shows the balance synchronization system")
    print("for monitoring account balances across exchanges.\n")
    
    # Check if we should run demos based on available credentials
    try:
        config_manager = HftConfig()
        
        # Check for MEXC credentials
        mexc_config = config_manager.get_exchange_config('mexc_spot')
        has_mexc_creds = mexc_config and hasattr(mexc_config, 'api_key') and mexc_config.api_key
        
        if not has_mexc_creds:
            print("⚠️  No MEXC API credentials found in config.")
            print("   Set MEXC_API_KEY and MEXC_SECRET_KEY environment variables")
            print("   to run the full balance sync demo with real exchanges.\n")
            
            # Run error handling demo only
            await demo_error_handling()
        else:
            print("✅ MEXC credentials found. Running full demos...\n")
            
            # Run all demos
            await demo_basic_balance_sync()
            await demo_task_manager_integration()
            await demo_error_handling()
        
    except Exception as e:
        print(f"❌ Demo initialization failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Set up logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(main())