from typing import TYPE_CHECKING
from .rest_manager import RestManager
from .strategies.strategy_set import RestStrategySet
from infrastructure.utils.exchange_utils import exchange_name_to_enum
from exchanges.structs.enums import ExchangeEnum
from infrastructure.logging import get_strategy_logger

if TYPE_CHECKING:
    from config.structs import ExchangeConfig

def create_rest_transport_manager(
        exchange_config: 'ExchangeConfig',
        is_private: bool = False,
        **kwargs
) -> RestManager:
    """
    Factory function to create RestTransportManager with direct strategy instantiation.

    Simplified method for creating REST transport without factory overhead.

    Args:
        exchange_config: Exchange configuration
        is_private: Whether to use private API (requires credentials)
        **kwargs: Additional strategy configuration

    Returns:
        RestTransportManager with configured strategies

    """
    if is_private and not exchange_config.has_credentials():
        raise ValueError("API key and secret key required for private API access")

    # Direct strategy creation based on exchange
    exchange = exchange_name_to_enum(exchange_config.name)
    api_type = 'private' if is_private else 'public'
    base_tags = [exchange.value, api_type, 'rest']
    
    if exchange == ExchangeEnum.MEXC:
        from exchanges.integrations.mexc.rest.strategies import (
            MexcRequestStrategy,
            MexcRateLimitStrategy, 
            MexcRetryStrategy
        )
        
        request_logger = get_strategy_logger('rest.request', base_tags + ['request'])
        request_strategy = MexcRequestStrategy(exchange_config, request_logger)
        
        rate_limit_logger = get_strategy_logger('rest.rate_limit', base_tags + ['rate_limit'])
        rate_limit_strategy = MexcRateLimitStrategy(exchange_config, rate_limit_logger)
        
        retry_logger = get_strategy_logger('rest.retry', base_tags + ['retry'])
        retry_strategy = MexcRetryStrategy(exchange_config, retry_logger)
        
        auth_strategy = None
        if is_private:
            from exchanges.integrations.mexc.rest.strategies import MexcAuthStrategy
            auth_logger = get_strategy_logger('rest.auth', base_tags + ['auth'])
            auth_strategy = MexcAuthStrategy(exchange_config, auth_logger)
            
    elif exchange == ExchangeEnum.GATEIO:
        from exchanges.integrations.gateio.rest.strategies import (
            GateioRequestStrategy,
            GateioRateLimitStrategy,
            GateioRetryStrategy
        )
        
        request_logger = get_strategy_logger('rest.request', base_tags + ['request'])
        request_strategy = GateioRequestStrategy(exchange_config, request_logger)
        
        rate_limit_logger = get_strategy_logger('rest.rate_limit', base_tags + ['rate_limit'])
        rate_limit_strategy = GateioRateLimitStrategy(exchange_config, rate_limit_logger)
        
        retry_logger = get_strategy_logger('rest.retry', base_tags + ['retry'])
        retry_strategy = GateioRetryStrategy(exchange_config, retry_logger)
        
        auth_strategy = None
        if is_private:
            from exchanges.integrations.gateio.rest.strategies import GateioAuthStrategy
            auth_logger = get_strategy_logger('rest.auth', base_tags + ['auth'])
            auth_strategy = GateioAuthStrategy(exchange_config, auth_logger)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        from exchanges.integrations.gateio.rest.strategies import (
            GateioRequestStrategy,
            GateioRateLimitStrategy,
            GateioRetryStrategy
        )
        
        request_logger = get_strategy_logger('rest.request', base_tags + ['request'])
        request_strategy = GateioRequestStrategy(exchange_config, request_logger)
        
        rate_limit_logger = get_strategy_logger('rest.rate_limit', base_tags + ['rate_limit'])
        rate_limit_strategy = GateioRateLimitStrategy(exchange_config, rate_limit_logger)
        
        retry_logger = get_strategy_logger('rest.retry', base_tags + ['retry'])
        retry_strategy = GateioRetryStrategy(exchange_config, retry_logger)
        
        auth_strategy = None
        if is_private:
            from exchanges.integrations.gateio.rest.strategies import GateioAuthStrategy
            auth_logger = get_strategy_logger('rest.auth', base_tags + ['auth'])
            auth_strategy = GateioAuthStrategy(exchange_config, auth_logger)
    else:
        raise ValueError(f"Exchange {exchange.value} REST strategies not implemented")
    
    strategy_set_logger = get_strategy_logger('rest.strategy_set', base_tags)
    strategy_set = RestStrategySet(
        request_strategy=request_strategy,
        rate_limit_strategy=rate_limit_strategy,
        retry_strategy=retry_strategy,
        auth_strategy=auth_strategy,
        exception_handler_strategy=None,  # Optional
        logger=strategy_set_logger
    )

    # Create and return transport manager
    return RestManager(strategy_set)