"""
MEXC Exchange Mapping Configuration

This module provides MEXC-specific mapping configurations for:
- Order status, type, and side mappings
- Time in force mappings  
- Kline interval mappings
- WebSocket status and type mappings (integer-based)

Separated from the main mapper for cleaner architecture and easier maintenance.
"""

from structs.common import OrderStatus, OrderType, Side, TimeInForce, KlineInterval
from core.exchanges.services import BaseMappingConfiguration


class MexcMappingConfiguration:
    """MEXC-specific mapping configuration factory."""
    
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
    
    @classmethod
    def create_mapping_configuration(cls) -> BaseMappingConfiguration:
        """
        Create MEXC-specific mapping configuration.
        
        Returns:
            BaseMappingConfiguration: Complete configuration for MEXC mappings
        """
        return BaseMappingConfiguration(
            order_status_mapping=cls.ORDER_STATUS_MAPPING,
            order_type_mapping=cls.ORDER_TYPE_MAPPING,
            side_mapping=cls.SIDE_MAPPING,
            time_in_force_mapping=cls.TIME_IN_FORCE_MAPPING,
            kline_interval_mapping=cls.KLINE_INTERVAL_MAPPING
        )
    
# Factory function for external use
def create_mexc_mapping_configuration() -> BaseMappingConfiguration:
    """
    Factory function to create MEXC mapping configuration.
    
    Returns:
        BaseMappingConfiguration: Complete MEXC mapping configuration
    """
    return MexcMappingConfiguration.create_mapping_configuration()