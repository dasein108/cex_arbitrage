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

class MexcMappings:
    """Static mapping constants for MEXC API integration."""
    

    
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
    
    @classmethod
    def get_unified_order_status(cls, mexc_status: str) -> OrderStatus:
        """
        Convert MEXC order status string to unified OrderStatus enum.
        
        Args:
            mexc_status: MEXC order status string
            
        Returns:
            Unified OrderStatus enum value
        """
        return cls.ORDER_STATUS_MAPPING.get(mexc_status, OrderStatus.UNKNOWN)
    
    @classmethod
    def get_mexc_order_type(cls, unified_type: OrderType) -> str:
        """
        Convert unified OrderType to MEXC API order type string.
        
        Args:
            unified_type: Unified OrderType enum value
            
        Returns:
            MEXC API order type string
        """
        return cls.ORDER_TYPE_MAPPING.get(unified_type, 'LIMIT')
    
    @classmethod
    def get_unified_order_type(cls, mexc_type: str) -> OrderType:
        """
        Convert MEXC order type string to unified OrderType enum.
        
        Args:
            mexc_type: MEXC order type string
            
        Returns:
            Unified OrderType enum value
        """
        return cls.ORDER_TYPE_REVERSE_MAPPING.get(mexc_type, OrderType.LIMIT)
    
    @classmethod
    def get_mexc_side(cls, unified_side: Side) -> str:
        """
        Convert unified Side to MEXC API side string.
        
        Args:
            unified_side: Unified Side enum value
            
        Returns:
            MEXC API side string
        """
        return cls.SIDE_MAPPING.get(unified_side, 'BUY')
    
    @classmethod
    def get_unified_side(cls, mexc_side: str) -> Side:
        """
        Convert MEXC side string to unified Side enum.
        
        Args:
            mexc_side: MEXC side string
            
        Returns:
            Unified Side enum value
        """
        return cls.SIDE_REVERSE_MAPPING.get(mexc_side, Side.BUY)
    
    @classmethod
    def get_mexc_time_in_force(cls, unified_tif: TimeInForce) -> str:
        """
        Convert unified TimeInForce to MEXC API time in force string.
        
        Args:
            unified_tif: Unified TimeInForce enum value
            
        Returns:
            MEXC API time in force string
        """
        return cls.TIME_IN_FORCE_MAPPING.get(unified_tif, 'GTC')
    
    @classmethod
    def get_unified_time_in_force(cls, mexc_tif: str) -> TimeInForce:
        """
        Convert MEXC time in force string to unified TimeInForce enum.
        
        Args:
            mexc_tif: MEXC time in force string
            
        Returns:
            Unified TimeInForce enum value
        """
        return cls.TIME_IN_FORCE_REVERSE_MAPPING.get(mexc_tif, TimeInForce.GTC)
    
    # Utility functions merged from mexc_utils.py
    
    @staticmethod
    def format_mexc_quantity(quantity: float, precision: int = 8) -> str:
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
    
    @staticmethod
    def format_mexc_price(price: float, precision: int = 8) -> str:
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
    
    @staticmethod
    def get_mexc_kline_interval(interval: KlineInterval) -> str:
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
    
    @staticmethod
    def pair_to_symbol(pair_str: str) -> Symbol:
        """
        Convert MEXC pair string to unified Symbol struct.
        
        Args:
            pair_str: MEXC trading pair string (e.g., "BTCUSDT")
            
        Returns:
            Unified Symbol struct
        """
        # Import here to avoid circular imports
        from cex.mexc.services.symbol_mapper import MexcSymbolMapper
        mapper = MexcSymbolMapper()
        return mapper.pair_to_symbol(pair_str)
    
    @staticmethod
    def transform_mexc_order_to_unified(mexc_order) -> Order:
        """
        Transform MEXC order response to unified Order struct.
        
        Args:
            mexc_order: MEXC order response structure
            
        Returns:
            Unified Order struct
        """
        # Convert MEXC symbol to unified Symbol
        symbol = MexcMappings.pair_to_symbol(mexc_order.symbol)

        # Calculate fee from fills if available
        fee = 0.0
        if hasattr(mexc_order, 'fills') and mexc_order.fills:
            fee = sum(float(fill.get('commission', '0')) for fill in mexc_order.fills)
        
        return Order(
            symbol=symbol,
            side=MexcMappings.get_unified_side(mexc_order.side),
            order_type=MexcMappings.get_unified_order_type(mexc_order.type),
            price=float(mexc_order.price),
            amount=float(mexc_order.origQty),
            amount_filled=float(mexc_order.executedQty),
            order_id=OrderId(str(mexc_order.orderId)),
            status=MexcMappings.get_unified_order_status(mexc_order.status),
            timestamp=datetime.fromtimestamp(mexc_order.transactTime / 1000) if mexc_order.transactTime else None,
            fee=fee
        )


# Legacy alias for backward compatibility
class MexcUtils:
    """Legacy alias for MexcMappings - use MexcMappings instead."""
    
    @staticmethod
    def format_mexc_quantity(quantity: float, precision: int = 8) -> str:
        return MexcMappings.format_mexc_quantity(quantity, precision)
    
    @staticmethod
    def format_mexc_price(price: float, precision: int = 8) -> str:
        return MexcMappings.format_mexc_price(price, precision)
    
    @staticmethod
    def get_mexc_kline_interval(interval: KlineInterval) -> str:
        return MexcMappings.get_mexc_kline_interval(interval)
    
    @staticmethod
    def pair_to_symbol(pair_str: str) -> Symbol:
        return MexcMappings.pair_to_symbol(pair_str)
    
    @staticmethod
    def transform_mexc_order_to_unified(mexc_order) -> Order:
        return MexcMappings.transform_mexc_order_to_unified(mexc_order)
