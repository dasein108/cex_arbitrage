"""
MEXC Private API Integration Check

Simple integration checks that call each private API method and display raw responses.
Used for API validation and response verification for authenticated endpoints.
"""

import asyncio
from structs.exchange import Symbol, AssetName, Side, OrderType, TimeInForce
from exchanges.mexc.rest.mexc_private import MexcPrivateExchange


async def check_get_account_balance(exchange: MexcPrivateExchange):
    """Check get_account_balance method."""
    print("=== GET ACCOUNT BALANCE CHECK ===")
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


async def check_get_asset_balance(exchange: MexcPrivateExchange):
    """Check get_asset_balance method."""
    print("\n=== GET ASSET BALANCE CHECK ===")
    asset = AssetName('USDT')
    
    try:
        result = await exchange.get_asset_balance(asset)
        print(f"Asset: {asset}")
        if result:
            print(f"Free: {result.free}")
            print(f"Locked: {result.locked}")
            print(f"Total: {result.total}")
        else:
            print("No balance found for asset")
            
    except Exception as e:
        print(f"Error: {e}")


async def check_place_order(exchange: MexcPrivateExchange):
    """Check place_order method."""
    print("\n=== PLACE ORDER CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    
    try:
        # Place a small limit buy order (this will likely fail due to insufficient funds or invalid price)
        result = await exchange.place_order(
            symbol=symbol,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            amount=0.001,
            price=30000.0,
            time_in_force=TimeInForce.GTC
        )
        print(f"Order placed:")
        print(f"  Order ID: {result.order_id}")
        print(f"  Symbol: {result.symbol}")
        print(f"  Side: {result.side}")
        print(f"  Order type: {result.order_type}")
        print(f"  Amount: {result.amount}")
        print(f"  Price: {result.price}")
        print(f"  Status: {result.status}")
        print(f"  Timestamp: {result.timestamp}")
        
    except Exception as e:
        print(f"Error: {e}")


async def check_get_open_orders(exchange: MexcPrivateExchange):
    """Check get_open_orders method."""
    print("\n=== GET OPEN ORDERS CHECK ===")
    
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
            print(f"  Amount: {order.amount}")
            print(f"  Price: {order.price}")
            print(f"  Status: {order.status}")
            print(f"  Filled: {order.amount_filled}")
            
    except Exception as e:
        print(f"Error: {e}")


async def check_get_order(exchange: MexcPrivateExchange):
    """Check get_order method."""
    print("\n=== GET ORDER CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    order_id = "123456789"  # This will likely fail as order doesn't exist
    
    try:
        result = await exchange.get_order(symbol, order_id)
        print(f"Order details:")
        print(f"  Order ID: {result.order_id}")
        print(f"  Symbol: {result.symbol}")
        print(f"  Side: {result.side}")
        print(f"  Order type: {result.order_type}")
        print(f"  Amount: {result.amount}")
        print(f"  Price: {result.price}")
        print(f"  Status: {result.status}")
        print(f"  Filled: {result.amount_filled}")
        print(f"  Timestamp: {result.timestamp}")
        
    except Exception as e:
        print(f"Error: {e}")


async def check_cancel_order(exchange: MexcPrivateExchange):
    """Check cancel_order method."""
    print("\n=== CANCEL ORDER CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
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


async def check_cancel_all_orders(exchange: MexcPrivateExchange):
    """Check cancel_all_orders method."""
    print("\n=== CANCEL ALL ORDERS CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    
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


async def check_modify_order(exchange: MexcPrivateExchange):
    """Check modify_order method."""
    print("\n=== MODIFY ORDER CHECK ===")
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    order_id = "123456789"  # This will likely fail as order doesn't exist
    
    try:
        result = await exchange.modify_order(
            symbol=symbol,
            order_id=order_id,
            amount=0.002,
            price=31000.0
        )
        print(f"Modified order:")
        print(f"  New Order ID: {result.order_id}")
        print(f"  Symbol: {result.symbol}")
        print(f"  Side: {result.side}")
        print(f"  Amount: {result.amount}")
        print(f"  Price: {result.price}")
        print(f"  Status: {result.status}")
        
    except Exception as e:
        print(f"Error: {e}")


async def main():
    """Run all integration checks."""
    print("MEXC PRIVATE API INTEGRATION CHECKS")
    print("=" * 50)
    
    try:
        exchange = MexcPrivateExchange()
        
        await check_get_account_balance(exchange)
        await check_get_asset_balance(exchange)
        await check_get_open_orders(exchange)
        await check_get_order(exchange)
        await check_place_order(exchange)
        await check_cancel_order(exchange)
        await check_cancel_all_orders(exchange)
        await check_modify_order(exchange)
        
        await exchange.close()
        
    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Make sure MEXC API credentials are configured in config.yaml")
    except Exception as e:
        print(f"Initialization Error: {e}")
    
    print("\n" + "=" * 50)
    print("INTEGRATION CHECKS COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())