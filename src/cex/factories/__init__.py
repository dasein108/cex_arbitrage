"""
CEX Exchange Factory Module

Centralized factory patterns for creating and managing CEX exchange instances.
Provides consistent creation patterns and dependency injection for all supported
centralized exchanges (MEXC, Gate.io).

Key Features:
- Unified exchange factory for consistent creation patterns
- Type-safe exchange enumeration and selection
- Automatic dependency injection and configuration
- Exchange-specific optimization and configuration
- Error handling and validation

Available Factories:
- ExchangeFactory: Creates exchange instances with proper configuration
- Exchange selection via ExchangeEnum for type safety
- Auto-configuration of REST clients, WebSocket clients, and services

Usage:
    from cex.factories import ExchangeFactory
    from cex import ExchangeEnum
    
    # Create MEXC public exchange
    mexc_public = ExchangeFactory.create_public_exchange(
        ExchangeEnum.MEXC, symbols=['BTCUSDT', 'ETHUSDT']
    )
    
    # Create Gate.io private exchange
    gateio_private = ExchangeFactory.create_private_exchange(
        ExchangeEnum.GATEIO, config=exchange_config
    )

All factory methods ensure proper initialization, service registration,
and dependency injection following SOLID principles and clean architecture.
"""

from .exchange_factory import ExchangeFactory

__all__ = [
    'ExchangeFactory'
]