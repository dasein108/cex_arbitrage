"""
CEX Exchange Interfaces

Unified interface definitions for all CEX (centralized exchange) implementations.
Provides consistent contracts for both public and private exchange operations.

This module centralizes interface definitions that were previously scattered
across individual exchange implementations, promoting code reuse and 
consistency across all exchange integrations.

Available Interfaces:
- PublicExchangeInterface: Market data operations (no authentication)
- PrivateExchangeInterface: Trading operations (requires authentication)
- ExchangeInterface: Combined interface for full exchange implementations

All exchange implementations should inherit from these interfaces to ensure
consistent behavior across the arbitrage engine.
"""

from interfaces.exchanges.base import (
    BasePublicExchangeInterface,
    BasePrivateExchangeInterface, 
    BaseExchangeInterface
)

# Create convenient aliases for CEX module usage
PublicExchangeInterface = BasePublicExchangeInterface
PrivateExchangeInterface = BasePrivateExchangeInterface  
ExchangeInterface = BaseExchangeInterface

__all__ = [
    'PublicExchangeInterface',
    'PrivateExchangeInterface', 
    'ExchangeInterface'
]