import asyncio
import time
from typing import Dict, Any

from core.transport.rest import RateLimitStrategy, RateLimitContext
from core.config.structs import ExchangeConfig


class MexcRateLimitStrategy(RateLimitStrategy):
    """MEXC-specific rate limiting based on ExchangeConfig."""

    def __init__(self, exchange_config: ExchangeConfig):
        """
        Initialize MEXC rate limiting strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing rate_limit settings
        """
        # Extract rate limits from config or use MEXC defaults
        if exchange_config.rate_limit:
            self.default_rps = float(exchange_config.rate_limit.requests_per_second)
            self.default_burst = self.default_rps * 3  # 3x burst capacity
            self.global_limit = 5  # MEXC default
        else:
            # MEXC HFT defaults
            self.default_rps = 20.0
            self.default_burst = 60
            self.global_limit = 5
        
        self.exchange_config = exchange_config
        
        # MEXC endpoint-specific rate limits
        self._endpoint_limits = {
            # Public endpoints - more generous limits
            "/api/v3/ticker/24hr": RateLimitContext(
                requests_per_second=10.0, burst_capacity=20, endpoint_weight=1
            ),
            "/api/v3/depth": RateLimitContext(
                requests_per_second=10.0, burst_capacity=20, endpoint_weight=1
            ),
            "/api/v3/klines": RateLimitContext(
                requests_per_second=5.0, burst_capacity=10, endpoint_weight=1
            ),
            "/api/v3/trades": RateLimitContext(
                requests_per_second=5.0, burst_capacity=10, endpoint_weight=1
            ),

            # Private endpoints - more restrictive
            "/api/v3/order": RateLimitContext(
                requests_per_second=2.0, burst_capacity=5, endpoint_weight=3
            ),
            "/api/v3/account": RateLimitContext(
                requests_per_second=1.0, burst_capacity=3, endpoint_weight=2
            ),
            "/api/v3/openOrders": RateLimitContext(
                requests_per_second=1.0, burst_capacity=3, endpoint_weight=2
            ),
            "/api/v3/allOrders": RateLimitContext(
                requests_per_second=0.5, burst_capacity=2, endpoint_weight=3
            ),
        }

        # Default rate limit for unknown endpoints
        self._default_limit = RateLimitContext(
            requests_per_second=5.0, burst_capacity=10, endpoint_weight=1
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

        # Global rate limiting
        self._global_semaphore = asyncio.Semaphore(self.global_limit)  # Max concurrent requests
        self._global_last_request = 0.0
        self._global_min_delay = 0.1  # 100ms between any requests

    async def acquire_permit(self, endpoint: str, request_weight: int = 1) -> bool:
        """Acquire rate limit permit for MEXC endpoint."""
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
        """Release rate limit permit for MEXC endpoint."""
        # Release endpoint-specific semaphore
        if endpoint in self._semaphores:
            self._semaphores[endpoint].release()

        # Release global semaphore
        self._global_semaphore.release()

    def get_rate_limit_context(self, endpoint: str) -> RateLimitContext:
        """Get rate limiting configuration for MEXC endpoint."""
        # Find best matching endpoint
        for known_endpoint, context in self._endpoint_limits.items():
            if endpoint.startswith(known_endpoint):
                return context

        # Return default if no match
        return self._default_limit

    def get_stats(self) -> Dict[str, Any]:
        """Get MEXC rate limiting statistics."""
        stats = {
            "exchange": "mexc",
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
