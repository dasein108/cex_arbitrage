from structs.exchange import OrderStatus, OrderType


status_mapping = {
    1: OrderStatus.NEW,
    2: OrderStatus.PARTIALLY_FILLED,
    3: OrderStatus.FILLED,
    4: OrderStatus.CANCELED,
    5: OrderStatus.PARTIALLY_CANCELED,
    6: OrderStatus.REJECTED,
    7: OrderStatus.EXPIRED
}

type_mapping = {
    1: OrderType.LIMIT,
    2: OrderType.MARKET,
    3: OrderType.LIMIT_MAKER,
    4: OrderType.IMMEDIATE_OR_CANCEL,
    5: OrderType.FILL_OR_KILL,
    6: OrderType.STOP_LIMIT,
    7: OrderType.STOP_MARKET
}