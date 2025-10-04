#!/usr/bin/env python3
"""
IcebergTask Demo with TaskManager - Refactored for Context-Based Configuration

Demonstrates iceberg order execution using the new context-based configuration system:
- Initialize IcebergTask with exchange_name in context (no config parameter)
- Dynamic configuration loading from ExchangeEnum
- Task persistence and recovery capabilities
- Multiple exchange coordination
- Add tasks to TaskManager for coordinated execution
- Monitor execution progress with enhanced statistics
- Demonstrate persistence cleanup and management

Key features demonstrated:
- Context-based exchange configuration (NEW)
- Dynamic config loading from ExchangeEnum (NEW)
- Task persistence and recovery system (NEW)
- Multiple exchange task coordination (NEW)
- TaskManager external loop management
- Symbol-based coordination (same symbol = sequential)
- Enhanced monitoring with persistence statistics
- Task lifecycle management with automatic persistence
- Proper error handling and logging

Usage:
    PYTHONPATH=src python src/examples/demo/iceberg_task_demo.py
"""

import asyncio
from typing import Optional
import signal
import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure immediate logging for dev environment
os.environ['ENVIRONMENT'] = 'dev'

from infrastructure.logging import get_logger

# # Set up immediate logging config
# immediate_config = LoggingConfig(
#     environment="dev",
#     console=ConsoleBackendConfig(
#         enabled=True,
#         min_level="DEBUG",
#         color=True,
#         include_context=True
#     ),
#     performance=PerformanceConfig(
#         buffer_size=100,         # Small buffer for immediate processing
#         batch_size=1,            # Process every message immediately
#         dispatch_interval=0.001  # Very fast dispatch
#     ),
#     router=RouterConfig(
#         default_backends=["console"]
#     )
# )
#
# # Override factory config for immediate logging
# LoggerFactory._default_config = immediate_config

from exchanges.structs.common import Symbol, AssetName, Side
from exchanges.structs import ExchangeEnum
from trading.tasks.iceberg_task import IcebergTask, IcebergTaskContext
from trading.task_manager.task_manager import TaskManager


class IcebergTaskDemo:
    """Demonstration of IcebergTask execution with TaskManager."""

    def __init__(self):
        self.logger = get_logger("iceberg_demo")
        self.task_manager: Optional[TaskManager] = None
        self.running = True

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    async def run_demo(self):
        """Main demo execution."""
        try:
            # Configuration - Use ExchangeEnum instead of string
            exchange_name = ExchangeEnum.GATEIO  # Change to desired exchange

            # Initialize TaskManager with persistence support
            self.task_manager = TaskManager(self.logger, "task_data")
            await self.task_manager.start(recover_tasks=True)  # Enable task recovery
            if self.task_manager.task_count == 0:
                # Define trading symbols
                ada_symbol = Symbol(
                    base=AssetName("ADA"),
                    quote=AssetName("USDT"),
                    is_futures=False
                )

                self.logger.info("Starting IcebergTask demo with TaskManager",
                                 exchange=exchange_name.value,
                                 symbols=[f"{ada_symbol.base}/{ada_symbol.quote}"])

                # Demo 1: Create and add IcebergTask to TaskManager
                self.logger.info("=== Create IcebergTask with context-based configuration ===")

                # Create task context with exchange_name (no config parameter needed)
                ada_context = IcebergTaskContext(
                    symbol=ada_symbol,
                    exchange_name=exchange_name,  # Exchange info now in context
                    side=Side.SELL,
                    total_quantity=20.0,
                    order_quantity=3.0,
                    offset_ticks=4,
                    tick_tolerance=8
                )

                # Create first task - ADA buy (config loaded automatically from exchange_name)
                ada_task = IcebergTask(
                    logger=self.logger,
                    context=ada_context
                )

                await ada_task.start()
                task_id = await self.task_manager.add_task(ada_task)

                self.logger.info("ADA IcebergTask created and added to TaskManager",
                                 task_id=ada_task.task_id,
                                 symbol=str(ada_symbol),
                                 exchange=ada_task.config.name,
                                 config_loaded_from=ada_context.exchange_name)

            # Show persistence statistics
            persistence_stats = self.task_manager.get_persistence_stats()
            self.logger.info("Task persistence statistics", stats=persistence_stats)

            start_time = asyncio.get_event_loop().time()
            status_count = 0
            
            while self.task_manager.task_count > 0 and self.running:
                # Get enhanced TaskManager status
                status = self.task_manager.get_status()
                
                # Log status every 100 iterations (reduce noise)
                if status_count % 100 == 0:
                    self.logger.info("TaskManager status",
                                     active_tasks=status['active_tasks'],
                                     total_executions=status['total_executions'],
                                     runtime=f"{status['runtime_seconds']:.1f}s",
                                     persistence_stats=status.get('persistence_stats', {}))
                    
                    # Show individual task status
                    for task_info in status.get('tasks', []):
                        self.logger.debug("Task status",
                                          task_id=task_info['task_id'],
                                          symbol=task_info['symbol'],
                                          state=task_info['state'],
                                          next_exec=f"{task_info['next_execution']:.3f}s")
                
                status_count += 1
                await asyncio.sleep(0.1)

            # Demo 5: Final statistics and cleanup demonstration
            self.logger.info("=== Demo 5: Final statistics and cleanup ===")
            
            final_status = self.task_manager.get_status()
            self.logger.info("Final TaskManager status",
                             active_tasks=final_status['active_tasks'],
                             total_executions=final_status['total_executions'],
                             runtime=f"{final_status['runtime_seconds']:.1f}s")
            
            # Show final persistence statistics
            final_persistence_stats = self.task_manager.get_persistence_stats()
            self.logger.info("Final persistence statistics", stats=final_persistence_stats)
            
            # Demonstrate cleanup functionality
            self.logger.info("Demonstrating persistence cleanup...")
            self.task_manager.cleanup_persistence(max_age_hours=0)  # Clean all for demo
            
            after_cleanup_stats = self.task_manager.get_persistence_stats()
            self.logger.info("Post-cleanup persistence statistics", stats=after_cleanup_stats)

        except Exception as e:
            self.logger.error("Demo execution failed", error=str(e))
            await self.logger.flush()
            raise
        finally:
            # Ensure cleanup
            await self.task_manager.stop()


async def main():
    """Main demo entry point."""
    demo = IcebergTaskDemo()

    try:
        await demo.run_demo()
        demo.logger.info("🎉 IcebergTask demo with TaskManager completed successfully")
        
        # Small delay to ensure logging is flushed
        await asyncio.sleep(0.01)

    except KeyboardInterrupt:
        demo.logger.info("Demo interrupted by user")
        await asyncio.sleep(0.01)  # Ensure log is flushed
    except Exception as e:
        if hasattr(demo, 'logger'):
            demo.logger.error("Demo failed", error=str(e))
            await asyncio.sleep(0.01)  # Ensure error log is flushed
        else:
            print(f"Demo failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("🚀 Starting IcebergTask Demo with TaskManager...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Demo terminated by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1)
