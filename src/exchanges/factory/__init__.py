"""
Exchange Factory Package.

Provides factory classes for creating composite exchanges with migration support.
Supports both legacy unified interface and new composite pattern.
"""

from .composite_exchange_factory import CompositeExchangeFactory
from .enhanced_factory import EnhancedExchangeFactory, get_global_factory, create_exchange_simple
from .migration_adapter import UnifiedToCompositeAdapter, LegacyInterfaceWarning
from .exchange_registry import ExchangeRegistry, ExchangePair, ExchangeType, ExchangeImplementation

__all__ = [
    "CompositeExchangeFactory",
    "EnhancedExchangeFactory", 
    "UnifiedToCompositeAdapter",
    "LegacyInterfaceWarning",
    "ExchangeRegistry",
    "ExchangePair",
    "ExchangeType",
    "ExchangeImplementation",
    "get_global_factory",
    "create_exchange_simple"
]

# Version info
__version__ = "1.0.0"
__author__ = "HFT Arbitrage Team"