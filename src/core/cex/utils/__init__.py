"""
Exchange Interface Utils

Unified utilities for exchange integrations including symbol mapping,
performance optimization tools, and common cex implementations.

Factory Pattern Architecture:
- BaseSymbolMapper: Abstract cex for symbol conversion
- ExchangeSymbolMapperFactory: Factory for exchange-specific mappers
- get_symbol_mapper(): Convenience function for mapper access

HFT Performance:
- Sub-microsecond symbol conversion with caching
- O(1) mapper retrieval and symbol lookup
- Memory-bounded cache management
"""

from core.cex.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from core.cex.services.symbol_mapper.symbol_mapper_factory import ExchangeSymbolMapperFactory, get_symbol_mapper
from .kline_utils import get_interval_seconds

__all__ = [
    # New factory pattern (recommended)
    'SymbolMapperInterface',
    'ExchangeSymbolMapperFactory', 
    'get_symbol_mapper',
    
    # Utilities
    'get_interval_seconds',
]