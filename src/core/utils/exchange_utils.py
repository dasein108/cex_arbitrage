"""
Exchange Utility Functions

Helper functions for consistent ExchangeEnum handling across factories and services.
Prevents code duplication and ensures consistent exchange key normalization.
"""

from typing import Union
from infrastructure.data_structures.common import ExchangeEnum


def exchange_name_to_enum(exchange: Union[str, ExchangeEnum]) -> ExchangeEnum:
    """
    Normalize exchange input to ExchangeEnum.
    
    Only accepts clean exchange names, no composite keys with _public/_private suffixes.
    
    Args:
        exchange: Exchange as string or ExchangeEnum
        
    Returns:
        ExchangeEnum instance
        
    Raises:
        ValueError: If exchange string is not recognized
    """
    if isinstance(exchange, ExchangeEnum):
        return exchange

    try:
        return ExchangeEnum(exchange.upper())
    except ValueError:
        # If we get here, the exchange is not recognized
        available_exchanges = [e.value for e in ExchangeEnum]
        raise ValueError(
            f"Unknown exchange: {exchange}. "
            f"Available exchanges: {available_exchanges}"
        )


