"""
Cross Exchange Arbitrage Strategy Demo

Demonstrates F/USDT arbitrage strategy across MEXC (source), Gate.io spot (dest), 
and Gate.io futures (hedge) using StrategyTaskManager for lifecycle management.

Usage:
    PYTHONPATH=src python src/examples/demo/cross_exchange_arbitrage_demo.py
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
from typing import Dict
from exchanges.structs import Symbol, AssetName, ExchangeEnum
from infrastructure.logging import get_logger
from trading.strategies.strategy_manager.strategy_task_manager import StrategyTaskManager
from trading.strategies.implementations import (
    CrossExchangeArbitrageTask,
    CrossExchangeArbitrageTaskContext,
    ExchangeData,
    ExchangeRoleType
)
from trading.analysis.cross_arbitrage_ta import CrossArbitrageSignalConfig
from exchanges.exchange_factory import create_rest_client

async def create_cross_exchange_arbitrage_task(
    symbol: Symbol,
    logger,
    total_quantity: float = 10.0,
    order_qty: float = 2.0
) -> CrossExchangeArbitrageTask:
    """Create a configured CrossExchangeArbitrageTask for F/USDT arbitrage.
    
    Args:
        symbol: Trading symbol (F/USDT)
        logger: HFT logger instance
        total_quantity: Total quantity to trade
        order_qty: Order size for limit orders
        
    Returns:
        Configured CrossExchangeArbitrageTask
    """
    
    # Configure exchange settings for arbitrage strategy
    settings: Dict[ExchangeRoleType,ExchangeData] = {
        'source': ExchangeData(
            exchange=ExchangeEnum.MEXC,
            tick_tolerance=3,
            ticks_offset=1,
            use_market=True
        ),
        'dest': ExchangeData(
            exchange=ExchangeEnum.GATEIO,  # Gate.io spot
            tick_tolerance=3,
            ticks_offset=1,
            use_market=True
        ),
        'hedge': ExchangeData(
            exchange=ExchangeEnum.GATEIO_FUTURES,  # Gate.io futures
            tick_tolerance=2,
            ticks_offset=0,
            use_market=True  # Use market orders for hedging
        )
    }
    
    # Create CrossExchangeArbitrageTaskContext
    context = CrossExchangeArbitrageTaskContext(
        symbol=symbol,
        total_quantity=total_quantity,
        order_qty=order_qty,
        settings=settings,
        # Dynamic threshold configuration for TA module
        signal_config=CrossArbitrageSignalConfig(
            lookback_hours=24,
            refresh_minutes=15,
            entry_percentile=10,
            exit_percentile=85,
            total_fees=0.2
        )
    )
    
    # Create and return the arbitrage task
    task = CrossExchangeArbitrageTask(
        logger=logger,
        context=context
    )
    
    logger.info("✅ Created Cross Exchange Arbitrage Task",
               symbol=str(symbol),
               total_quantity=total_quantity,
               order_qty=order_qty,
               source_exchange="MEXC",
               dest_exchange="GATEIO",
               hedge_exchange="GATEIO_FUTURES")
    
    return task


async def run_cross_exchange_arbitrage_demo():
    """Run cross exchange arbitrage strategy under StrategyTaskManager."""
    logger = get_logger("cross_exchange_arbitrage_demo")
    
    # Initialize StrategyTaskManager with persistence
    manager = StrategyTaskManager(logger, base_path="task_data")
    await manager.initialize()
    # Set up graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    # Start StrategyTaskManager (no recovery for this simple demo)
    logger.info("🔄 Starting StrategyTaskManager...")
    try:
        await manager.start(recover_tasks=True)

        if manager.task_count > 0:
            logger.info(f"♻️ Recovered {manager.task_count} tasks from previous session")
        else:
            # Create F/USDT arbitrage task
            symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))

            logger.info(f"🚀 Creating cross exchange arbitrage task for {symbol}")
            logger.info("📋 Strategy Configuration:",
                       source="MEXC (spot)",
                       destination="Gate.io (spot)",
                       hedge="Gate.io (futures)",
                       strategy="Dynamic threshold arbitrage with TA signals")

            exchange = create_rest_client(get_exchange_config(ExchangeEnum.MEXC.value), is_private=False)

            total_quantity_usdt = 20
            order_qty_usdt = 2

            price = (await exchange.get_ticker_info(symbol))[symbol].last_price

            total_quantity = total_quantity_usdt / price
            order_qty = order_qty_usdt / price

            arbitrage_task = await create_cross_exchange_arbitrage_task(
                symbol=symbol,
                logger=logger,
                total_quantity=total_quantity,
                order_qty=order_qty
            )

            # Add task to StrategyTaskManager
            task_id = await manager.add_task(arbitrage_task)
            logger.info(f"✅ Added cross exchange arbitrage task to StrategyTaskManager: {task_id}")



            # Monitor StrategyTaskManager execution
            logger.info("📊 StrategyTaskManager started, monitoring execution...")

            monitor_count = 0

            while not shutdown_event.is_set():
                # Log status every 30 seconds
                if monitor_count % 300 == 0:  # 300 * 0.1s = 30s
                    task_count = manager.task_count
                    logger.info("📈 Cross Exchange Arbitrage Monitor",
                               active_tasks=task_count,
                               symbol=str(symbol),
                               strategy="MEXC → Gate.io spot → Gate.io futures hedge")

                    if task_count == 0:
                        logger.info("✅ All arbitrage tasks completed, shutting down")
                        break

                monitor_count += 1
                await asyncio.sleep(0.1)

            logger.info("🔄 Shutting down StrategyTaskManager...")
        
    except Exception as e:
        logger.error(f"❌ Cross exchange arbitrage demo execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean shutdown
        await manager.stop()
        logger.info("✅ StrategyTaskManager shutdown complete")


async def main():
    """Main demo execution with error handling."""
    try:
        await run_cross_exchange_arbitrage_demo()
    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted by user")
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
    print("🚀 Starting Cross Exchange Arbitrage Strategy Demo")
    print("📋 Configuration:")
    print("   Symbol: F/USDT")
    print("   Source: MEXC (spot)")
    print("   Destination: Gate.io (spot)")
    print("   Hedge: Gate.io (futures)")
    print("   Strategy: Dynamic threshold arbitrage with TA signals")
    print("💡 The strategy will automatically detect arbitrage opportunities")
    print("🎯 Technical analysis module provides dynamic entry/exit thresholds")
    print("📊 Use Ctrl+C for graceful shutdown\n")
    
    asyncio.run(main())