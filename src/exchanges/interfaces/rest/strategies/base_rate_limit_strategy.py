import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, Any

from infrastructure.networking.http import RateLimitStrategy, RateLimitContext
from config.structs import ExchangeConfig


class BaseExchangeRateLimitStrategy(RateLimitStrategy, ABC):
    """
    Base rate limiting strategy for exchanges with common semaphore-based patterns.
    
    Provides shared functionality for:
    - Global and endpoint-specific rate limiting
    - Semaphore-based concurrency control
    - Request timing and statistics
    - Configurable rate limits from ExchangeConfig
    """

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize base exchange rate limiting strategy.
        
        Args:
            exchange_config: Exchange configuration containing rate_limit settings
            logger: Optional HFT logger injection
            **kwargs: Additional parameters for exchange-specific needs
        """
        self.exchange_config = exchange_config
        
        # Initialize logger if not provided
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = [self.exchange_name.lower(), 'rest', 'rate_limit']
            logger = get_strategy_logger(f'rest.rate_limit.{self.exchange_name.lower()}', tags)
        self.logger = logger
        
        # Extract rate limits from config or use exchange defaults
        self._initialize_rate_limits()
        
        # Initialize endpoint-specific limits
        self._endpoint_limits = self.get_endpoint_limits()
        self._default_limit = self.get_default_limit()
        
        # Initialize semaphores and tracking
        self._semaphores = {}
        self._last_request_times = {}
        self._request_counts = {}
        
        for endpoint, context in self._endpoint_limits.items():
            self._semaphores[endpoint] = asyncio.Semaphore(context.burst_capacity)
            self._last_request_times[endpoint] = 0.0
            self._request_counts[endpoint] = 0
        
        # Global rate limiting
        self._global_semaphore = asyncio.Semaphore(self.global_limit)
        self._global_last_request = 0.0
        self._global_min_delay = self.get_global_min_delay()

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        pass

    @abstractmethod
    def get_default_rate_limits(self) -> tuple[float, int, int]:
        """
        Get default rate limits for this exchange.
        
        Returns:
            tuple: (requests_per_second, burst_capacity, global_limit)
        """
        pass

    @abstractmethod
    def get_endpoint_limits(self) -> Dict[str, RateLimitContext]:
        """Get exchange-specific endpoint rate limits."""
        pass

    @abstractmethod
    def get_default_limit(self) -> RateLimitContext:
        """Get default rate limit for unknown endpoints."""
        pass

    @abstractmethod
    def get_global_min_delay(self) -> float:
        """Get minimum delay between any requests (in seconds)."""
        pass

    def _initialize_rate_limits(self):
        """Initialize rate limits from config or defaults."""
        if self.exchange_config.rate_limit:
            self.default_rps = float(self.exchange_config.rate_limit.requests_per_second)
            self.default_burst = self._calculate_burst_capacity(self.default_rps)
            self.global_limit = self._get_global_limit_from_config()
        else:
            # Use exchange-specific defaults
            default_rps, default_burst, global_limit = self.get_default_rate_limits()
            self.default_rps = default_rps
            self.default_burst = default_burst
            self.global_limit = global_limit

    @abstractmethod
    def _calculate_burst_capacity(self, rps: float) -> int:
        """Calculate burst capacity based on RPS for this exchange."""
        pass

    @abstractmethod
    def _get_global_limit_from_config(self) -> int:
        """Get global concurrent request limit for this exchange."""
        pass

    async def acquire_permit(self, endpoint: str, request_weight: int = 1) -> bool:
        """Acquire rate limit permit for endpoint."""
        # Get rate limit context
        context = self.get_rate_limit_context(endpoint)

        # Acquire global semaphore first
        await self._global_semaphore.acquire()

        try:
            # Global rate limiting
            await self._apply_global_rate_limiting()

            # Endpoint-specific rate limiting
            if endpoint in self._semaphores:
                await self._apply_endpoint_rate_limiting(endpoint, context)

            return True
        except:
            # Release global semaphore on error
            self._global_semaphore.release()
            raise

    async def _apply_global_rate_limiting(self):
        """Apply global rate limiting delay."""
        current_time = time.time()
        time_since_last = current_time - self._global_last_request
        if time_since_last < self._global_min_delay:
            await asyncio.sleep(self._global_min_delay - time_since_last)
        self._global_last_request = time.time()

    async def _apply_endpoint_rate_limiting(self, endpoint: str, context: RateLimitContext):
        """Apply endpoint-specific rate limiting."""
        semaphore = self._semaphores[endpoint]
        await semaphore.acquire()

        # Apply delay if needed
        current_time = time.time()
        last_time = self._last_request_times[endpoint]
        required_delay = (1.0 / context.requests_per_second) - (current_time - last_time)
        if required_delay > 0:
            await asyncio.sleep(required_delay)

        self._last_request_times[endpoint] = time.time()
        self._request_counts[endpoint] += 1

    def release_permit(self, endpoint: str, request_weight: int = 1) -> None:
        """Release rate limit permit for endpoint."""
        # Release endpoint-specific semaphore
        if endpoint in self._semaphores:
            self._semaphores[endpoint].release()

        # Release global semaphore
        self._global_semaphore.release()

    def get_rate_limit_context(self, endpoint: str) -> RateLimitContext:
        """Get rate limiting configuration for endpoint."""
        # Find best matching endpoint
        for known_endpoint, context in self._endpoint_limits.items():
            if endpoint.startswith(known_endpoint):
                return context

        # Return default if no match
        return self._default_limit

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiting statistics."""
        stats = {
            "exchange": self.exchange_name.lower(),
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