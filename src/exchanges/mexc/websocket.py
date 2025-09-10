# MEXC WebSocket Main Entry Point
# 
# This file now serves as the main entry point for MEXC WebSocket functionality,
# importing the separated public and private stream implementations for better
# code organization and maintainability.

from typing import Any, Dict, List, Optional, Callable, Coroutine

from structs.exchange import ExchangeName

# Import separated WebSocket stream implementations
from exchanges.mexc.mexc_ws_public import MexcWebSocketPublicStream
from exchanges.mexc.mexc_ws_private import MexcWebSocketPrivateStream


# Re-export main classes for backward compatibility
__all__ = [
    'MexcWebSocketPublicStream',
    'MexcWebSocketPrivateStream'
]


def create_public_stream(
    exchange_name: ExchangeName,
    on_message: Callable[[Dict[str, Any]], Coroutine],
    timeout: float = 30.0,
    on_connected: Optional[Callable[[], Coroutine]] = None,
    on_restart: Optional[Callable[[], Coroutine]] = None,
    streams: List[str] = None,
    max_retries: int = 10
) -> MexcWebSocketPublicStream:
    """
    Factory function to create MEXC public WebSocket stream.
    
    Args:
        exchange_name: Exchange identifier
        on_message: Callback for WebSocket messages
        timeout: Connection timeout in seconds
        on_connected: Optional callback when connection is established
        on_restart: Optional callback when connection is restarted
        streams: List of streams to subscribe to
        max_retries: Maximum connection retry attempts
        
    Returns:
        Configured MexcWebSocketPublicStream instance
    """
    return MexcWebSocketPublicStream(
        exchange_name=exchange_name,
        on_message=on_message,
        timeout=timeout,
        on_connected=on_connected,
        on_restart=on_restart,
        streams=streams,
        max_retries=max_retries
    )


def create_private_stream(
    exchange_name: ExchangeName,
    listen_key: str,
    on_message: Callable[[Dict[str, Any]], Coroutine],
    timeout: float = 30.0,
    on_connected: Optional[Callable[[], Coroutine]] = None,
    on_restart: Optional[Callable[[], Coroutine]] = None,
    max_retries: int = 10
) -> MexcWebSocketPrivateStream:
    """
    Factory function to create MEXC private WebSocket stream.
    
    Args:
        exchange_name: Exchange identifier
        listen_key: Authentication listen key from MEXC API
        on_message: Callback for WebSocket messages
        timeout: Connection timeout in seconds
        on_connected: Optional callback when connection is established
        on_restart: Optional callback when connection is restarted
        max_retries: Maximum connection retry attempts
        
    Returns:
        Configured MexcWebSocketPrivateStream instance
    """
    return MexcWebSocketPrivateStream(
        exchange_name=exchange_name,
        listen_key=listen_key,
        on_message=on_message,
        timeout=timeout,
        on_connected=on_connected,
        on_restart=on_restart,
        max_retries=max_retries
    )