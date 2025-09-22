"""
Exchange Utility Functions

Helper functions for consistent ExchangeEnum handling across factories and services.
Prevents code duplication and ensures consistent exchange key normalization.
"""

from typing import Union
from structs.common import ExchangeEnum


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
    
    # Handle string input
    if isinstance(exchange, str):
        exchange_upper = exchange.upper()
        
        # Try direct enum name mapping first
        for enum_item in ExchangeEnum:
            if enum_item.name == exchange_upper:
                return enum_item
            if str(enum_item.value) == exchange_upper:
                return enum_item
        
        # Try common alias mappings
        alias_mapping = {
            "MEXC": ExchangeEnum.MEXC,
            "MEXC_SPOT": ExchangeEnum.MEXC,
            "GATEIO": ExchangeEnum.GATEIO,
            "GATEIO_SPOT": ExchangeEnum.GATEIO,
            "GATEIO_FUTURES": ExchangeEnum.GATEIO_FUTURES,
            "GATE": ExchangeEnum.GATEIO,
            "GATE_IO": ExchangeEnum.GATEIO,
        }
        
        if exchange_upper in alias_mapping:
            return alias_mapping[exchange_upper]
    
    # If we get here, the exchange is not recognized
    available_exchanges = [e.value for e in ExchangeEnum]
    raise ValueError(
        f"Unknown exchange: {exchange}. "
        f"Available exchanges: {available_exchanges}"
    )


def exchange_to_key(exchange: Union[str, ExchangeEnum]) -> str:
    """
    Convert exchange to normalized string key for factory registries.
    
    Args:
        exchange: Exchange as string or ExchangeEnum
        
    Returns:
        Normalized string key for use in factory registries
    """
    enum_exchange = exchange_name_to_enum(exchange)
    return enum_exchange.value


def get_all_exchange_keys() -> list[str]:
    """
    Get all available exchange keys.
    
    Returns:
        List of all exchange keys (values)
    """
    return [e.value for e in ExchangeEnum]


def get_all_exchanges() -> list[ExchangeEnum]:
    """
    Get all available exchanges as enums.
    
    Returns:
        List of all ExchangeEnum values
    """
    return list(ExchangeEnum)