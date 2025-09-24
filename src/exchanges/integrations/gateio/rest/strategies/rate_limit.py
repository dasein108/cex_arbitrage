import asyncio
import time
from typing import Dict, Any

from infrastructure.networking.http import RateLimitStrategy, RateLimitContext
from infrastructure.config.structs import ExchangeConfig


class GateioRateLimitStrategy(RateLimitStrategy):
    """Gate.io-specific rate limiting based on ExchangeConfig."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize Gate.io rate limiting strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing rate_limit settings
            logger: Optional HFT logger injection
            **kwargs: Additional parameters (ignored for compatibility)
        """
        # Extract rate limits from config or use Gate.io defaults
        if exchange_config.rate_limit:
            self.default_rps = float(exchange_config.rate_limit.requests_per_second)
            self.default_burst = self.default_rps * 2  # 2x burst capacity (Gate.io is more restrictive)
            self.global_limit = 3  # Gate.io is more conservative
        else:
            # Gate.io HFT defaults (more conservative than MEXC)
            self.default_rps = 10.0
            self.default_burst = 20
            self.global_limit = 3
        
        self.exchange_config = exchange_config
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = ['gateio', 'rest', 'rate_limit']
            logger = get_strategy_logger('rest.rate_limit.gateio', tags)
        self.logger = logger
        
        # Gate.io endpoint-specific rate limits based on API documentation
        self._endpoint_limits = {
            # Public endpoints - Gate.io limits: 200 requests/10 seconds (20 req/sec)
            "/spot/currency_pairs": RateLimitContext(
                requests_per_second=5.0, burst_capacity=10, endpoint_weight=1
            ),
            "/spot/order_book": RateLimitContext(
                requests_per_second=8.0, burst_capacity=15, endpoint_weight=1
            ),
            "/spot/candlesticks": RateLimitContext(
                requests_per_second=3.0, burst_capacity=6, endpoint_weight=1
            ),
            "/spot/trades": RateLimitContext(
                requests_per_second=5.0, burst_capacity=10, endpoint_weight=1
            ),
            "/spot/time": RateLimitContext(
                requests_per_second=10.0, burst_capacity=20, endpoint_weight=1
            ),

            # Private endpoints - Gate.io limits: 10 requests/second for spot trading
            "/spot/orders": RateLimitContext(
                requests_per_second=2.0, burst_capacity=4, endpoint_weight=3
            ),
            "/spot/accounts": RateLimitContext(
                requests_per_second=1.0, burst_capacity=2, endpoint_weight=2
            ),
            "/spot/fee": RateLimitContext(
                requests_per_second=0.5, burst_capacity=1, endpoint_weight=2
            ),
        }

        # Default rate limit for unknown endpoints
        self._default_limit = RateLimitContext(
            requests_per_second=3.0, burst_capacity=6, endpoint_weight=1
        )

        # Semaphores for each endpoint
        self._semaphores = {}
        self._last_request_times = {}
        self._request_counts = {}

        # Initialize semaphores and tracking
        for endpoint, context in self._endpoint_limits.items():
            self._semaphores[endpoint] = asyncio.Semaphore(context.burst_capacity)
            self._last_request_times[endpoint] = 0.0
            self._request_counts[endpoint] = 0

        # Global rate limiting (more conservative for Gate.io)
        self._global_semaphore = asyncio.Semaphore(self.global_limit)  # Max concurrent requests
        self._global_last_request = 0.0
        self._global_min_delay = 0.2  # 200ms between any requests (more conservative)

    async def acquire_permit(self, endpoint: str, request_weight: int = 1) -> bool:
        """Acquire rate limit permit for Gate.io endpoint."""
        # Get rate limit context
        context = self.get_rate_limit_context(endpoint)

        # Acquire global semaphore first
        await self._global_semaphore.acquire()

        try:
            # Global rate limiting
            current_time = time.time()
            time_since_last = current_time - self._global_last_request
            if time_since_last < self._global_min_delay:
                await asyncio.sleep(self._global_min_delay - time_since_last)
            self._global_last_request = time.time()

            # Endpoint-specific rate limiting
            if endpoint in self._semaphores:
                semaphore = self._semaphores[endpoint]
                await semaphore.acquire()

                # Apply delay if needed
                last_time = self._last_request_times[endpoint]
                required_delay = (1.0 / context.requests_per_second) - (current_time - last_time)
                if required_delay > 0:
                    await asyncio.sleep(required_delay)

                self._last_request_times[endpoint] = time.time()
                self._request_counts[endpoint] += 1

            return True
        except:
            # Release global semaphore on error
            self._global_semaphore.release()
            raise

    def release_permit(self, endpoint: str, request_weight: int = 1) -> None:
        """Release rate limit permit for Gate.io endpoint."""
        # Release endpoint-specific semaphore
        if endpoint in self._semaphores:
            self._semaphores[endpoint].release()

        # Release global semaphore
        self._global_semaphore.release()

    def get_rate_limit_context(self, endpoint: str) -> RateLimitContext:
        """Get rate limiting configuration for Gate.io endpoint."""
        # Find best matching endpoint
        for known_endpoint, context in self._endpoint_limits.items():
            if endpoint.startswith(known_endpoint):
                return context

        # Return default if no match
        return self._default_limit

    def get_stats(self) -> Dict[str, Any]:
        """Get Gate.io rate limiting statistics."""
        stats = {
            "exchange": "gateio",
            "global_available": self._global_semaphore._value,
            "endpoints": {}
        }

        for endpoint, context in self._endpoint_limits.items():
            semaphore = self._semaphores.get(endpoint)
            available = semaphore._value if semaphore else 0

            stats["endpoints"][endpoint] = {
                "requests_per_second": context.requests_per_second,
                "available_permits": available,
                "total_requests": self._request_counts.get(endpoint, 0),
                "last_request_time": self._last_request_times.get(endpoint, 0)
            }

        return stats