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
from structs.common import Symbol, AssetName
from core.config.config_manager import get_exchange_config

from examples.utils.rest_api_factory import get_exchange_rest_class
from examples.utils.decorators import rest_api_test




@rest_api_test("ping")
async def check_ping(exchange, exchange_name: str):
    """Check ping method."""
    return await exchange.ping()


@rest_api_test("server_time")
async def check_get_server_time(exchange, exchange_name: str):
    """Check get_server_time method."""
    result = await exchange.get_server_time()
    return {"server_time": result}


@rest_api_test("exchange_info")
async def check_get_exchange_info(exchange, exchange_name: str):
    """Check get_exchange_info method."""
    result = await exchange.get_exchange_info()
    
    # Prepare structured result with sample symbols
    sample_symbols = []
    for i, (symbol, info) in enumerate(result.items()):
        if i >= 3:
            break
        sample_symbols.append({
            "symbol": str(symbol),
            "base_precision": info.base_precision,
            "quote_precision": info.quote_precision, 
            "min_base_amount": info.min_base_amount,
            "min_quote_amount": info.min_quote_amount,
            "maker_commission": info.maker_commission,
            "taker_commission": info.taker_commission,
            "inactive": info.inactive
        })
    
    return {
        "total_symbols": len(result),
        "sample_symbols": sample_symbols
    }


@rest_api_test("orderbook")
async def check_get_orderbook(exchange, exchange_name: str):
    """Check get_orderbook method."""
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    result = await exchange.get_orderbook(symbol, limit=5)
    
    # Structure the result
    bids_data = [{"price": bid.price, "size": bid.size} for bid in result.bids]
    asks_data = [{"price": ask.price, "size": ask.size} for ask in result.asks]
    
    return {
        "symbol": f"{symbol.base}/{symbol.quote}",
        "timestamp": result.timestamp,
        "bids_count": len(result.bids),
        "asks_count": len(result.asks),
        "bids": bids_data,
        "asks": asks_data
    }


@rest_api_test("recent_trades")
async def check_get_recent_trades(exchange, exchange_name: str):
    """Check get_recent_trades method.""" 
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    result = await exchange.get_recent_trades(symbol, limit=5)
    
    # Structure the trade data
    trades_data = []
    for trade in result:
        trades_data.append({
            "price": trade.price,
            "quantity": trade.quantity,
            "side": trade.side.name,
            "timestamp": trade.timestamp,
            "is_maker": trade.is_maker
        })
    
    return {
        "symbol": f"{symbol.base}/{symbol.quote}",
        "trades_count": len(result),
        "trades": trades_data
    }


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