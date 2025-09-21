"""
CEX (Centralized Exchange) Module

Unified interface for all centralized cryptocurrency exchange implementations.
Provides consistent access patterns for both MEXC and Gate.io exchanges through
standardized public and private interfaces.

Key Features:
- Unified exchange enumeration for type-safe exchange selection
- Consistent interface contracts across all exchange implementations  
- Centralized exchange factory for creating exchange instances
- Auto-registration of exchange-specific services and strategies

Exchange Support:
- MEXC: Spot trading with futures support
- Gate.io: Spot trading with comprehensive API coverage

Architecture:
- ExchangeEnum: Type-safe exchange identification
- Interfaces: Unified contracts for all exchange implementations
- Individual exchange modules: Exchange-specific implementations
- Services: Auto-registered mappers and utility services
- Strategies: WebSocket and REST strategy implementations

All exchange implementations follow the same architectural patterns:
- PublicExchangeInterface: Market data operations (no auth required)
- PrivateExchangeInterface: Trading operations (auth required)
- Auto-registration: Services and strategies register automatically on import
"""

# Import interfaces for external access
from .interfaces import PublicExchangeInterface, PrivateExchangeInterface, ExchangeInterface

# Import centralized factory
from .factories import ExchangeFactory
# Auto-import exchange modules to trigger service registration
from . import mexc
from . import gateio
from .consts import ExchangeEnum, DEFAULT_PUBLIC_WEBSOCKET_CHANNELS



__all__ = [
    'PublicExchangeInterface',
    'PrivateExchangeInterface',
    'ExchangeInterface',
    'ExchangeFactory',
    'mexc',
    'gateio',
    'ExchangeEnum',
    'DEFAULT_PUBLIC_WEBSOCKET_CHANNELS'
]
