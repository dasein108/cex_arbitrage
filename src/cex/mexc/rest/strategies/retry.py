import asyncio
from typing import Dict

from core.exceptions.exchange import RateLimitErrorBase, ExchangeConnectionError
from core.transport.rest import RetryStrategy


class MexcRetryStrategy(RetryStrategy):
    """MEXC-specific retry logic with fast failure for HFT."""

    def __init__(self, **kwargs):
        self.max_attempts = 2  # Fast failure for HFT
        self.base_delay = 0.1  # 100ms base delay
        self.max_delay = 2.0   # 2 second max delay

    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if request should be retried for MEXC."""
        if attempt >= self.max_attempts:
            return False

        # Retry on connection errors and rate limits
        if isinstance(error, (
            RateLimitErrorBase,
            ExchangeConnectionError,
            asyncio.TimeoutError
        )):
            return True

        # Retry on 5xx server errors
        if hasattr(error, 'status_code') and 500 <= error.status_code < 600:
            return True

        return False

    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        """Calculate retry delay with MEXC-specific backoff."""
        if isinstance(error, RateLimitErrorBase):
            # Longer delay for rate limits
            return min(self.base_delay * (3 ** attempt), self.max_delay)

        # Exponential backoff for other errors
        delay = self.base_delay * (2 ** (attempt - 1))
        return min(delay, self.max_delay)

    def handle_rate_limit(self, response_headers: Dict[str, str]) -> float:
        """Extract rate limit information from MEXC response headers."""
        # MEXC-specific rate limit headers
        retry_after = response_headers.get('Retry-After')
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        # Check X-MBX-USED-WEIGHT headers (Binance-style)
        used_weight = response_headers.get('X-MBX-USED-WEIGHT-1M')
        if used_weight:
            try:
                weight = int(used_weight)
                if weight > 1000:  # Near limit
                    return 60.0  # Wait 1 minute
            except ValueError:
                pass

        # Default rate limit delay
        return 30.0  # 30 seconds default
