"""
Spot-Futures Arbitrage Strategy Demo

Demonstrates cross-exchange spot-futures arbitrage using the integrated analyzer signal logic.
Features z-score based entry/exit signals_v2 with basis spread analysis and rolling statistics.

Examples:
- MEXC spot vs Gate.io futures (cross-exchange)
- Gate.io spot vs Gate.io futures (same-exchange)

Usage:
    PYTHONPATH=src python src/examples/demo/spot_futures_arbitrage_demo.py
"""

import asyncio
import sys
import signal
from pathlib import Path

from config import get_exchange_config

# Add src to path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from typing import Optional, Tuple
from exchanges.structs import Symbol, AssetName, ExchangeEnum
from infrastructure.logging import get_logger
from trading.strategies.strategy_manager.strategy_task_manager import StrategyTaskManager
from trading.strategies.implementations.inventory_spot_strategy.inventory_spot_strategy_task import create_inventory_spread_strategy_task


from exchanges.exchange_factory import create_rest_client


async def run_spot_futures_arbitrage_demo():
    """Run spot-futures arbitrage strategy demo with analyzer signal integration."""
    logger = get_logger("spot_futures_arbitrage_demo")
    
    # Initialize StrategyTaskManager
    manager = StrategyTaskManager(logger)
    await manager.initialize()
    
    # Set up graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🔄 Starting StrategyTaskManager for spot-futures arbitrage...")

    async def get_base_qty(symbol: Symbol, total_usdt: float, order_usdt: float) -> Tuple[float, float]:
        mexc_exchange = create_rest_client(
            get_exchange_config(ExchangeEnum.MEXC.value),
            is_private=False
        )

        ticker_info = await mexc_exchange.get_ticker_info(symbol)
        current_price = ticker_info[symbol].last_price

        total_qty = total_usdt / current_price
        order_usdt = order_usdt / current_price

        return total_qty, order_usdt

    try:
        await manager.start(recover_tasks=True)

        if manager.task_count > 0:
            logger.info(f"♻️ Recovered {manager.task_count} spot-futures arbitrage tasks")
        else:
            logger.info("🚀 Creating new spot-futures arbitrage tasks...")

            async def add_inventory_spot_task(symbol: Symbol):
                """Add cross-exchange spot-futures arbitrage task."""
                logger.info(f"📈 Creating MAKER LIMIT MEXC spot vs Gate.io futures task for {symbol}")

                # Size positions in USDT terms
                total_qty, order_qty = await get_base_qty(symbol, 5,5)
                # Create cross-exchange arbitrage task
                task = create_inventory_spread_strategy_task(
                    symbol=symbol,
                    order_qty=order_qty,
                    total_qty=total_qty,
                )

                # Add to manager
                task_id = await manager.add_task(task)
                logger.info(f"✅ Created {task.tag} for {symbol}")

            await add_inventory_spot_task(Symbol(base=AssetName("U"), quote=AssetName("USDT")))
            # Add same-exchange task for comparison
            # await add_same_exchange_task(Symbol(base=AssetName("BTC"), quote=AssetName("USDT")))

        # Monitor execution
        logger.info("📊 Spot-futures arbitrage strategies active, monitoring execution...")
        monitor_count = 0
        while not shutdown_event.is_set():
            # Status monitoring every 60 seconds
            if monitor_count % 3000 == 0:  # 600 * 0.1s = 60s
                task_count = manager.task_count
                logger.info("📈 Spot-Futures Arbitrage Monitor",
                           active_tasks=task_count,
                           strategy_type="Z-score based signal generation",
                           analyzer_integration="✅ Complete")
                
                if task_count == 0:
                    logger.info("✅ All spot-futures arbitrage tasks completed")
                    break
            
            monitor_count += 1
            await asyncio.sleep(0.1)
        
        logger.info("🔄 Shutting down spot-futures arbitrage demo...")
        
    except Exception as e:
        logger.error(f"❌ Spot-futures arbitrage demo failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean shutdown
        await manager.stop()
        logger.info("✅ StrategyTaskManager shutdown complete")


async def main():
    """Main demo execution with comprehensive error handling."""
    try:
        await run_spot_futures_arbitrage_demo()
    except KeyboardInterrupt:
        print("\n🛑 Spot-futures arbitrage demo interrupted by user")
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure clean shutdown of all resources
        from exchanges.dual_exchange import DualExchange
        from infrastructure.logging.hft_logger import HFTLogger
        
        # Close all exchange connections
        try:
            await DualExchange.cleanup_all()
        except:
            pass
        
        # Shutdown all logger background tasks
        try:
            await HFTLogger.shutdown_all()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())