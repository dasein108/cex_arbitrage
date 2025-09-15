"""
MEXC Public API Integration Check

Simple integration checks that call each API method and display raw responses.
Used for API validation and response verification.
"""

import asyncio
from structs.exchange import Symbol, AssetName
from exchanges.mexc.rest.mexc_public import MexcPublicSpotRest
from config import get_exchange_config_struct

async def check_ping(exchange: MexcPublicSpotRest):
    """Check ping method."""
    print("=== PING CHECK ===")
    try:
        result = await exchange.ping()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")


async def check_get_server_time(exchange: MexcPublicSpotRest):
    """Check get_server_time method."""
    print("\n=== GET SERVER TIME CHECK ===")
    try:
        result = await exchange.get_server_time()
        print(f"Server time: {result}")
    except Exception as e:
        print(f"Error: {e}")


async def check_get_exchange_info(exchange: MexcPublicSpotRest):
    """Check get_exchange_info method."""
    print("\n=== GET EXCHANGE INFO CHECK ===")
    try:
        result = await exchange.get_exchange_info()
        print(f"Total symbols: {len(result)}")
        
        # Show first 3 symbols
        for i, (symbol, info) in enumerate(result.items()):
            if i >= 3:
                break
            print(f"Symbol {i+1}: {symbol}")
            print(f"  Exchange: {info.exchange}")
            print(f"  Base precision: {info.base_precision}")
            print(f"  Quote precision: {info.quote_precision}")
            print(f"  Min base amount: {info.min_base_amount}")
            print(f"  Min quote amount: {info.min_quote_amount}")
            print(f"  Maker commission: {info.maker_commission}")
            print(f"  Taker commission: {info.taker_commission}")
            print(f"  Inactive: {info.inactive}")
            
    except Exception as e:
        print(f"Error: {e}")


async def check_get_orderbook(exchange: MexcPublicSpotRest):
    """Check get_orderbook method."""
    print("\n=== GET ORDERBOOK CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    
    try:
        result = await exchange.get_orderbook(symbol, limit=5)
        print(f"Symbol: {symbol}")
        print(f"Timestamp: {result.timestamp}")
        print(f"Bids count: {len(result.bids)}")
        print(f"Asks count: {len(result.asks)}")
        
        print("Bids:")
        for i, bid in enumerate(result.bids):
            print(f"  {i+1}: price={bid.price}, size={bid.size}")
            
        print("Asks:")
        for i, ask in enumerate(result.asks):
            print(f"  {i+1}: price={ask.price}, size={ask.size}")
            
    except Exception as e:
        print(f"Error: {e}")


async def check_get_recent_trades(exchange: MexcPublicSpotRest):
    """Check get_recent_trades method.""" 
    print("\n=== GET RECENT TRADES CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    
    try:
        result = await exchange.get_recent_trades(symbol, limit=5)
        print(f"Symbol: {symbol}")
        print(f"Trades count: {len(result)}")
        
        for i, trade in enumerate(result):
            print(f"Trade {i+1}:")
            print(f"  Price: {trade.price}")
            print(f"  Amount: {trade.amount}")
            print(f"  Side: {trade.side}")
            print(f"  Timestamp: {trade.timestamp}")
            print(f"  Is maker: {trade.is_maker}")
            
    except Exception as e:
        print(f"Error: {e}")


async def main():
    """Run all integration checks."""
    print("MEXC PUBLIC API INTEGRATION CHECKS")
    print("=" * 50)

    config = get_exchange_config_struct('MEXC')
    exchange = MexcPublicSpotRest(config)
    
    await check_ping(exchange)
    await check_get_server_time(exchange)
    await check_get_exchange_info(exchange)
    await check_get_orderbook(exchange)
    await check_get_recent_trades(exchange)
    await exchange.close()
    print("\n" + "=" * 50)
    print("INTEGRATION CHECKS COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())