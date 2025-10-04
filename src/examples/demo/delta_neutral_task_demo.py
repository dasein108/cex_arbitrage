#!/usr/bin/env python3
"""
DeltaNeutralTask Demo with TaskManager - Context-Based Configuration

Demonstrates delta neutral order execution using the new context-based configuration system:
- Initialize DeltaNeutralTask with exchange_names in context (no config parameter)
- Dynamic configuration loading from ExchangeEnum for both BUY and SELL sides
- Delta neutral execution across different exchanges for market neutrality
- Task persistence and recovery capabilities
- Multi-exchange coordination for simultaneous buy/sell execution
- Add tasks to TaskManager for coordinated execution
- Monitor execution progress with enhanced statistics
- Demonstrate persistence cleanup and management

Key features demonstrated:
- Context-based dual exchange configuration (NEW)
- Dynamic config loading for both exchanges from ExchangeEnum (NEW)
- Delta neutral trading strategy with buy/sell coordination (NEW)
- Cross-exchange arbitrage execution pattern (NEW)
- Task persistence and recovery system (NEW)
- Multi-exchange task coordination (NEW)
- TaskManager external loop management
- Symbol-based coordination (same symbol = delta neutral execution)
- Enhanced monitoring with persistence statistics
- Task lifecycle management with automatic persistence
- Proper error handling and logging

Delta Neutral Strategy:
- Simultaneously executes BUY and SELL orders across different exchanges
- Maintains market neutrality while capturing price differences
- Coordinates execution to minimize directional exposure
- Optimized for high-frequency trading with sub-50ms execution targets

Usage:
    PYTHONPATH=src python src/examples/demo/delta_neutral_task_demo.py
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

from exchanges.structs.common import Symbol, AssetName, Side
from exchanges.structs import ExchangeEnum
from trading.tasks.delta_neutral_task import DeltaNeutralTask, DeltaNeutralTaskContext
from trading.task_manager.task_manager import TaskManager


class DeltaNeutralTaskDemo:
    """Demonstration of DeltaNeutralTask execution with TaskManager."""

    def __init__(self):
        self.logger = get_logger("delta_neutral_demo")
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
            # Configuration - Use different exchanges for delta neutral strategy
            buy_exchange = ExchangeEnum.GATEIO    # Exchange for BUY side
            sell_exchange = ExchangeEnum.GATEIO_FUTURES  # Exchange for SELL side

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

                self.logger.info("Starting DeltaNeutralTask demo with TaskManager",
                                 buy_exchange=buy_exchange.value,
                                 sell_exchange=sell_exchange.value,
                                 symbols=[f"{ada_symbol.base}/{ada_symbol.quote}"])

                # Demo 1: Create and add DeltaNeutralTask to TaskManager
                self.logger.info("=== Create DeltaNeutralTask with dual-exchange configuration ===")

                # Create task context with dual exchange configuration
                ada_context = DeltaNeutralTaskContext(
                    symbol=ada_symbol,
                    exchange_names={
                        Side.BUY: buy_exchange,   # MEXC for buying
                        Side.SELL: sell_exchange  # GATEIO for selling
                    },
                    total_quantity=50.0,  # Total delta neutral quantity
                    order_quantity=8.0,   # Size of each execution slice
                    offset_ticks={
                        Side.BUY: 3,     # BUY orders 3 ticks above bid
                        Side.SELL: 4     # SELL orders 4 ticks below ask
                    },
                    tick_tolerance={
                        Side.BUY: 6,     # BUY tolerance: 6 ticks
                        Side.SELL: 8     # SELL tolerance: 8 ticks
                    }
                )

                # Create delta neutral task - coordinates buy/sell across exchanges
                ada_task = DeltaNeutralTask(
                    logger=self.logger,
                    context=ada_context
                )

                await ada_task.start()
                task_id = await self.task_manager.add_task(ada_task)

                self.logger.info("ADA DeltaNeutralTask created and added to TaskManager",
                                 task_id=ada_task.task_id,
                                 symbol=str(ada_symbol),
                                 buy_exchange=buy_exchange.value,
                                 sell_exchange=sell_exchange.value,
                                 strategy="delta_neutral",
                                 total_quantity=ada_context.total_quantity,
                                 order_slice=ada_context.order_quantity)

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
                    
                    # Show individual task status with delta neutral metrics
                    for task_info in status.get('tasks', []):
                        self.logger.debug("Delta neutral task status",
                                          task_id=task_info['task_id'],
                                          symbol=task_info['symbol'],
                                          state=task_info['state'],
                                          next_exec=f"{task_info['next_execution']:.3f}s",
                                          strategy="delta_neutral")
                
                status_count += 1
                await asyncio.sleep(0.1)

            # Demo 5: Final statistics and cleanup demonstration
            self.logger.info("=== Demo 5: Final delta neutral statistics and cleanup ===")
            
            final_status = self.task_manager.get_status()
            self.logger.info("Final TaskManager status",
                             active_tasks=final_status['active_tasks'],
                             total_executions=final_status['total_executions'],
                             runtime=f"{final_status['runtime_seconds']:.1f}s",
                             strategy_completed="delta_neutral")
            
            # Show final persistence statistics
            final_persistence_stats = self.task_manager.get_persistence_stats()
            self.logger.info("Final persistence statistics", stats=final_persistence_stats)
            
            # Demonstrate cleanup functionality
            self.logger.info("Demonstrating persistence cleanup...")
            self.task_manager.cleanup_persistence(max_age_hours=0)  # Clean all for demo
            
            after_cleanup_stats = self.task_manager.get_persistence_stats()
            self.logger.info("Post-cleanup persistence statistics", stats=after_cleanup_stats)

        except Exception as e:
            self.logger.error("Delta neutral demo execution failed", error=str(e))
            await self.logger.flush()
            raise
        finally:
            # Comprehensive cleanup in couple lines
            await self._comprehensive_cleanup()

    async def _comprehensive_cleanup(self):
        """Complete system cleanup - all resources properly closed."""
        from exchanges.dual_exchange import DualExchange
        from infrastructure.logging.hft_logger import HFTLogger
        
        # Stop task manager (cleans up all task resources)
        if self.task_manager:
            await self.task_manager.stop()
        
        # Close all exchange connections (both buy and sell side exchanges)
        await DualExchange.cleanup_all()
        
        # Shutdown all logger background tasks
        await HFTLogger.shutdown_all()


async def main():
    """Main demo entry point."""
    demo = DeltaNeutralTaskDemo()

    try:
        await demo.run_demo()
        demo.logger.info("🎉 DeltaNeutralTask demo with TaskManager completed successfully")
        
        # Small delay to ensure logging is flushed
        await asyncio.sleep(0.01)

    except KeyboardInterrupt:
        demo.logger.info("Delta neutral demo interrupted by user")
        await asyncio.sleep(0.01)  # Ensure log is flushed
    except Exception as e:
        if hasattr(demo, 'logger'):
            demo.logger.error("Delta neutral demo failed", error=str(e))
            await asyncio.sleep(0.01)  # Ensure error log is flushed
        else:
            print(f"Delta neutral demo failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("🚀 Starting DeltaNeutralTask Demo with TaskManager...")
    print("📊 Strategy: Delta neutral execution across MEXC (BUY) and GATEIO (SELL)")
    print("⚡ Target: Sub-50ms execution with market neutrality")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Delta neutral demo terminated by user")
    except Exception as e:
        print(f"\n❌ Delta neutral demo failed: {e}")
        sys.exit(1)