#!/usr/bin/env python3
"""Simple demo script for TaskManager with external loop management.

Shows the simplified TaskManager API without complex wrappers or execution modes.
"""

import asyncio
import signal
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config_manager import get_exchange_config
from config.logging.config import get_logger, get_logging_config
from exchanges.structs.common import Symbol, AssetName, Side
from trading.tasks.iceberg_task import IcebergTask, IcebergTaskContext
from trading.tasks.task_manager import TaskManager


class SimpleTaskManagerDemo:
    """Simple demonstration of TaskManager."""
    
    def __init__(self):
        self.logger = get_logger("simple_task_demo")
        self.task_manager = None
        self._running = True
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info("Shutdown signal received, stopping...")
        self._running = False
    
    async def run(self):
        """Main demo execution."""
        try:
            # Setup signal handlers
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
            
            # Initialize task manager
            self.task_manager = TaskManager(self.logger)
            await self.task_manager.start()
            
            self.logger.info("\n" + "="*60)
            self.logger.info("SIMPLE TASK MANAGER DEMO")
            self.logger.info("="*60)
            
            # Get exchange config
            config = get_exchange_config("gateio_futures")
            
            # Create symbols
            btc_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=True)
            eth_symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"), is_futures=True)
            
            # Demo 1: Create and add tasks
            self.logger.info("\n=== Creating Tasks ===")
            
            # Task 1: BTC Sell
            btc_task = IcebergTask(
                config=config,
                logger=self.logger,
                context=IcebergTaskContext(
                    symbol=btc_symbol,
                    side=Side.SELL,
                    total_quantity=1.0,
                    order_quantity=0.1,
                    offset_ticks=2
                )
            )
            await btc_task.start()
            
            # Task 2: ETH Buy  
            eth_task = IcebergTask(
                config=config,
                logger=self.logger,
                context=IcebergTaskContext(
                    symbol=eth_symbol,
                    side=Side.BUY,
                    total_quantity=10.0,
                    order_quantity=1.0,
                    offset_ticks=1
                )
            )
            await eth_task.start()
            
            # Task 3: Another BTC task (will execute sequentially with first BTC task)
            btc_task2 = IcebergTask(
                config=config,
                logger=self.logger,
                context=IcebergTaskContext(
                    symbol=btc_symbol,
                    side=Side.BUY,
                    total_quantity=0.5,
                    order_quantity=0.05,
                    offset_ticks=3
                )
            )
            await btc_task2.start()
            
            # Add all tasks to manager
            await self.task_manager.add_task(btc_task)
            await self.task_manager.add_task(eth_task)
            await self.task_manager.add_task(btc_task2)
            
            self.logger.info(f"Added 3 tasks to manager")
            self.logger.info("Note: BTC tasks will execute sequentially (same symbol)")
            self.logger.info("      ETH task will execute in parallel (different symbol)")
            
            # Let them run for a bit
            await asyncio.sleep(5)
            
            # Show status
            status = self.task_manager.get_status()
            self.logger.info(f"\n=== Status after 5 seconds ===")
            self.logger.info(f"Active tasks: {status['active_tasks']}")
            self.logger.info(f"Total executions: {status['total_executions']}")
            
            for task_info in status['tasks']:
                self.logger.info(f"  {task_info['task_id']}: state={task_info['state']}, "
                               f"next in {task_info['next_execution']:.2f}s")
            
            # Demo 2: Dynamic task management
            self.logger.info(f"\n=== Dynamic Management ===")
            
            # Add another task while running
            ada_symbol = Symbol(base=AssetName("ADA"), quote=AssetName("USDT"), is_futures=True)
            ada_task = IcebergTask(
                config=config,
                logger=self.logger,
                context=IcebergTaskContext(
                    symbol=ada_symbol,
                    side=Side.SELL,
                    total_quantity=1000.0,
                    order_quantity=100.0
                )
            )
            await ada_task.start()
            await self.task_manager.add_task(ada_task)
            
            self.logger.info("Added ADA task while others are running")
            
            await asyncio.sleep(3)
            
            # Remove a specific task
            removed = await self.task_manager.remove_task("eth_buy_001")
            self.logger.info(f"Removed ETH task: {removed}")
            
            # Final status
            await asyncio.sleep(2)
            final_status = self.task_manager.get_status()
            self.logger.info(f"\n=== Final Status ===")
            self.logger.info(f"Active tasks: {final_status['active_tasks']}")
            self.logger.info(f"Total executions: {final_status['total_executions']}")
            self.logger.info(f"Runtime: {final_status['runtime_seconds']:.1f}s")
            
            # Monitor until stopped
            self.logger.info("\nMonitoring... Press Ctrl+C to stop")
            
            while self._running:
                await asyncio.sleep(5)
                
                status = self.task_manager.get_status()
                if status['active_tasks'] > 0:
                    self.logger.info(f"Running: {status['active_tasks']} tasks, "
                                   f"{status['total_executions']} total executions")
                else:
                    self.logger.info("All tasks completed")
                    break
            
        except Exception as e:
            self.logger.error(f"Demo error: {e}", exc_info=True)
        
        finally:
            # Cleanup
            if self.task_manager:
                self.logger.info("Stopping task manager...")
                await self.task_manager.stop()
                self.logger.info("Task manager stopped")


async def main():
    """Main entry point."""
    demo = SimpleTaskManagerDemo()
    await demo.run()


if __name__ == "__main__":
    # Setup logging
    logging_config = get_logging_config()
    
    # Run demo
    asyncio.run(main())