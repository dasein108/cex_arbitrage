from typing import Dict

from config.structs import ExchangeConfig
from exchanges.interfaces.rest.base_rate_limit import BaseExchangeRateLimit, RateLimitContext

class GateioRateLimit(BaseExchangeRateLimit):
    """Gate.io-specific rate limiting based on ExchangeConfig."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize Gate.io rate limiting strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing rate_limit settings
            logger: Optional HFT logger injection
            **kwargs: Additional parameters (ignored for compatibility)
        """
        super().__init__(exchange_config, logger, **kwargs)
        

    @property
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        return "Gate.io"

    def get_default_rate_limits(self) -> tuple[float, int, int]:
        """Get default rate limits for Gate.io."""
        return (10.0, 20, 3)  # (rps, burst, global_limit)

    def get_endpoint_limits(self) -> Dict[str, RateLimitContext]:
        """Get Gate.io-specific endpoint rate limits."""
        return {
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

    def get_default_limit(self) -> RateLimitContext:
        """Get default rate limit for unknown endpoints."""
        return RateLimitContext(
            requests_per_second=3.0, burst_capacity=6, endpoint_weight=1
        )

    def get_global_min_delay(self) -> float:
        """Get minimum delay between any requests (in seconds)."""
        return 0.2  # 200ms between any requests (more conservative)

    def _calculate_burst_capacity(self, rps: float) -> int:
        """Calculate burst capacity based on RPS for Gate.io (2x)."""
        return int(rps * 2)  # Gate.io is more restrictive

    def _get_global_limit_from_config(self) -> int:
        """Get global concurrent request limit for Gate.io."""
        return 3  # Gate.io is more conservative