"""
Generic Private REST API Integration Demo

Demonstrates private API functionality across multiple exchanges.
Tests core private methods: account balance, orders, trading operations.

Usage:
    python src/examples/rest_private_demo.py mexc
    python src/examples/rest_private_demo.py gateio
"""

import asyncio
import sys
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from exchanges.structs.enums import TimeInForce
from exchanges.structs import OrderType, Side
from exchanges.interfaces.rest import PrivateSpotRestInterface
from config.config_manager import HftConfig
from exchanges.exchange_factory import create_rest_client


async def check_get_account_balance(exchange: PrivateSpotRestInterface, exchange_name: str):
    """Check get_account_balance method."""
    print(f"\n=== {exchange_name.upper()} GET ACCOUNT BALANCE CHECK ===")
    try:
        result = await exchange.get_balances()
        print(f"Total balances: {len(result)}")
        
        # Show first 5 non-zero balances
        for i, balance in enumerate(result[:5]):
            print(f"Balance {i+1}: {balance.asset}")
            print(f"  Free: {balance.available}")
            print(f"  Locked: {balance.locked}")
            print(f"  Total: {balance.total}")
            
    except Exception as e:
        print(f"Error: {e}")


async def check_get_asset_balance(exchange: PrivateSpotRestInterface, exchange_name: str):
    """Check get_asset_balance method."""
    print(f"\n=== {exchange_name.upper()} GET ASSET BALANCE CHECK ===")
    asset = AssetName('USDT')
    
    try:
        result = await exchange.get_asset_balance(asset)
        print(f"Asset: {asset}")
        if result:
            print(f"Free: {result.available}")
            print(f"Locked: {result.locked}")
            print(f"Total: {result.total}")
        else:
            print("No balance found for asset")
            
    except Exception as e:
        print(f"Error: {e}")


async def check_place_order(exchange: PrivateSpotRestInterface, exchange_name: str):
    """Check place_order method."""
    print(f"\n=== {exchange_name.upper()} PLACE ORDER CHECK ===")
    symbol = Symbol(base=AssetName('ADA'), quote=AssetName('USDT'))
    
    try:
        # Place a small limit buy order (this will likely fail due to insufficient funds or invalid price)
        result = await exchange.place_order(
            symbol=symbol,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=3000.0,
            time_in_force=TimeInForce.GTC
        )
        print(f"Order placed:")
        print(f"  Order ID: {result.order_id}")
        print(f"  Symbol: {result.symbol}")
        print(f"  Side: {result.side}")
        print(f"  Order type: {result.order_type}")
        print(f"  Amount: {result.quantity}")
        print(f"  Price: {result.price}")
        print(f"  Status: {result.status}")
        print(f"  Timestamp: {result.timestamp}")
        
    except Exception as e:
        print(f"Error: {e}")


async def check_get_open_orders(exchange: PrivateSpotRestInterface, exchange_name: str):
    """Check get_open_orders method."""
    print(f"\n=== {exchange_name.upper()} GET OPEN ORDERS CHECK ===")
    
    try:
        result = await exchange.get_open_orders()
        print(f"Open orders count: {len(result)}")
        
        # Show first 3 open orders
        for i, order in enumerate(result[:3]):
            print(f"Order {i+1}:")
            print(f"  Order ID: {order.order_id}")
            print(f"  Symbol: {order.symbol}")
            print(f"  Side: {order.side}")
            print(f"  Order type: {order.order_type}")
            print(f"  Quantity: {order.quantity}")
            print(f"  Price: {order.price}")
            print(f"  Status: {order.status}")
            print(f"  Filled: {order.filled_quantity}")
            
    except Exception as e:
        print(f"Error: {e}")


async def check_get_order(exchange: PrivateSpotRestInterface, exchange_name: str):
    """Check get_order method."""
    print(f"\n=== {exchange_name.upper()} GET ORDER CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'))
    order_id = "123456789"  # This will likely fail as order doesn't exist
    
    try:
        result = await exchange.get_order(symbol, order_id)
        print(f"Order details:")
        print(f"  Order ID: {result.order_id}")
        print(f"  Symbol: {result.symbol}")
        print(f"  Side: {result.side}")
        print(f"  Order type: {result.order_type}")
        print(f"  Amount: {result.quantity}")
        print(f"  Price: {result.price}")
        print(f"  Status: {result.status}")
        print(f"  Filled: {result.filled_quantity}")
        print(f"  Timestamp: {result.timestamp}")
        
    except Exception as e:
        print(f"Error: {e}")


async def check_cancel_order(exchange: PrivateSpotRestInterface, exchange_name: str):
    """Check cancel_order method."""
    print(f"\n=== {exchange_name.upper()} CANCEL ORDER CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'))
    order_id = "123456789"  # This will likely fail as order doesn't exist
    
    try:
        result = await exchange.cancel_order(symbol, order_id)
        print(f"Cancelled order:")
        print(f"  Order ID: {result.order_id}")
        print(f"  Symbol: {result.symbol}")
        print(f"  Status: {result.status}")
        print(f"  Timestamp: {result.timestamp}")
        
    except Exception as e:
        print(f"Error: {e}")


async def check_cancel_all_orders(exchange: PrivateSpotRestInterface, exchange_name: str):
    """Check cancel_all_orders method."""
    print(f"\n=== {exchange_name.upper()} CANCEL ALL ORDERS CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'))
    
    try:
        result = await exchange.cancel_all_orders(symbol)
        print(f"Cancelled orders count: {len(result)}")
        
        # Show cancelled orders
        for i, order in enumerate(result):
            print(f"Cancelled order {i+1}:")
            print(f"  Order ID: {order.order_id}")
            print(f"  Symbol: {order.symbol}")
            print(f"  Status: {order.status}")
            
    except Exception as e:
        print(f"Error: {e}")


async def main(exchange_name: str):
    """Run all private API integration checks for the specified exchange."""
    print(f"{exchange_name.upper()} PRIVATE REST API INTEGRATION DEMO")
    print("=" * 50)
    
    try:
        # Load exchange configuration and API credentials
        config_manager = HftConfig()
        config = config_manager.get_exchange_config(exchange_name.lower())
        # Use unified factory function for private REST clients
        from utils.exchange_utils import get_exchange_enum
        exchange = get_exchange_enum(exchange_name)
        exchange = create_rest_client(exchange, is_private=True, config=config)
        
        # Execute all private API checks
        await check_get_account_balance(exchange, exchange_name)
        await check_get_asset_balance(exchange, exchange_name)
        await check_get_open_orders(exchange, exchange_name)
        await check_get_order(exchange, exchange_name)
        await check_place_order(exchange, exchange_name)
        await check_cancel_order(exchange, exchange_name)
        await check_cancel_all_orders(exchange, exchange_name)

        await exchange.close()
        
    except ValueError as e:
        print(f"Configuration Error: {e}")
        print(f"Make sure {exchange_name.upper()} API credentials are configured")
    except Exception as e:
        print(f"Initialization Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print(f"{exchange_name.upper()} PRIVATE API DEMO COMPLETE")


if __name__ == "__main__":
    exchange_name = sys.argv[1] if len(sys.argv) > 1 else "mexc_spot"

    try:
        asyncio.run(main(exchange_name))
        print(f"\n✅ {exchange_name.upper()} private API demo completed successfully!")
    except Exception as e:
        print(f"\n❌ {exchange_name.upper()} private API demo failed: {e}")
        import traceback
        traceback.print_exc()