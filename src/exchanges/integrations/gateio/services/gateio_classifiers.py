"""
Gate.io Exchange Mapping Configuration

Direct utility mappings for Gate.io-specific transformations:
- Order status, type, and side mappings
- Time in force mappings  
- Kline interval mappings
- Error code mappings

Direct mappings without BaseExchangeClassifiers dependency.
"""

from exchanges.structs.enums import TimeInForce, KlineInterval
from exchanges.structs import OrderStatus, OrderType, Side


# Gate.io Order Status Mapping (Unified enum -> Gate.io string)
ORDER_STATUS_MAPPING = {
    OrderStatus.NEW: 'open',
    OrderStatus.FILLED: 'closed',
    OrderStatus.CANCELED: 'cancelled',
    OrderStatus.EXPIRED: 'expired',
}

# Gate.io Order Type Mapping (Unified to Gate.io API)
ORDER_TYPE_MAPPING = {
    OrderType.LIMIT: 'limit',
    OrderType.MARKET: 'market',
    OrderType.LIMIT_MAKER: 'limit',  # Use regular limit with post_only
    OrderType.IMMEDIATE_OR_CANCEL: 'limit',  # Use limit with time_in_force IOC
    OrderType.FILL_OR_KILL: 'limit',  # Use limit with time_in_force FOK
    OrderType.STOP_LIMIT: 'limit',
    OrderType.STOP_MARKET: 'market',
}

# Gate.io Side Mapping (Unified to Gate.io API)
SIDE_MAPPING = {
    Side.BUY: 'buy',
    Side.SELL: 'sell',
}

# Gate.io Time In Force Mapping (Unified to Gate.io API)
TIME_IN_FORCE_MAPPING = {
    TimeInForce.GTC: 'gtc',
    TimeInForce.IOC: 'ioc',
    TimeInForce.FOK: 'fok',
}

# Gate.io Kline Interval Mapping (Unified to Gate.io API)
KLINE_INTERVAL_MAPPING = {
    KlineInterval.MINUTE_1: "1m",
    KlineInterval.MINUTE_5: "5m",
    KlineInterval.MINUTE_15: "15m",
    KlineInterval.MINUTE_30: "30m",
    KlineInterval.HOUR_1: "1h",
    KlineInterval.HOUR_4: "4h",
    KlineInterval.HOUR_12: "12h",  # Gate.io doesn't have 12h, map to closest
    KlineInterval.DAY_1: "1d",
    KlineInterval.WEEK_1: "7d",  # Gate.io uses 7d instead of 1w
    KlineInterval.MONTH_1: "30d"  # Gate.io uses 30d instead of 1M
}

# Create reverse mappings for efficient lookup
ORDER_STATUS_REVERSE = {v: k for k, v in ORDER_STATUS_MAPPING.items()}
ORDER_TYPE_REVERSE = {v: k for k, v in ORDER_TYPE_MAPPING.items()}
SIDE_REVERSE = {v: k for k, v in SIDE_MAPPING.items()}
TIME_IN_FORCE_REVERSE = {v: k for k, v in TIME_IN_FORCE_MAPPING.items()}
KLINE_INTERVAL_REVERSE = {v: k for k, v in KLINE_INTERVAL_MAPPING.items()}

# Export all mappings for direct usage
__all__ = [
    # Forward mappings (unified -> exchange)
    'ORDER_STATUS_MAPPING', 'ORDER_TYPE_MAPPING', 'SIDE_MAPPING',
    'TIME_IN_FORCE_MAPPING', 'KLINE_INTERVAL_MAPPING',
    # Reverse mappings (exchange -> unified)
    'ORDER_STATUS_REVERSE', 'ORDER_TYPE_REVERSE', 'SIDE_REVERSE',
    'TIME_IN_FORCE_REVERSE', 'KLINE_INTERVAL_REVERSE'
]