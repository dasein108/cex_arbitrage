"""
MEXC Exchange Mappings and Utilities

Collection of mapping constants, utility functions, and conversion helpers used across MEXC exchange implementations.
Contains error code mappings, order status mappings, type conversion mappings, and utility functions.

Key Features:
- Unified exception hierarchy mappings
- Order status and type conversions  
- Side mappings for BUY/SELL operations
- Reverse mappings for API response processing
- Symbol conversion utilities with smart detection
- MEXC-specific formatting functions for prices and quantities
- All constants optimized for performance lookups

Threading: All functions are thread-safe as they're pure functions
Performance: Dict-based lookups optimized for O(1) access with minimal allocations
"""

from datetime import datetime
from structs.exchange import Symbol, Order, OrderId, OrderStatus, OrderType, Side, TimeInForce, KlineInterval
from cex.mexc.services.symbol_mapper import MexcSymbolMapper

class MexcMappings:
    """MEXC API mapping service using dependency injection pattern."""
    
    def __init__(self, symbol_mapper: MexcSymbolMapper):
        """Initialize mappings with injected symbol mapper dependency."""
        self._symbol_mapper = symbol_mapper

    
    # MEXC Order Status Mapping to Unified Status
    ORDER_STATUS_MAPPING = {
        'NEW': OrderStatus.NEW,
        'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
        'FILLED': OrderStatus.FILLED,
        'CANCELED': OrderStatus.CANCELED,
        'REJECTED': OrderStatus.REJECTED,
        'EXPIRED': OrderStatus.EXPIRED,
    }
    
    # Unified Order Type to MEXC API Mapping
    ORDER_TYPE_MAPPING = {
        OrderType.LIMIT: 'LIMIT',
        OrderType.MARKET: 'MARKET',
        OrderType.LIMIT_MAKER: 'LIMIT_MAKER',
        OrderType.IMMEDIATE_OR_CANCEL: 'IMMEDIATE_OR_CANCEL',
        OrderType.FILL_OR_KILL: 'FILL_OR_KILL',
        OrderType.STOP_LIMIT: 'STOP_LIMIT',
        OrderType.STOP_MARKET: 'STOP_MARKET',
    }
    
    # Reverse mapping for API responses (MEXC -> Unified)
    ORDER_TYPE_REVERSE_MAPPING = {v: k for k, v in ORDER_TYPE_MAPPING.items()}
    
    # Unified Side to MEXC API Mapping
    SIDE_MAPPING = {
        Side.BUY: 'BUY',
        Side.SELL: 'SELL',
    }
    
    # Reverse mapping for API responses (MEXC -> Unified)
    SIDE_REVERSE_MAPPING = {v: k for k, v in SIDE_MAPPING.items()}
    
    # Unified TimeInForce to MEXC API Mapping
    TIME_IN_FORCE_MAPPING = {
        TimeInForce.GTC: 'GTC',
        TimeInForce.IOC: 'IOC',
        TimeInForce.FOK: 'FOK',
        TimeInForce.GTD: 'GTD',
    }
    
    # Reverse mapping for API responses (MEXC -> Unified)
    TIME_IN_FORCE_REVERSE_MAPPING = {v: k for k, v in TIME_IN_FORCE_MAPPING.items()}
    
    def get_unified_order_status(self, mexc_status: str) -> OrderStatus:
        """
        Convert MEXC order status string to unified OrderStatus enum.
        
        Args:
            mexc_status: MEXC order status string
            
        Returns:
            Unified OrderStatus enum value
        """
        return self.ORDER_STATUS_MAPPING.get(mexc_status, OrderStatus.UNKNOWN)
    
    def get_mexc_order_type(self, unified_type: OrderType) -> str:
        """
        Convert unified OrderType to MEXC API order type string.
        
        Args:
            unified_type: Unified OrderType enum value
            
        Returns:
            MEXC API order type string
        """
        return self.ORDER_TYPE_MAPPING.get(unified_type, 'LIMIT')
    
    def get_unified_order_type(self, mexc_type: str) -> OrderType:
        """
        Convert MEXC order type string to unified OrderType enum.
        
        Args:
            mexc_type: MEXC order type string
            
        Returns:
            Unified OrderType enum value
        """
        return self.ORDER_TYPE_REVERSE_MAPPING.get(mexc_type, OrderType.LIMIT)
    
    def get_mexc_side(self, unified_side: Side) -> str:
        """
        Convert unified Side to MEXC API side string.
        
        Args:
            unified_side: Unified Side enum value
            
        Returns:
            MEXC API side string
        """
        return self.SIDE_MAPPING.get(unified_side, 'BUY')
    
    def get_unified_side(self, mexc_side: str) -> Side:
        """
        Convert MEXC side string to unified Side enum.
        
        Args:
            mexc_side: MEXC side string
            
        Returns:
            Unified Side enum value
        """
        return self.SIDE_REVERSE_MAPPING.get(mexc_side, Side.BUY)
    
    def get_mexc_time_in_force(self, unified_tif: TimeInForce) -> str:
        """
        Convert unified TimeInForce to MEXC API time in force string.
        
        Args:
            unified_tif: Unified TimeInForce enum value
            
        Returns:
            MEXC API time in force string
        """
        return self.TIME_IN_FORCE_MAPPING.get(unified_tif, 'GTC')
    
    def get_unified_time_in_force(self, mexc_tif: str) -> TimeInForce:
        """
        Convert MEXC time in force string to unified TimeInForce enum.
        
        Args:
            mexc_tif: MEXC time in force string
            
        Returns:
            Unified TimeInForce enum value
        """
        return self.TIME_IN_FORCE_REVERSE_MAPPING.get(mexc_tif, TimeInForce.GTC)
    
    # Utility functions merged from mexc_utils.py
    
    def format_mexc_quantity(self, quantity: float, precision: int = 8) -> str:
        """
        Format quantity to MEXC precision requirements.
        
        Args:
            quantity: Raw quantity value
            precision: Decimal places precision (default: 8)
            
        Returns:
            Formatted quantity string suitable for MEXC API
        """
        formatted = f"{quantity:.{precision}f}".rstrip('0').rstrip('.')
        return formatted if formatted else "0"
    
    def format_mexc_price(self, price: float, precision: int = 8) -> str:
        """
        Format price to MEXC precision requirements.
        
        Args:
            price: Raw price value
            precision: Decimal places precision (default: 8)
            
        Returns:
            Formatted price string suitable for MEXC API
        """
        formatted = f"{price:.{precision}f}".rstrip('0').rstrip('.')
        return formatted if formatted else "0"
    
    def get_mexc_kline_interval(self, interval: KlineInterval) -> str:
        """
        Convert unified KlineInterval to MEXC API interval string.
        
        Args:
            interval: Unified KlineInterval enum value
            
        Returns:
            MEXC API interval string (e.g., "1m", "5m", "1h", "1d")
        """
        interval_map = {
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
        
        return interval_map.get(interval, "1h")  # Default to 1 hour
    
    def pair_to_symbol(self, pair_str: str) -> Symbol:
        """
        Convert MEXC pair string to unified Symbol struct.
        
        Args:
            pair_str: MEXC trading pair string (e.g., "BTCUSDT")
            
        Returns:
            Unified Symbol struct
        """
        return self._symbol_mapper.pair_to_symbol(pair_str)
    
    def transform_mexc_order_to_unified(self, mexc_order) -> Order:
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
