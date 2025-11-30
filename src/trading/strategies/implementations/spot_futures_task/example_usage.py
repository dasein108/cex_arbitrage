"""
Example usage of the simplified SpotFuturesTaskStrategy.

This example demonstrates how to configure and use the spot_futures_task
strategy for MEXC spot vs Gate.io futures arbitrage with minimal setup.
"""

from db.models import Symbol
from exchanges.structs import ExchangeEnum
from .spot_futures_task import create_spot_futures_strategy_task

# Example configuration for BTC/USDT arbitrage
def create_btc_mexc_gateio_strategy():
    """
    Create a simplified BTC arbitrage strategy between MEXC spot and Gate.io futures.
    
    Returns:
        Configured SpotFuturesStrategyTask ready for execution
    """
    
    # Configuration parameters
    symbol = Symbol(base="BTC", quote="USDT")
    spot_exchange = ExchangeEnum.MEXC
    futures_exchange = ExchangeEnum.GATEIO_FUTURES
    
    # Trading parameters
    order_qty = 0.01          # 0.01 BTC per trade
    total_quantity = 0.1      # Maximum 0.1 BTC position
    
    # Threshold parameters (optimized for BTC volatility)
    entry_quantile = 0.75     # Enter when spread is in top 25% (favorable)
    exit_quantile = 0.25      # Exit when spread is in bottom 25% (unfavorable)
    
    # Create strategy instance
    strategy = create_spot_futures_strategy_task(
        symbol=symbol,
        spot_exchange=spot_exchange,
        futures_exchange=futures_exchange,
        order_qty=order_qty,
        total_quantity=total_quantity,
        entry_quantile=entry_quantile,
        exit_quantile=exit_quantile,
        
        # Optional: Custom fee structure
        spot_taker_fee=0.0005,      # 0.05% MEXC spot fee
        futures_taker_fee=0.0006,   # 0.06% Gate.io futures fee
        
        # Optional: Risk management
        max_daily_trades=20,        # Limit to 20 trades per day
        min_spread_threshold=0.002, # Require 0.2% spread above fees
        
        # Optional: Advanced parameters
        historical_window_hours=12, # 12 hours of spread history
        volatility_adjustment=True  # Enable volatility-based threshold adjustment
    )
    
    return strategy

# Example usage in a trading application
async def run_strategy_example():
    """
    Example of how to run the spot-futures strategy in a trading application.
    """
    # Create strategy instance
    strategy = create_btc_mexc_gateio_strategy()
    
    try:
        # Initialize strategy (connects to exchanges, loads positions)
        await strategy.start()
        
        print(f"✅ Strategy started: {strategy.status()}")
        
        # Run strategy loop (this would typically be in a scheduler)
        for _ in range(100):  # Run for 100 iterations as example
            await strategy.step()
            await asyncio.sleep(1)  # 1 second between iterations
            
        print(f"📊 Final status: {strategy.status()}")
        
    except Exception as e:
        print(f"❌ Strategy error: {e}")
        
    finally:
        # Clean shutdown
        await strategy.stop()
        await strategy.cleanup()

if __name__ == "__main__":
    import asyncio
    
    # Run the example
    asyncio.run(run_strategy_example())