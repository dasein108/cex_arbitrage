from exchanges.structs import ExchangeEnum

def get_exchange_enum(exchange_name: str) -> ExchangeEnum:
    """
    Convert exchange name string to ExchangeEnum.
    
    Handles common variations like 'mexc' -> ExchangeEnum.MEXC
    
    Args:
        exchange_name: Exchange name (case insensitive)
        
    Returns:
        ExchangeEnum instance
        
    Raises:
        ValueError: If exchange is not supported
    """
    try:
        # First try direct enum name lookup (mexc -> MEXC)
        return ExchangeEnum[exchange_name.upper()]
    except KeyError:
        try:
            # Then try by enum value (MEXC_SPOT -> ExchangeEnum.MEXC)
            return ExchangeEnum(exchange_name.upper())
        except ValueError:
            raise ValueError(f"Exchange '{exchange_name}' is not supported.")