"""
Demo script showing how to use the trading state machines.

This script demonstrates the basic usage of different trading strategies
implemented as state machines, including setup, execution, and result handling.
"""

import asyncio
import sys
import os
from typing import Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from trading.state_machines import (
    state_machine_factory,
    StrategyType,
    StrategyResult,
    SimpleSymbol,
    SimpleLogger
)


async def demo_simple_arbitrage():
    """Demo simple arbitrage strategy execution."""
    logger = SimpleLogger("arbitrage_demo")
    logger.info("Starting simple arbitrage demo")
    
    # Create trading symbol
    symbol = SimpleSymbol("BTC", "USDT", is_futures=False)
    
    try:
        # Create arbitrage strategy
        # Note: In real usage, you'd pass actual exchange instances
        strategy = state_machine_factory.create_strategy(
            strategy_type=StrategyType.SIMPLE_ARBITRAGE,
            symbol=symbol,
            position_size_usdt=100.0,
            min_profit_threshold=0.005,  # 0.5% minimum profit
            max_execution_time_ms=5000.0  # 5 seconds timeout
            # exchange_a_private=exchange_a_private,
            # exchange_b_private=exchange_b_private,
            # exchange_a_public=exchange_a_public,
            # exchange_b_public=exchange_b_public
        )
        
        logger.info("Arbitrage strategy created successfully")
        
        # In a real implementation, you would execute the strategy:
        # result = await strategy.execute_strategy()
        # logger.info(f"Strategy result: {result}")
        
        logger.info("Demo completed (strategy not executed due to missing exchange connections)")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")


async def demo_market_making():
    """Demo market making strategy execution."""
    logger = SimpleLogger("market_making_demo")
    logger.info("Starting market making demo")
    
    symbol = SimpleSymbol("ETH", "USDT", is_futures=False)
    
    try:
        # Create market making strategy
        strategy = state_machine_factory.create_strategy(
            strategy_type=StrategyType.MARKET_MAKING,
            symbol=symbol,
            base_quantity_usdt=50.0,
            min_spread_percent=0.001,  # 0.1% minimum spread
            max_spread_percent=0.01,   # 1% maximum spread
            num_levels=3,              # 3 order levels
            level_spacing=0.002        # 0.2% spacing between levels
            # private_exchange=private_exchange,
            # public_exchange=public_exchange
        )
        
        logger.info("Market making strategy created successfully")
        logger.info("Demo completed (strategy not executed due to missing exchange connections)")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")


async def demo_spot_futures_hedging():
    """Demo spot/futures hedging strategy execution."""
    logger = SimpleLogger("hedging_demo")
    logger.info("Starting spot/futures hedging demo")
    
    spot_symbol = SimpleSymbol("BTC", "USDT", is_futures=False)
    futures_symbol = SimpleSymbol("BTC", "USDT", is_futures=True)
    
    try:
        # Create hedging strategy
        strategy = state_machine_factory.create_strategy(
            strategy_type=StrategyType.SPOT_FUTURES_HEDGING,
            symbol=spot_symbol,  # Primary symbol
            spot_symbol=spot_symbol,
            futures_symbol=futures_symbol,
            position_size_usdt=200.0,
            target_funding_rate=0.01,  # 1% APR minimum
            max_position_imbalance=0.05  # 5% max delta
            # spot_private_exchange=spot_private_exchange,
            # futures_private_exchange=futures_private_exchange,
            # spot_public_exchange=spot_public_exchange,
            # futures_public_exchange=futures_public_exchange
        )
        
        logger.info("Spot/futures hedging strategy created successfully")
        logger.info("Demo completed (strategy not executed due to missing exchange connections)")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")


async def demo_futures_futures_hedging():
    """Demo futures/futures hedging strategy execution."""
    logger = SimpleLogger("futures_hedging_demo")
    logger.info("Starting futures/futures hedging demo")
    
    symbol_a = SimpleSymbol("BTC", "USDT", is_futures=True)
    symbol_b = SimpleSymbol("BTC", "USDT", is_futures=True)
    
    try:
        # Create futures hedging strategy
        strategy = state_machine_factory.create_strategy(
            strategy_type=StrategyType.FUTURES_FUTURES_HEDGING,
            symbol=symbol_a,  # Primary symbol
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            position_size_usdt=150.0,
            min_spread_threshold=0.005,  # 0.5% minimum spread
            max_spread_threshold=0.02,   # 2% maximum spread
            position_timeout_seconds=300.0  # 5 minutes timeout
            # exchange_a_private=exchange_a_private,
            # exchange_b_private=exchange_b_private,
            # exchange_a_public=exchange_a_public,
            # exchange_b_public=exchange_b_public
        )
        
        logger.info("Futures/futures hedging strategy created successfully")
        logger.info("Demo completed (strategy not executed due to missing exchange connections)")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")


async def show_available_strategies():
    """Show all available strategies."""
    logger = SimpleLogger("strategies_demo")
    
    available_strategies = state_machine_factory.get_available_strategies()
    
    logger.info("Available trading strategies:")
    for strategy_type in available_strategies:
        logger.info(f"  - {strategy_type.value}")
    
    logger.info(f"Total strategies available: {len(available_strategies)}")


async def main():
    """Run all demo functions."""
    logger = SimpleLogger("state_machine_demo")
    
    logger.info("🚀 Starting trading state machines demo")
    
    try:
        # Show available strategies
        await show_available_strategies()
        
        print("\n" + "="*60)
        print("DEMO: Simple Arbitrage Strategy")
        print("="*60)
        await demo_simple_arbitrage()
        
        print("\n" + "="*60)
        print("DEMO: Market Making Strategy")
        print("="*60)
        await demo_market_making()
        
        print("\n" + "="*60)
        print("DEMO: Spot/Futures Hedging Strategy")
        print("="*60)
        await demo_spot_futures_hedging()
        
        print("\n" + "="*60)
        print("DEMO: Futures/Futures Hedging Strategy") 
        print("="*60)
        await demo_futures_futures_hedging()
        
        print("\n" + "="*60)
        print("✅ All demos completed successfully!")
        print("="*60)
        
        logger.info("All demos completed successfully")
        
    except Exception as e:
        logger.error(f"Demo execution failed: {e}")
        print(f"\n❌ Demo failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())