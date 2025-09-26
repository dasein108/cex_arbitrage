import asyncio
from typing import Dict

from infrastructure.exceptions.exchange import RateLimitErrorRest, ExchangeConnectionRestError
from infrastructure.networking.http import RetryStrategy
from config.structs import ExchangeConfig


class GateioRetryStrategy(RetryStrategy):
    """Gate.io-specific retry logic based on ExchangeConfig."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize Gate.io retry strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing network retry settings
            logger: Optional HFT logger injection
            **kwargs: Additional parameters (ignored for compatibility)
        """
        # Extract retry settings from config or use Gate.io defaults
        if exchange_config.network:
            self.max_attempts = exchange_config.network.max_retries
            self.base_delay = exchange_config.network.retry_delay
            self.max_delay = self.base_delay * 12  # 12x max (Gate.io is more conservative)
        else:
            # Gate.io HFT defaults (more conservative than MEXC)
            self.max_attempts = 2
            self.base_delay = 0.2
            self.max_delay = 5.0
        
        self.exchange_config = exchange_config
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = ['gateio', 'rest', 'retry']
            logger = get_strategy_logger('rest.retry.gateio', tags)
        self.logger = logger

    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if request should be retried for Gate.io."""
        if attempt >= self.max_attempts:
            return False

        # Retry on connection errors and rate limits
        if isinstance(error, (
                RateLimitErrorRest,
                ExchangeConnectionRestError,
                asyncio.TimeoutError
        )):
            return True

        # Retry on 5xx server errors
        if hasattr(error, 'status_code') and 500 <= error.status_code < 600:
            return True

        # Gate.io specific error codes
        if hasattr(error, 'status_code'):
            # 429 Too Many Requests
            if error.status_code == 429:
                return True
            # 502 Bad Gateway, 503 Service Unavailable
            if error.status_code in [502, 503]:
                return True

        return False

    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        """Calculate retry delay with Gate.io-specific backoff."""
        if isinstance(error, RateLimitErrorRest):
            # Longer delay for rate limits (Gate.io is stricter)
            return min(self.base_delay * (4 ** attempt), self.max_delay)

        # Check for 429 Too Many Requests
        if hasattr(error, 'status_code') and error.status_code == 429:
            # Even longer delay for 429 errors
            return min(self.base_delay * (5 ** attempt), self.max_delay)

        # Exponential backoff for other errors
        delay = self.base_delay * (2 ** (attempt - 1))
        return min(delay, self.max_delay)

    def handle_rate_limit(self, response_headers: Dict[str, str]) -> float:
        """Extract rate limit information from Gate.io response headers."""
        # Gate.io-specific rate limit headers
        retry_after = response_headers.get('Retry-After')
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        # Check for Gate.io rate limit headers
        rate_limit_remaining = response_headers.get('X-Gate-RateLimit-Remaining')
        if rate_limit_remaining:
            try:
                remaining = int(rate_limit_remaining)
                if remaining < 5:  # Very low remaining requests
                    return 60.0  # Wait 1 minute
                elif remaining < 20:  # Low remaining requests
                    return 30.0  # Wait 30 seconds
            except ValueError:
                pass

        # Check for reset time
        rate_limit_reset = response_headers.get('X-Gate-RateLimit-Reset')
        if rate_limit_reset:
            try:
                reset_time = int(rate_limit_reset)
                # If reset time is within next 60 seconds, use it
                if reset_time <= 60:
                    return float(reset_time)
            except ValueError:
                pass

        # Default rate limit delay (Gate.io requires longer waits)
        return 45.0  # 45 seconds default