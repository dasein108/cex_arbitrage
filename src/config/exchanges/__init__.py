"""
Exchange configuration management module.

Provides specialized configuration management for exchange settings including:
- Exchange-specific configuration
- Direct credential management via environment variables
- API endpoint configuration
- Rate limiting and performance settings
"""

from .exchange_config import ExchangeConfigManager

__all__ = [
    'ExchangeConfigManager'
]