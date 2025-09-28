"""
WebSocket Utilities - Mixin-Based Architecture

Factory functions for creating WebSocket managers with mixin-based handlers.
Replaces strategy pattern with composition-based handlers for better performance
and maintainability.

HFT COMPLIANCE: Sub-millisecond handler creation, optimized for direct processing.
"""

from typing import Optional
from config.structs import ExchangeConfig, WebSocketConfig
from infrastructure.networking.websocket.ws_manager import WebSocketManager
from infrastructure.utils.exchange_utils import exchange_name_to_enum
from exchanges.structs.enums import ExchangeEnum


def create_websocket_manager(
    exchange_config: ExchangeConfig,
    is_private: bool = False,
    message_handler=None,  # Deprecated - handlers manage message processing directly
    connection_handler=None,
    **kwargs
) -> WebSocketManager:
    """
    Factory function to create WebSocketManager with mixin-based handlers.

    Creates WebSocket transport using composition-based handlers instead of 
    strategy pattern for optimal HFT performance and simplified architecture.

    Args:
        exchange_config: Exchange configuration
        is_private: Whether to use private API (requires credentials)
        message_handler: Deprecated - handlers process messages directly
        connection_handler: Callback for connection state changes
        **kwargs: Additional arguments for WebSocketManager

    Returns:
        WebSocketManager with mixin-based handler

    Raises:
        ValueError: If exchange is not supported or missing credentials
    """
    if is_private and not exchange_config.has_credentials():
        raise ValueError("API key and secret key required for private WebSocket access")

    # Create mixin-based handler based on exchange
    exchange = exchange_name_to_enum(exchange_config.name)
    
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.ws.handlers.private_handler import MexcPrivateWebSocketHandler
            direct_handler = MexcPrivateWebSocketHandler(config=exchange_config)
        else:
            from exchanges.integrations.mexc.ws.handlers.public_handler import MexcPublicWebSocketHandler
            direct_handler = MexcPublicWebSocketHandler(config=exchange_config)
            
    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            from exchanges.integrations.gateio.ws.handlers.spot_private_handler import GateioSpotPrivateWebSocketHandler
            direct_handler = GateioSpotPrivateWebSocketHandler(config=exchange_config)
        else:
            from exchanges.integrations.gateio.ws.handlers.spot_public_handler import GateioSpotPublicWebSocketHandler  
            direct_handler = GateioSpotPublicWebSocketHandler(config=exchange_config)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            from exchanges.integrations.gateio.ws.handlers.futures_private_handler import GateioFuturesPrivateWebSocketHandler
            direct_handler = GateioFuturesPrivateWebSocketHandler(config=exchange_config)
        else:
            from exchanges.integrations.gateio.ws.handlers.futures_public_handler import GateioFuturesPublicWebSocketHandler
            direct_handler = GateioFuturesPublicWebSocketHandler(config=exchange_config)
            
    else:
        raise ValueError(f"Exchange {exchange.value} WebSocket handlers not implemented")
    
    # Create and return WebSocketManager with mixin-based handler
    return WebSocketManager(
        config=WebSocketConfig(
            url=exchange_config.websocket_url,
            heartbeat_interval=30.0,  # Default heartbeat interval
        ),
        direct_handler=direct_handler,
        connection_handler=connection_handler,
        **kwargs
    )


def create_websocket_handler_direct(
    exchange_config: ExchangeConfig,
    is_private: bool = False,
    connection_handler=None,
    **kwargs
):
    """
    Factory function to create handlers using BaseWebSocketInterface directly.
    
    Creates WebSocket handlers that inherit from BaseWebSocketInterface directly,
    bypassing WebSocketManager for use cases that need direct interface access.
    
    Args:
        exchange_config: Exchange configuration
        is_private: Whether to use private API (requires credentials)
        connection_handler: Callback for connection state changes
        **kwargs: Additional arguments for BaseWebSocketInterface
        
    Returns:
        Handler instance that extends BaseWebSocketInterface
        
    Raises:
        ValueError: If exchange is not supported or missing credentials
    """
    if is_private and not exchange_config.has_credentials():
        raise ValueError("API key and secret key required for private WebSocket access")

    # Create handler that implements BaseWebSocketInterface
    exchange = exchange_name_to_enum(exchange_config.name)
    
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.ws.handlers.private_handler import MexcPrivateWebSocketHandler
            return MexcPrivateWebSocketHandler(config=exchange_config)
        else:
            from exchanges.integrations.mexc.ws.handlers.public_handler import MexcPublicWebSocketHandler
            return MexcPublicWebSocketHandler(config=exchange_config)
            
    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            from exchanges.integrations.gateio.ws.handlers.spot_private_handler import GateioSpotPrivateWebSocketHandler
            return GateioSpotPrivateWebSocketHandler(config=exchange_config)
        else:
            from exchanges.integrations.gateio.ws.handlers.spot_public_handler import GateioSpotPublicWebSocketHandler  
            return GateioSpotPublicWebSocketHandler(config=exchange_config)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            from exchanges.integrations.gateio.ws.handlers.futures_private_handler import GateioFuturesPrivateWebSocketHandler
            return GateioFuturesPrivateWebSocketHandler(config=exchange_config)
        else:
            from exchanges.integrations.gateio.ws.handlers.futures_public_handler import GateioFuturesPublicWebSocketHandler
            return GateioFuturesPublicWebSocketHandler(config=exchange_config)
            
    else:
        raise ValueError(f"Exchange {exchange.value} handlers not implemented")