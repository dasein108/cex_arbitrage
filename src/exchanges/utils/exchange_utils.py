from exchanges.structs import ExchangeEnum

def get_exchange_enum(exchange_name: str) -> ExchangeEnum:
    """
    Convert user-friendly exchange names to canonical semantic ExchangeEnum format.
    
    Implements the semantic naming convention migration from the documentation:
    - mexc -> ExchangeEnum.MEXC (mexc_spot)
    - gateio -> ExchangeEnum.GATEIO (gateio_spot)
    - gateio_futures -> ExchangeEnum.GATEIO_FUTURES
    
    Args:
        exchange_name: User input exchange name (case insensitive)
        
    Returns:
        ExchangeEnum instance using semantic format
        
    Raises:
        ValueError: If exchange is not supported
        
    Examples:
        get_exchange_enum("mexc") -> ExchangeEnum.MEXC
        get_exchange_enum("gateio") -> ExchangeEnum.GATEIO
        get_exchange_enum("gateio_futures") -> ExchangeEnum.GATEIO_FUTURES
    """
    # Normalize input
    normalized_name = exchange_name.lower().strip()
    
    # Mapping from user-friendly names to semantic format
    mappings = {
        "mexc": ExchangeEnum.MEXC,
        "mexc_spot": ExchangeEnum.MEXC,
        "gateio": ExchangeEnum.GATEIO,
        "gateio_spot": ExchangeEnum.GATEIO,
        "gate": ExchangeEnum.GATEIO,
        "gate_spot": ExchangeEnum.GATEIO,
        "gateio_futures": ExchangeEnum.GATEIO_FUTURES,
        "gateio_fut": ExchangeEnum.GATEIO_FUTURES,
        "gate_futures": ExchangeEnum.GATEIO_FUTURES
    }
    
    # Direct mapping lookup
    if normalized_name in mappings:
        return mappings[normalized_name]
    
    # Fallback: try direct enum lookup for exact matches
    try:
        return ExchangeEnum[normalized_name.upper()]
    except KeyError:
        try:
            # Try by enum value (MEXC_SPOT -> ExchangeEnum.MEXC)
            return ExchangeEnum(normalized_name.upper())
        except ValueError:
            # List supported exchanges for better error message
            supported = list(mappings.keys())
            raise ValueError(f"Exchange '{exchange_name}' is not supported. Supported exchanges: {supported}")