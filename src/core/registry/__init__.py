"""
Registry system for dynamic component loading.

This package provides registry patterns for dynamically loading
exchange implementations, factories, and other components based
on configuration.
"""

from .exchange_registry import ExchangeRegistry
from .factory_registry import FactoryRegistry

__all__ = [
    'ExchangeRegistry',
    'FactoryRegistry'
]