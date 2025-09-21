"""
Gate.io Futures REST API Integration Demo

Demonstrates Gate.io futures API functionality for both public and private operations.
Tests futures-specific methods: contracts info, orderbook, positions, futures orders.

Usage:
    PYTHONPATH=src python3 -m examples.demo.gateio_futures_demo public
    PYTHONPATH=src python3 -m examples.demo.gateio_futures_demo private
    PYTHONPATH=src python3 -m examples.demo.gateio_futures_demo both
"""

import asyncio
import sys
import time
from typing import Optional
from datetime import datetime, timedelta

from structs.common import Symbol, AssetName, Side, OrderType, TimeInForce, KlineInterval
from core.config.config_manager import get_exchange_config
from examples.utils.decorators import rest_api_test
from datetime import datetime

def get_gateio_futures_rest_classes():
    """Get Gate.io futures REST client classes."""
    # Import Gate.io futures classes and register strategies/services
    import exchanges.gateio.rest.strategies  # Triggers strategy registration
    import exchanges.gateio.services  # Register symbol mapper
    from exchanges.gateio.rest.gateio_futures_public import GateioPublicFuturesRest
    from exchanges.gateio.rest.gateio_futures_private import GateioPrivateFuturesRest

    return GateioPublicFuturesRest, GateioPrivateFuturesRest


# Public API Tests
@rest_api_test("futures_ping")
async def check_futures_ping(exchange, exchange_name: str):
    """Check ping method for futures."""
    return await exchange.ping()


@rest_api_test("futures_server_time")
async def check_futures_server_time(exchange, exchange_name: str):
    """Check get_server_time method for futures."""
    result = await exchange.get_server_time()
    return {"server_time": result}


@rest_api_test("futures_exchange_info")
async def check_futures_exchange_info(exchange, exchange_name: str):
    """Check get_exchange_info method for futures contracts."""
    result = await exchange.get_exchange_info()

    # Prepare structured result with sample futures contracts
    sample_contracts = []
    for i, (symbol, info) in enumerate(result.items()):
        if i >= 5:  # Show first 5 contracts
            break
        sample_contracts.append({
            "contract": str(symbol),
            "base": symbol.base,
            "quote": symbol.quote,
            "is_futures": symbol.is_futures,
            "base_precision": info.base_precision,
            "quote_precision": info.quote_precision,
            "min_base_amount": info.min_base_amount,
            "min_quote_amount": info.min_quote_amount,
            "maker_commission": info.maker_commission,
            "taker_commission": info.taker_commission,
            "inactive": info.inactive
        })

    return {
        "total_contracts": len(result),
        "sample_contracts": sample_contracts
    }


@rest_api_test("futures_orderbook")
async def check_futures_orderbook(exchange, exchange_name: str):
    """Check get_orderbook method for futures."""
    # Use BTC perpetual contract
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
    result = await exchange.get_orderbook(symbol, limit=5)

    # Structure the result
    bids_data = [{"price": bid.price, "size": bid.size} for bid in result.bids]
    asks_data = [{"price": ask.price, "size": ask.size} for ask in result.asks]

    return {
        "contract": f"{symbol.base}_{symbol.quote}",
        "is_futures": symbol.is_futures,
        "timestamp": result.timestamp,
        "bids_count": len(result.bids),
        "asks_count": len(result.asks),
        "bids": bids_data,
        "asks": asks_data
    }


@rest_api_test("futures_recent_trades")
async def check_futures_recent_trades(exchange, exchange_name: str):
    """Check get_recent_trades method for futures."""
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
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
        "contract": f"{symbol.base}_{symbol.quote}",
        "is_futures": symbol.is_futures,
        "trades_count": len(result),
        "trades": trades_data
    }


