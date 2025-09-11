"""
MEXC Exchange Mapping Constants

Collection of mapping constants and dictionaries used across MEXC exchange implementations.
Contains error code mappings, order status mappings, and type conversion mappings.

Key Features:
- Unified exception hierarchy mappings
- Order status and type conversions  
- Side mappings for BUY/SELL operations
- Reverse mappings for API response processing
- All constants optimized for performance lookups

Threading: All constants are thread-safe (immutable)
Performance: Dict-based lookups optimized for O(1) access
"""

from structs.exchange import OrderStatus, OrderType, Side, TimeInForce
from common.exceptions import (
    ExchangeAPIError, RateLimitError, TradingDisabled,
    InsufficientPosition, OversoldException
)


class MexcMappings:
    """Static mapping constants for MEXC API integration."""
    
    # MEXC Error Code Mapping to Unified Exceptions
    ERROR_CODE_MAPPING = {
        -2011: OrderStatus.CANCELED,  # Order cancelled
        429: RateLimitError,  # Too many requests
        418: RateLimitError,  # I'm a teapot (rate limit)
        10007: TradingDisabled,  # Symbol not support API
        700003: ExchangeAPIError,  # Timestamp outside recvWindow
        30016: TradingDisabled,  # Trading disabled
        10203: ExchangeAPIError,  # Order processing error
        30004: InsufficientPosition,  # Insufficient balance
        30005: OversoldException,  # Oversold
        30002: OversoldException,  # Minimum transaction volume
    }
    
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