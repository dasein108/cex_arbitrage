"""
WebSocket API Factory for Exchange Clients

Unified factory function for creating WebSocket exchange clients following
the same pattern as REST factory. Uses the new WebSocket factory infrastructure.
"""

from typing import Optional, Callable, Awaitable, List
from infrastructure.transport_factory import create_websocket_client, PublicWebsocketHandlers, PrivateWebsocketHandlers
from config import HftConfig
from exchanges.structs.common import Symbol, OrderBook, Trade, BookTicker, Order, AssetBalance
from infrastructure.networking.websocket.structs import ConnectionState

# Import exchange modules to trigger auto-registration

# Trigger manual WebSocket registration after modules are loaded
from exchanges.integrations.mexc.ws.registration import register_mexc_websocket_implementations
from exchanges.integrations.gateio.ws.registration import register_gateio_websocket_implementations

# Trigger manual REST registration (WebSocket depends on REST)
from exchanges.integrations.mexc.rest.registration import register_mexc_rest_implementations
from exchanges.integrations.gateio.rest.registration import register_gateio_rest_implementations

register_mexc_websocket_implementations()
register_gateio_websocket_implementations()
register_mexc_rest_implementations()
register_gateio_rest_implementations()


def get_exchange_websocket_instance(exchange_name: str, is_private: bool = False, config: Optional[any] = None,
                                   orderbook_diff_handler: Optional[Callable[[OrderBook, Symbol], Awaitable[None]]] = None,
                                   trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
                                   book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
                                   order_update_handler: Optional[Callable[[Symbol, Order], Awaitable[None]]] = None,
                                   balance_update_handler: Optional[Callable[[AssetBalance], Awaitable[None]]] = None,
                                   state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None):
    """
    Get a WebSocket client instance using the unified factory pattern.
    
    Args:
        exchange_name: Exchange name (mexc, gateio, gateio_futures)
        is_private: Whether to get private client (default: False for public)
        config: Exchange configuration (optional, will use default if None)
        orderbook_diff_handler: Callback for orderbook updates
        trades_handler: Callback for trade updates
        book_ticker_handler: Callback for book ticker updates
        order_update_handler: Callback for order updates (private only)
        balance_update_handler: Callback for balance updates (private only)
        state_change_handler: Callback for connection state changes
        
    Returns:
        WebSocket client instance (public or private)
    """
    if config is None:
        config_manager = HftConfig()
        config = config_manager.get_exchange_config(exchange_name.lower())
    
    exchange_upper = exchange_name.upper()
    
    from exchanges.structs import ExchangeEnum
    exchange_enum = ExchangeEnum(exchange_upper)
    
    # Create appropriate handler class based on client type
    if is_private:
        handlers = PrivateWebsocketHandlers(
            order_handler=order_update_handler,
            balance_handler=balance_update_handler,
            trade_handler=trades_handler,  # Note: private uses trade_handler
            state_change_handler=state_change_handler
        )
    else:
        handlers = PublicWebsocketHandlers(
            orderbook_diff_handler=orderbook_diff_handler,
            trades_handler=trades_handler,
            book_ticker_handler=book_ticker_handler,
            state_change_handler=state_change_handler
        )
    
    return create_websocket_client(
        exchange=exchange_enum,
        config=config,
        is_private=is_private,
        handlers=handlers
    )


