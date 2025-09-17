from core.config.structs import ExchangeConfig
from .rest_transport_manager import RestTransportManager
from .strategies import RestStrategyFactory

def create_rest_transport_manager(
        exchange_config: ExchangeConfig,
        is_private: bool = False,
        **kwargs
) -> RestTransportManager:
    """
    Factory function to create RestTransportManager with exchange strategies.

    Preferred method for creating REST transport with integrated rate limiting,
    authentication, and retry policies.

    Args:
        exchange_config: Exchange configuration
        is_private: Whether to use private API (requires credentials)
        **kwargs: Additional strategy configuration

    Returns:
        RestTransportManager with configured strategies

    """
    if is_private and not exchange_config.has_credentials():
        raise ValueError("API key and secret key required for private API access")

    # Create strategy set
    strategy_set = RestStrategyFactory.create_strategies(
        exchange_config=exchange_config,
        is_private=is_private,
    )

    # Create and return transport manager
    return RestTransportManager(strategy_set)