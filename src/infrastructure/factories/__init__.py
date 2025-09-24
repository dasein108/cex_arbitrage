"""
Infrastructure Factories

PARTIALLY CONSOLIDATED: Transport factories have been simplified.

Use infrastructure.transport_factory for REST/WebSocket client creation.
Remaining base classes are still used by strategy factories.

TODO: Consider simplifying strategy factories in future refactoring.
"""

from .factory_interface import ExchangeFactoryInterface
from .base_exchange_factory import BaseExchangeFactory
from .base_composite_factory import BaseCompositeFactory

__all__ = [
    'ExchangeFactoryInterface',
    'BaseExchangeFactory',
    'BaseCompositeFactory'
]