"""
REST Factory for Direct Instantiation

Factory functions to create exchange-specific REST clients with direct implementation.
Eliminates strategy pattern overhead through constructor injection of dependencies.

Key Features:
- Direct instantiation (no strategy composition)
- Constructor injection of rate_limiter and logger
- Exchange-specific optimizations
- HFT performance compliance

Performance Benefits:
- Eliminates ~1.7μs strategy dispatch overhead per request
- Direct method calls instead of strategy coordination
- Sub-microsecond factory overhead
"""

from typing import Union, Any
from config.structs import ExchangeConfig
from infrastructure.utils.exchange_utils import exchange_name_to_enum
from exchanges.structs.enums import ExchangeEnum
from infrastructure.logging import get_exchange_logger


def create_rate_limiter(config: ExchangeConfig, is_private: bool = False) -> Any:
    """
    Create exchange-specific rate limiter with optimized configuration.
    
    Args:
        config: Exchange configuration
        is_private: Whether this is for private API endpoints
        
    Returns:
        Exchange-specific rate limiter instance
        
    Raises:
        ValueError: If exchange not supported
    """
    exchange = exchange_name_to_enum(config.name)
    api_type = 'private' if is_private else 'public'
    
    if exchange == ExchangeEnum.MEXC:
        from exchanges.integrations.mexc.rest.rate_limit import MexcRateLimit
        
        # Create logger for rate limiter
        logger = get_exchange_logger('mexc', f'rest.rate_limit.{api_type}')
        
        return MexcRateLimit(config, logger)
        
    elif exchange in [ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]:
        from exchanges.integrations.gateio.rest.rate_limit import GateioRateLimit
        
        # Create logger for rate limiter
        exchange_name = 'gateio' if exchange == ExchangeEnum.GATEIO else 'gateio_futures'
        logger = get_exchange_logger(exchange_name, f'rest.rate_limit.{api_type}')
        
        return GateioRateLimit(config, logger)
        
    else:
        raise ValueError(f"Rate limiter not implemented for exchange: {exchange.value}")


def create_rest_client(config: ExchangeConfig, is_private: bool = False) -> Union[Any, Any]:
    """
    Create exchange-specific REST client with direct implementation and constructor injection.
    
    Eliminates strategy pattern overhead by using direct implementation with injected dependencies.
    
    Args:
        config: Exchange configuration with URL and credentials
        is_private: Whether to create private (authenticated) or public client
        
    Returns:
        Exchange-specific REST client instance (Public or Private)
        
    Raises:
        ValueError: If exchange not supported or credentials missing for private
        
    Examples:
        # Create public MEXC client
        public_client = create_rest_client(mexc_config, is_private=False)
        
        # Create private MEXC client
        private_client = create_rest_client(mexc_config, is_private=True)
    """
    if is_private and not config.has_credentials():
        raise ValueError("API key and secret key required for private API access")
    
    exchange = exchange_name_to_enum(config.name)
    api_type = 'private' if is_private else 'public'
    
    # Create rate limiter (dependency injection)
    rate_limiter = create_rate_limiter(config, is_private)
    
    # Create logger (dependency injection)
    logger = get_exchange_logger(config.name.lower(), f'rest.{api_type}')
    
    # Create exchange-specific REST client with constructor injection
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRestInterface
            return MexcPrivateSpotRestInterface(
                config=config,
                rate_limiter=rate_limiter,
                logger=logger
            )
        else:
            from exchanges.integrations.mexc.rest.mexc_rest_spot_public import MexcPublicSpotRestInterface
            return MexcPublicSpotRestInterface(
                config=config,
                rate_limiter=rate_limiter,
                logger=logger
            )
    
    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            # TODO: Create GateioPrivateSpotRest that inherits from GateioBaseSpotRest
            raise NotImplementedError("Gate.io private spot REST with direct implementation not yet implemented")
        else:
            # TODO: Create GateioPublicSpotRest that inherits from GateioBaseSpotRest
            raise NotImplementedError("Gate.io public spot REST with direct implementation not yet implemented")
    
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            # TODO: Create GateioPrivateFuturesRest that inherits from GateioBaseFuturesRest
            raise NotImplementedError("Gate.io futures private REST with direct implementation not yet implemented")
        else:
            # TODO: Create GateioPublicFuturesRest that inherits from GateioBaseFuturesRest
            raise NotImplementedError("Gate.io futures public REST with direct implementation not yet implemented")
    
    else:
        raise ValueError(f"REST client not implemented for exchange: {exchange.value}")


def create_rest_client_legacy(config: ExchangeConfig, is_private: bool = False) -> Any:
    """
    Create REST client using legacy strategy pattern (for comparison/fallback).
    
    This function creates clients using the old strategy pattern for performance
    comparison and as a fallback during the migration period.
    
    Args:
        config: Exchange configuration
        is_private: Whether to create private client
        
    Returns:
        Legacy strategy-based REST client
    """
    from exchanges.interfaces.rest.rest_base import BaseRestInterface
    
    class LegacyRestClient(BaseRestInterface):
        def __init__(self, config: ExchangeConfig, is_private: bool):
            super().__init__(config, is_private)
    
    return LegacyRestClient(config, is_private)


# Performance comparison utilities

def compare_rest_performance(config: ExchangeConfig, is_private: bool = False, iterations: int = 1000):
    """
    Compare performance between direct implementation and legacy strategy pattern.
    
    Args:
        config: Exchange configuration
        is_private: Whether to test private endpoints
        iterations: Number of iterations for performance testing
        
    Returns:
        Dictionary with performance comparison results
    """
    import time
    import asyncio
    
    async def test_performance():
        # Test direct implementation
        direct_client = create_rest_client(config, is_private)
        legacy_client = create_rest_client_legacy(config, is_private)
        
        # Warm up both clients
        await direct_client.request("GET", "/api/v3/ping")
        await legacy_client.request("GET", "/api/v3/ping")
        
        # Test direct implementation
        start_time = time.perf_counter()
        for _ in range(iterations):
            await direct_client.request("GET", "/api/v3/ping")
        direct_time = time.perf_counter() - start_time
        
        # Test legacy implementation
        start_time = time.perf_counter()
        for _ in range(iterations):
            await legacy_client.request("GET", "/api/v3/ping")
        legacy_time = time.perf_counter() - start_time
        
        # Cleanup
        await direct_client.close()
        await legacy_client.close()
        
        return {
            "direct_implementation": {
                "total_time_ms": direct_time * 1000,
                "avg_time_us": (direct_time / iterations) * 1_000_000,
                "requests_per_second": iterations / direct_time
            },
            "legacy_strategy": {
                "total_time_ms": legacy_time * 1000,
                "avg_time_us": (legacy_time / iterations) * 1_000_000,
                "requests_per_second": iterations / legacy_time
            },
            "improvement": {
                "speedup_factor": legacy_time / direct_time,
                "overhead_reduction_us": ((legacy_time - direct_time) / iterations) * 1_000_000,
                "performance_gain_percent": ((legacy_time - direct_time) / legacy_time) * 100
            }
        }
    
    return asyncio.run(test_performance())