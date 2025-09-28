"""
Gate.io REST Manager Factory

Factory for creating Gate.io-specific REST managers with appropriate strategies.
Follows the same pattern as MEXC for consistency across exchange integrations.

Key Features:
- Unified REST manager creation for all Gate.io clients
- Separate public and private manager configurations
- Consistent strategy application across spot and futures
- Centralized logger creation
"""

from infrastructure.networking.http.strategies.strategy_set import RestStrategySet
from infrastructure.networking.http import RestManager
from infrastructure.logging import get_exchange_logger
from exchanges.integrations.gateio.rest.strategies import (
    GateioRequestStrategy, GateioRateLimitStrategy, GateioRetryStrategy,
    GateioExceptionHandlerStrategy, GateioAuthStrategy
)
from config.structs import ExchangeConfig


def create_private_rest_manager(config: ExchangeConfig, logger):
    """
    Create Gate.io-specific REST manager with private strategies including auth.
    
    Used by both spot and futures private REST clients.
    
    Args:
        config: ExchangeConfig with Gate.io configuration and credentials
        logger: HFT logger instance
        
    Returns:
        RestManager configured for Gate.io private API access
    """
    # Create Gate.io-specific loggers
    request_logger = get_exchange_logger(config.name, 'rest.request')
    rate_limit_logger = get_exchange_logger(config.name, 'rest.rate_limit')
    retry_logger = get_exchange_logger(config.name, 'rest.retry')
    auth_logger = get_exchange_logger(config.name, 'rest.auth')
    
    # Create Gate.io-specific strategies with authentication
    strategy_set = RestStrategySet(
        request_strategy=GateioRequestStrategy(config, request_logger),
        rate_limit_strategy=GateioRateLimitStrategy(config, rate_limit_logger),
        retry_strategy=GateioRetryStrategy(config, retry_logger),
        exception_handler_strategy=GateioExceptionHandlerStrategy(),
        auth_strategy=GateioAuthStrategy(config, auth_logger)
    )
    
    return RestManager(strategy_set)


def create_public_rest_manager(config: ExchangeConfig, logger):
    """
    Create Gate.io-specific REST manager with public strategies.
    
    Used by both spot and futures public REST clients.
    
    Args:
        config: ExchangeConfig with Gate.io configuration
        logger: HFT logger instance
        
    Returns:
        RestManager configured for Gate.io public API access
    """
    # Create Gate.io-specific loggers
    request_logger = get_exchange_logger(config.name, 'rest.request')
    rate_limit_logger = get_exchange_logger(config.name, 'rest.rate_limit')
    retry_logger = get_exchange_logger(config.name, 'rest.retry')
    
    # Create Gate.io-specific strategies
    strategy_set = RestStrategySet(
        request_strategy=GateioRequestStrategy(config, request_logger),
        rate_limit_strategy=GateioRateLimitStrategy(config, rate_limit_logger),
        retry_strategy=GateioRetryStrategy(config, retry_logger),
        exception_handler_strategy=GateioExceptionHandlerStrategy(),
        auth_strategy=None  # No auth for public APIs
    )
    
    return RestManager(strategy_set)