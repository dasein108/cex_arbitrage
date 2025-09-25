"""
Symbol Mapper Interface

Base interface for exchange-specific symbol mappers.
Factory pattern has been removed in favor of global singleton instances.
"""

from .base_symbol_mapper import SymbolMapperInterface

__all__ = [
    'SymbolMapperInterface'
]