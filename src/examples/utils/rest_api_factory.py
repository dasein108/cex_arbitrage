"""
REST API Factory for Exchange Clients

Unified factory function for creating REST exchange clients.
"""

from typing import Optional
from infrastructure.transport_factory import create_rest_client
from config import HftConfig

# Import exchange modules to trigger auto-registration

# Trigger manual registration after modules are loaded
from exchanges.integrations.mexc.rest.registration import register_mexc_rest_implementations
from exchanges.integrations.gateio.rest.registration import register_gateio_rest_implementations

register_mexc_rest_implementations()
register_gateio_rest_implementations()


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
    
    from exchanges.structs import ExchangeEnum
    exchange_enum = ExchangeEnum(exchange_upper)
    
    return create_rest_client(
        exchange=exchange_enum,
        config=config,
        is_private=is_private
    )
