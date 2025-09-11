# MEXC WebSocket Main Entry Point
# 
# This file now serves as the main entry point for MEXC WebSocket functionality,
# importing the separated public and private stream implementations for better
# code organization and maintainability.

from typing import Any, Dict, Optional, Callable, Coroutine

from exchanges.interface.websocket.base_ws import WebSocketConfig

# Import separated WebSocket stream implementations
from exchanges.mexc.ws.mexc_ws_public import MexcWebSocketPublicStream
from exchanges.mexc.ws.mexc_ws_private import MexcWebSocketPrivateStream


# Re-export main classes for backward compatibility
__all__ = [
    'MexcWebSocketPublicStream',
    'MexcWebSocketPrivateStream'
]


def create_public_stream(
    message_handler: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
    error_handler: Optional[Callable[[Exception], Coroutine]] = None,
    timeout: float = 30.0,
    ping_interval: float = 15.0,
    max_reconnect_attempts: int = 20,
    **config_overrides
) -> MexcWebSocketPublicStream:
    """
    Factory function to create MEXC public WebSocket stream.
    
    Args:
        message_handler: Callback for processed WebSocket messages
        error_handler: Callback for error handling
        timeout: Connection timeout in seconds
        ping_interval: WebSocket ping interval
        max_reconnect_attempts: Maximum connection retry attempts
        **config_overrides: Additional WebSocket configuration overrides
        
    Returns:
        Configured MexcWebSocketPublicStream instance
    """
    # Create configuration with defaults
    config_dict = {
        'url': "wss://wbs-api.mexc.com/ws",
        'timeout': timeout,
        'ping_interval': ping_interval,
        'ping_timeout': 5.0,
        'close_timeout': 3.0,
        'max_reconnect_attempts': max_reconnect_attempts,
        'reconnect_delay': 0.5,
        'reconnect_backoff': 1.5,
        'max_reconnect_delay': 30.0,
        'max_message_size': 2 * 1024 * 1024,
        'max_queue_size': 5000,
        'heartbeat_interval': 20.0,
        'enable_compression': True
    }
    
    # Apply any configuration overrides
    config_dict.update(config_overrides)
    ws_config = WebSocketConfig(**config_dict)
    
    return MexcWebSocketPublicStream(
        message_handler=message_handler,
        error_handler=error_handler,
        config=ws_config
    )


def create_private_stream(
    listen_key: str,
    message_handler: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
    error_handler: Optional[Callable[[Exception], Coroutine]] = None,
    timeout: float = 30.0,
    ping_interval: float = 15.0,
    max_reconnect_attempts: int = 20,
    **config_overrides
) -> MexcWebSocketPrivateStream:
    """
    Factory function to create MEXC private WebSocket stream.
    
    Args:
        listen_key: Authentication listen key from MEXC API
        message_handler: Callback for processed WebSocket messages
        error_handler: Callback for error handling
        timeout: Connection timeout in seconds
        ping_interval: WebSocket ping interval
        max_reconnect_attempts: Maximum connection retry attempts
        **config_overrides: Additional WebSocket configuration overrides
        
    Returns:
        Configured MexcWebSocketPrivateStream instance
    """
    # Create configuration with defaults (private stream uses different URL)
    config_dict = {
        'url': f"wss://wbs.mexc.com/ws?listenKey={listen_key}",
        'timeout': timeout,
        'ping_interval': ping_interval,
        'ping_timeout': 5.0,
        'close_timeout': 3.0,
        'max_reconnect_attempts': max_reconnect_attempts,
        'reconnect_delay': 0.5,
        'reconnect_backoff': 1.5,
        'max_reconnect_delay': 30.0,
        'max_message_size': 2 * 1024 * 1024,
        'max_queue_size': 5000,
        'heartbeat_interval': 20.0,
        'enable_compression': True
    }
    
    # Apply any configuration overrides
    config_dict.update(config_overrides)
    ws_config = WebSocketConfig(**config_dict)
    
    return MexcWebSocketPrivateStream(
        message_handler=message_handler,
        error_handler=error_handler,
        config=ws_config
    )