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

from typing import Optional
from exchanges.structs import Symbol, AssetName, ExchangeEnum
from infrastructure.logging import get_logger, LoggerFactory, HFTLoggerInterface
from trading.strategies.strategy_manager.strategy_task_manager import StrategyTaskManager
from trading.strategies.implementations.spot_futures_spread_arbitrage_strategy import (
    SpotFuturesArbitrageTask,
    SpotFuturesArbitrageTaskContext
)
from trading.strategies.implementations.spot_futures_spread_arbitrage_strategy.spot_futures_arbitrage_task import MarketData
from trading.strategies.implementations.maker_limit_delta_neutral__simple_strategy.maker_limit_simple_delta_neutral_task import MakerLimitDeltaNeutralTask, MakerLimitDeltaNeutralTaskContext

from exchanges.exchange_factory import create_rest_client


async def create_maker_limit_mexc_gateio_futures_task(
        symbol: Symbol,
        logger: Optional[HFTLoggerInterface] = None,
        total_quantity: float = 20.0,
        order_qty: float = 10.0,
        tick_tolerance=3,
        ticks_offset=6,
) -> MakerLimitDeltaNeutralTask:
    """Create a MEXC spot vs Gate.io futures arbitrage task.

    This is the most profitable cross-exchange spot-futures setup.
    Uses z-score based signals_v2 with analyzer logic integration.

    Args:
        symbol: Trading symbol (e.g., F/USDT)
        logger: HFT logger instance
        total_quantity: Total position size
        order_qty: Individual order size

    Returns:
        Configured SpotFuturesArbitrageTask
    """

    # Cross-exchange configuration: MEXC spot vs Gate.io futures
    context = MakerLimitDeltaNeutralTaskContext(
        symbol=symbol,
        total_quantity=total_quantity,
        order_qty=order_qty,
        # Cross-exchange thresholds (higher due to transfer costs)
        min_profit_margin=0.15,  # 0.15% minimum profit

        settings={
            'spot': MarketData(
                exchange=ExchangeEnum.MEXC,  # MEXC spot market
                tick_tolerance=tick_tolerance,
                ticks_offset=ticks_offset,
                use_market=False  # Use limit orders for better fills
            ),
            'futures': MarketData(
                exchange=ExchangeEnum.GATEIO_FUTURES,  # Gate.io futures market
            )
        }
    )

    # Create task with integrated analyzer signal logic
    task = MakerLimitDeltaNeutralTask(
        context=context,
        logger=logger
    )

    return task

async def create_mexc_gateio_futures_task(
    symbol: Symbol,
    logger: Optional[HFTLoggerInterface] = None,
    total_quantity: float = 100.0,
    order_qty: float = 10.0
) -> SpotFuturesArbitrageTask:
    """Create a MEXC spot vs Gate.io futures arbitrage task.
    
    This is the most profitable cross-exchange spot-futures setup.
    Uses z-score based signals_v2 with analyzer logic integration.
    
    Args:
        symbol: Trading symbol (e.g., F/USDT)
        logger: HFT logger instance
        total_quantity: Total position size
        order_qty: Individual order size
        
    Returns:
        Configured SpotFuturesArbitrageTask
    """
    
    # Cross-exchange configuration: MEXC spot vs Gate.io futures
    context = SpotFuturesArbitrageTaskContext(
        symbol=symbol,
        total_quantity=total_quantity,
        order_qty=order_qty,
        # Cross-exchange thresholds (higher due to transfer costs)
        min_profit_margin=0.15,  # 0.15% minimum profit
        max_acceptable_spread=0.3,  # 0.3% max spread tolerance
        
        settings={
            'spot': MarketData(
                exchange=ExchangeEnum.MEXC,  # MEXC spot market
                tick_tolerance=5,
                ticks_offset=1,
                use_market=True  # Use limit orders for better fills
            ),
            'futures': MarketData(
                exchange=ExchangeEnum.GATEIO_FUTURES,  # Gate.io futures market
                tick_tolerance=5,
                ticks_offset=1,
                use_market=True  # Use limit orders for precision
            )
        }
    )
    
    # Create task with integrated analyzer signal logic
    task = SpotFuturesArbitrageTask(
        context=context,
        logger=logger
    )
    
    return task


