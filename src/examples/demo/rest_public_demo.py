"""
Generic Public REST API Integration Demo

Demonstrates public API functionality across multiple exchanges.
Tests core public methods: ping, server time, exchange info, orderbook, recent trades, 
historical trades, and ticker information.

Usage:
    python src/examples/demo/rest_public_demo.py mexc
    python src/examples/demo/rest_public_demo.py gateio
"""

import asyncio
import sys
import time
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from config.config_manager import HftConfig
from exchanges.factory import create_rest_client
from examples.utils.decorators import rest_api_test
from exchanges.utils.exchange_utils import get_exchange_enum


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
    result = await exchange.get_symbols_info()
    
    # Prepare structured result with sample symbols
    sample_symbols = []
    for i, (symbol, info) in enumerate(result.items()):
        if i >= 3:
            break
        sample_symbols.append({
            "symbol": str(symbol),
            "base_precision": info.base_precision,
            "quote_precision": info.quote_precision, 
            "min_base_amount": info.min_base_quantity,
            "min_quote_amount": info.min_quote_quantity,
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


@rest_api_test("historical_trades")
async def check_get_historical_trades(exchange, exchange_name: str):
    """Check get_historical_trades method."""
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    
    # Test with 24 hour time range
    now_ms = int(time.time() * 1000)
    from_ms = now_ms - (24 * 60 * 60 * 1000)  # 24 hours ago
    
    result = await exchange.get_historical_trades(
        symbol, 
        limit=10, 
        timestamp_from=from_ms, 
        timestamp_to=now_ms
    )
    
    # Structure the trade data
    trades_data = []
    for trade in result[:5]:  # Show first 5 trades
        trades_data.append({
            "price": trade.price,
            "quantity": trade.quantity,
            "side": trade.side.name,
            "timestamp": trade.timestamp,
            "trade_id": trade.trade_id,
            "is_maker": trade.is_maker
        })
    
    # Check if exchange supports timestamp filtering
    supports_filtering = True
    if exchange_name.upper() == "MEXC":
        supports_filtering = False  # MEXC returns recent trades regardless of timestamp
    
    return {
        "symbol": f"{symbol.base}/{symbol.quote}",
        "trades_count": len(result),
        "timestamp_from": from_ms,
        "timestamp_to": now_ms,
        "supports_timestamp_filtering": supports_filtering,
        "sample_trades": trades_data
    }


@rest_api_test("ticker_info")
async def check_get_ticker_info(exchange, exchange_name: str):
    """Check get_ticker_info method."""
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    
    # Test single symbol ticker
    single_result = await exchange.get_ticker_info(symbol)
    
    # Test all symbols ticker (limit to first 5 for demo)
    all_result = await exchange.get_ticker_info()
    
    # Extract single symbol data
    ticker = single_result.get(symbol)
    single_ticker_data = {}
    if ticker:
        single_ticker_data = {
            "symbol": f"{ticker.symbol.base}/{ticker.symbol.quote}",
            "last_price": ticker.last_price,
            "price_change": ticker.price_change,
            "price_change_percent": ticker.price_change_percent,
            "high_price": ticker.high_price,
            "low_price": ticker.low_price,
            "volume": ticker.volume,
            "quote_volume": ticker.quote_volume,
            "bid_price": ticker.bid_price,
            "ask_price": ticker.ask_price,
            "open_time": ticker.open_time,
            "close_time": ticker.close_time
        }
    
    # Sample from all symbols
    sample_tickers = []
    for i, (sym, tick) in enumerate(all_result.items()):
        if i >= 5:  # Show first 5 tickers
            break
        sample_tickers.append({
            "symbol": f"{sym.base}/{sym.quote}",
            "last_price": tick.last_price,
            "price_change_percent": tick.price_change_percent,
            "volume": tick.volume
        })
    
    return {
        "test_symbol": f"{symbol.base}/{symbol.quote}",
        "single_ticker_found": symbol in single_result,
        "single_ticker_data": single_ticker_data,
        "all_symbols_count": len(all_result),
        "sample_all_tickers": sample_tickers
    }


async def main(exchange_name: str):
    """Run all public API integration checks for the specified exchange."""
    print(f"{exchange_name.upper()} PUBLIC REST API INTEGRATION DEMO")
    print("=" * 50)

    try:
        # Load exchange configuration and create instance
        config_manager = HftConfig()
        config = config_manager.get_exchange_config(exchange_name.lower())
        exchange = create_rest_client(get_exchange_enum(exchange_name), is_private=False, config=config)
        
        # Execute all public API checks
        await check_ping(exchange, exchange_name)
        await check_get_server_time(exchange, exchange_name)
        await check_get_exchange_info(exchange, exchange_name)
        await check_get_orderbook(exchange, exchange_name)
        await check_get_recent_trades(exchange, exchange_name)
        await check_get_historical_trades(exchange, exchange_name)
        await check_get_ticker_info(exchange, exchange_name)
        
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
    exchange_name = sys.argv[1] if len(sys.argv) > 1 else "gateio_spot"

    try:
        asyncio.run(main(exchange_name))
        print(f"\n✅ {exchange_name.upper()} public API demo completed successfully!")
    except Exception as e:
        print(f"\n❌ {exchange_name.upper()} public API demo failed: {e}")
        import traceback
        traceback.print_exc()