from exchanges.structs import Order, OrderStatus, Symbol, ExchangeEnum, Side
from typing import List


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
    
    # Map user-friendly names to enum names (not values)
    name_mapping = {
        'mexc': 'MEXC',
        'mexc_spot': 'MEXC', 
        'gateio': 'GATEIO',
        'gateio_spot': 'GATEIO',
        'gateio_futures': 'GATEIO_FUTURES'
    }
    
    # Try direct mapping first
    if normalized_name in name_mapping:
        enum_name = name_mapping[normalized_name]
        return getattr(ExchangeEnum, enum_name)
    
    # Try uppercase as enum name (for direct enum name input)
    try:
        return getattr(ExchangeEnum, normalized_name.upper())
    except AttributeError:
        pass
    
    # Try as enum value (for compatibility)
    try:
        return ExchangeEnum(normalized_name.upper())
    except ValueError:
        pass
    
    # If all fails, provide helpful error
    available_names = list(name_mapping.keys())
    available_values = [e.value for e in ExchangeEnum]
    raise ValueError(f"Unsupported exchange: {exchange_name}. Available: {available_names + available_values}")


def is_order_done(order: Order) -> bool:
    """Check if order is done (filled or cancelled)."""
    return order.status in {OrderStatus.FILLED,
                            OrderStatus.CANCELED,
                            OrderStatus.REJECTED,
                            OrderStatus.EXPIRED,
                            OrderStatus.PARTIALLY_CANCELED}

def is_order_filled(order: Order) -> bool:
    """Check if order is completely filled."""
    return order.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED, OrderStatus.PARTIALLY_CANCELED]

def flip_side(side: Side) -> Side:
    """Flip order side."""
    return Side.BUY if side == Side.SELL else Side.SELL