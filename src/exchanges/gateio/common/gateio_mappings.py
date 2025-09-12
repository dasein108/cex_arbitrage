"""
Gate.io Exchange Mapping Constants

Collection of mapping constants and dictionaries used across Gate.io exchange implementations.
Contains error code mappings, order status mappings, and type conversion mappings.

Key Features:
- Unified exception hierarchy mappings for Gate.io specific errors
- Order status and type conversions between Gate.io and unified formats
- Side mappings for BUY/SELL operations
- Reverse mappings for API response processing
- All constants optimized for performance lookups

Threading: All constants are thread-safe (immutable)
Performance: Dict-based lookups optimized for O(1) access
"""

from exchanges.interface.structs import OrderStatus, OrderType, Side, TimeInForce
from common.exceptions import (
    ExchangeAPIError, RateLimitError, TradingDisabled,
    InsufficientPosition, OversoldException
)


class GateioMappings:
    """Static mapping constants for Gate.io API integration."""
    
    # Gate.io Error Label Mapping to Unified Exceptions (from API docs)
    ERROR_LABEL_MAPPING = {
        'BALANCE_NOT_ENOUGH': InsufficientPosition,  # Insufficient balance
        'ORDER_NOT_FOUND': ExchangeAPIError,  # Order not found
        'INVALID_CURRENCY_PAIR': ExchangeAPIError,  # Invalid trading pair
        'INVALID_PRICE': ExchangeAPIError,  # Invalid price
        'INVALID_AMOUNT': ExchangeAPIError,  # Invalid amount
        'MIN_AMOUNT_NOT_REACHED': OversoldException,  # Minimum amount not met
        'TRADING_DISABLED': TradingDisabled,  # Trading disabled for pair
        'TOO_MANY_REQUESTS': RateLimitError,  # Rate limit exceeded
        'SIGNATURE_ERROR': ExchangeAPIError,  # Authentication failed
        'TIMESTAMP_EXPIRED': ExchangeAPIError,  # Request timestamp expired
        'IP_NOT_ALLOWED': ExchangeAPIError,  # IP not whitelisted
        'ACCOUNT_LOCKED': TradingDisabled,  # Account locked
        'INSUFFICIENT_BALANCE': InsufficientPosition,  # Alternative balance error
    }
    
    # Gate.io HTTP Status Code Mapping
    HTTP_STATUS_MAPPING = {
        400: ExchangeAPIError,  # Bad Request
        401: ExchangeAPIError,  # Unauthorized
        403: ExchangeAPIError,  # Forbidden
        404: ExchangeAPIError,  # Not Found
        429: RateLimitError,    # Too Many Requests
        500: ExchangeAPIError,  # Internal Server Error
        502: ExchangeAPIError,  # Bad Gateway
        503: ExchangeAPIError,  # Service Unavailable
    }
    
    # Gate.io Order Status Mapping to Unified Status
    ORDER_STATUS_MAPPING = {
        'open': OrderStatus.NEW,
        'closed': OrderStatus.FILLED,
        'cancelled': OrderStatus.CANCELED,
        'expired': OrderStatus.EXPIRED,
    }
    
    # Reverse mapping for API responses (Gate.io -> Unified)
    ORDER_STATUS_REVERSE_MAPPING = {v: k for k, v in ORDER_STATUS_MAPPING.items()}
    
    # Unified Order Type to Gate.io API Mapping
    ORDER_TYPE_MAPPING = {
        OrderType.LIMIT: 'limit',
        OrderType.MARKET: 'market',
        # Gate.io doesn't have LIMIT_MAKER, IOC, FOK - map to closest equivalent
        OrderType.LIMIT_MAKER: 'limit',  # Use regular limit with post_only
        OrderType.IMMEDIATE_OR_CANCEL: 'limit',  # Use limit with time_in_force IOC
        OrderType.FILL_OR_KILL: 'limit',  # Use limit with time_in_force FOK
        # Gate.io doesn't support stop orders in spot trading
        OrderType.STOP_LIMIT: 'limit',
        OrderType.STOP_MARKET: 'market',
    }
    
    # Reverse mapping for API responses (Gate.io -> Unified)
    ORDER_TYPE_REVERSE_MAPPING = {v: k for k, v in ORDER_TYPE_MAPPING.items()}
    # Add explicit mappings for Gate.io response parsing
    ORDER_TYPE_REVERSE_MAPPING.update({
        'limit': OrderType.LIMIT,
        'market': OrderType.MARKET,
    })
    
    # Unified Side to Gate.io API Mapping
    SIDE_MAPPING = {
        Side.BUY: 'buy',
        Side.SELL: 'sell',
    }
    
    # Reverse mapping for API responses (Gate.io -> Unified)
    SIDE_REVERSE_MAPPING = {v: k for k, v in SIDE_MAPPING.items()}
    
    # Unified TimeInForce to Gate.io API Mapping
    TIME_IN_FORCE_MAPPING = {
        TimeInForce.GTC: 'gtc',  # Good Till Cancelled
        TimeInForce.IOC: 'ioc',  # Immediate or Cancel
        TimeInForce.FOK: 'fok',  # Fill or Kill
        TimeInForce.GTD: 'gtc',  # Gate.io doesn't support GTD, use GTC
    }
    
    # Reverse mapping for API responses (Gate.io -> Unified)
    TIME_IN_FORCE_REVERSE_MAPPING = {v: k for k, v in TIME_IN_FORCE_MAPPING.items()}
    
    # WebSocket channel mappings
    WS_CHANNEL_MAPPING = {
        'orderbook': 'spot.order_book_update',
        'trades': 'spot.trades',
        'ticker': 'spot.tickers',
        'candlesticks': 'spot.candlesticks',
        'orders': 'spot.orders',  # Private channel
        'balances': 'spot.balances',  # Private channel
    }
    
    # Kline interval mapping (unified -> Gate.io)
    KLINE_INTERVAL_MAPPING = {
        '1m': '1m',
        '5m': '5m', 
        '15m': '15m',
        '30m': '30m',
        '1h': '1h',
        '4h': '4h',
        '8h': '8h',
        '1d': '1d',
        '7d': '7d',
        '1w': '7d',  # Gate.io uses 7d instead of 1w
        '30d': '30d',
    }
    
    @classmethod
    def get_unified_order_status(cls, gateio_status: str) -> OrderStatus:
        """
        Convert Gate.io order status string to unified OrderStatus enum.
        
        Args:
            gateio_status: Gate.io order status string
            
        Returns:
            Unified OrderStatus enum value
        """
        return cls.ORDER_STATUS_MAPPING.get(gateio_status.lower(), OrderStatus.UNKNOWN)
    
    @classmethod
    def get_gateio_order_status(cls, unified_status: OrderStatus) -> str:
        """
        Convert unified OrderStatus to Gate.io API status string.
        
        Args:
            unified_status: Unified OrderStatus enum value
            
        Returns:
            Gate.io API status string
        """
        return cls.ORDER_STATUS_REVERSE_MAPPING.get(unified_status, 'open')
    
    @classmethod
    def get_gateio_order_type(cls, unified_type: OrderType) -> str:
        """
        Convert unified OrderType to Gate.io API order type string.
        
        Args:
            unified_type: Unified OrderType enum value
            
        Returns:
            Gate.io API order type string
        """
        return cls.ORDER_TYPE_MAPPING.get(unified_type, 'limit')
    
    @classmethod
    def get_unified_order_type(cls, gateio_type: str) -> OrderType:
        """
        Convert Gate.io order type string to unified OrderType enum.
        
        Args:
            gateio_type: Gate.io order type string
            
        Returns:
            Unified OrderType enum value
        """
        return cls.ORDER_TYPE_REVERSE_MAPPING.get(gateio_type.lower(), OrderType.LIMIT)
    
    @classmethod
    def get_gateio_side(cls, unified_side: Side) -> str:
        """
        Convert unified Side to Gate.io API side string.
        
        Args:
            unified_side: Unified Side enum value
            
        Returns:
            Gate.io API side string
        """
        return cls.SIDE_MAPPING.get(unified_side, 'buy')
    
    @classmethod
    def get_unified_side(cls, gateio_side: str) -> Side:
        """
        Convert Gate.io side string to unified Side enum.
        
        Args:
            gateio_side: Gate.io side string
            
        Returns:
            Unified Side enum value
        """
        return cls.SIDE_REVERSE_MAPPING.get(gateio_side.lower(), Side.BUY)
    
    @classmethod
    def get_gateio_time_in_force(cls, unified_tif: TimeInForce) -> str:
        """
        Convert unified TimeInForce to Gate.io API time in force string.
        
        Args:
            unified_tif: Unified TimeInForce enum value
            
        Returns:
            Gate.io API time in force string
        """
        return cls.TIME_IN_FORCE_MAPPING.get(unified_tif, 'gtc')
    
    @classmethod
    def get_unified_time_in_force(cls, gateio_tif: str) -> TimeInForce:
        """
        Convert Gate.io time in force string to unified TimeInForce enum.
        
        Args:
            gateio_tif: Gate.io time in force string
            
        Returns:
            Unified TimeInForce enum value
        """
        return cls.TIME_IN_FORCE_REVERSE_MAPPING.get(gateio_tif.lower(), TimeInForce.GTC)
    
    @classmethod
    def get_exception_from_label(cls, label: str) -> type:
        """
        Get unified exception class from Gate.io error label.
        
        Args:
            label: Gate.io error label string
            
        Returns:
            Unified exception class
        """
        return cls.ERROR_LABEL_MAPPING.get(label, ExchangeAPIError)
    
    @classmethod
    def get_exception_from_status(cls, status_code: int) -> type:
        """
        Get unified exception class from HTTP status code.
        
        Args:
            status_code: HTTP status code
            
        Returns:
            Unified exception class
        """
        return cls.HTTP_STATUS_MAPPING.get(status_code, ExchangeAPIError)
    
    @classmethod
    def get_ws_channel(cls, channel_type: str) -> str:
        """
        Get Gate.io WebSocket channel name from channel type.
        
        Args:
            channel_type: Channel type (orderbook, trades, etc.)
            
        Returns:
            Gate.io WebSocket channel name
        """
        return cls.WS_CHANNEL_MAPPING.get(channel_type, channel_type)
    
    @classmethod
    def get_kline_interval(cls, unified_interval: str) -> str:
        """
        Get Gate.io kline interval from unified interval.
        
        Args:
            unified_interval: Unified interval string
            
        Returns:
            Gate.io kline interval string
        """
        return cls.KLINE_INTERVAL_MAPPING.get(unified_interval, '1m')
    
    @classmethod 
    def should_use_post_only(cls, order_type: OrderType) -> bool:
        """
        Check if order type should use post_only flag for Gate.io.
        
        Args:
            order_type: Unified OrderType enum
            
        Returns:
            True if should use post_only flag
        """
        return order_type == OrderType.LIMIT_MAKER
    
    @classmethod
    def get_order_params(cls, order_type: OrderType, time_in_force: TimeInForce) -> dict:
        """
        Get additional order parameters based on order type and time in force.
        
        Args:
            order_type: Unified OrderType enum
            time_in_force: Unified TimeInForce enum
            
        Returns:
            Dictionary of additional parameters for Gate.io API
        """
        params = {}
        
        # Set time_in_force
        params['time_in_force'] = cls.get_gateio_time_in_force(time_in_force)
        
        # Set post_only for limit maker orders
        if cls.should_use_post_only(order_type):
            params['post_only'] = True
        
        return params