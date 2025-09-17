"""
WebSocket Transport Utilities

Factory utilities for creating WebSocket managers with proper strategy injection.
Provides unified interface for WebSocket creation similar to REST transport pattern.

HFT COMPLIANT: Sub-millisecond strategy creation with pre-validated combinations.
"""

from core.config.structs import ExchangeConfig
from .ws_manager import WebSocketManager, WebSocketManagerConfig
from .strategies import WebSocketStrategyFactory


def create_websocket_manager(
    exchange_config: ExchangeConfig,
    is_private: bool = False,
    message_handler=None,
    state_change_handler=None,
    **kwargs
) -> WebSocketManager:
    """
    Factory function to create WebSocketManager with exchange strategies.

    Preferred method for creating WebSocket transport with integrated strategy pattern,
    authentication, subscription management, and message parsing.

    Args:
        exchange_config: Exchange configuration
        is_private: Whether to use private API (requires credentials)
        message_handler: Callback for parsed messages
        state_change_handler: Callback for connection state changes
        **kwargs: Additional strategy configuration

    Returns:
        WebSocketManager with configured strategies

    Raises:
        ValueError: If private API requested but no credentials available
    """
    if is_private and not exchange_config.has_credentials():
        raise ValueError("API key and secret key required for private WebSocket access")

    # Create strategy set using factory pattern
    exchange_name = str(exchange_config.name).upper()
    strategy_key = f"{exchange_name}_{'PRIVATE' if is_private else 'PUBLIC'}"
    
    strategy_set = WebSocketStrategyFactory.inject(
        strategy_key,
        config=exchange_config,
        **kwargs
    )

    # Configure manager for HFT performance
    manager_config = WebSocketManagerConfig(
        batch_processing_enabled=True,
        batch_size=100,
        max_pending_messages=1000,
        enable_performance_tracking=True
    )

    # Create and return WebSocket manager
    return WebSocketManager(
        config=exchange_config.websocket,
        strategies=strategy_set,
        message_handler=message_handler,
        manager_config=manager_config,
        state_change_handler=state_change_handler
    )