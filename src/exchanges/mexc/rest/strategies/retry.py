import asyncio
from typing import Dict

from core.exceptions.exchange import RateLimitErrorBase, ExchangeConnectionError
from core.transport.rest import RetryStrategy
from core.config.structs import ExchangeConfig

# HFT Logger Integration
from core.logging import get_strategy_logger, LoggingTimer


class MexcRetryStrategy(RetryStrategy):
    """MEXC-specific retry logic based on ExchangeConfig."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None):
        """
        Initialize MEXC retry strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing network retry settings
            logger: Optional HFT logger injection
        """
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            tags = ['mexc', 'public', 'rest', 'retry']  # Default to public
            logger = get_strategy_logger('rest.retry.mexc.public', tags)
        
        self.logger = logger
        
        # Extract retry settings from config or use MEXC defaults
        if exchange_config.network:
            self.max_attempts = exchange_config.network.max_retries
            self.base_delay = exchange_config.network.retry_delay
            self.max_delay = self.base_delay * 10  # 10x max
        else:
            # MEXC HFT defaults
            self.max_attempts = 2
            self.base_delay = 0.1
            self.max_delay = 2.0
        
        self.exchange_config = exchange_config
        
        # Log strategy initialization
        self.logger.info("MEXC retry strategy initialized",
                        max_attempts=self.max_attempts,
                        base_delay=self.base_delay,
                        max_delay=self.max_delay)
        
        self.logger.metric("rest_retry_strategies_created", 1,
                          tags={"exchange": "mexc"})

    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if request should be retried for MEXC."""
        should_retry = False
        error_type = type(error).__name__
        
        if attempt >= self.max_attempts:
            self.logger.debug("Max retry attempts reached",
                            attempt=attempt,
                            max_attempts=self.max_attempts,
                            error_type=error_type)
            return False

        # Retry on connection errors and rate limits
        if isinstance(error, (
            RateLimitErrorBase,
            ExchangeConnectionError,
            asyncio.TimeoutError
        )):
            should_retry = True

        # Retry on 5xx server errors
        if hasattr(error, 'status_code') and 500 <= error.status_code < 600:
            should_retry = True

        # Log retry decision
        self.logger.debug("Retry decision made",
                        attempt=attempt,
                        error_type=error_type,
                        should_retry=should_retry)
        
        # Track retry decision metrics
        self.logger.metric("rest_retry_decisions", 1,
                          tags={"exchange": "mexc", "should_retry": str(should_retry), "error_type": error_type})
        
        return should_retry

    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        """Calculate retry delay with MEXC-specific backoff."""
        error_type = type(error).__name__
        
        if isinstance(error, RateLimitErrorBase):
            # Longer delay for rate limits
            delay = min(self.base_delay * (3 ** attempt), self.max_delay)
            delay_reason = "rate_limit_backoff"
        else:
            # Exponential backoff for other errors
            delay = self.base_delay * (2 ** (attempt - 1))
            delay = min(delay, self.max_delay)
            delay_reason = "exponential_backoff"
        
        # Log and track delay calculation
        self.logger.debug("Retry delay calculated",
                        attempt=attempt,
                        error_type=error_type,
                        delay_seconds=delay,
                        delay_reason=delay_reason)
        
        self.logger.metric("rest_retry_delays", delay,
                          tags={"exchange": "mexc", "error_type": error_type, "attempt": str(attempt)})
        
        return delay

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