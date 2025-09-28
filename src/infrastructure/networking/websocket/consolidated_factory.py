"""
Consolidated WebSocket Factory

Factory functions for creating consolidated WebSocket interfaces that integrate
all functionality directly without intermediate layers.

Features:
- Direct interface creation without WebSocketManager
- Support for both public and private interfaces
- Exchange-specific implementations
- Simplified architecture with better performance
"""

from typing import Optional, Callable, Awaitable

from config.structs import ExchangeConfig
from infrastructure.utils.exchange_utils import exchange_name_to_enum
from infrastructure.networking.websocket.structs import ConnectionState
from exchanges.structs.enums import ExchangeEnum
from exchanges.interfaces.ws.consolidated_interfaces import (
    ConsolidatedPublicWebSocketInterface,
    ConsolidatedPrivateWebSocketInterface
)


def create_consolidated_websocket_interface(
    exchange_config: ExchangeConfig,
    is_private: bool = False,
    user_id: Optional[str] = None,
    connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
) -> ConsolidatedPublicWebSocketInterface | ConsolidatedPrivateWebSocketInterface:
    """
    Create consolidated WebSocket interface for specified exchange.
    
    This factory creates direct WebSocket interfaces without WebSocketManager
    or other intermediate layers, providing optimal performance for HFT trading.
    
    Args:
        exchange_config: Exchange configuration
        is_private: Whether to create private interface (requires credentials)
        user_id: Optional user ID for private interfaces
        connection_handler: Optional callback for connection state changes
        
    Returns:
        Consolidated WebSocket interface (public or private)
        
    Raises:
        ValueError: If exchange is not supported or missing credentials for private
    """
    if is_private and not exchange_config.has_credentials():
        raise ValueError("API credentials required for private WebSocket interface")
    
    exchange = exchange_name_to_enum(exchange_config.name)
    
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.ws.consolidated_mexc_private import MexcConsolidatedPrivateWebSocket
            return MexcConsolidatedPrivateWebSocket(
                config=exchange_config,
                user_id=user_id,
                connection_handler=connection_handler
            )
        else:
            from exchanges.integrations.mexc.ws.consolidated_mexc_public import MexcConsolidatedPublicWebSocket
            return MexcConsolidatedPublicWebSocket(
                config=exchange_config,
                connection_handler=connection_handler
            )
            
    elif exchange == ExchangeEnum.GATEIO_SPOT:
        if is_private:
            from exchanges.integrations.gateio.ws.consolidated_gateio_spot_private import GateioConsolidatedSpotPrivateWebSocket
            return GateioConsolidatedSpotPrivateWebSocket(
                config=exchange_config,
                user_id=user_id,
                connection_handler=connection_handler
            )
        else:
            from exchanges.integrations.gateio.ws.consolidated_gateio_spot_public import GateioConsolidatedSpotPublicWebSocket
            return GateioConsolidatedSpotPublicWebSocket(
                config=exchange_config,
                connection_handler=connection_handler
            )
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            from exchanges.integrations.gateio.ws.consolidated_gateio_futures_private import GateioConsolidatedFuturesPrivateWebSocket
            return GateioConsolidatedFuturesPrivateWebSocket(
                config=exchange_config,
                user_id=user_id,
                connection_handler=connection_handler
            )
        else:
            from exchanges.integrations.gateio.ws.consolidated_gateio_futures_public import GateioConsolidatedFuturesPublicWebSocket
            return GateioConsolidatedFuturesPublicWebSocket(
                config=exchange_config,
                connection_handler=connection_handler
            )
    
    else:
        raise ValueError(f"Exchange {exchange.value} not supported in consolidated architecture")


def create_public_websocket_interface(
    exchange_config: ExchangeConfig,
    connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
) -> ConsolidatedPublicWebSocketInterface:
    """
    Create public WebSocket interface for market data.
    
    Args:
        exchange_config: Exchange configuration
        connection_handler: Optional callback for connection state changes
        
    Returns:
        Public WebSocket interface for market data
    """
    return create_consolidated_websocket_interface(
        exchange_config=exchange_config,
        is_private=False,
        connection_handler=connection_handler
    )


def create_private_websocket_interface(
    exchange_config: ExchangeConfig,
    user_id: Optional[str] = None,
    connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
) -> ConsolidatedPrivateWebSocketInterface:
    """
    Create private WebSocket interface for trading operations.
    
    Args:
        exchange_config: Exchange configuration
        user_id: Optional user ID for private operations
        connection_handler: Optional callback for connection state changes
        
    Returns:
        Private WebSocket interface for trading
        
    Raises:
        ValueError: If exchange configuration lacks required credentials
    """
    return create_consolidated_websocket_interface(
        exchange_config=exchange_config,
        is_private=True,
        user_id=user_id,
        connection_handler=connection_handler
    )


# Convenience factory functions for specific use cases

def create_market_data_interface(exchange_config: ExchangeConfig) -> ConsolidatedPublicWebSocketInterface:
    """
    Create market data interface with default settings.
    
    Args:
        exchange_config: Exchange configuration
        
    Returns:
        Public interface optimized for market data streaming
    """
    return create_public_websocket_interface(exchange_config)


def create_trading_interface(
    exchange_config: ExchangeConfig,
    user_id: Optional[str] = None
) -> ConsolidatedPrivateWebSocketInterface:
    """
    Create trading interface with default settings.
    
    Args:
        exchange_config: Exchange configuration with valid credentials
        user_id: Optional user ID for trading operations
        
    Returns:
        Private interface optimized for trading operations
    """
    return create_private_websocket_interface(exchange_config, user_id)


# Migration helpers for backward compatibility

def migrate_from_websocket_manager(
    exchange_config: ExchangeConfig,
    is_private: bool = False,
    **kwargs
) -> ConsolidatedPublicWebSocketInterface | ConsolidatedPrivateWebSocketInterface:
    """
    Migration helper for code using old WebSocketManager pattern.
    
    Args:
        exchange_config: Exchange configuration
        is_private: Whether to create private interface
        **kwargs: Additional arguments (for compatibility)
        
    Returns:
        Consolidated WebSocket interface
    """
    return create_consolidated_websocket_interface(
        exchange_config=exchange_config,
        is_private=is_private
    )