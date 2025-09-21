"""
REST API Factory for Exchange Clients

Unified factory function for creating REST exchange clients.
"""

from typing import Optional
from core.factories.rest.public_rest_factory import PublicRestExchangeFactory
from core.factories.rest.private_rest_factory import PrivateRestExchangeFactory
from core.config.config_manager import HftConfig

# Import exchange modules to trigger auto-registration
import cex.mexc.rest
import cex.gateio.rest


def get_exchange_rest_instance(exchange_name: str, is_private: bool = False, config: Optional[any] = None):
    """
    Get a REST client instance using the unified factory pattern.
    
    Args:
        exchange_name: Exchange name (mexc, gateio)
        is_private: Whether to get private client (default: False for public)
        config: Exchange configuration (optional, will use default if None)
        
    Returns:
        REST client instance (public or private)
    """
    if config is None:
        config_manager = HftConfig()
        config = config_manager.get_exchange_config(exchange_name.upper())
    
    exchange_upper = exchange_name.upper()
    
    if is_private:
        return PrivateRestExchangeFactory.inject(exchange_upper, config=config)
    else:
        return PublicRestExchangeFactory.inject(exchange_upper, config=config)
