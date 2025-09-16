"""
MEXC Exchange Configuration

Simple, centralized configuration for MEXC exchange REST configs.
Uses the new YAML-based configuration system.
"""

from core.config.config import config
from core.transport.rest.rest_client import RestConfig


def _create_mexc_config(endpoint_type: str, timeout_multiplier: float = 1.0, max_retries: int = None) -> RestConfig:
    """Create MEXC-specific REST config using YAML-based config."""
    # MEXC endpoint timeout mapping
    timeout_map = {
        'account': config._network_config.request_timeout * 0.8,
        'my_orders': config._network_config.request_timeout * 0.7,
        'order': config._network_config.request_timeout * 0.6, 
        'market_data': config._network_config.request_timeout * 1.0,
        'default': config._network_config.request_timeout
    }
    
    base_timeout = timeout_map.get(endpoint_type, config._network_config.request_timeout)
    final_timeout = base_timeout * timeout_multiplier
    
    mexc_config = config._exchange_configs.get('mexc')
    return RestConfig(
        timeout=final_timeout,
        max_retries=max_retries if max_retries is not None else config._network_config.max_retries,
        retry_delay=config._network_config.retry_delay,
        max_concurrent=getattr(mexc_config.rate_limit, 'requests_per_second', 18) if mexc_config and hasattr(mexc_config, 'rate_limit') else 18
    )


class MexcConfig:
    """Simple MEXC configuration using YAML-based config."""
    
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