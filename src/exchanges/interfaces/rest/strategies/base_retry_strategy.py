import asyncio
from abc import ABC, abstractmethod
from typing import Dict

from infrastructure.exceptions.exchange import RateLimitErrorRest, ExchangeConnectionRestError
from infrastructure.networking.http import RetryStrategy
from config.structs import ExchangeConfig


class BaseExchangeRetryStrategy(RetryStrategy, ABC):
    """
    Base retry strategy for exchanges with common exponential backoff patterns.
    
    Provides shared functionality for:
    - Exponential backoff algorithms
    - Rate limit specific retry logic
    - Common retry conditions
    - Response header parsing for rate limit info
    """

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize base exchange retry strategy.
        
        Args:
            exchange_config: Exchange configuration containing network retry settings
            logger: Optional HFT logger injection
            **kwargs: Additional parameters for exchange-specific needs
        """
        self.exchange_config = exchange_config
        
        # Initialize logger if not provided
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = [self.exchange_name.lower(), 'rest', 'retry']
            logger = get_strategy_logger(f'rest.retry.{self.exchange_name.lower()}', tags)
        self.logger = logger
        
        # Initialize retry settings
        self._initialize_retry_settings()

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        pass

    @abstractmethod
    def get_default_retry_settings(self) -> tuple[int, float, float]:
        """
        Get default retry settings for this exchange.
        
        Returns:
            tuple: (max_attempts, base_delay, max_delay)
        """
        pass

    @abstractmethod
    def get_rate_limit_multiplier(self) -> int:
        """Get backoff multiplier for rate limit errors."""
        pass

    @abstractmethod
    def get_default_rate_limit_delay(self) -> float:
        """Get default delay for rate limit errors when headers don't provide info."""
        pass

    def _initialize_retry_settings(self):
        """Initialize retry settings from config or defaults."""
        if self.exchange_config.network:
            self.max_attempts = self.exchange_config.network.max_retries
            self.base_delay = self.exchange_config.network.retry_delay
            self.max_delay = self._calculate_max_delay(self.base_delay)
        else:
            # Use exchange-specific defaults
            max_attempts, base_delay, max_delay = self.get_default_retry_settings()
            self.max_attempts = max_attempts
            self.base_delay = base_delay
            self.max_delay = max_delay

    @abstractmethod
    def _calculate_max_delay(self, base_delay: float) -> float:
        """Calculate maximum delay based on base delay for this exchange."""
        pass

    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if request should be retried."""
        if attempt >= self.max_attempts:
            return False

        # Common retry conditions
        if isinstance(error, (
                RateLimitErrorRest,
                ExchangeConnectionRestError,
                asyncio.TimeoutError
        )):
            return True

        # Retry on 5xx server errors
        if hasattr(error, 'status_code') and 500 <= error.status_code < 600:
            return True

        # Exchange-specific retry conditions
        return self._should_retry_exchange_specific(error)

    @abstractmethod
    def _should_retry_exchange_specific(self, error: Exception) -> bool:
        """Check exchange-specific retry conditions."""
        pass

    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        """Calculate retry delay with exchange-specific backoff."""
        if isinstance(error, RateLimitErrorRest):
            # Rate limit specific backoff
            multiplier = self.get_rate_limit_multiplier()
            return min(self.base_delay * (multiplier ** attempt), self.max_delay)

        # Check for specific HTTP status codes
        if hasattr(error, 'status_code'):
            delay = self._calculate_status_code_delay(error.status_code, attempt)
            if delay is not None:
                return delay

        # Standard exponential backoff
        delay = self.base_delay * (2 ** (attempt - 1))
        return min(delay, self.max_delay)

    @abstractmethod
    def _calculate_status_code_delay(self, status_code: int, attempt: int) -> float | None:
        """Calculate delay for specific HTTP status codes. Return None for default handling."""
        pass

    def handle_rate_limit(self, response_headers: Dict[str, str]) -> float:
        """Extract rate limit information from response headers."""
        # Standard Retry-After header
        retry_after = response_headers.get('Retry-After')
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        # Exchange-specific rate limit header handling
        exchange_delay = self._parse_exchange_rate_limit_headers(response_headers)
        if exchange_delay is not None:
            return exchange_delay

        # Default rate limit delay
        return self.get_default_rate_limit_delay()

    @abstractmethod
    def _parse_exchange_rate_limit_headers(self, response_headers: Dict[str, str]) -> float | None:
        """
        Parse exchange-specific rate limit headers.
        
        Returns:
            float: Delay in seconds, or None if no exchange-specific headers found
        """
        pass