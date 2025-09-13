"""
Gate.io Exchange Configuration

Simple, centralized configuration for Gate.io exchange REST configs.
Uses the YAML-based configuration system following MEXC patterns.
"""

from common.config import config
from common.rest_client import RestConfig


def _create_gateio_config(endpoint_type: str, timeout_multiplier: float = 1.0, max_retries: int = None) -> RestConfig:
    """Create Gate.io-specific REST config using YAML-based config."""
    # Gate.io endpoint timeout mapping (optimized for lower latency than MEXC)
    timeout_map = {
        'account': config.REQUEST_TIMEOUT * 0.7,      # Account balance queries - fast
        'my_orders': config.REQUEST_TIMEOUT * 0.6,    # Order status queries - very fast  
        'order': config.REQUEST_TIMEOUT * 0.5,        # Order placement - ultra fast for HFT
        'market_data': config.REQUEST_TIMEOUT * 0.8,  # Market data - standard
        'default': config.REQUEST_TIMEOUT
    }
    
    base_timeout = timeout_map.get(endpoint_type, config.REQUEST_TIMEOUT)
    final_timeout = base_timeout * timeout_multiplier
    
    return RestConfig(
        timeout=final_timeout,
        max_retries=max_retries if max_retries is not None else config.MAX_RETRIES,
        retry_delay=config.RETRY_DELAY,
        max_concurrent=20  # Gate.io rate limit: 200 req/10s = ~20 req/s
    )


class GateioConfig:
    """Simple Gate.io configuration using YAML-based config."""
    
    # Exchange constants
    EXCHANGE_NAME = "GATEIO"
    BASE_URL = "https://api.gateio.ws/api/v4"
    TESTNET_BASE_URL = "https://api-testnet.gateapi.io/api/v4"
    WEBSOCKET_URL = "wss://api.gateio.ws/ws/v4/"
    TESTNET_WEBSOCKET_URL = "wss://ws-testnet.gate.com/v4/ws/spot"
    
    # Rate limiting (from Gate.io API docs)
    PUBLIC_RATE_LIMIT = 20  # 200 requests per 10 seconds = 20 req/s
    PRIVATE_RATE_LIMIT = 10  # 10 requests per second for spot trading
    ORDER_RATE_LIMIT = 10   # 10 orders per second
    CANCEL_RATE_LIMIT = 200 # 200 cancellations per second
    
    # API endpoint groups for different rate limits
    ENDPOINT_GROUPS = {
        'spot_orders': ['orders', 'orders_batch'],
        'spot_cancel': ['cancel_order', 'cancel_orders', 'cancel_all'],
        'spot_account': ['accounts', 'my_trades', 'order_history'],
        'spot_market': ['currency_pairs', 'tickers', 'order_book', 'trades', 'candlesticks']
    }
    
    # REST configs for different operation types
    rest_config = {
        'account': _create_gateio_config('account'),
        'order': _create_gateio_config('order'),
        'my_orders': _create_gateio_config('my_orders'),
        'market_data': _create_gateio_config('market_data'),
        'market_data_fast': _create_gateio_config('market_data', timeout_multiplier=0.3, max_retries=1),
        'default': _create_gateio_config('default'),
        'default_fast_time': _create_gateio_config('default', timeout_multiplier=0.2),
        'default_fast_ping': _create_gateio_config('default', timeout_multiplier=0.25)
    }
    
    # API endpoint paths (following Gate.io API v4 structure)
    SPOT_ENDPOINTS = {
        # Market Data (Public)
        'currency_pairs': '/spot/currency_pairs',
        'tickers': '/spot/tickers',
        'order_book': '/spot/order_book',
        'trades': '/spot/trades',
        'candlesticks': '/spot/candlesticks',
        
        # Trading (Private - Authentication Required)
        'accounts': '/spot/accounts',
        'orders': '/spot/orders',
        'cancel_order': '/spot/orders/{order_id}',
        'cancel_orders': '/spot/orders',
        'my_trades': '/spot/my_trades',
        'order_history': '/spot/orders',
        'fee': '/spot/fee',
        
        # Batch Operations
        'orders_batch': '/spot/batch_orders',
        'cancel_batch': '/spot/cancel_batch_orders'
    }
    
    # Full API paths for signature generation (includes /api/v4 prefix)
    SIGNATURE_ENDPOINTS = {
        # Market Data (Public)  
        'currency_pairs': '/api/v4/spot/currency_pairs',
        'tickers': '/api/v4/spot/tickers',
        'order_book': '/api/v4/spot/order_book',
        'trades': '/api/v4/spot/trades',
        'candlesticks': '/api/v4/spot/candlesticks',
        
        # Trading (Private - Authentication Required)
        'accounts': '/api/v4/spot/accounts',
        'orders': '/api/v4/spot/orders',
        'cancel_order': '/api/v4/spot/orders/{order_id}',
        'cancel_orders': '/api/v4/spot/orders',
        'my_trades': '/api/v4/spot/my_trades',
        'order_history': '/api/v4/spot/orders',
        'fee': '/api/v4/spot/fee',
        
        # Batch Operations
        'orders_batch': '/api/v4/spot/batch_orders',
        'cancel_batch': '/api/v4/spot/cancel_batch_orders'
    }
    
    # WebSocket channels
    WS_CHANNELS = {
        'spot_tickers': 'spot.tickers',
        'spot_trades': 'spot.trades',
        'spot_candlesticks': 'spot.candlesticks',
        'spot_order_book': 'spot.order_book',
        'spot_order_book_update': 'spot.order_book_update',
        
        # Private channels (require authentication)
        'spot_orders': 'spot.orders',
        'spot_usertrades': 'spot.usertrades',
        'spot_balances': 'spot.balances'
    }
    
    # Order type mappings for Gate.io API
    ORDER_TYPE_MAP = {
        'LIMIT': 'limit',
        'MARKET': 'market'
    }
    
    # Time in force mappings
    TIME_IN_FORCE_MAP = {
        'GTC': 'gtc',  # Good Till Cancelled
        'IOC': 'ioc',  # Immediate or Cancel  
        'FOK': 'fok'   # Fill or Kill
    }
    
    # Side mappings
    SIDE_MAP = {
        'BUY': 'buy',
        'SELL': 'sell'
    }
    
    @classmethod
    def get_base_url(cls, use_testnet: bool = False) -> str:
        """Get appropriate base URL based on environment."""
        return cls.TESTNET_BASE_URL if use_testnet else cls.BASE_URL
    
    @classmethod  
    def get_websocket_url(cls, use_testnet: bool = False) -> str:
        """Get appropriate WebSocket URL based on environment."""
        return cls.TESTNET_WEBSOCKET_URL if use_testnet else cls.WEBSOCKET_URL
    
    @classmethod
    def get_endpoint_url(cls, endpoint: str, use_testnet: bool = False) -> str:
        """Get full endpoint URL."""
        base_url = cls.get_base_url(use_testnet)
        endpoint_path = cls.SPOT_ENDPOINTS.get(endpoint, '')
        return f"{base_url}{endpoint_path}"
    
    @classmethod
    def get_rate_limit_for_group(cls, group: str) -> int:
        """Get rate limit for specific endpoint group."""
        rate_limits = {
            'spot_orders': cls.ORDER_RATE_LIMIT,
            'spot_cancel': cls.CANCEL_RATE_LIMIT,
            'spot_account': cls.PRIVATE_RATE_LIMIT,
            'spot_market': cls.PUBLIC_RATE_LIMIT
        }
        return rate_limits.get(group, cls.PRIVATE_RATE_LIMIT)