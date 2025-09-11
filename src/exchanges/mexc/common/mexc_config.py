"""
MEXC Exchange Configuration

Simple, centralized configuration for MEXC exchange REST configs.
Uses the new YAML-based configuration system.
"""

from common.config import config
from common.rest_client import RestConfig


def _create_mexc_config(endpoint_type: str, timeout_multiplier: float = 1.0, max_retries: int = None) -> RestConfig:
    """Create MEXC-specific REST config using YAML-based config."""
    # MEXC endpoint timeout mapping
    timeout_map = {
        'account': config.REQUEST_TIMEOUT * 0.8,
        'my_orders': config.REQUEST_TIMEOUT * 0.7,
        'order': config.REQUEST_TIMEOUT * 0.6, 
        'market_data': config.REQUEST_TIMEOUT * 1.0,
        'default': config.REQUEST_TIMEOUT
    }
    
    base_timeout = timeout_map.get(endpoint_type, config.REQUEST_TIMEOUT)
    final_timeout = base_timeout * timeout_multiplier
    
    return RestConfig(
        timeout=final_timeout,
        max_retries=max_retries if max_retries is not None else config.MAX_RETRIES,
        retry_delay=config.RETRY_DELAY,
        require_auth=endpoint_type in ['account', 'order', 'my_orders'],
        max_concurrent=config.MEXC_RATE_LIMIT_PER_SECOND
    )


class MexcConfig:
    """Simple MEXC configuration using YAML-based config."""
    
    # Exchange constants from YAML config
    EXCHANGE_NAME = "MEXC"
    BASE_URL = config.MEXC_BASE_URL
    WEBSOCKET_URL = config.MEXC_WEBSOCKET_URL
    
    # REST configs only - no paths
    rest_config = {
        'account': _create_mexc_config('account'),
        'order': _create_mexc_config('order'),
        'my_orders': _create_mexc_config('my_orders'),
        'market_data': _create_mexc_config('market_data'),
        'market_data_fast': _create_mexc_config('market_data', timeout_multiplier=0.4, max_retries=1),
        'default': _create_mexc_config('default'),
        'default_fast_time': _create_mexc_config('default', timeout_multiplier=0.2),
        'default_fast_ping': _create_mexc_config('default', timeout_multiplier=0.3)
    }