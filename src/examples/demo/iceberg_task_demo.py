#!/usr/bin/env python3
"""
IcebergTask Demo with TaskManager

Demonstrates iceberg order execution using the TaskManager for external loop management:
- Initialize IcebergTask with context
- Add task to TaskManager for coordinated execution
- Monitor execution progress via TaskManager
- Update parameters during execution
- Demonstrate symbol-based coordination
- Handle cleanup and graceful shutdown

Key features demonstrated:
- TaskManager external loop management
- Symbol-based coordination (same symbol = sequential)
- Partial context update pattern
- Real-time parameter updates during execution
- Task lifecycle management
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
from infrastructure.logging.factory import LoggerFactory
from infrastructure.logging.structs import (
    LoggingConfig, ConsoleBackendConfig, PerformanceConfig, RouterConfig
)

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

from config.config_manager import get_exchange_config
from exchanges.structs.common import Symbol, AssetName, Side
from trading.tasks.iceberg_task import IcebergTask, IcebergTaskContext
from trading.tasks.task_manager import TaskManager


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
            # Configuration
            exchange_name = "gateio_spot"  # Change to desired exchange

            # Get exchange configuration and logging setup
            config = get_exchange_config(exchange_name)

            # Initialize TaskManager
            self.task_manager = TaskManager(self.logger)
            await self.task_manager.start()

            # Define trading symbols
            ada_symbol = Symbol(
                base=AssetName("ADA"),
                quote=AssetName("USDT"),
                is_futures=False
            )

            self.logger.info("Starting IcebergTask demo with TaskManager",
                             exchange=exchange_name,
                             symbols=[f"{ada_symbol.base}/{ada_symbol.quote}"])

            # Demo 1: Create and add IcebergTask to TaskManager
            self.logger.info("=== Demo 1: Create IcebergTask and add to TaskManager ===")

            # Create first task - ADA sell
            ada_task = IcebergTask(
                config=config,
                logger=self.logger,
                task_id="ada_sell_001",
                context=IcebergTaskContext(
                    symbol=ada_symbol,
                    side=Side.BUY,
                    total_quantity=20.0,
                    order_quantity=3.0,
                    offset_ticks=4,
                    tick_tolerance=8
                )
            )

            await ada_task.start()
            task_id = await self.task_manager.add_task(ada_task)

            self.logger.info("ADA IcebergTask created and added to TaskManager",
                             task_id=task_id,
                             symbol=str(ada_symbol))

            start_time = asyncio.get_event_loop().time()
            while self.task_manager.task_count > 0 and self.running:
                # Get TaskManager status
                status = self.task_manager.get_status()
                self.logger.info("TaskManager status",
                                 active_tasks=status['active_tasks'],
                                 total_executions=status['total_executions'],
                                 runtime=f"{status['runtime_seconds']:.1f}s")
                await asyncio.sleep(0.1)


            final_status = self.task_manager.get_status()
            self.logger.info("Final TaskManager status",
                             active_tasks=final_status['active_tasks'],
                             total_executions=final_status['total_executions'])

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
