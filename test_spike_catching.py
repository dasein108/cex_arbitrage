"""
Test script for Spike-Catching Strategy
"""
import asyncio
from exchanges.structs import Symbol, AssetName
from trading.signals_v2.signal_backtester import SignalBacktester
from exchanges.structs.enums import KlineInterval

async def main():
    """Test the spike-catching strategy"""
    
    # Initialize backtester
    backtester = SignalBacktester(
        initial_capital_usdt=1000.0,
        position_size_usdt=100.0,
        candles_timeframe=KlineInterval.MINUTE_1,
        snapshot_seconds=60
    )
    
    # Test with AIA (matches the indicator test data)
    symbol = Symbol(base=AssetName('AIA'), quote=AssetName('USDT'))
    
    print(f"🚀 Testing Spike-Catching Strategy for {symbol.base}/{symbol.quote}")
    print("=" * 60)
    
    # Run backtest using candles data source
    await backtester.run_backtest(
        symbol=symbol,
        data_source='candles',  # Use candles for faster testing
        hours=24
    )

if __name__ == "__main__":
    asyncio.run(main())