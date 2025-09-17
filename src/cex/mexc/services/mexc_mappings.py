"""
MEXC Exchange Mappings Implementation

MEXC-specific implementation of the exchange-agnostic mapping interface.
Provides MEXC API format conversions and order transformations.

HFT COMPLIANCE: Sub-microsecond mapping operations, zero-copy patterns.
"""

from datetime import datetime
from typing import Any

from structs.exchange import (
    Order, OrderId, OrderStatus, OrderType, Side,
    TimeInForce, KlineInterval
)
from core.cex.services.unified_mapper.exchange_mappings import BaseExchangeMappings, MappingConfiguration


class MexcMappings(BaseExchangeMappings):
    """
    MEXC-specific mapping implementation.
    
    Handles conversion between unified types and MEXC API formats.
    Uses configuration-driven approach for maintainable mappings.
    """
    
    def __init__(self, symbol_mapper):
        """Initialize MEXC mappings with exchange-specific configuration."""
        config = MexcMappings._create_mexc_config()
        super().__init__(symbol_mapper, config)
    
    @staticmethod
    def _create_mexc_config() -> MappingConfiguration:
        """Create MEXC-specific mapping configuration."""
        return MappingConfiguration(
            # MEXC Order Status Mapping (exchange_status -> unified)
            order_status_mapping={
                'NEW': OrderStatus.NEW,
                'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
                'FILLED': OrderStatus.FILLED,
                'CANCELED': OrderStatus.CANCELED,
                'REJECTED': OrderStatus.REJECTED,
                'EXPIRED': OrderStatus.EXPIRED,
            },
            
            # MEXC Order Type Mapping (unified -> exchange)
            order_type_mapping={
                OrderType.LIMIT: 'LIMIT',
                OrderType.MARKET: 'MARKET',
                OrderType.LIMIT_MAKER: 'LIMIT_MAKER',
                OrderType.IMMEDIATE_OR_CANCEL: 'IMMEDIATE_OR_CANCEL',
                OrderType.FILL_OR_KILL: 'FILL_OR_KILL',
                OrderType.STOP_LIMIT: 'STOP_LIMIT',
                OrderType.STOP_MARKET: 'STOP_MARKET',
            },
            
            # MEXC Side Mapping (unified -> exchange)
            side_mapping={
                Side.BUY: 'BUY',
                Side.SELL: 'SELL',
            },
            
            # MEXC Time In Force Mapping (unified -> exchange)
            time_in_force_mapping={
                TimeInForce.GTC: 'GTC',
                TimeInForce.IOC: 'IOC',
                TimeInForce.FOK: 'FOK',
                TimeInForce.GTD: 'GTD',
            },
            
            # MEXC Kline Interval Mapping (unified -> exchange)
            kline_interval_mapping={
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
        )
    
    def transform_exchange_order_to_unified(self, mexc_order: Any) -> Order:
        """
        Transform MEXC order response to unified Order struct.
        
        Args:
            mexc_order: MEXC order response structure
            
        Returns:
            Unified Order struct
        """
        # Convert MEXC symbol to unified Symbol
        symbol = self.pair_to_symbol(mexc_order.symbol)
        
        # Calculate fee from fills if available
        fee = 0.0
        if hasattr(mexc_order, 'fills') and mexc_order.fills:
            fee = sum(float(fill.get('commission', '0')) for fill in mexc_order.fills)
        
        return Order(
            symbol=symbol,
            side=self.get_unified_side(mexc_order.side),
            order_type=self.get_unified_order_type(mexc_order.type),
            price=float(mexc_order.price),
            amount=float(mexc_order.origQty),
            amount_filled=float(mexc_order.executedQty),
            order_id=OrderId(str(mexc_order.orderId)),
            status=self.get_unified_order_status(mexc_order.status),
            timestamp=datetime.fromtimestamp(mexc_order.transactTime / 1000) if mexc_order.transactTime else None,
            fee=fee
        )