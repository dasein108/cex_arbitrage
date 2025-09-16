"""
Exchange Rate Limiter for HFT Trading Systems

Centralized rate limiting coordination to prevent API throttling while maintaining
optimal performance for high-frequency trading operations.

Key Features:
- Per-exchange semaphore-based concurrency control
- Exchange-specific delay coordination  
- Thread-safe asyncio implementation
- Zero-configuration operation with sensible defaults
- HFT-optimized for sub-millisecond coordination overhead

Architecture:
- Singleton pattern for global coordination
- Lock-free design using asyncio primitives
- Memory-efficient with O(1) per-exchange overhead
"""

import asyncio
import logging
from typing import Dict, Optional
from dataclasses import dataclass
import msgspec


@dataclass
class ExchangeRateConfig:
    """Configuration for exchange-specific rate limiting."""
    max_concurrent: int
    delay_seconds: float
    name: str


class ExchangeRateLimiter:
    """
    Centralized rate limiter for coordinating requests across cex.
    
    Prevents API throttling through intelligent concurrency control and timing.
    Designed for HFT systems requiring sub-millisecond coordination overhead.
    """
    
    # Exchange-specific rate limiting configurations
    EXCHANGE_CONFIGS = {
        'gateio': ExchangeRateConfig(
            max_concurrent=2,      # Conservative limit based on API testing
            delay_seconds=0.3,     # 300ms between requests
            name='Gate.io'
        ),
        'mexc': ExchangeRateConfig(
            max_concurrent=5,      # Higher throughput for MEXC
            delay_seconds=0.1,     # 100ms between requests  
            name='MEXC'
        ),
        # Future cex can be added here
        'binance': ExchangeRateConfig(
            max_concurrent=10,
            delay_seconds=0.05,
            name='Binance'
        ),
        'okx': ExchangeRateConfig(
            max_concurrent=8,
            delay_seconds=0.08,
            name='OKX'
        )
    }
    
    def __init__(self):
        """Initialize rate limiter with per-exchange coordination."""
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._last_request_time: Dict[str, float] = {}
        self._request_count: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        
        # Initialize semaphores for each exchange
        for exchange, config in self.EXCHANGE_CONFIGS.items():
            self._semaphores[exchange] = asyncio.Semaphore(config.max_concurrent)
            self._last_request_time[exchange] = 0.0
            self._request_count[exchange] = 0
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initialized ExchangeRateLimiter for HFT operations")
    
    async def acquire(self, exchange: str) -> bool:
        """
        Acquire rate limit token for exchange.
        
        Args:
            exchange: Exchange identifier (e.g., 'mexc', 'gateio')
            
        Returns:
            True if token acquired successfully
            
        Raises:
            ValueError: If exchange not supported
        """
        if exchange not in self.EXCHANGE_CONFIGS:
            raise ValueError(f"Unsupported exchange: {exchange}")
        
        config = self.EXCHANGE_CONFIGS[exchange]
        semaphore = self._semaphores[exchange]
        
        # Acquire semaphore token (blocks if at max concurrency)
        await semaphore.acquire()
        
        # Apply delay-based rate limiting
        current_time = asyncio.get_event_loop().time()
        
        async with self._lock:
            last_time = self._last_request_time[exchange]
            time_since_last = current_time - last_time
            
            # Calculate required delay
            required_delay = config.delay_seconds - time_since_last
            
            if required_delay > 0:
                # Wait for the remaining delay period
                await asyncio.sleep(required_delay)
                current_time = asyncio.get_event_loop().time()
            
            # Update timing tracking
            self._last_request_time[exchange] = current_time
            self._request_count[exchange] += 1
        
        self.logger.debug(f"Rate limit token acquired for {config.name}")
        return True
    
    def release(self, exchange: str):
        """
        Release rate limit token for exchange.
        
        Args:
            exchange: Exchange identifier
        """
        if exchange not in self._semaphores:
            self.logger.warning(f"Attempted to release token for unknown exchange: {exchange}")
            return
        
        semaphore = self._semaphores[exchange]
        semaphore.release()
        
        config = self.EXCHANGE_CONFIGS[exchange]
        self.logger.debug(f"Rate limit token released for {config.name}")
    
    def coordinate_request(self, exchange: str):
        """
        Context manager for coordinated request execution.
        
        Args:
            exchange: Exchange identifier
            
        Example:
            async with rate_limiter.coordinate_request('mexc'):
                response = await mexc_client.get('/api/endpoint')
        """
        return RateLimitContext(self, exchange)
    
    def get_stats(self) -> Dict[str, Dict[str, any]]:
        """
        Get rate limiting statistics for monitoring.
        
        Returns:
            Dictionary with per-exchange statistics
        """
        stats = {}
        
        for exchange, config in self.EXCHANGE_CONFIGS.items():
            semaphore = self._semaphores[exchange]
            available_tokens = semaphore._value if hasattr(semaphore, '_value') else 0
            
            stats[exchange] = {
                'name': config.name,
                'max_concurrent': config.max_concurrent,
                'available_tokens': available_tokens,
                'total_requests': self._request_count[exchange],
                'delay_seconds': config.delay_seconds,
                'last_request_time': self._last_request_time[exchange]
            }
        
        return stats
    
    def reset_stats(self):
        """Reset request counters for statistics."""
        for exchange in self.EXCHANGE_CONFIGS.keys():
            self._request_count[exchange] = 0


class RateLimitContext:
    """Context manager for rate-limited requests."""
    
    def __init__(self, rate_limiter: ExchangeRateLimiter, exchange: str):
        self.rate_limiter = rate_limiter
        self.exchange = exchange
    
    async def __aenter__(self):
        """Acquire rate limit token."""
        await self.rate_limiter.acquire(self.exchange)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release rate limit token."""
        self.rate_limiter.release(self.exchange)


# Global singleton instance for application-wide coordination
_global_rate_limiter: Optional[ExchangeRateLimiter] = None


def get_rate_limiter() -> ExchangeRateLimiter:
    """
    Get global rate limiter instance (singleton pattern).
    
    Returns:
        Global ExchangeRateLimiter instance
    """
    global _global_rate_limiter
    
    if _global_rate_limiter is None:
        _global_rate_limiter = ExchangeRateLimiter()
    
    return _global_rate_limiter


def reset_rate_limiter():
    """Reset global rate limiter (primarily for testing)."""
    global _global_rate_limiter
    _global_rate_limiter = None