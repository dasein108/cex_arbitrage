"""
Retry Decorators for HFT Systems

High-performance retry decorators optimized for sub-millisecond overhead.
Replaces strategy pattern with direct decorator application for better performance.

Key Features:
- Sub-microsecond decorator overhead
- Configurable backoff strategies  
- Exchange-specific exception handling
- HFT-compliant retry timing
"""

import asyncio
import logging
from functools import wraps
from typing import Tuple, Type, Union, Callable, Any, Optional
import time
import aiohttp
from ..exceptions.exchange import (
    ExchangeRestError, RateLimitErrorRest, ExchangeConnectionRestError,
    RecvWindowError, OrderNotFoundError, OrderCancelledOrFilled
)


def retry_decorator(
    max_attempts: int = 3,
    backoff: str = "exponential", 
    base_delay: float = 0.1,
    max_delay: float = 5.0,
    exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    rate_limit_exceptions: Tuple[Type[Exception], ...] = (RateLimitErrorRest,),
    recv_window_exceptions: Tuple[Type[Exception], ...] = (RecvWindowError,)
):
    """
    Configurable retry decorator for REST requests with HFT optimization.
    
    Provides sub-microsecond overhead compared to strategy pattern dispatch.
    Handles different exception types with appropriate retry logic.
    
    Args:
        max_attempts: Maximum retry attempts (default: 3)
        backoff: Backoff strategy - "exponential", "linear", "fixed" (default: "exponential") 
        base_delay: Base delay in seconds (default: 0.1)
        max_delay: Maximum delay cap in seconds (default: 5.0)
        exceptions: Network/connection exceptions to retry
        rate_limit_exceptions: Rate limit exceptions (special handling)
        recv_window_exceptions: Timestamp sync exceptions (special handling)
        
    Returns:
        Decorated async function with retry logic
    """
    import aiohttp  # Import here to avoid circular imports
    
    # Default exceptions if not provided
    if exceptions is None:
        exceptions = (
            aiohttp.ClientConnectionError, 
            asyncio.TimeoutError,
            ExchangeConnectionRestError
        )
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except (OrderNotFoundError, OrderCancelledOrFilled) as e:
                    raise e
                except rate_limit_exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        raise
                    
                    # Rate limit specific delay (longer)
                    if backoff == "exponential":
                        delay = min(base_delay * (2 ** attempt), max_delay)
                    else:
                        delay = base_delay * 2  # Double delay for rate limits
                    
                    logging.warning(f"Rate limit hit on attempt {attempt}, waiting {delay}s")
                    await asyncio.sleep(delay)
                    
                except recv_window_exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        raise
                    
                    # RecvWindow errors need quick retry with timestamp refresh
                    logging.warning(f"RecvWindow error on attempt {attempt}, retrying quickly")
                    await asyncio.sleep(0.1)  # Fast retry for timestamp issues
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        raise
                    
                    # Calculate delay based on backoff strategy
                    if backoff == "exponential":
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    elif backoff == "linear":
                        delay = min(base_delay * attempt, max_delay)
                    else:  # fixed
                        delay = base_delay
                    
                    logging.debug(f"Request failed on attempt {attempt}, retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    # Don't retry other exceptions (business logic errors)
                    raise
            
            # Should never reach here, but raise last exception if we do
            raise last_exception
            
        return wrapper
    return decorator


def retry_with_backoff(
    attempts: int = 3,
    initial_delay: float = 0.1,
    backoff_factor: float = 2.0,
    max_delay: float = 5.0
):
    """
    Simple exponential backoff retry decorator.
    
    Optimized for common retry patterns with minimal configuration.
    
    Args:
        attempts: Number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for each retry (default: 2.0)
        max_delay: Maximum delay cap
        
    Returns:
        Decorated function with exponential backoff retry
    """
    return retry_decorator(
        max_attempts=attempts,
        backoff="exponential",
        base_delay=initial_delay,
        max_delay=max_delay
    )


class RetryContext:
    """
    Context manager for retry operations with performance tracking.
    
    Provides detailed metrics for HFT compliance monitoring.
    """
    
    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None):
        self.operation_name = operation_name
        self.logger = logger or logging.getLogger(__name__)
        self.start_time = None
        self.attempt_count = 0
        self.total_delay = 0.0
        
    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            total_time = (time.perf_counter() - self.start_time) * 1000
            
            self.logger.debug(
                f"Retry operation '{self.operation_name}' completed: "
                f"{self.attempt_count} attempts, {total_time:.2f}ms total, "
                f"{self.total_delay*1000:.2f}ms delay"
            )
    
    def record_attempt(self, delay: float = 0.0):
        """Record a retry attempt with delay."""
        self.attempt_count += 1
        self.total_delay += delay


# Exchange-specific retry decorators

def mexc_retry(max_attempts: int = 3):
    """MEXC-specific retry decorator with optimized settings."""
    return retry_decorator(
        max_attempts=max_attempts,
        backoff="exponential",
        base_delay=0.1,
        max_delay=2.0,  # MEXC has good performance, shorter max delay
        exceptions=(
            aiohttp.ClientConnectionError,
            asyncio.TimeoutError,
            ExchangeConnectionRestError
        )
    )


def gateio_retry(max_attempts: int = 3):
    """Gate.io-specific retry decorator with longer delays."""
    return retry_decorator(
        max_attempts=max_attempts,
        backoff="exponential", 
        base_delay=0.2,  # Gate.io benefits from slightly longer delays
        max_delay=5.0,
        exceptions=(
            aiohttp.ClientConnectionError,
            asyncio.TimeoutError,
            ExchangeConnectionRestError
        )
    )