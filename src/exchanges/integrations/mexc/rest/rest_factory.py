from infrastructure.networking.http.strategies.strategy_set import RestStrategySet
# from infrastructure.logging import get_exchange_logger
from exchanges.integrations.mexc.rest.strategies import (
    MexcRequestStrategy, MexcRateLimitStrategy, MexcRetryStrategy,
    MexcExceptionHandlerStrategy, MexcAuthStrategy
)
from config.structs import ExchangeConfig
from infrastructure.networking.http import RestManager

def create_private_rest_manager(config: ExchangeConfig, logger):
    """Create MEXC-specific REST manager with private strategies including auth."""

    # Create MEXC-specific strategies with authentication
    strategy_set = RestStrategySet(
        request_strategy=MexcRequestStrategy(config, logger),
        rate_limit_strategy=MexcRateLimitStrategy(config, logger),
        retry_strategy=MexcRetryStrategy(config, logger),
        exception_handler_strategy=MexcExceptionHandlerStrategy(logger),
        auth_strategy=MexcAuthStrategy(config, logger)
    )

    return RestManager(strategy_set)

def create_public_rest_manager(config: ExchangeConfig, logger):
    """Create MEXC-specific REST manager with public strategies."""
    # Create MEXC-specific strategies
    strategy_set = RestStrategySet(
        request_strategy=MexcRequestStrategy(config, logger),
        rate_limit_strategy=MexcRateLimitStrategy(config, logger),
        retry_strategy=MexcRetryStrategy(config, logger),
        exception_handler_strategy=MexcExceptionHandlerStrategy(logger),
        auth_strategy=None  # No auth for public APIs
    )

    return RestManager(strategy_set)