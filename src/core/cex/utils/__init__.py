"""
Exchange Interface Utils

Unified utilities for exchange integrations including symbol mapping,
performance optimization tools, and common cex implementations.

Factory Pattern Architecture:
- BaseSymbolMapper: Abstract cex for symbol conversion
- ExchangeSymbolMapperFactory: Factory for exchange-specific mappers

HFT Performance:
- Sub-microsecond symbol conversion with caching
- O(1) mapper retrieval and symbol lookup
- Memory-bounded cache management
"""

from core.cex.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from core.cex.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
from .kline_utils import get_interval_seconds

__all__ = [
    # New factory pattern (recommended)
    'SymbolMapperInterface',
    'ExchangeSymbolMapperFactory', 

    # Utilities
    'get_interval_seconds',
]