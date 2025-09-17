"""
Gate.io Exchange Unified Mappings Implementation

Gate.io-specific implementation of the exchange-agnostic mapping interface.
Provides Gate.io API format conversions and order transformations following
the same pattern as MEXC.

HFT COMPLIANCE: Sub-microsecond mapping operations, zero-copy patterns.
"""

from datetime import datetime
from typing import Any

from structs.exchange import (
    Order, OrderId, OrderStatus, OrderType, Side,
    TimeInForce, KlineInterval
)
from core.cex.services.unified_mapper.exchange_mappings import BaseExchangeMappings, MappingConfiguration
from .gateio_mappings import GateioMappings


class GateioUnifiedMappings(BaseExchangeMappings):
    """
    Gate.io-specific unified mapping implementation.
    
    Handles conversion between unified types and Gate.io API formats.
    Uses configuration-driven approach for maintainable mappings.
    """
    
    def __init__(self, symbol_mapper):
        """Initialize Gate.io mappings with exchange-specific configuration."""
        config = GateioUnifiedMappings._create_gateio_config()
        super().__init__(symbol_mapper, config)
    
    @staticmethod
    def _create_gateio_config() -> MappingConfiguration:
        """Create Gate.io-specific mapping configuration."""
        # Create proper KlineInterval enum mapping for Gate.io
        kline_interval_mapping = {
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
        
        return MappingConfiguration(
            # Order status mapping - Gate.io to Unified
            order_status_mapping=GateioMappings.ORDER_STATUS_MAPPING,
            
            # Order type mapping - Unified to Gate.io
            order_type_mapping=GateioMappings.ORDER_TYPE_MAPPING,
            
            # Side mapping - Unified to Gate.io
            side_mapping=GateioMappings.SIDE_MAPPING,
            
            # Time in force mapping - Unified to Gate.io
            time_in_force_mapping=GateioMappings.TIME_IN_FORCE_MAPPING,
            
            # Kline interval mapping - Unified to Gate.io
            kline_interval_mapping=kline_interval_mapping
        )
    
    def get_exchange_side(self, side: Side) -> str:
        """Convert unified Side to Gate.io API format."""
        return self._config.side_mapping.get(side, side.name.lower())
    
    def get_unified_side(self, gate_side: str) -> Side:
        """Convert Gate.io side to unified Side."""
        return GateioMappings.SIDE_REVERSE_MAPPING.get(gate_side.lower(), Side.BUY)
    
    def get_exchange_order_type(self, order_type: OrderType) -> str:
        """Convert unified OrderType to Gate.io API format."""
        return self._config.order_type_mapping.get(order_type, order_type.name.lower())
    
    def get_exchange_time_in_force(self, tif: TimeInForce) -> str:
        """Convert unified TimeInForce to Gate.io API format."""
        return self._config.time_in_force_mapping.get(tif, tif.name.lower())
    
    def get_exchange_interval(self, interval: KlineInterval) -> str:
        """Convert unified KlineInterval to Gate.io API format."""
        return self._config.kline_interval_mapping.get(interval, "1m")
    
    def get_unified_order_status(self, gate_status: str) -> OrderStatus:
        """Convert Gate.io order status to unified OrderStatus."""
        return GateioMappings.ORDER_STATUS_REVERSE_MAPPING.get(gate_status, OrderStatus.UNKNOWN)
    
    def transform_balance_to_unified(self, gate_balance: dict) -> 'AssetBalance':
        """Transform Gate.io balance response to unified AssetBalance."""
        from structs.exchange import AssetBalance, AssetName
        
        return AssetBalance(
            asset=AssetName(gate_balance.get('currency', '')),
            available=float(gate_balance.get('available', '0')),
            free=float(gate_balance.get('available', '0')),  # Gate.io uses 'available' for free
            locked=float(gate_balance.get('locked', '0'))
        )
    
    def transform_exchange_order_to_unified(self, gate_order: dict) -> Order:
        """Transform Gate.io order response to unified Order."""
        # Extract basic order information
        order_id = OrderId(gate_order.get('id', ''))
        symbol_str = gate_order.get('currency_pair', '')
        symbol = self._symbol_mapper.to_symbol(symbol_str)
        
        # Convert Gate.io status to unified status
        gate_status = gate_order.get('status', 'open')
        status = self.get_unified_order_status(gate_status)
        
        # Convert Gate.io side to unified side
        gate_side = gate_order.get('side', 'buy')
        side = self.get_unified_side(gate_side)
        
        # Convert Gate.io type to unified type (reverse lookup needed)
        gate_type = gate_order.get('type', 'limit')
        order_type = self._reverse_lookup_order_type(gate_type)
        
        # Gate.io API fields based on official documentation:
        # - filled_amount: actual filled amount (not filled_total)
        # - left: remaining amount to be filled
        filled_amount = float(gate_order.get('filled_amount', '0'))
        total_amount = float(gate_order.get('amount', '0'))
        remaining_amount = float(gate_order.get('left', total_amount - filled_amount))
        
        return Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=total_amount,
            price=float(gate_order.get('price', '0')) if gate_order.get('price') else None,
            amount_filled=filled_amount,
            status=status,
            timestamp=int(float(gate_order.get('create_time', '0')) * 1000),  # Convert to milliseconds
            # update_time=int(float(gate_order.get('update_time', '0')) * 1000) if gate_order.get('update_time') else None
        )
    
    def _reverse_lookup_order_type(self, gate_type: str) -> OrderType:
        """Reverse lookup Gate.io order type to unified OrderType."""
        # Create reverse mapping from order type mapping
        reverse_mapping = {v: k for k, v in self._config.order_type_mapping.items()}
        return reverse_mapping.get(gate_type, OrderType.LIMIT)
    
    def format_quantity(self, quantity: float) -> str:
        """Format quantity for Gate.io API (typically 8 decimal places)."""
        return f"{quantity:.8f}".rstrip('0').rstrip('.')
    
    def format_price(self, price: float) -> str:
        """Format price for Gate.io API (typically 8 decimal places)."""
        return f"{price:.8f}".rstrip('0').rstrip('.')
    
    def get_order_params(self, order_type: OrderType, time_in_force: TimeInForce) -> dict:
        """Get additional order parameters for specific order types."""
        params = {}
        
        # Gate.io specific parameters based on order type
        if order_type == OrderType.MARKET:
            # Market orders don't need additional parameters in Gate.io
            pass
        elif order_type == OrderType.LIMIT:
            # Limit orders are default, no additional parameters needed
            pass
        elif order_type == OrderType.LIMIT_MAKER:
            # Post-only orders in Gate.io
            params['time_in_force'] = 'poc'  # Post-only
        
        return params