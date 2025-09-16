"""
Gate.io-Specific REST Transport Strategies

Conservative HFT strategies for Gate.io exchange API with stricter rate limiting.
Implements Gate.io-specific authentication, rate limiting, and retry logic.

Gate.io API Characteristics:
- Base URL: https://api.gateio.ws
- Rate Limits: Conservative (200 requests/10 seconds for most endpoints)
- Authentication: API Key + HMAC SHA512 signature with complex signing
- Timeout: Conservative timeouts (60ms target) due to higher latency
"""

import asyncio
import hashlib
import hmac
import time
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from core.exceptions.exchange import RateLimitErrorBase, ExchangeConnectionError
from core.transport.rest.strategies import (
    RequestStrategy, RateLimitStrategy, RetryStrategy, AuthStrategy,
    RequestContext, RateLimitContext, PerformanceTargets, AuthenticationData
)
from core.transport.rest.structs import HTTPMethod


class GateioRequestStrategy(RequestStrategy):
    """Gate.io-specific request configuration with conservative HFT settings."""
    
    def __init__(self, **kwargs):
        self.base_url = "" #"https://api.gateio.ws"

    async def create_request_context(self) -> RequestContext:
        """Create Gate.io-optimized request configuration."""
        return RequestContext(
            base_url=self.base_url,
            timeout=12.0,  # Conservative timeout for Gate.io
            max_concurrent=2,  # Very conservative concurrency
            connection_timeout=3.0,  # Slower connection establishment
            read_timeout=8.0,  # Longer read timeout
            keepalive_timeout=60,  # Longer keepalive
            default_headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "HFTArbitrageEngine-Gateio/1.0"
            }
        )
    
    async def prepare_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Prepare Gate.io-specific request parameters."""
        request_kwargs = {
            'headers': headers.copy(),
        }
        
        # Gate.io prefers query parameters for most requests
        if method == HTTPMethod.GET:
            if params:
                request_kwargs['params'] = params
        elif method in [HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.DELETE]:
            # Gate.io typically uses JSON for POST/PUT requests
            if params:
                request_kwargs['json'] = params
        
        return request_kwargs
    
    def get_performance_targets(self) -> PerformanceTargets:
        """Get Gate.io-specific HFT performance targets."""
        return PerformanceTargets(
            max_latency_ms=60.0,  # Gate.io needs more conservative targets
            max_retry_attempts=3,  # More retries due to higher error rates
            connection_timeout_ms=3000.0,
            read_timeout_ms=8000.0,
            target_throughput_rps=5.0  # Very conservative for stability
        )


class GateioRateLimitStrategy(RateLimitStrategy):
    """Gate.io-specific rate limiting with very strict controls."""
    
    def __init__(self, **kwargs):
        # Gate.io endpoint-specific rate limits (very conservative)
        self._endpoint_limits = {
            # Public endpoints
            "/api/v4/spot/tickers": RateLimitContext(
                requests_per_second=2.0, burst_capacity=5, endpoint_weight=1
            ),
            "/api/v4/spot/order_book": RateLimitContext(
                requests_per_second=3.0, burst_capacity=6, endpoint_weight=1
            ),
            "/api/v4/spot/candlesticks": RateLimitContext(
                requests_per_second=2.0, burst_capacity=4, endpoint_weight=1
            ),
            "/api/v4/spot/trades": RateLimitContext(
                requests_per_second=2.0, burst_capacity=4, endpoint_weight=1
            ),
            
            # Private endpoints - very restrictive
            "/api/v4/spot/orders": RateLimitContext(
                requests_per_second=0.5, burst_capacity=2, endpoint_weight=5
            ),
            "/api/v4/spot/accounts": RateLimitContext(
                requests_per_second=0.3, burst_capacity=1, endpoint_weight=3
            ),
            "/api/v4/spot/open_orders": RateLimitContext(
                requests_per_second=0.3, burst_capacity=1, endpoint_weight=3
            ),
            "/api/v4/spot/my_trades": RateLimitContext(
                requests_per_second=0.2, burst_capacity=1, endpoint_weight=5
            ),
        }
        
        # Default rate limit for unknown endpoints (very conservative)
        self._default_limit = RateLimitContext(
            requests_per_second=1.0, burst_capacity=2, endpoint_weight=1
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
        
        # Global rate limiting (very strict)
        self._global_semaphore = asyncio.Semaphore(2)  # Max 2 concurrent requests
        self._global_last_request = 0.0
        self._global_min_delay = 0.3  # 300ms between any requests
    
    async def acquire_permit(self, endpoint: str, request_weight: int = 1) -> bool:
        """Acquire rate limit permit for Gate.io endpoint."""
        # Get rate limit context
        context = self.get_rate_limit_context(endpoint)
        
        # Acquire global semaphore first
        await self._global_semaphore.acquire()
        
        try:
            # Global rate limiting with strict delays
            current_time = time.time()
            time_since_last = current_time - self._global_last_request
            if time_since_last < self._global_min_delay:
                await asyncio.sleep(self._global_min_delay - time_since_last)
            self._global_last_request = time.time()
            
            # Endpoint-specific rate limiting
            if endpoint in self._semaphores:
                semaphore = self._semaphores[endpoint]
                await semaphore.acquire()
                
                # Apply stricter delay
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
        """Release rate limit permit for Gate.io endpoint."""
        # Release endpoint-specific semaphore
        if endpoint in self._semaphores:
            self._semaphores[endpoint].release()
        
        # Release global semaphore
        self._global_semaphore.release()
    
    def get_rate_limit_context(self, endpoint: str) -> RateLimitContext:
        """Get rate limiting configuration for Gate.io endpoint."""
        # Find best matching endpoint
        for known_endpoint, context in self._endpoint_limits.items():
            if endpoint.startswith(known_endpoint):
                return context
        
        # Return default if no match
        return self._default_limit
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Gate.io rate limiting statistics."""
        stats = {
            "exchange": "gateio",
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


class GateioRetryStrategy(RetryStrategy):
    """Gate.io-specific retry logic with more aggressive retries."""
    
    def __init__(self, **kwargs):
        self.max_attempts = 3  # More retries for Gate.io
        self.base_delay = 0.5  # 500ms base delay
        self.max_delay = 5.0   # 5 second max delay
    
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if request should be retried for Gate.io."""
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
        
        # Gate.io specific: retry on 502/503 more aggressively
        if hasattr(error, 'status_code') and error.status_code in [502, 503]:
            return True
        
        return False
    
    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        """Calculate retry delay with Gate.io-specific backoff."""
        if isinstance(error, RateLimitErrorBase):
            # Much longer delay for rate limits
            return min(self.base_delay * (4 ** attempt), self.max_delay)
        
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
        
        # Check custom Gate.io headers
        rate_limit_remaining = response_headers.get('X-Gate-Rate-Limit-Remaining')
        if rate_limit_remaining:
            try:
                remaining = int(rate_limit_remaining)
                if remaining < 5:  # Very low remaining requests
                    return 60.0  # Wait 1 minute
                elif remaining < 20:
                    return 30.0  # Wait 30 seconds
            except ValueError:
                pass
        
        # Default rate limit delay (longer for Gate.io)
        return 45.0  # 45 seconds default


class GateioAuthStrategy(AuthStrategy):
    """Gate.io-specific authentication using API Key + HMAC SHA512."""
    
    def __init__(self, api_key: str, secret_key: str, **kwargs):
        self.api_key = api_key
        self.secret_key = secret_key.encode('utf-8')
    
    async def sign_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        timestamp: int
    ) -> AuthenticationData:
        """Generate Gate.io authentication data."""
        # Gate.io uses a complex signing process
        
        # Create the request body
        if method == HTTPMethod.GET:
            query_string = urlencode(sorted(params.items())) if params else ""
            body = ""
        else:
            import json
            body = json.dumps(params, separators=(',', ':')) if params else ""
            query_string = ""
        
        # Create the signing payload
        # Format: METHOD\n/path/to/endpoint\nquery_string\nbody_hash\ntimestamp
        body_hash = hashlib.sha512(body.encode('utf-8')).hexdigest()
        
        signing_string = f"{method.value}\n{endpoint}\n{query_string}\n{body_hash}\n{timestamp}"
        
        # Create signature using HMAC SHA512
        signature = hmac.new(
            self.secret_key,
            signing_string.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        # Prepare authentication headers
        headers = {
            'KEY': self.api_key,
            'Timestamp': str(timestamp),
            'SIGN': signature
        }
        
        # Add content type for non-GET requests
        if method != HTTPMethod.GET:
            headers['Content-Type'] = 'application/json'
        
        # Return authentication data (Gate.io uses headers only, no additional params)
        return AuthenticationData(
            headers=headers,
            params={}  # Gate.io doesn't add auth params to URL/body
        )
    
    def requires_auth(self, endpoint: str) -> bool:
        """Check if Gate.io endpoint requires authentication."""
        # Private endpoints that require authentication
        private_endpoints = [
            '/api/v4/spot/accounts',
            '/api/v4/spot/orders',
            '/api/v4/spot/open_orders',
            '/api/v4/spot/my_trades',
            '/api/v4/wallet/deposits',
            '/api/v4/wallet/withdrawals',
        ]
        
        return any(endpoint.startswith(private_ep) for private_ep in private_endpoints)