from exchanges.structs import Order, OrderStatus

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
    normalized_name = exchange_name.upper()

    try:
        return ExchangeEnum(normalized_name)
    except Exception:
        supported = [e.value for e in ExchangeEnum]
        raise ValueError(f"Exchange '{exchange_name}' is not supported. Supported exchanges: {supported}")

def is_order_done(order: Order) -> bool:
    """Check if order is done (filled or cancelled)."""
    return order.status in {OrderStatus.FILLED,
                            OrderStatus.CANCELED,
                            OrderStatus.REJECTED,
                            OrderStatus.EXPIRED,
                            OrderStatus.PARTIALLY_CANCELED}