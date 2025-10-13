#!/usr/bin/env python3
"""
MEXC-Gate.io Arbitrage Strategy Quick Start Example

This example demonstrates how to quickly set up and run the MEXC-Gate.io
arbitrage strategy with minimal configuration.

Features demonstrated:
- Basic strategy setup and configuration
- Exchange connection and initialization
- Real-time monitoring and status reporting
- Graceful shutdown and cleanup

Usage:
    python examples/mexc_gateio_quickstart.py
"""

import sys
import asyncio
import signal
from pathlib import Path

# Add src to path for imports
current_dir = Path(__file__).parent
project_root = current_dir.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from exchanges.structs import Symbol
from exchanges.structs.types import AssetName
from infrastructure.logging import get_logger
from applications.hedged_arbitrage.strategy.mexc_gateio_futures_strategy import (
    create_mexc_gateio_strategy
)


async def quick_start_demo():
    """Quick start demonstration of the MEXC-Gate.io arbitrage strategy."""
    
    print("🚀 MEXC-Gate.io Arbitrage Strategy Quick Start")
    print("=" * 50)
    
    # Initialize logger
    logger = get_logger('mexc_gateio_quickstart')
    
    # Configuration
    symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
    base_position_size = 5.0  # Small size for demo
    entry_threshold_bps = 15  # 0.15% entry threshold
    exit_threshold_bps = 5    # 0.05% exit threshold
    futures_leverage = 1.0    # Conservative 1x leverage
    
    print(f"📊 Configuration:")
    print(f"  • Symbol: {symbol.base}/{symbol.quote}")
    print(f"  • Position Size: {base_position_size}")
    print(f"  • Entry Threshold: {entry_threshold_bps} bps ({entry_threshold_bps/100:.2f}%)")
    print(f"  • Exit Threshold: {exit_threshold_bps} bps ({exit_threshold_bps/100:.2f}%)")
    print(f"  • Futures Leverage: {futures_leverage}x")
    print()
    
    # Create shutdown event
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print("🔧 Creating and initializing strategy...")
        
        # Create strategy
        strategy = await create_mexc_gateio_strategy(
            symbol=symbol,
            base_position_size_usdt=base_position_size,
            entry_threshold_bps=entry_threshold_bps,
            exit_threshold_bps=exit_threshold_bps,
            futures_leverage=futures_leverage
        )
        
        print("✅ Strategy created successfully!")
        print(f"  • Strategy Name: {strategy.name}")
        print(f"  • Task ID: {strategy.context.task_id}")
        print(f"  • Exchange Roles: {len(strategy.context.exchange_roles)}")
        print()
        
        print("📡 Starting real-time monitoring (Press Ctrl+C to stop)...")
        print("=" * 50)
        
        # Monitor strategy for 30 seconds or until shutdown
        start_time = asyncio.get_event_loop().time()
        last_status_time = start_time
        status_interval = 5.0  # Print status every 5 seconds
        
        while not shutdown_event.is_set():
            current_time = asyncio.get_event_loop().time()
            
            # Print status every 5 seconds
            if (current_time - last_status_time) >= status_interval:
                elapsed = current_time - start_time
                
                # Get strategy summary
                summary = strategy.get_strategy_summary()
                
                print(f"⏰ {elapsed:.1f}s | "
                      f"State: {strategy.context.state.name if hasattr(strategy.context, 'state') else 'RUNNING'} | "
                      f"Cycles: {summary['performance']['arbitrage_cycles']} | "
                      f"Volume: {summary['performance']['total_volume']:.2f} | "
                      f"Profit: {summary['performance']['total_profit']:.4f} | "
                      f"Delta: {summary['positions']['current_delta']:.4f}")
                
                last_status_time = current_time
            
            # Check for shutdown or timeout
            if (current_time - start_time) > 30.0:  # 30 second demo
                print("\n⏰ Demo timeout reached (30 seconds)")
                break
            
            await asyncio.sleep(0.5)  # Check every 500ms
        
        print("\n" + "=" * 50)
        print("📊 Final Strategy Summary:")
        
        final_summary = strategy.get_strategy_summary()
        
        print(f"  • Runtime: {asyncio.get_event_loop().time() - start_time:.1f} seconds")
        print(f"  • Total Arbitrage Cycles: {final_summary['performance']['arbitrage_cycles']}")
        print(f"  • Total Volume: {final_summary['performance']['total_volume']:.2f}")
        print(f"  • Total Profit: {final_summary['performance']['total_profit']:.4f}")
        print(f"  • Current Delta: {final_summary['positions']['current_delta']:.4f}")
        print(f"  • MEXC Position: {final_summary['positions']['mexc_spot']:.2f}")
        print(f"  • Gate.io Position: {final_summary['positions']['gateio_futures']:.2f}")
        
        # Exchange health summary
        if final_summary.get('exchange_manager'):
            em_summary = final_summary['exchange_manager']
            print(f"  • Connected Exchanges: {em_summary['connected_exchanges']}/{em_summary['total_exchanges']}")
            print(f"  • Price Updates: {em_summary['total_price_updates']}")
            print(f"  • Orders Processed: {em_summary['total_orders_processed']}")
        
        print("\n🔄 Cleaning up strategy...")
        await strategy.cleanup()
        print("✅ Cleanup completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎉 Quick start demo completed!")


if __name__ == "__main__":
    print("Starting MEXC-Gate.io Arbitrage Strategy Quick Start...")
    asyncio.run(quick_start_demo())