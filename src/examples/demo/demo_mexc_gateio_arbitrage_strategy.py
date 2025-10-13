"""
Demo Script for Redesigned Hedged Arbitrage Strategy

Demonstrates the new arbitrage strategy architecture that is compatible with
DualExchange and BaseTradingTask patterns. Shows real-time integration and
HFT-optimized execution.

Usage:
    PYTHONPATH=src python hedged_arbitrage/strategy/demo_mexc_gateio_arbitrage_strategy.py
"""

import sys
import asyncio
import signal
from pathlib import Path
# Float-only policy - no Decimal imports per PROJECT_GUIDES.md
from trading.struct import TradingStrategyState

# Add src and project root to path for imports
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Configure environment for demo
import os
os.environ['ENVIRONMENT'] = 'dev'

from exchanges.structs import Symbol
from exchanges.structs.types import AssetName
from infrastructure.logging import get_logger

from applications.hedged_arbitrage.strategy.mexc_gateio_futures_strategy import MexcGateioFuturesStrategy, create_mexc_gateio_strategy


logger = get_logger('arbitrage_demo')

async def main():
    """Main demo execution with graceful shutdown."""
    # Set up signal handling
    shutdown_event = asyncio.Event()
    running = True

    # Run demos in sequence
    symbol = Symbol(base=AssetName("LUNC"), quote=AssetName("USDT"))

    print(f"📊 Trading Symbol: {symbol}")

    # Create strategy using the simplified factory function
    strategy = await create_mexc_gateio_strategy(
        symbol=symbol,
        base_position_size_usdt=10.0,
        entry_threshold_pct=0.007,
        exit_threshold_pct=0.005,
        futures_leverage=1.0
    )
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()
        nonlocal running
        running = False
        asyncio.create_task(strategy.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        pass
        while strategy.context.state != TradingStrategyState.CANCELLED and running:
            await strategy.execute_once()
            await asyncio.sleep(0.1)

        print("\n🎉 All demos completed!")

        await strategy.cleanup()
    except Exception as e:
        print(f"❌ Demo execution failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())