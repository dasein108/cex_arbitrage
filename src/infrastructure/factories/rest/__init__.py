"""
REST Factory Module

Provides factory infrastructure for creating REST exchange implementations.
Follows the established BaseExchangeFactory pattern with auto-registration support.
"""

from .public_rest_factory import PublicRestExchangeFactory
from .private_rest_factory import PrivateRestExchangeFactory

__all__ = [
    "PublicRestExchangeFactory",
    "PrivateRestExchangeFactory"
]