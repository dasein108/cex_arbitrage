"""
MEXC-Specific REST Transport Strategies

HFT-optimized strategies for MEXC exchange API with aggressive performance targets.
Implements MEXC-specific rate limiting, authentication, and retry logic.

MEXC API Characteristics:
- Base URL: https://api.mexc.com
- Rate Limits: 1200 requests/minute (20 req/sec) for most endpoints
- Authentication: API Key + HMAC SHA256 signature
- Timeout: Aggressive timeouts for HFT (40ms target)
"""

import asyncio
import hashlib
import hmac
import time
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from core.exceptions.exchange import RateLimitErrorBase, ExchangeConnectionError
from .strategies import (
    RequestStrategy, RateLimitStrategy, RetryStrategy, AuthStrategy,
    RequestContext, RateLimitContext, PerformanceTargets
)
from .structs import HTTPMethod


class MexcRequestStrategy(RequestStrategy):
    """MEXC-specific request configuration with aggressive HFT settings."""
    
    def __init__(self, **kwargs):
        self.base_url = "https://api.mexc.com"
    
    async def create_request_context(self) -> RequestContext:
        """Create MEXC-optimized request configuration."""
        return RequestContext(
            base_url=self.base_url,
            timeout=8.0,  # Aggressive timeout for HFT
            max_concurrent=5,  # MEXC-specific concurrency limit
            connection_timeout=1.5,  # Fast connection establishment
            read_timeout=4.0,  # Fast read timeout
            keepalive_timeout=30,  # Shorter keepalive for fresh connections
            default_headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "HFTArbitrageEngine-MEXC/1.0"
            }
        )
    
    async def prepare_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Prepare MEXC-specific request parameters."""
        request_kwargs = {
            'headers': headers.copy(),
        }
        
        # MEXC uses query parameters for most requests
        if method == HTTPMethod.GET:
            if params:
                request_kwargs['params'] = params
        elif method in [HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.DELETE]:
            # For trading endpoints, MEXC typically uses form data
            if params:
                if 'Content-Type' not in headers or headers['Content-Type'] == 'application/json':
                    # Use JSON for complex data
                    request_kwargs['json'] = params
                else:
                    # Use form data for simple parameters
                    request_kwargs['data'] = params
        
        return request_kwargs
    
    def get_performance_targets(self) -> PerformanceTargets:
        """Get MEXC-specific HFT performance targets."""
        return PerformanceTargets(
            max_latency_ms=40.0,  # MEXC has good latency characteristics
            max_retry_attempts=2,  # Fast failure for HFT
            connection_timeout_ms=1500.0,
            read_timeout_ms=4000.0,
            target_throughput_rps=15.0  # Conservative for stability
        )


class MexcRateLimitStrategy(RateLimitStrategy):
    """MEXC-specific rate limiting with endpoint awareness."""
    
    def __init__(self, **kwargs):
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
        self._global_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests
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


class MexcAuthStrategy(AuthStrategy):
    """MEXC-specific authentication using API Key + HMAC SHA256."""
    
    def __init__(self, api_key: str, secret_key: str, **kwargs):
        self.api_key = api_key
        self.secret_key = secret_key.encode('utf-8')
    
    async def sign_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        timestamp: int
    ) -> Dict[str, str]:
        """Generate MEXC authentication headers."""
        # Add timestamp to parameters
        params = params.copy()
        params['timestamp'] = timestamp
        
        # Create query string
        query_string = urlencode(sorted(params.items()))
        
        # Create signature
        signature = hmac.new(
            self.secret_key,
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Return authentication headers
        return {
            'X-MEXC-APIKEY': self.api_key,
            'signature': signature
        }
    
    def requires_auth(self, endpoint: str) -> bool:
        """Check if MEXC endpoint requires authentication."""
        # Private endpoints that require authentication
        private_endpoints = [
            '/api/v3/account',
            '/api/v3/order',
            '/api/v3/openOrders',
            '/api/v3/allOrders',
            '/api/v3/myTrades',
        ]
        
        return any(endpoint.startswith(private_ep) for private_ep in private_endpoints)