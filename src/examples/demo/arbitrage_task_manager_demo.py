"""
Arbitrage Strategy with TaskManager Integration Demo

Demonstrates MEXC + Gate.io arbitrage strategy running under TaskManager
with full persistence, recovery, and lifecycle management.

Usage:
    PYTHONPATH=src python src/examples/demo/arbitrage_task_manager_demo.py
"""

import asyncio
import sys
import signal
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from exchanges.structs import Symbol, AssetName, ExchangeEnum
from infrastructure.logging import get_logger
from trading.task_manager.task_manager import TaskManager
from trading.tasks.spot_futures_arbitrage_task import create_spot_futures_arbitrage_task


async def run_arbitrage_demo():
    """Run arbitrage strategy under TaskManager with persistence."""
    logger = get_logger("arbitrage_task_demo")
    
    # Initialize TaskManager with persistence
    manager = TaskManager(logger, base_path="task_data")
    
    # Set up graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Create arbitrage task
        symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
        
        logger.info(f"🚀 Creating spot + futures arbitrage task for {symbol}")
        
        arbitrage_task = await create_spot_futures_arbitrage_task(
            symbol=symbol,
            spot_exchange=ExchangeEnum.MEXC,
            futures_exchange=ExchangeEnum.GATEIO_FUTURES,
            base_position_size_usdt=5,
            max_entry_cost_pct=0.3, #0.5,
            min_profit_pct=0.5, #0.1,
            max_hours=6.0,
            logger=logger
        )
        
        # Add task to TaskManager
        task_id = await manager.add_task(arbitrage_task)
        logger.info(f"✅ Added arbitrage task to TaskManager: {task_id}")
        
        # Start TaskManager with recovery enabled
        logger.info("🔄 Starting TaskManager with recovery enabled...")
        await manager.start(recover_tasks=True)
        
        # Monitor TaskManager
        logger.info("📊 TaskManager started, monitoring execution...")
        monitor_count = 0
        
        while not shutdown_event.is_set():
            # Check TaskManager status
            status = manager.get_status()
            
            # Log status every 30 seconds
            if monitor_count % 300 == 0:  # 300 * 0.1s = 30s
                logger.info("📈 TaskManager Status",
                           running=status['running'],
                           active_tasks=status['active_tasks'],
                           total_executions=status['total_executions'],
                           runtime_seconds=status['runtime_seconds'])
                
                # Log individual task status
                for task_info in status['tasks']:
                    logger.info(f"📋 Task {task_info['task_id'][:12]}...",
                               state=task_info['state'],
                               next_execution=f"{task_info['next_execution']:.1f}s",
                               symbol=task_info['symbol'])
            
            monitor_count += 1
            
            # Break if no active tasks
            if status['active_tasks'] == 0:
                logger.info("✅ All tasks completed, shutting down")
                break
            
            await asyncio.sleep(0.1)
        
        logger.info("🔄 Shutting down TaskManager...")
        
    except Exception as e:
        logger.error(f"❌ Demo execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean shutdown
        await manager.stop()
        logger.info("✅ TaskManager shutdown complete")


async def recovery_demo():
    """Demonstrate task recovery capabilities."""
    logger = get_logger("arbitrage_recovery_demo")
    
    # Initialize TaskManager
    manager = TaskManager(logger, base_path="task_data")
    
    try:
        logger.info("🔄 Testing task recovery capabilities...")
        
        # Start with recovery enabled
        await manager.start(recover_tasks=True)
        
        # Get recovery statistics
        status = manager.get_status()
        persistence_stats = status['persistence_stats']
        
        logger.info("📊 Recovery Statistics",
                   active_tasks=persistence_stats['active'],
                   completed_tasks=persistence_stats['completed'],
                   errored_tasks=persistence_stats['errored'])
        
        # If tasks were recovered, monitor them
        if status['active_tasks'] > 0:
            logger.info(f"✅ Recovered {status['active_tasks']} arbitrage tasks")
            
            # Monitor recovered tasks
            for i in range(100):  # Monitor for 10 seconds
                status = manager.get_status()
                if status['active_tasks'] == 0:
                    break
                await asyncio.sleep(0.1)
        else:
            logger.info("ℹ️ No tasks to recover")
        
        # Clean up old completed tasks
        logger.info("🧹 Cleaning up old completed tasks...")
        manager.cleanup_persistence(max_age_hours=1)
        
    except Exception as e:
        logger.error(f"❌ Recovery demo failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await manager.stop()

        from exchanges.dual_exchange import DualExchange
        from infrastructure.logging.hft_logger import HFTLogger

        # Close all exchange connections
        await DualExchange.cleanup_all()

        # Shutdown all logger background tasks
        await HFTLogger.shutdown_all()
        logger.info("✅ Recovery demo complete")


async def main():
    """Main demo execution."""
    import os
    
    # Check demo mode from environment

    await run_arbitrage_demo()




if __name__ == "__main__":
    print("🚀 Starting Arbitrage TaskManager Integration Demo")
    print("💡 Set DEMO_MODE environment variable:")
    print("   - arbitrage: Run single arbitrage task (default)")
    print("   - recovery: Test task recovery capabilities")  
    print("   - stress: Run multiple concurrent arbitrage tasks")
    print("📋 Use Ctrl+C for graceful shutdown\n")
    
    asyncio.run(main())