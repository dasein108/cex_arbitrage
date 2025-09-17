"""
Generic Public REST API Integration Demo

Demonstrates public API functionality across multiple exchanges.
Tests core public methods: ping, server time, exchange info, orderbook, recent trades.

Usage:
    python src/examples/rest_public_demo.py mexc
    python src/examples/rest_public_demo.py gateio
"""

import asyncio
import sys
from structs.exchange import Symbol, AssetName
from core.config.config_manager import get_exchange_config

from examples.utils.rest_api_factory import get_exchange_rest_class




async def check_ping(exchange, exchange_name: str):
    """Check ping method."""
    print(f"=== {exchange_name.upper()} PING CHECK ===")
    try:
        result = await exchange.ping()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")


async def check_get_server_time(exchange, exchange_name: str):
    """Check get_server_time method."""
    print(f"\n=== {exchange_name.upper()} GET SERVER TIME CHECK ===")
    try:
        result = await exchange.get_server_time()
        print(f"Server time: {result}")
    except Exception as e:
        print(f"Error: {e}")


async def check_get_exchange_info(exchange, exchange_name: str):
    """Check get_exchange_info method."""
    print(f"\n=== {exchange_name.upper()} GET EXCHANGE INFO CHECK ===")
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


async def check_get_orderbook(exchange, exchange_name: str):
    """Check get_orderbook method."""
    print(f"\n=== {exchange_name.upper()} GET ORDERBOOK CHECK ===")
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


async def check_get_recent_trades(exchange, exchange_name: str):
    """Check get_recent_trades method.""" 
    print(f"\n=== {exchange_name.upper()} GET RECENT TRADES CHECK ===")
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


async def main(exchange_name: str):
    """Run all public API integration checks for the specified exchange."""
    print(f"{exchange_name.upper()} PUBLIC REST API INTEGRATION DEMO")
    print("=" * 50)

    try:
        # Load exchange configuration
        config = get_exchange_config(exchange_name.upper())
        exchange_class = get_exchange_rest_class(exchange_name, is_private=False)
        exchange = exchange_class(config)
        
        # Execute all public API checks
        await check_ping(exchange, exchange_name)
        await check_get_server_time(exchange, exchange_name)
        await check_get_exchange_info(exchange, exchange_name)
        await check_get_orderbook(exchange, exchange_name)
        await check_get_recent_trades(exchange, exchange_name)
        
        await exchange.close()
        
    except ValueError as e:
        print(f"Configuration Error: {e}")
        print(f"Make sure {exchange_name.upper()} configuration is available")
    except Exception as e:
        print(f"Initialization Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print(f"{exchange_name.upper()} PUBLIC API DEMO COMPLETE")


if __name__ == "__main__":
    exchange_name = sys.argv[1] if len(sys.argv) > 1 else "gateio"

    try:
        asyncio.run(main(exchange_name))
        print(f"\n✅ {exchange_name.upper()} public API demo completed successfully!")
    except Exception as e:
        print(f"\n❌ {exchange_name.upper()} public API demo failed: {e}")
        import traceback
        traceback.print_exc()