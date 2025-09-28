"""
WebSocket Adapters Module

This module provides compatibility adapters for seamless dual-path operation
during the migration from strategy pattern to direct message handling.

Key Components:
- WebSocketHandlerAdapter: Wraps new handlers for old WebSocket Manager
- StrategyPatternAdapter: Wraps old strategies for new handler interface
- AdapterConfig: Configuration for adapter behavior
- Factory functions for creating appropriate adapters

Architecture Benefits:
- Zero-downtime migration capability
- Hot-swapping between old and new architectures
- Performance monitoring and circuit breaker patterns
- Gradual rollout support with fallback mechanisms

Usage:
    ```python
    # Wrap new handler for legacy WebSocket Manager
    from infrastructure.networking.websocket.adapters import (
        create_handler_adapter,
        AdapterConfig
    )
    
    config = AdapterConfig(use_direct_handling=True, fallback_on_error=True)
    adapter = create_handler_adapter(new_mexc_handler, config)
    
    # Use adapter with existing WebSocket Manager
    websocket_manager.set_handler(adapter)
    ```

Migration Strategy:
1. Use StrategyPatternAdapter to wrap legacy components in new interface
2. Migrate exchange by exchange to direct handlers
3. Use WebSocketHandlerAdapter to maintain compatibility during transition
4. Remove adapters after full migration completion
"""

from .handler_adapter import (
    WebSocketHandlerAdapter,
    PublicHandlerAdapter,
    PrivateHandlerAdapter,
    AdapterConfig,
    create_handler_adapter
)
from .strategy_adapter import (
    StrategyPatternAdapter,
    create_strategy_adapter
)

__all__ = [
    # Handler adapters (new -> old interface)
    "WebSocketHandlerAdapter",
    "PublicHandlerAdapter", 
    "PrivateHandlerAdapter",
    "create_handler_adapter",
    
    # Strategy adapters (old -> new interface)
    "StrategyPatternAdapter",
    "create_strategy_adapter",
    
    # Configuration
    "AdapterConfig",
]

# Module metadata
__version__ = "1.0.0"
__author__ = "CEX Arbitrage Engine"
__description__ = "Compatibility adapters for WebSocket architecture migration"