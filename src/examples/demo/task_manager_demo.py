#!/usr/bin/env python3
"""Demo script for TaskManager with external loop management.

Demonstrates how to use the TaskManager to orchestrate multiple trading tasks
with symbol-based coordination and different execution modes.
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
from trading.struct import TradingStrategyState


class TaskManagerDemo:
    """Demonstration of TaskManager with multiple trading tasks."""
    
    def __init__(self):
        self.logger = get_logger("task_manager_demo")
        self.task_manager = None
        self._running = True
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info("Shutdown signal received, stopping...")
        self._running = False
    
    async def create_iceberg_task(self, 
                                 config,
                                 symbol: Symbol,
                                 side: Side,
                                 total_qty: float,
                                 slice_qty: float) -> IcebergTask:
        """Create and configure an iceberg task.
        
        Args:
            config: Exchange configuration
            symbol: Trading symbol
            side: Buy or sell
            total_qty: Total quantity to execute
            slice_qty: Size of each order slice
            
        Returns:
            Configured IcebergTask
        """
        # Create context with all parameters
        context = IcebergTaskContext(
            symbol=symbol,
            side=side,
            total_quantity=total_qty,
            order_quantity=slice_qty,
            offset_ticks=2,
            tick_tolerance=3
        )
        
        # Create task with context
        task = IcebergTask(
            config=config,
            logger=self.logger,
            context=context
        )
        
        # Initialize task (connects to exchange)
        await task.start()
        
        return task
    
    async def demo_parallel_execution(self):
        """Demo: Multiple tasks on different symbols execute in parallel."""
        self.logger.info("\n" + "="*60)
        self.logger.info("DEMO 1: Parallel Execution (Different Symbols)")
        self.logger.info("="*60)
        
        config = get_exchange_config("gateio_futures")
        
        # Create tasks for different symbols
        btc_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=True)
        eth_symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"), is_futures=True)
        ada_symbol = Symbol(base=AssetName("ADA"), quote=AssetName("USDT"), is_futures=True)
        
        # Create iceberg tasks
        btc_task = await self.create_iceberg_task(
            config, btc_symbol, Side.SELL, 
            total_qty=1.0, slice_qty=0.1
        )
        
        eth_task = await self.create_iceberg_task(
            config, eth_symbol, Side.BUY,
            total_qty=10.0, slice_qty=1.0
        )
        
        ada_task = await self.create_iceberg_task(
            config, ada_symbol, Side.SELL,
            total_qty=1000.0, slice_qty=100.0
        )
        
        # Add tasks to manager (TaskManager handles execution automatically)
        btc_id = await self.task_manager.add_task(btc_task)
        eth_id = await self.task_manager.add_task(eth_task)  
        ada_id = await self.task_manager.add_task(ada_task)
        
        self.logger.info(f"Registered 3 parallel tasks: {btc_id}, {eth_id}, {ada_id}")
        self.logger.info("These will execute concurrently as they're on different symbols")
        
        # Let them run for a bit
        await asyncio.sleep(5)
        
        # Show progress
        for task_id, task in [("btc_sell", btc_task), ("eth_buy", eth_task), ("ada_sell", ada_task)]:
            if hasattr(task, 'get_progress'):
                progress = await task.get_progress()
                self.logger.info(f"{task_id}: {progress['progress_percent']:.1f}% complete")
    
    async def demo_sequential_execution(self):
        """Demo: Multiple tasks on same symbol execute sequentially."""
        self.logger.info("\n" + "="*60)
        self.logger.info("DEMO 2: Sequential Execution (Same Symbol)")
        self.logger.info("="*60)
        
        config = get_exchange_config("gateio_futures")
        
        # Create multiple tasks for the SAME symbol
        btc_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=True)
        
        # Task 1: Buy side iceberg
        buy_task = await self.create_iceberg_task(
            config, btc_symbol, Side.BUY,
            total_qty=2.0, slice_qty=0.2
        )
        
        # Task 2: Sell side iceberg (same symbol)
        sell_task = await self.create_iceberg_task(
            config, btc_symbol, Side.SELL,
            total_qty=1.5, slice_qty=0.15
        )
        
        # Add tasks to manager (sequential execution on same symbol is automatic)
        buy_id = await self.task_manager.add_task(buy_task)
        sell_id = await self.task_manager.add_task(sell_task)
        
        self.logger.info(f"Registered 2 sequential tasks on BTC: {buy_id}, {sell_id}")
        self.logger.info("Buy task (priority=10) will execute before sell task (priority=5)")
        
        await asyncio.sleep(5)
        
        # Show which one is executing
        buy_info = buy_task.get_execution_info()
        sell_info = sell_task.get_execution_info()
        
        self.logger.info(f"Buy task state: {buy_info['state']}")
        self.logger.info(f"Sell task state: {sell_info['state']}")
    
    async def demo_dynamic_management(self):
        """Demo: Dynamic task registration and removal."""
        self.logger.info("\n" + "="*60)
        self.logger.info("DEMO 3: Dynamic Task Management")
        self.logger.info("="*60)
        
        config = get_exchange_config("gateio_futures")
        
        # Start with one task
        eth_symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"), is_futures=True)
        task1 = await self.create_iceberg_task(
            config, eth_symbol, Side.BUY,
            total_qty=5.0, slice_qty=0.5
        )
        
        task1_id = await self.task_manager.add_task(task1)
        self.logger.info(f"Started with task: {task1_id}")
        
        await asyncio.sleep(2)
        
        # Add another task while first is running
        task2 = await self.create_iceberg_task(
            config, eth_symbol, Side.SELL,
            total_qty=3.0, slice_qty=0.3
        )
        
        task2_id = await self.task_manager.add_task(task2)
        self.logger.info(f"Added new task while running: {task2_id}")
        
        await asyncio.sleep(3)
        
        # Remove first task
        removed = await self.task_manager.remove_task(task1_id)
        self.logger.info(f"Removed task {task1_id}: {removed}")
        
        # Show remaining tasks
        status = self.task_manager.get_status()
        self.logger.info(f"Active tasks after removal: {status['active_tasks']}")
    
    async def show_metrics(self):
        """Display task manager metrics."""
        metrics = self.task_manager.get_metrics()
        
        self.logger.info("\n" + "="*60)
        self.logger.info("TASK MANAGER METRICS")
        self.logger.info("="*60)
        self.logger.info(f"Active tasks: {metrics['active_tasks']}")
        self.logger.info(f"Total executions: {metrics['total_executions']}")
        self.logger.info(f"Executions/second: {metrics['executions_per_second']:.2f}")
        
        if metrics['tasks']:
            self.logger.info("\nPer-task metrics:")
            for task_metric in metrics['tasks']:
                self.logger.info(f"  {task_metric['task_id']}: "
                               f"{task_metric['executions']} execs, "
                               f"avg {task_metric['avg_time_ms']:.2f}ms, "
                               f"state={task_metric['state']}")
    
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
            self.logger.info("TASK MANAGER DEMO - External Loop Management")
            self.logger.info("="*60)
            
            # Run demonstrations
            await self.demo_parallel_execution()
            await asyncio.sleep(2)
            
            await self.demo_sequential_execution()
            await asyncio.sleep(2)
            
            await self.demo_dynamic_management()
            
            # Show final metrics
            await self.show_metrics()
            
            # Monitor for a bit
            self.logger.info("\nMonitoring tasks... Press Ctrl+C to stop")
            
            monitor_interval = 5
            while self._running:
                await asyncio.sleep(monitor_interval)
                
                # Show periodic status
                status = self.task_manager.get_status()
                self.logger.info(f"Status: {status['active_tasks']} active, "
                               f"{status['total_executions']} total executions")
                
                # Show tasks by state
                if status['tasks_by_state']:
                    self.logger.info(f"Tasks by state: {status['tasks_by_state']}")
            
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
    demo = TaskManagerDemo()
    await demo.run()


if __name__ == "__main__":
    # Setup logging
    logging_config = get_logging_config()
    
    # Run demo
    asyncio.run(main())