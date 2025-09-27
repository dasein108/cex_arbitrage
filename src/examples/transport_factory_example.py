"""
Transport Factory Usage Example

Shows how to use the updated transport factory with handler objects
for creating WebSocket and REST clients.
"""

import asyncio
from exchanges.structs import ExchangeEnum
from config.structs import ExchangeConfig, ExchangeCredentials
from exchanges.factory import (
    create_rest_client,
    create_public_handlers,
    create_private_handlers
)


async def example_handler_orderbook(orderbook_update):
    """Example orderbook handler."""
    print(f"📊 Orderbook update: {orderbook_update}")


async def example_handler_trades(trade):
    """Example trade handler."""
    print(f"💱 Trade: {trade}")


async def example_handler_order(order):
    """Example order update handler."""
    print(f"📋 Order update: {order}")


async def example_handler_balance(balances):
    """Example balance handler."""
    print(f"💰 Balance update: {len(balances)} assets")


async def main():
    """Demonstrate transport factory usage with handler objects."""
    
    # Example exchange config (replace with real credentials)
    config = ExchangeConfig(
        name="mexc",
        base_url="https://api.mexc.com",
        websocket_url="wss://wbs-api.mexc.com",
        credentials=ExchangeCredentials(
            api_key="your_api_key_here",
            secret_key="your_secret_key_here"
        )
    )
    
    print("🚀 Transport Factory with Handler Objects Example")
    print("=" * 60)
    
    # 1. REST Client Creation (unchanged)
    print("\n1. Creating REST clients...")
    
    try:
        # Public REST client
        public_rest = create_rest_client(
            exchange=ExchangeEnum.MEXC,
            config=config,
            is_private=False
        )
        print("✅ Public REST client created")
        
        # Private REST client (requires valid credentials)
        # private_rest = create_rest_client(
        #     exchange=ExchangeEnum.MEXC,
        #     config=config,
        #     is_private=True
        # )
        # print("✅ Private REST client created")
        
    except Exception as e:
        print(f"⚠️ REST client creation skipped: {e}")
    
    # 2. WebSocket Client Creation (NEW - with handler objects)
    print("\n2. Creating WebSocket clients with handler objects...")
    
    try:
        # Create handler objects using convenience functions
        public_handlers = create_public_handlers(
            orderbook_diff_handler=example_handler_orderbook,
            trades_handler=example_handler_trades
        )
        
        private_handlers = create_private_handlers(
            order_handler=example_handler_order,
            balance_handler=example_handler_balance
        )
        
        print("✅ Handler objects created")
        
        # Create WebSocket clients with handler objects
        # Public WebSocket client
        # public_ws = create_websocket_client(
        #     exchange=ExchangeEnum.MEXC,
        #     config=config,
        #     handlers=public_handlers,
        #     is_private=False
        # )
        # print("✅ Public WebSocket client created")
        
        # Private WebSocket client (requires valid credentials)
        # private_ws = create_websocket_client(
        #     exchange=ExchangeEnum.MEXC,
        #     config=config,
        #     handlers=private_handlers,
        #     is_private=True
        # )
        # print("✅ Private WebSocket client created")
        
    except Exception as e:
        print(f"⚠️ WebSocket client creation skipped: {e}")
    
    # 3. Alternative - Direct handler creation
    print("\n3. Creating handlers directly...")
    
    from infrastructure.networking.websocket.handlers import (
        PublicWebsocketHandlers, 
        PrivateWebsocketHandlers
    )
    
    # Direct handler creation
    public_handlers_direct = PublicWebsocketHandlers(
        trade_handler=example_handler_trades,
        book_ticker_handler=None  # Optional handlers
    )
    
    private_handlers_direct = PrivateWebsocketHandlers(
        order_handler=example_handler_order
        # balance_handler and trade_handler are optional
    )
    
    print("✅ Direct handler objects created")
    
    # 4. Error handling examples
    print("\n4. Error handling examples...")
    
    try:
        # This should fail - wrong handler type
        wrong_handlers = create_public_handlers()
        
        # This would fail if we tried to create a private client with public handlers
        # create_websocket_client(
        #     exchange=ExchangeEnum.MEXC,
        #     config=config,
        #     handlers=wrong_handlers,  # Wrong type!
        #     is_private=True  # Expects PrivateWebsocketHandlers
        # )
        
    except ValueError as e:
        print(f"✅ Type validation working: {e}")
    
    print("\n✅ Transport factory examples completed!")
    
    print("\nKey Benefits of Handler Objects:")
    print("  • Type safety - correct handler type enforced")
    print("  • Clean organization - related handlers grouped")
    print("  • Optional handlers - only set what you need")
    print("  • Better error messages - clear validation")
    print("  • Easier maintenance - single object parameter")
    
    print("\nUsage Summary:")
    print("  1. Create handler objects with your callback functions")
    print("  2. Pass handler object to create_websocket_client()")
    print("  3. Factory validates handler type matches client type")
    print("  4. WebSocket client uses handlers for message routing")


if __name__ == "__main__":
    asyncio.run(main())