async def create_gateio_same_exchange_task(
    symbol: Symbol,
    logger: Optional[HFTLoggerInterface] = None,
    total_quantity: float = 50.0,
    order_qty: float = 5.0
) -> SpotFuturesArbitrageTask:
    """Create a Gate.io spot vs Gate.io futures arbitrage task.
    
    Traditional same-exchange basis arbitrage with tighter thresholds.
    
    Args:
        symbol: Trading symbol (e.g., F/USDT)
        logger: HFT logger instance  
        total_quantity: Total position size
        order_qty: Individual order size
        
    Returns:
        Configured SpotFuturesArbitrageTask
    """
    
    # Same-exchange configuration: Gate.io spot vs Gate.io futures
    context = SpotFuturesArbitrageTaskContext(
        symbol=symbol,
        total_quantity=total_quantity,
        order_qty=order_qty,

        # Same-exchange thresholds (tighter due to lower costs)
        min_profit_margin=0.1,  # 0.1% minimum profit
        max_acceptable_spread=0.2,  # 0.2% max spread tolerance
        
        settings={
            'spot': MarketData(
                exchange=ExchangeEnum.GATEIO,  # Gate.io spot
                tick_tolerance=3,
                ticks_offset=1,
                use_market=False
            ),
            'futures': MarketData(
                exchange=ExchangeEnum.GATEIO_FUTURES,  # Gate.io futures
                tick_tolerance=3,
                ticks_offset=1,
                use_market=False
            )
        }
    )
    
    # Create task with z-score based signal logic
    task = SpotFuturesArbitrageTask(
        context=context,
        logger=logger
    )
    
    return task


