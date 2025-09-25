"""
MEXC Exchange Mapping Configuration

Direct utility mappings for MEXC-specific transformations:
- Order status, type, and side mappings
- Time in force mappings  
- Kline interval mappings
- WebSocket status and type mappings (integer-based)

Direct mappings without BaseExchangeClassifiers dependency.
"""

from exchanges.structs.enums import TimeInForce, KlineInterval
from exchanges.structs import OrderStatus, OrderType, Side



# MEXC Order Status Mapping (Unified enum -> MEXC string)
ORDER_STATUS_MAPPING = {
    OrderStatus.NEW: 'NEW',
    OrderStatus.PARTIALLY_FILLED: 'PARTIALLY_FILLED',
    OrderStatus.FILLED: 'FILLED',
    OrderStatus.CANCELED: 'CANCELED',
    OrderStatus.REJECTED: 'REJECTED',
    OrderStatus.EXPIRED: 'EXPIRED',
}

# MEXC Order Type Mapping (Unified to MEXC API)
ORDER_TYPE_MAPPING = {
    OrderType.LIMIT: 'LIMIT',
    OrderType.MARKET: 'MARKET',
    OrderType.LIMIT_MAKER: 'LIMIT_MAKER',
    OrderType.IMMEDIATE_OR_CANCEL: 'IMMEDIATE_OR_CANCEL',
    OrderType.FILL_OR_KILL: 'FILL_OR_KILL',
    OrderType.STOP_LIMIT: 'STOP_LIMIT',
    OrderType.STOP_MARKET: 'STOP_MARKET',
}

# MEXC Side Mapping (Unified to MEXC API)
SIDE_MAPPING = {
    Side.BUY: 'BUY',
    Side.SELL: 'SELL',
}

# MEXC Time In Force Mapping (Unified to MEXC API)
TIME_IN_FORCE_MAPPING = {
    TimeInForce.GTC: 'GTC',
    TimeInForce.IOC: 'IOC',
    TimeInForce.FOK: 'FOK',
}

# MEXC Kline Interval Mapping (Unified to MEXC API)
KLINE_INTERVAL_MAPPING = {
    KlineInterval.MINUTE_1: "1m",
    KlineInterval.MINUTE_5: "5m",
    KlineInterval.MINUTE_15: "15m",
    KlineInterval.MINUTE_30: "30m",
    KlineInterval.HOUR_1: "1h",
    KlineInterval.HOUR_4: "4h",
    KlineInterval.HOUR_12: "12h",
    KlineInterval.DAY_1: "1d",
    KlineInterval.WEEK_1: "1w",
    KlineInterval.MONTH_1: "1M"
}

# MEXC WebSocket Status Mapping (Unified enum -> MEXC integer)
WS_STATUS_MAPPING = {
    OrderStatus.NEW: 1,
    OrderStatus.PARTIALLY_FILLED: 2,
    OrderStatus.FILLED: 3,
    OrderStatus.CANCELED: 4,
    OrderStatus.PARTIALLY_CANCELED: 5,
    OrderStatus.REJECTED: 6,
    OrderStatus.EXPIRED: 7
}


# MEXC WebSocket Type Mapping (Unified enum -> MEXC integer)
WS_TYPE_MAPPING = {
    OrderType.LIMIT: 1,
    OrderType.MARKET: 2,
    OrderType.LIMIT_MAKER: 3,
    OrderType.IMMEDIATE_OR_CANCEL: 4,
    OrderType.FILL_OR_KILL: 5,
    OrderType.STOP_LIMIT: 6,
    OrderType.STOP_MARKET: 7
}
    

# Create reverse mappings for efficient lookup
ORDER_STATUS_REVERSE = {v: k for k, v in ORDER_STATUS_MAPPING.items()}
ORDER_TYPE_REVERSE = {v: k for k, v in ORDER_TYPE_MAPPING.items()}
SIDE_REVERSE = {v: k for k, v in SIDE_MAPPING.items()}
TIME_IN_FORCE_REVERSE = {v: k for k, v in TIME_IN_FORCE_MAPPING.items()}
KLINE_INTERVAL_REVERSE = {v: k for k, v in KLINE_INTERVAL_MAPPING.items()}
WS_STATUS_REVERSE = {v: k for k, v in WS_STATUS_MAPPING.items()}
WS_TYPE_REVERSE = {v: k for k, v in WS_TYPE_MAPPING.items()}

# Export all mappings for direct usage
__all__ = [
    # Forward mappings (unified -> exchange)
    'ORDER_STATUS_MAPPING', 'ORDER_TYPE_MAPPING', 'SIDE_MAPPING',
    'TIME_IN_FORCE_MAPPING', 'KLINE_INTERVAL_MAPPING',
    'WS_STATUS_MAPPING', 'WS_TYPE_MAPPING',
    # Reverse mappings (exchange -> unified)
    'ORDER_STATUS_REVERSE', 'ORDER_TYPE_REVERSE', 'SIDE_REVERSE',
    'TIME_IN_FORCE_REVERSE', 'KLINE_INTERVAL_REVERSE',
    'WS_STATUS_REVERSE', 'WS_TYPE_REVERSE'
]