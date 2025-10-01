from typing import Dict

from exchanges.interfaces.rest.strategies import BaseExchangeRateLimit
from infrastructure.networking.http import RateLimitContext
from config.structs import ExchangeConfig


class MexcRateLimit(BaseExchangeRateLimit):
    """MEXC-specific rate limiting based on ExchangeConfig."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize MEXC rate limiting strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing rate_limit settings
            logger: Optional HFT logger injection
            **kwargs: Additional parameters (ignored for compatibility)
        """
        super().__init__(exchange_config, logger, **kwargs)
        

    @property
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        return "MEXC"

    def get_default_rate_limits(self) -> tuple[float, int, int]:
        """Get default rate limits for MEXC."""
        return (20.0, 60, 5)  # (rps, burst, global_limit)

    def get_endpoint_limits(self) -> Dict[str, RateLimitContext]:
        """Get MEXC-specific endpoint rate limits."""
        return {
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

    def get_default_limit(self) -> RateLimitContext:
        """Get default rate limit for unknown endpoints."""
        return RateLimitContext(
            requests_per_second=5.0, burst_capacity=10, endpoint_weight=1
        )

    def get_global_min_delay(self) -> float:
        """Get minimum delay between any requests (in seconds)."""
        return 0.1  # 100ms between any requests

    def _calculate_burst_capacity(self, rps: float) -> int:
        """Calculate burst capacity based on RPS for MEXC (3x)."""
        return int(rps * 3)  # 3x burst capacity

    def _get_global_limit_from_config(self) -> int:
        """Get global concurrent request limit for MEXC."""
        return 5  # MEXC default