async def run_spot_futures_arbitrage_demo():
    """Run spot-futures arbitrage strategy demo with analyzer signal integration."""
    logger = get_logger("spot_futures_arbitrage_demo")
    
    # Initialize StrategyTaskManager
    manager = StrategyTaskManager(logger, base_path="spot_futures_task_data")
    await manager.initialize()
    
    # Set up graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🔄 Starting StrategyTaskManager for spot-futures arbitrage...")
    
    try:
        await manager.start(recover_tasks=True)

        if manager.task_count > 0:
            logger.info(f"♻️ Recovered {manager.task_count} spot-futures arbitrage tasks")
        else:
            logger.info("🚀 Creating new spot-futures arbitrage tasks...")

            async def add_maker_limit_task(symbol: Symbol):
                """Add cross-exchange spot-futures arbitrage task."""
                logger.info(f"📈 Creating MAKER LIMIT MEXC spot vs Gate.io futures task for {symbol}")

                # Get current price for position sizing
                mexc_exchange = create_rest_client(
                    get_exchange_config(ExchangeEnum.MEXC.value),
                    is_private=False
                )

                ticker_info = await mexc_exchange.get_ticker_info(symbol)
                current_price = ticker_info[symbol].last_price

                # Size positions in USDT terms
                total_quantity_usdt = 5  # $50 total position
                order_qty_usdt = 5  # $5 per order

                total_quantity = total_quantity_usdt / current_price
                order_qty = order_qty_usdt / current_price

                # Create cross-exchange arbitrage task
                task = await create_maker_limit_mexc_gateio_futures_task(
                    symbol=symbol,
                    total_quantity=total_quantity,
                    order_qty=order_qty,
                    ticks_offset=7,
                    tick_tolerance=3
                    # total_quantity=11,
                    # order_qty=11
                )

                # Add to manager
                task_id = await manager.add_task(task)
                logger.info("✅ Created Cross-Exchange Spot-Futures Task",
                            symbol=str(symbol),
                            # total_quantity=f"{total_quantity:.4f}",
                            # total_value_usdt=total_quantity_usdt,
                            spot_exchange="MEXC",
                            futures_exchange="GATEIO_FUTURES",
                            signal_type="Z-score based")

            async def add_cross_exchange_task(symbol: Symbol):
                """Add cross-exchange spot-futures arbitrage task."""
                logger.info(f"📈 Creating MEXC spot vs Gate.io futures task for {symbol}")
                logger.info("📋 Cross-Exchange Configuration:",
                           spot_exchange="MEXC",
                           futures_exchange="Gate.io Futures", 
                           signal_logic="Z-score based with analyzer integration",
                           entry_threshold="abs(z_score) > 2",
                           exit_conditions="Mean reversion (z<0.5), max 4h, sign flip")
                
                # Get current price for position sizing
                mexc_exchange = create_rest_client(
                    get_exchange_config(ExchangeEnum.MEXC.value), 
                    is_private=False
                )
                
                ticker_info = await mexc_exchange.get_ticker_info(symbol)
                current_price = ticker_info[symbol].last_price
                
                # Size positions in USDT terms
                total_quantity_usdt = 20  # $50 total position
                order_qty_usdt = 5       # $5 per order
                
                total_quantity = total_quantity_usdt / current_price
                order_qty = order_qty_usdt / current_price
                
                # Create cross-exchange arbitrage task
                task = await create_mexc_gateio_futures_task(
                    symbol=symbol,
                    total_quantity=total_quantity,
                    order_qty=order_qty
                )
                
                # Add to manager
                task_id = await manager.add_task(task)
                logger.info("✅ Created Cross-Exchange Spot-Futures Task",
                           symbol=str(symbol),
                           total_quantity=f"{total_quantity:.4f}",
                           total_value_usdt=total_quantity_usdt,
                           spot_exchange="MEXC",
                           futures_exchange="GATEIO_FUTURES",
                           signal_type="Z-score based")
            
            async def add_same_exchange_task(symbol: Symbol):
                """Add same-exchange spot-futures arbitrage task."""
                logger.info(f"📊 Creating Gate.io spot vs futures task for {symbol}")
                logger.info("📋 Same-Exchange Configuration:",
                           spot_exchange="Gate.io Spot",
                           futures_exchange="Gate.io Futures",
                           signal_logic="Z-score based with tighter thresholds",
                           transfer_required="No")
                
                # Get current price for position sizing
                gateio_exchange = create_rest_client(
                    get_exchange_config(ExchangeEnum.GATEIO.value),
                    is_private=False
                )
                
                ticker_info = await gateio_exchange.get_ticker_info(symbol)
                current_price = ticker_info[symbol].last_price
                
                # Smaller positions for same-exchange (lower opportunity)
                total_quantity_usdt = 10  # $25 total position
                order_qty_usdt = 10    # $2.5 per order
                
                total_quantity = total_quantity_usdt / current_price
                order_qty = order_qty_usdt / current_price
                
                # Create same-exchange arbitrage task
                task = await create_gateio_same_exchange_task(
                    symbol=symbol,
                    total_quantity=total_quantity,
                    order_qty=order_qty
                )
                
                # Add to manager
                task_id = await manager.add_task(task)
                logger.info("✅ Created Same-Exchange Spot-Futures Task",
                           symbol=str(symbol),
                           total_quantity=f"{total_quantity:.4f}",
                           total_value_usdt=total_quantity_usdt,
                           exchange="GATEIO (spot & futures)",
                           signal_type="Z-score based")
            
            # Add cross-exchange tasks (most profitable)
            # await add_maker_limit_task(Symbol(base=AssetName("EVAA"), quote=AssetName("USDT")))
            # await add_maker_limit_task(Symbol(base=AssetName("WAVES"), quote=AssetName("USDT")))
            # await add_maker_limit_task(Symbol(base=AssetName("METAX"), quote=AssetName("USDT")))
            # await add_maker_limit_task(Symbol(base=AssetName("AIOT"), quote=AssetName("USDT")))
            await add_cross_exchange_task(Symbol(base=AssetName("FLK"), quote=AssetName("USDT")))
            await add_cross_exchange_task(Symbol(base=AssetName("PIGGY"), quote=AssetName("USDT")))
            # await add_same_exchange_task(Symbol(base=AssetName("FHE"), quote=AssetName("USDT")))

            #TODO: map ARCSOL for MEXC
            # await add_cross_exchange_task(Symbol(base=AssetName("ARC"), quote=AssetName("USDT")))

            # Add same-exchange task for comparison
            # await add_same_exchange_task(Symbol(base=AssetName("BTC"), quote=AssetName("USDT")))

        # Monitor execution
        logger.info("📊 Spot-futures arbitrage strategies active, monitoring execution...")
        logger.info("🎯 Strategy Features:",
                   signal_generation="Z-score based (from analyzer)",
                   entry_logic="abs(z_score) > 2 AND spread > fees",
                   exit_logic="Mean reversion OR max 4h OR sign flip",
                   rolling_window="20 periods for statistics",
                   cross_exchange_support="Yes (with asset transfers)")
        
        monitor_count = 0
        while not shutdown_event.is_set():
            # Status monitoring every 60 seconds
            if monitor_count % 600 == 0:  # 600 * 0.1s = 60s
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