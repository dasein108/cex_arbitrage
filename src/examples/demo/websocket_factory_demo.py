#!/usr/bin/env python3
"""
WebSocket Factory Pattern Demo

Demonstrates the new unified WebSocket factory pattern that follows the same
approach as the REST factory. Shows how to create WebSocket instances using
both direct factory calls and the utility function.

This replaces the old pattern of manually importing WebSocket classes.
"""

import asyncio
import logging
from typing import List

# New factory-based approach
from core.factories.websocket import PublicWebSocketExchangeFactory, PrivateWebSocketExchangeFactory
from examples.utils.ws_api_factory import get_exchange_websocket_instance
from core.config.config_manager import HftConfig

# Common types
from structs.common import Symbol, OrderBook, Trade, BookTicker, AssetName
from core.transport.websocket.structs import ConnectionState

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demo_direct_factory_usage():
    """Demonstrate direct factory usage (advanced usage)."""
    print("\n=== Direct Factory Usage Demo ===")
    
    config_manager = HftConfig()
    
    # Create MEXC public WebSocket using direct factory
    mexc_config = config_manager.get_exchange_config('mexc')
    mexc_ws = PublicWebSocketExchangeFactory.inject(
        'MEXC', 
        config=mexc_config,
        orderbook_diff_handler=handle_orderbook_update,
        trades_handler=handle_trades_update,
        state_change_handler=handle_connection_state
    )
    print(f"✅ Created MEXC WebSocket: {type(mexc_ws).__name__}")
    
    # Create Gate.io futures WebSocket using direct factory  
    gateio_futures_config = config_manager.get_exchange_config('gateio_futures')
    gateio_futures_ws = PublicWebSocketExchangeFactory.inject(
        'GATEIO_FUTURES',
        config=gateio_futures_config,
        orderbook_diff_handler=handle_orderbook_update,
        trades_handler=handle_trades_update,
        state_change_handler=handle_connection_state
    )
    print(f"✅ Created Gate.io futures WebSocket: {type(gateio_futures_ws).__name__}")
    
    # Demonstrate available exchanges
    available_public = PublicWebSocketExchangeFactory.get_available_exchanges()
    available_private = PrivateWebSocketExchangeFactory.get_available_exchanges()
    print(f"📋 Available public WebSocket exchanges: {available_public}")
    print(f"📋 Available private WebSocket exchanges: {available_private}")
    
    return mexc_ws, gateio_futures_ws


async def demo_utility_function_usage():
    """Demonstrate utility function usage (recommended for most cases)."""
    print("\n=== Utility Function Usage Demo ===")
    
    # Create WebSocket instances using the utility function (simple approach)
    mexc_ws = get_exchange_websocket_instance(
        'mexc',
        is_private=False,
        orderbook_diff_handler=handle_orderbook_update,
        trades_handler=handle_trades_update,
        state_change_handler=handle_connection_state
    )
    print(f"✅ Created MEXC WebSocket via utility: {type(mexc_ws).__name__}")
    
    gateio_ws = get_exchange_websocket_instance(
        'gateio',
        is_private=False,
        orderbook_diff_handler=handle_orderbook_update,
        trades_handler=handle_trades_update,
        state_change_handler=handle_connection_state
    )
    print(f"✅ Created Gate.io WebSocket via utility: {type(gateio_ws).__name__}")
    
    # Gate.io futures as separate exchange
    gateio_futures_ws = get_exchange_websocket_instance(
        'gateio_futures',
        is_private=False,
        orderbook_diff_handler=handle_orderbook_update,
        trades_handler=handle_trades_update,
        state_change_handler=handle_connection_state
    )
    print(f"✅ Created Gate.io futures WebSocket via utility: {type(gateio_futures_ws).__name__}")
    
    return mexc_ws, gateio_ws, gateio_futures_ws


# Event handlers
async def handle_orderbook_update(orderbook: OrderBook, symbol: Symbol):
    """Handle orderbook updates."""
    print(f"📊 Orderbook update for {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")


async def handle_trades_update(symbol: Symbol, trades: List[Trade]):
    """Handle trade updates."""
    print(f"💰 Trade update for {symbol}: {len(trades)} trades")


async def handle_connection_state(state: ConnectionState):
    """Handle connection state changes."""
    print(f"🔗 Connection state changed: {state}")


async def main():
    """Main demo function."""
    print("🚀 WebSocket Factory Pattern Demo")
    print("=" * 50)
    
    try:
        # Demo 1: Direct factory usage
        mexc_ws1, gateio_futures_ws1 = await demo_direct_factory_usage()
        
        # Demo 2: Utility function usage (recommended)
        mexc_ws2, gateio_ws2, gateio_futures_ws2 = await demo_utility_function_usage()
        
        print("\n=== Factory Pattern Benefits ===")
        print("✅ Consistent API across REST and WebSocket")
        print("✅ Automatic registration and dependency injection")
        print("✅ Type-safe exchange selection")
        print("✅ Singleton caching for performance")
        print("✅ Support for Gate.io futures as separate exchange")
        print("✅ Clean separation between public and private operations")
        
        print("\n=== Migration from Old Pattern ===")
        print("❌ Old: from exchanges.mexc.ws import MexcWebsocketPublic")
        print("❌ Old: ws = MexcWebsocketPublic(...)")
        print("✅ New: ws = get_exchange_websocket_instance('mexc', ...)")
        
        # Note: In a real application, you would call initialize() and connect
        # Here we just demonstrate the factory pattern
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())