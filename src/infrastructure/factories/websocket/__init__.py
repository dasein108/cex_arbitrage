"""
WebSocket Exchange Factory Module

Centralized factory patterns for creating and managing WebSocket exchange instances.
Provides consistent creation patterns and dependency injection for all supported
WebSocket exchanges following the same pattern as REST factories.

Key Features:
- Unified WebSocket factory for consistent creation patterns
- Type-safe exchange enumeration and selection
- Automatic dependency injection and configuration
- Exchange-specific optimization and configuration
- Error handling and validation
- Singleton caching for performance

Available Factories:
- PublicWebSocketExchangeFactory: Creates public WebSocket instances
- PrivateWebSocketExchangeFactory: Creates private WebSocket instances
- Auto-configuration of handlers and callback functions
- Exchange selection via ExchangeEnum for type safety

Usage:
    from infrastructure.factories.ws import PublicWebSocketExchangeFactory, PrivateWebSocketExchangeFactory
    from structs.common import ExchangeEnum
    from infrastructure.config.config_manager import HftConfig
    
    # Create MEXC public WebSocket
    config_manager = HftConfig()
    mexc_config = config_manager.get_exchange_config('mexc')
    mexc_public_ws = PublicWebSocketExchangeFactory.inject(
        'MEXC', config=mexc_config,
        orderbook_diff_handler=my_orderbook_handler,
        trades_handler=my_trades_handler
    )
    
    # Create Gate.io futures private WebSocket
    gateio_futures_config = config_manager.get_exchange_config('gateio_futures')
    gateio_futures_private_ws = PrivateWebSocketExchangeFactory.inject(
        'GATEIO_FUTURES', config=gateio_futures_config,
        order_update_handler=my_order_handler,
        balance_update_handler=my_balance_handler
    )

All factory methods ensure proper initialization, service registration,
and dependency injection following SOLID principles and clean architecture.
"""

from .public_websocket_factory import PublicWebSocketExchangeFactory
from .private_websocket_factory import PrivateWebSocketExchangeFactory

__all__ = [
    'PublicWebSocketExchangeFactory',
    'PrivateWebSocketExchangeFactory'
]