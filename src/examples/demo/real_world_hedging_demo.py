#!/usr/bin/env python3
"""
Real-World Spot/Futures Hedging Demo

Production-ready demo that executes real spot/futures hedging using Gate.io.
Implements delta-neutral positioning to capture funding rate arbitrage.

Usage:
    # Basic execution
    PYTHONPATH=src python src/examples/demo/real_world_hedging_demo.py --symbol BTC/USDT --amount 100

    # With custom parameters
    PYTHONPATH=src python src/examples/demo/real_world_hedging_demo.py \
        --symbol BTC/USDT \
        --amount 100 \
        --min-funding-rate 0.01 \
        --max-position-imbalance 0.05

Safety Features:
- Validates Gate.io credentials before execution
- Implements position limits and risk management
- Real-time monitoring with automatic stop-loss
- Comprehensive logging and error handling
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import get_exchange_config
from exchanges.exchange_factory import get_composite_implementation
from exchanges.structs import Symbol, AssetName
from trading.state_machines.hedging.spot_futures_hedging import (
    SpotFuturesHedgingStateMachine,
    SpotFuturesHedgingContext
)
from infrastructure.logging import get_logger
from infrastructure.networking.websocket.structs import (
    PublicWebsocketChannelType,
    PrivateWebsocketChannelType
)


@dataclass
class HedgingConfiguration:
    """Configuration for hedging demo."""
    symbol: Symbol
    spot_symbol: Symbol
    futures_symbol: Symbol
    amount_usdt: float
    min_funding_rate: float
    max_position_imbalance: float
    max_execution_time_minutes: float
    enable_rebalancing: bool


class HedgingDemoError(Exception):
    """Demo-specific errors."""
    pass

def parse_symbol(symbol_str: str) -> Tuple[Symbol, Symbol, Symbol]:
    """Parse symbol string and create spot/futures symbol objects."""
    try:
        if "/" not in symbol_str:
            raise ValueError("Symbol must be in format 'BASE/QUOTE' (e.g., BTC/USDT)")
        
        base, quote = symbol_str.upper().split("/")
        
        # Create symbols
        spot_symbol = Symbol(
            base=AssetName(base),
            quote=AssetName(quote),
            is_futures=False
        )
        
        futures_symbol = Symbol(
            base=AssetName(base),
            quote=AssetName(quote),
            is_futures=True
        )
        
        # Primary symbol (use spot as primary)
        primary_symbol = spot_symbol
        
        return primary_symbol, spot_symbol, futures_symbol
        
    except Exception as e:
        raise ValueError(f"Invalid symbol format '{symbol_str}': {e}")


async def create_exchanges(spot_config, futures_config, symbols: Tuple[Symbol, Symbol, Symbol], logger):
    """Create and initialize all required exchanges."""
    primary_symbol, spot_symbol, futures_symbol = symbols
    
    logger.info("Creating exchange connections...")
    
    try:
        # Create spot exchanges
        spot_private = get_composite_implementation(spot_config, is_private=True)
        spot_public = get_composite_implementation(spot_config, is_private=False)
        
        # Create futures exchanges
        futures_private = get_composite_implementation(futures_config, is_private=True)
        futures_public = get_composite_implementation(futures_config, is_private=False)
        
        # Initialize public exchanges with symbols
        await spot_public.initialize(
            [spot_symbol], 
            [PublicWebsocketChannelType.BOOK_TICKER]
        )
        
        await futures_public.initialize(
            [futures_symbol], 
            [PublicWebsocketChannelType.BOOK_TICKER]
        )
        
        # Initialize private exchanges
        await spot_private.initialize(
            spot_public.symbols_info,
            [PrivateWebsocketChannelType.ORDER, PrivateWebsocketChannelType.BALANCE]
        )
        
        await futures_private.initialize(
            futures_public.symbols_info,
            [PrivateWebsocketChannelType.ORDER, PrivateWebsocketChannelType.BALANCE]
        )
        
        logger.info("✅ All exchanges initialized successfully")
        
        return {
            'spot_private': spot_private,
            'spot_public': spot_public,
            'futures_private': futures_private,
            'futures_public': futures_public
        }
        
    except Exception as e:
        logger.error(f"Failed to create exchanges: {e}")
        raise HedgingDemoError(f"Exchange initialization failed: {e}")


async def execute_hedging_strategy(
    config: HedgingConfiguration,
    exchanges: dict,
    logger,
) -> Optional[dict]:
    """Execute the hedging strategy."""
    
    logger.info(f"🚀 Starting hedging strategy execution")
    logger.info(f"   Symbol: {config.symbol.base}/{config.symbol.quote}")
    logger.info(f"   Amount: ${config.amount_usdt}")
    logger.info(f"   Min funding rate: {config.min_funding_rate*100:.2f}%")

    try:
        # Create hedging context
        context = SpotFuturesHedgingContext(
            strategy_name="gateio_spot_futures_hedge",
            symbol=config.symbol,
            logger=logger,
            spot_private_exchange=exchanges['spot_private'],
            futures_private_exchange=exchanges['futures_private'],
            spot_public_exchange=exchanges['spot_public'],
            futures_public_exchange=exchanges['futures_public'],
            position_size_usdt=config.amount_usdt,
            spot_symbol=config.spot_symbol,
            futures_symbol=config.futures_symbol,
            target_funding_rate=config.min_funding_rate,
            max_position_imbalance=config.max_position_imbalance
        )
        
        # Create and execute state machine
        strategy = SpotFuturesHedgingStateMachine(context)
        
        # Execute with timeout
        result = await asyncio.wait_for(
            strategy.execute_strategy(),
            timeout=config.max_execution_time_minutes * 60
        )
        
        return {
            'success': result.success,
            'profit_usdt': result.profit_usdt,
            'execution_time_ms': result.execution_time_ms,
            'orders_executed': len(result.orders_executed),
            'error_message': result.error_message
        }
        
    except asyncio.TimeoutError:
        logger.error("Strategy execution timed out")
        raise HedgingDemoError("Execution timeout - positions may need manual cleanup")
    
    except Exception as e:
        logger.error(f"Strategy execution failed: {e}")
        raise HedgingDemoError(f"Execution failed: {e}")


async def cleanup_resources(exchanges: Optional[dict], logger) -> None:
    """Cleanup all exchange connections."""
    if not exchanges:
        return
    
    logger.info("Cleaning up exchange connections...")
    
    cleanup_tasks = []
    for name, exchange in exchanges.items():
        if exchange:
            task = asyncio.create_task(exchange.close())
            cleanup_tasks.append(task)
    
    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    
    logger.info("✅ Cleanup completed")


def display_results(result: Optional[dict], config: HedgingConfiguration, logger) -> None:
    """Display execution results."""
    print("\n" + "="*60)
    print("📊 HEDGING EXECUTION RESULTS")
    print("="*60)
    
    if not result:
        print("❌ No results to display")
        return
    
    print(f"Symbol: {config.symbol.base}/{config.symbol.quote}")
    print(f"Position Size: ${config.amount_usdt}")
    
    if result.get('simulated'):
        print("🧪 SIMULATED EXECUTION")
    
    if result['success']:
        print(f"✅ Status: SUCCESS")
        print(f"💰 Profit: ${result['profit_usdt']:.2f}")
        print(f"⏱️  Execution Time: {result['execution_time_ms']:.0f}ms")
        if 'orders_executed' in result:
            print(f"📦 Orders Executed: {result['orders_executed']}")
    else:
        print(f"❌ Status: FAILED")
        if result.get('error_message'):
            print(f"🚨 Error: {result['error_message']}")
    
    print("="*60)


async def main():
    """Main demo execution function."""
    # Setup logging
    logger = get_logger("hedging_demo")
    
    exchanges = None
    symbol = "HIFI/USDT"
    amount = 25
    max_position_imbalance = 0.001
    min_funding_rate = 0.0
    no_rebalancing = False
    max_execution_time = 10
    try:
        # Parse and validate inputs
        primary_symbol, spot_symbol, futures_symbol = parse_symbol(symbol)

        # Create configuration
        config = HedgingConfiguration(
            symbol=primary_symbol,
            spot_symbol=spot_symbol,
            futures_symbol=futures_symbol,
            amount_usdt=amount,
            min_funding_rate=min_funding_rate,
            max_position_imbalance=max_position_imbalance,
            max_execution_time_minutes=max_execution_time,
            enable_rebalancing=not no_rebalancing
        )
        
        # Load exchange configurations
        logger.info("Loading Gate.io configurations...")
        spot_config = get_exchange_config("gateio_spot")
        futures_config = get_exchange_config("gateio_futures")
        
        exchanges = await create_exchanges(
            spot_config,
            futures_config,
            (primary_symbol, spot_symbol, futures_symbol),
            logger
        )
        
        # Execute hedging strategy
        result = await execute_hedging_strategy(
            config, 
            exchanges or {}, 
            logger, 
        )
        
        # Display results
        display_results(result, config, logger)
        
        return 0
        
    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user")
        print("\n⚠️ Execution interrupted - cleaning up...")
        return 1
        
    except HedgingDemoError as e:
        logger.error(f"Demo error: {e}")
        print(f"\n❌ Demo failed: {e}")
        return 1
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n💥 Unexpected error: {e}")
        return 1
        
    finally:
        if exchanges:
            await cleanup_resources(exchanges, logger)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)