"""
Core Factories Module

Provides generic factory infrastructure for exchange-based services with
standardized patterns for registration, dependency injection, and lifecycle management.

HFT COMPLIANCE: Sub-millisecond factory operations with pre-compiled registries.
"""

from .base_exchange_factory import BaseExchangeFactory

__all__ = [
    "BaseExchangeFactory"
]