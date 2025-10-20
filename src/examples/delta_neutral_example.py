"""Example of using DeltaNeutralTask with FILL and RELEASE modes."""

import asyncio
from trading.tasks.delta_neutral_task import DeltaNeutralTask, DeltaNeutralTaskContext, Direction
from exchanges.structs import Symbol, ExchangeEnum, AssetName
from exchanges.structs.common import Side
from infrastructure.logging import get_logger

async def main():
    logger = get_logger("delta_neutral_example")
    
    # Create symbol
    symbol = Symbol(
        base=AssetName("BTC"),
        quote=AssetName("USDT"),
        is_futures=False  # This is for the symbol itself
    )
    
    # Example 1: FILL mode (accumulate position - buy spot, sell futures)
    fill_context = DeltaNeutralTaskContext(
        symbol=symbol,
        spot_exchange=ExchangeEnum.MEXC,
        futures_exchange=ExchangeEnum.GATEIO_FUTURES,
        direction=Direction.FILL,  # Buy spot, sell futures
        total_quantity=0.1,
        order_quantity=0.01,
        offset_ticks={Side.BUY: 1, Side.SELL: 1},
        tick_tolerance={Side.BUY: 5, Side.SELL: 5}
    )
    
    fill_task = DeltaNeutralTask(logger, fill_context)
    logger.info("Starting FILL mode: buying spot, selling futures")
    await fill_task.start()
    
    # Let it run for a while
    await asyncio.sleep(60)
    
    # Pause the fill task
    await fill_task.pause()
    
    # Example 2: RELEASE mode (unwind position - buy futures, sell spot)
    release_context = DeltaNeutralTaskContext(
        symbol=symbol,
        spot_exchange=ExchangeEnum.MEXC,
        futures_exchange=ExchangeEnum.GATEIO_FUTURES,
        direction=Direction.RELEASE,  # Buy futures, sell spot
        total_quantity=0.1,  # Same quantity to unwind
        order_quantity=0.01,
        offset_ticks={Side.BUY: 1, Side.SELL: 1},
        tick_tolerance={Side.BUY: 5, Side.SELL: 5}
    )
    
    release_task = DeltaNeutralTask(logger, release_context)
    logger.info("Starting RELEASE mode: buying futures, selling spot")
    await release_task.start()
    
    # Let it run until complete
    await asyncio.sleep(60)
    
    # Complete the tasks
    await release_task.complete()
    
    logger.info("Delta neutral example completed")

if __name__ == "__main__":
    asyncio.run(main())