@rest_api_test("futures_ticker_info")
async def check_futures_ticker_info(exchange, exchange_name: str):
    """Check get_ticker_info method for futures."""
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)

    # Test single contract ticker
    single_result = await exchange.get_ticker_info(symbol)

    # Test all contracts ticker (limit to first 5 for demo)
    all_result = await exchange.get_ticker_info()

    # Extract single contract data
    ticker = single_result.get(symbol)
    single_ticker_data = {}
    if ticker:
        single_ticker_data = {
            "contract": f"{ticker.symbol.base}_{ticker.symbol.quote}",
            "is_futures": ticker.symbol.is_futures,
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

    # Sample from all contracts
    sample_tickers = []
    for i, (sym, tick) in enumerate(all_result.items()):
        if i >= 5:  # Show first 5 tickers
            break
        sample_tickers.append({
            "contract": f"{sym.base}_{sym.quote}",
            "is_futures": sym.is_futures,
            "last_price": tick.last_price,
            "price_change_percent": tick.price_change_percent,
            "volume": tick.volume
        })

    return {
        "test_contract": f"{symbol.base}_{symbol.quote}",
        "single_ticker_found": symbol in single_result,
        "single_ticker_data": single_ticker_data,
        "all_contracts_count": len(all_result),
        "sample_all_tickers": sample_tickers
    }


@rest_api_test("futures_klines")
async def check_futures_klines(exchange, exchange_name: str):
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)

    date_to = datetime.now()
    date_from = date_to - timedelta(hours=10)

    # Передаем реальный часовой интервал
    result = await exchange.get_klines(
        symbol,
        timeframe=KlineInterval.HOUR_1,
        date_from=date_from,
        date_to=date_to
    )

    klines_data = [
        {
            "open_time": k.open_time,
            "close_time": k.close_time,
            "open_price": k.open_price,
            "high_price": k.high_price,
            "low_price": k.low_price,
            "close_price": k.close_price,
            "volume": k.volume,
            "quote_volume": k.quote_volume,
            "trades_count": k.trades_count
        }
        for k in result
    ]

    return {
        "contract": f"{symbol.base}_{symbol.quote}",
        "is_futures": symbol.is_futures,
        "interval": "1h",
        "klines_count": len(result),
        "klines": klines_data
    }
# Private API Tests
async def check_futures_account_balance(exchange, exchange_name: str):
    """Check get_account_balance method for futures."""
    print(f"\n=== {exchange_name.upper()} FUTURES ACCOUNT BALANCE CHECK ===")
    try:
        result = await exchange.get_account_balance()
        print(f"Total balances: {len(result)}")

        # Show first 5 non-zero balances
        for i, balance in enumerate(result[:5]):
            print(f"Balance {i+1}: {balance.asset}")
            print(f"  Free: {balance.free}")
            print(f"  Locked: {balance.locked}")
            print(f"  Total: {balance.total}")

    except Exception as e:
        print(f"Error: {e}")


async def check_futures_positions(exchange, exchange_name: str):
    """Check get_positions method for futures."""
    print(f"\n=== {exchange_name.upper()} FUTURES POSITIONS CHECK ===")
    try:
        result = await exchange.get_positions()
        print(f"Total positions: {len(result)}")

        # Show all positions (futures typically have fewer active positions)
        for i, position in enumerate(result):
            print(f"Position {i+1}:")
            print(f"  Contract: {position.symbol}")
            print(f"  Side: {position.side}")
            print(f"  Size: {position.size}")
            print(f"  Entry Price: {position.entry_price}")
            print(f"  Mark Price: {position.mark_price}")
            print(f"  Unrealized PnL: {position.unrealized_pnl}")
            print(f"  Percentage: {position.percentage}")

    except Exception as e:
        print(f"Error: {e}")


