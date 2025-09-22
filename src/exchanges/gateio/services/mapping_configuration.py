"""
Gate.io Exchange Mapping Configuration

This module provides Gate.io-specific mapping configurations for:
- Order status, type, and side mappings
- Time in force mappings  
- Kline interval mappings
- Error code mappings

Separated from the main mapper for cleaner architecture and easier maintenance.
"""

from structs.common import OrderStatus, OrderType, Side, TimeInForce, KlineInterval
from core.exchanges.services import BaseMappingConfiguration


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

    
# Factory function for external use
def create_gateio_mapping_configuration() -> BaseMappingConfiguration:
    """
    Factory function to create Gate.io mapping configuration.
    
    Returns:
        BaseMappingConfiguration: Complete Gate.io mapping configuration
    """
    return BaseMappingConfiguration(
        order_status_mapping=ORDER_STATUS_MAPPING,
        order_type_mapping=ORDER_TYPE_MAPPING,
        side_mapping=SIDE_MAPPING,
        time_in_force_mapping=TIME_IN_FORCE_MAPPING,
        kline_interval_mapping=KLINE_INTERVAL_MAPPING
    )