async def check_futures_place_order(exchange, exchange_name: str):
    """Check place_order method for futures."""
    print(f"\n=== {exchange_name.upper()} FUTURES PLACE ORDER CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)

    try:
        # Place a small limit buy order (this will likely fail due to insufficient funds or invalid price)
        result = await exchange.place_order(
            symbol=symbol,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            amount=0.001,  # Very small position for BTC futures
            price=30000.0,  # Far from market price
            time_in_force=TimeInForce.GTC
        )
        print(f"Futures order placed:")
        print(f"  Order ID: {result.order_id}")
        print(f"  Contract: {result.symbol}")
        print(f"  Side: {result.side}")
        print(f"  Order type: {result.order_type}")
        print(f"  Amount: {result.amount}")
        print(f"  Price: {result.price}")
        print(f"  Status: {result.status}")
        print(f"  Timestamp: {result.timestamp}")

    except Exception as e:
        print(f"Error: {e}")


async def check_futures_open_orders(exchange, exchange_name: str):
    """Check get_open_orders method for futures."""
    print(f"\n=== {exchange_name.upper()} FUTURES OPEN ORDERS CHECK ===")

    try:
        result = await exchange.get_open_orders()
        print(f"Open futures orders count: {len(result)}")

        # Show first 3 open orders
        for i, order in enumerate(result[:3]):
            print(f"Futures Order {i+1}:")
            print(f"  Order ID: {order.order_id}")
            print(f"  Contract: {order.symbol}")
            print(f"  Side: {order.side}")
            print(f"  Order type: {order.order_type}")
            print(f"  Quantity: {order.quantity}")
            print(f"  Price: {order.price}")
            print(f"  Status: {order.status}")
            print(f"  Filled: {order.filled_quantity}")

    except Exception as e:
        print(f"Error: {e}")


async def run_public_tests(exchange_class):
    """Run all public futures API tests."""
    print("GATE.IO FUTURES PUBLIC REST API DEMO")
    print("=" * 50)

    try:
        # Load exchange configuration
        config = get_exchange_config('GATEIO')
        exchange = exchange_class(config)

        # Execute all public API checks for futures
        await check_futures_ping(exchange, 'gateio_futures')
        await check_futures_server_time(exchange, 'gateio_futures')
        await check_futures_exchange_info(exchange, 'gateio_futures')
        await check_futures_orderbook(exchange, 'gateio_futures')
        await check_futures_recent_trades(exchange, 'gateio_futures')
        await check_futures_ticker_info(exchange, 'gateio_futures')
        await check_futures_klines(exchange, 'gateio_futures')

        await exchange.close()

    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Make sure GATEIO configuration is available")
    except Exception as e:
        print(f"Initialization Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 50)
    print("GATE.IO FUTURES PUBLIC API DEMO COMPLETE")


async def run_private_tests(exchange_class):
    """Run all private futures API tests."""
    print("GATE.IO FUTURES PRIVATE REST API DEMO")
    print("=" * 50)

    try:
        # Load exchange configuration and API credentials
        config = get_exchange_config('GATEIO')
        exchange = exchange_class(config)

        # Execute all private API checks for futures
        await check_futures_account_balance(exchange, 'gateio_futures')
        await check_futures_positions(exchange, 'gateio_futures')
        await check_futures_open_orders(exchange, 'gateio_futures')
        await check_futures_place_order(exchange, 'gateio_futures')

        await exchange.close()

    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Make sure GATEIO API credentials are configured")
    except Exception as e:
        print(f"Initialization Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 50)
    print("GATE.IO FUTURES PRIVATE API DEMO COMPLETE")


async def main(test_type: str):
    """Run Gate.io futures API integration tests."""
    public_class, private_class = get_gateio_futures_rest_classes()

    if test_type.lower() in ['public', 'both']:
        await run_public_tests(public_class)

    if test_type.lower() in ['private', 'both']:
        if test_type.lower() == 'both':
            print("\n" + "=" * 70 + "\n")
        await run_private_tests(private_class)


if __name__ == "__main__":
    test_type = sys.argv[1] if len(sys.argv) > 1 else "public"

    if test_type.lower() not in ['public', 'private', 'both']:
        print("Usage: python gateio_futures_demo.py [public|private|both]")
        print("Example: PYTHONPATH=src python3 -m examples.demo.gateio_futures_demo public")
        sys.exit(1)

    try:
        asyncio.run(main(test_type))
        print(f"\n✅ Gate.io futures {test_type} API demo completed successfully!")
    except Exception as e:
        print(f"\n❌ Gate.io futures {test_type} API demo failed: {e}")
        import traceback
        traceback.print_exc()