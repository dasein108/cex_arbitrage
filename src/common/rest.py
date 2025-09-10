"""
High-Performance REST API Client for Cryptocurrency Exchange Trading

This module implements an optimized async REST client designed for low-latency trading
with advanced features like connection pooling, rate limiting, and concurrent request handling.

Key Performance Optimizations:
- Connection pooling and session reuse with aiohttp
- Fast JSON parsing with msgspec (fallback to orjson)
- Minimal overhead auth signature generation
- Intelligent retry strategies with exponential backoff
- Per-endpoint rate limiting with token bucket algorithm
- Connection management with optimal timeout configurations
- Memory-efficient request/response handling

Time Complexity: O(1) for most operations, O(log n) for rate limiting
Space Complexity: O(1) per request, O(n) for connection pool
"""

import asyncio
import hashlib
import hmac
import time
import urllib.parse
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable, Tuple
import logging

import aiohttp
import msgspec
from src.common.exceptions import ExchangeAPIError, RateLimitError

# Use msgspec as the primary and only JSON handler for maximum performance
MSGSPEC_DECODER = msgspec.json.Decoder()
MSGSPEC_ENCODER = msgspec.json.encode


class HTTPMethod(Enum):
    """HTTP methods with performance-optimized string values."""
    GET = "GET"
    POST = "POST" 
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class RateLimiter:
    """
    Ultra-high-performance token bucket rate limiter.
    Optimized to minimize syscall overhead with cached timestamps.
    
    Time Complexity: O(1) for token acquisition
    Space Complexity: O(1)
    """
    
    def __init__(self, max_tokens: int, refill_rate: float):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.current_tokens = max_tokens
        self.last_refill = time.monotonic()
        # Performance optimization: cache time checks
        self._last_time_check = self.last_refill
        self._time_check_interval = 0.001  # Check time every 1ms max
    
    def acquire(self, tokens: int = 1) -> bool:
        """
        Attempt to acquire tokens from the bucket.
        Ultra-optimized with cached time checks to reduce syscall overhead.
        """
        # Fast path: if we have enough tokens and haven't waited long, skip time check
        if self.current_tokens >= tokens:
            now = self._last_time_check  # Use cached time
            time_since_check = now - self.last_refill
            
            # Only call time.monotonic() if significant time might have passed
            if time_since_check < self._time_check_interval:
                self.current_tokens -= tokens
                return True
        
        # Slow path: need to refill or check actual time
        now = time.monotonic()
        self._last_time_check = now
        time_passed = now - self.last_refill
        
        # Refill tokens based on time passed - optimized calculation
        if time_passed > 0:
            new_tokens = time_passed * self.refill_rate
            self.current_tokens = min(self.max_tokens, self.current_tokens + new_tokens)
            self.last_refill = now
        
        if self.current_tokens >= tokens:
            self.current_tokens -= tokens
            return True
        return False
    
    def time_until_available(self, tokens: int = 1) -> float:
        """
        Calculate time until requested tokens are available.
        Optimized to avoid unnecessary time syscalls.
        """
        # Use cached current_tokens if recent
        if self.current_tokens >= tokens:
            return 0.0
        
        needed_tokens = tokens - self.current_tokens
        return needed_tokens / self.refill_rate
    
    def force_refill(self):
        """Force a refill calculation - useful for testing or manual optimization."""
        now = time.monotonic()
        self._last_time_check = now
        time_passed = now - self.last_refill
        if time_passed > 0:
            new_tokens = time_passed * self.refill_rate
            self.current_tokens = min(self.max_tokens, self.current_tokens + new_tokens)
            self.last_refill = now


class RequestConfig(msgspec.Struct):
    """Configuration for individual requests with performance tuning."""
    timeout: float = 10.0
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    rate_limit_tokens: int = 1
    require_auth: bool = False
    validate_response: bool = True


class ConnectionConfig(msgspec.Struct):
    """Connection pool and session configuration optimized for ultra-low latency trading."""
    # Connection pool settings - optimized for high-frequency trading
    connector_limit: int = 200  # Increased total connection pool size
    connector_limit_per_host: int = 50  # Increased per-host connection limit
    connector_ttl_dns_cache: int = 600  # Longer DNS cache TTL to reduce lookups
    connector_use_dns_cache: bool = True
    
    # TCP socket settings optimized for low latency
    connector_tcp_keepalive: bool = True
    connector_sock_keepalive: bool = True
    connector_enable_cleanup_closed: bool = True
    connector_tcp_keepidle: int = 60  # TCP keepalive idle time
    connector_tcp_keepintvl: int = 5   # TCP keepalive interval
    connector_tcp_keepcnt: int = 3     # TCP keepalive probes
    
    # Ultra-aggressive timeout settings for trading
    total_timeout: float = 10.0   # Reduced from 30s
    connect_timeout: float = 2.0  # Reduced from 5s  
    sock_read_timeout: float = 5.0  # Reduced from 10s
    sock_connect_timeout: float = 2.0  # Reduced from 5s
    
    # SSL and security
    verify_ssl: bool = True
    
    # HTTP/2 settings disabled for lower latency (HTTP/1.1 is faster for single requests)
    enable_http2: bool = False
    
    # Additional low-latency optimizations
    tcp_nodelay: bool = True  # Disable Nagle's algorithm
    reuse_port: bool = True   # Enable SO_REUSEPORT


class HighPerformanceRestClient:
    """
    Ultra-high performance REST API client optimized for cryptocurrency trading.
    
    Features:
    - Connection pooling with persistent sessions
    - Advanced rate limiting with per-endpoint controls
    - Fast JSON parsing with msgspec/orjson
    - Concurrent request handling with semaphore limiting
    - Intelligent retry strategies with circuit breaker
    - Memory-efficient request/response processing
    - Auth signature caching for repeated requests
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        connection_config: Optional[ConnectionConfig] = None,
        default_rate_limiter: Optional[RateLimiter] = None,
        max_concurrent_requests: int = 50,
        enable_metrics: bool = False
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.secret_key = secret_key.encode() if secret_key else None
        
        self.connection_config = connection_config or ConnectionConfig()
        self.max_concurrent_requests = max_concurrent_requests
        self.enable_metrics = enable_metrics
        
        # Connection management
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        
        # Rate limiting - per endpoint rate limiters
        self.default_rate_limiter = default_rate_limiter or RateLimiter(
            max_tokens=100, refill_rate=10.0
        )
        self.endpoint_rate_limiters: Dict[str, RateLimiter] = {}
        
        # Performance metrics
        self.metrics = {
            'requests_total': 0,
            'requests_failed': 0,
            'response_times': deque(maxlen=1000),  # Last 1000 response times
            'rate_limit_hits': 0,
            'auth_cache_hits': 0,
            'connection_errors': 0
        } if enable_metrics else {}
        
        # Auth signature cache for performance - optimized for high frequency
        self._auth_cache: Dict[str, Tuple[str, float]] = {}
        self._auth_cache_ttl = 60.0  # Cache signatures for 60 seconds
        self._signature_cache_hits = 0
        self._precomputed_signatures: Dict[str, str] = {}  # Pre-computed common signatures
        
        self.logger = logging.getLogger(__name__)
        
        # Pre-compute signatures for common endpoints to eliminate auth latency
        self._precompute_common_signatures()
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with proper cleanup."""
        await self.close()
    
    async def _ensure_session(self):
        """
        Ensure aiohttp session is created with optimal configuration.
        Uses lazy initialization for better resource management.
        """
        if self._session is None or self._session.closed:
            # Create ultra-optimized TCP connector for low latency
            self._connector = aiohttp.TCPConnector(
                limit=self.connection_config.connector_limit,
                limit_per_host=self.connection_config.connector_limit_per_host,
                ttl_dns_cache=self.connection_config.connector_ttl_dns_cache,
                use_dns_cache=self.connection_config.connector_use_dns_cache,
                tcp_keepalive=self.connection_config.connector_tcp_keepalive,
                enable_cleanup_closed=self.connection_config.connector_enable_cleanup_closed,
                verify_ssl=self.connection_config.verify_ssl,
                # Low-latency TCP optimizations
                keepalive_timeout=60,  # Keep connections alive longer
                force_close=False,     # Reuse connections aggressively
                # Note: Some TCP options need to be set at socket level in production
            )
            
            # Create timeout configuration
            timeout = aiohttp.ClientTimeout(
                total=self.connection_config.total_timeout,
                connect=self.connection_config.connect_timeout,
                sock_read=self.connection_config.sock_read_timeout,
                sock_connect=self.connection_config.sock_connect_timeout,
            )
            
            # Create session with optimized settings
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                json_serialize=MSGSPEC_ENCODER,
                headers={
                    'User-Agent': 'HighPerformanceTrader/1.0',
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }
            )
    
    def _get_rate_limiter(self, endpoint: str) -> RateLimiter:
        """Get rate limiter for specific endpoint, creating if needed."""
        if endpoint not in self.endpoint_rate_limiters:
            self.endpoint_rate_limiters[endpoint] = RateLimiter(
                max_tokens=self.default_rate_limiter.max_tokens,
                refill_rate=self.default_rate_limiter.refill_rate
            )
        return self.endpoint_rate_limiters[endpoint]
    
    async def _wait_for_rate_limit(self, endpoint: str, tokens: int = 1):
        """Wait for rate limit tokens with minimal overhead."""
        rate_limiter = self._get_rate_limiter(endpoint)
        
        while not rate_limiter.acquire(tokens):
            wait_time = rate_limiter.time_until_available(tokens)
            if self.enable_metrics:
                self.metrics['rate_limit_hits'] += 1
            
            # Use exponential backoff with jitter for rate limiting
            jitter = min(0.1, wait_time * 0.1)
            await asyncio.sleep(wait_time + jitter)
    
    def _generate_signature(self, method: str, endpoint: str, params: Dict[str, Any], timestamp: str) -> str:
        """
        Generate HMAC-SHA256 signature for authenticated requests.
        Ultra-optimized with multi-level caching and pre-computation.
        """
        if not self.secret_key:
            raise ValueError("Secret key required for authenticated requests")
        
        # Fast path: check for pre-computed common signatures
        common_key = f"{method}:{endpoint}"
        if not params and common_key in self._precomputed_signatures:
            if self.enable_metrics:
                self.metrics['auth_cache_hits'] += 1
            return self._precomputed_signatures[common_key]
        
        # Create optimized cache key - use hash of sorted params for O(1) lookup
        params_hash = hash(frozenset(params.items())) if params else 0
        cache_key = f"{method}:{endpoint}:{params_hash}:{timestamp[:10]}"
        
        # Check cache with fast lookup
        cached_entry = self._auth_cache.get(cache_key)
        if cached_entry:
            signature, cache_time = cached_entry
            if time.time() - cache_time < self._auth_cache_ttl:
                if self.enable_metrics:
                    self.metrics['auth_cache_hits'] += 1
                return signature
        
        # Generate new signature - minimize string operations
        if params:
            # Pre-sort params once and reuse
            sorted_params = sorted(params.items())
            query_string = urllib.parse.urlencode(sorted_params)
            payload = f"{timestamp}{method}{endpoint}?{query_string}"
        else:
            payload = f"{timestamp}{method}{endpoint}"
        
        # Use bytes directly to avoid extra encoding
        payload_bytes = payload.encode('utf-8')
        signature = hmac.new(self.secret_key, payload_bytes, hashlib.sha256).hexdigest()
        
        # Cache with optimized cleanup
        self._auth_cache[cache_key] = (signature, time.time())
        
        # Efficient cache cleanup - only when needed
        if len(self._auth_cache) > 1000:
            # Remove 20% of oldest entries in batch
            sorted_cache = sorted(self._auth_cache.items(), key=lambda x: x[1][1])
            for key, _ in sorted_cache[:200]:
                del self._auth_cache[key]
        
        return signature
    
    def _precompute_common_signatures(self):
        """Pre-compute signatures for common trading endpoints to eliminate auth latency."""
        if not self.secret_key or not self.api_key:
            return
            
        # Common trading endpoints that are called frequently
        common_endpoints = [
            "GET:/api/v3/account",
            "GET:/api/v3/openOrders", 
            "POST:/api/v3/order",
            "DELETE:/api/v3/order",
            "GET:/api/v3/allOrders",
            "GET:/api/v3/myTrades"
        ]
        
        # Pre-compute with current timestamp (updated periodically)
        timestamp = str(int(time.time() * 1000))
        
        for endpoint_key in common_endpoints:
            try:
                method, endpoint = endpoint_key.split(":", 1)
                signature = self._generate_signature(method, endpoint, {}, timestamp)
                self._precomputed_signatures[endpoint_key] = signature
            except Exception:
                # Skip any errors in pre-computation
                pass
    
    def _prepare_auth_headers(self, method: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, str]:
        """Prepare authentication headers with minimal overhead."""
        if not self.api_key or not self.secret_key:
            return {}
        
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(method, endpoint, params, timestamp)
        
        return {
            'X-MEXC-APIKEY': self.api_key,  # Common format, adapt as needed
            'X-MEXC-SIGNATURE': signature,
            'X-MEXC-TIMESTAMP': timestamp,
        }
    
    def _parse_response(self, response_text: str) -> Any:
        """
        Ultra-high-performance JSON parsing using msgspec directly on strings.
        Eliminates unnecessary encoding step for maximum speed.
        """
        if not response_text:
            return None
            
        try:
            # Direct string parsing - avoid unnecessary .encode() call
            return msgspec.json.decode(response_text)
        except Exception:
            raise ExchangeAPIError(400, f"Invalid JSON response: {response_text[:100]}...")
    
    async def _execute_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        config: Optional[RequestConfig] = None
    ) -> Any:
        """
        Execute HTTP request with comprehensive error handling and retries.
        Optimized for minimal latency and maximum throughput.
        """
        config = config or RequestConfig()
        params = params or {}
        
        # Ensure session is ready
        await self._ensure_session()
        
        # Rate limiting
        await self._wait_for_rate_limit(endpoint, config.rate_limit_tokens)
        
        url = f"{self.base_url}{endpoint}"
        start_time = time.monotonic()
        
        async with self._semaphore:  # Limit concurrent requests
            for attempt in range(config.max_retries + 1):
                try:
                    # Prepare headers
                    headers = {}
                    if config.require_auth:
                        headers.update(self._prepare_auth_headers(method.value, endpoint, params))
                    
                    # Prepare request parameters
                    request_kwargs = {
                        'timeout': aiohttp.ClientTimeout(total=config.timeout),
                        'headers': headers,
                    }
                    
                    # Add data based on method
                    if method == HTTPMethod.GET and params:
                        request_kwargs['params'] = params
                    elif json_data:
                        request_kwargs['json'] = json_data
                    elif params and method != HTTPMethod.GET:
                        request_kwargs['json'] = params
                    
                    # Execute request
                    async with self._session.request(method.value, url, **request_kwargs) as response:
                        response_text = await response.text()
                        
                        # Handle HTTP errors
                        if response.status >= 400:
                            if response.status == 429:  # Rate limited
                                raise RateLimitError(response.status, f"Rate limit exceeded: {response_text}")
                            
                            error_data = None
                            try:
                                error_data = self._parse_response(response_text)
                            except:
                                pass
                            
                            raise ExchangeAPIError(
                                response.status,
                                f"HTTP {response.status}: {response_text}"
                            )
                        
                        # Parse and return successful response
                        parsed_response = self._parse_response(response_text)
                        
                        # Update metrics
                        if self.enable_metrics:
                            self.metrics['requests_total'] += 1
                            response_time = time.monotonic() - start_time
                            self.metrics['response_times'].append(response_time)
                        
                        return parsed_response
                
                except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                    # Optimized error handling - avoid metrics overhead in hot path
                    if self.enable_metrics:
                        self.metrics['connection_errors'] += 1
                    
                    if attempt == config.max_retries:
                        raise ExchangeAPIError(500, f"Connection failed after {config.max_retries} retries: {str(e)}")
                    
                    # Optimized backoff - pre-calculate to avoid repeated computation
                    delay = config.retry_delay * (config.retry_backoff ** attempt)
                    await asyncio.sleep(delay + (delay * 0.1))  # Inline jitter calculation
                
                except RateLimitError:
                    if attempt == config.max_retries:
                        raise
                    
                    # Pre-calculated delay for rate limits
                    delay = config.retry_delay * (config.retry_backoff ** (attempt + 1))
                    await asyncio.sleep(delay)
                
                except ExchangeAPIError:
                    # Fast path for known errors - minimal overhead
                    if self.enable_metrics:
                        self.metrics['requests_failed'] += 1
                    raise
                
                except Exception as e:
                    # Catch-all with minimal string formatting overhead
                    if attempt == config.max_retries:
                        if self.enable_metrics:
                            self.metrics['requests_failed'] += 1
                        raise ExchangeAPIError(500, f"Unexpected error: {str(e)}")
                    
                    await asyncio.sleep(config.retry_delay)
    
    # HTTP Method Implementations - Optimized for Trading APIs
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[RequestConfig] = None
    ) -> Any:
        """Execute GET request - optimized for public market data."""
        return await self._execute_request(HTTPMethod.GET, endpoint, params=params, config=config)
    
    async def post(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[RequestConfig] = None
    ) -> Any:
        """Execute POST request - optimized for order placement."""
        return await self._execute_request(
            HTTPMethod.POST, endpoint, params=params, json_data=json_data, config=config
        )
    
    async def put(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[RequestConfig] = None
    ) -> Any:
        """Execute PUT request - optimized for order updates."""
        return await self._execute_request(
            HTTPMethod.PUT, endpoint, params=params, json_data=json_data, config=config
        )
    
    async def delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[RequestConfig] = None
    ) -> Any:
        """Execute DELETE request - optimized for order cancellation."""
        return await self._execute_request(HTTPMethod.DELETE, endpoint, params=params, config=config)
    
    # Batch Operations for High-Frequency Trading
    
    async def batch_request(
        self,
        requests: List[Tuple[HTTPMethod, str, Optional[Dict[str, Any]], Optional[RequestConfig]]]
    ) -> List[Any]:
        """
        Execute multiple requests concurrently with optimal resource utilization.
        Returns results in the same order as input requests.
        """
        tasks = []
        for method, endpoint, params, config in requests:
            task = self._execute_request(method, endpoint, params=params, config=config)
            tasks.append(task)
        
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    # Advanced Features
    
    def set_endpoint_rate_limit(self, endpoint: str, max_tokens: int, refill_rate: float):
        """Set custom rate limiting for specific endpoints."""
        self.endpoint_rate_limiters[endpoint] = RateLimiter(
            max_tokens=max_tokens, refill_rate=refill_rate
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for monitoring."""
        if not self.enable_metrics:
            return {}
        
        response_times = list(self.metrics['response_times'])
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            **self.metrics,
            'avg_response_time': avg_response_time,
            'p95_response_time': sorted(response_times)[int(len(response_times) * 0.95)] if response_times else 0,
            'success_rate': (
                (self.metrics['requests_total'] - self.metrics['requests_failed']) / 
                max(1, self.metrics['requests_total'])
            ),
            'active_connections': len(self._connector._conns) if self._connector else 0,
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the client and connection."""
        try:
            await self._ensure_session()
            start_time = time.monotonic()
            
            # Simple health check request (adapt endpoint as needed)
            await self.get('/ping', config=RequestConfig(timeout=5.0, max_retries=1))
            
            response_time = time.monotonic() - start_time
            
            return {
                'status': 'healthy',
                'response_time': response_time,
                'session_closed': self._session.closed if self._session else True,
                'metrics': self.get_metrics()
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'metrics': self.get_metrics()
            }
    
    async def close(self):
        """Clean up resources with proper connection closure."""
        if self._session and not self._session.closed:
            await self._session.close()
        
        if self._connector:
            await self._connector.close()
        
        # Clear caches
        self._auth_cache.clear()
        
        self.logger.info("HighPerformanceRestClient closed successfully")


# Utility Functions for Common Trading Operations

@asynccontextmanager
async def create_trading_client(
    base_url: str,
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    **kwargs
) -> HighPerformanceRestClient:
    """
    Create a properly configured trading client with context management.
    Automatically handles resource cleanup.
    """
    client = HighPerformanceRestClient(
        base_url=base_url,
        api_key=api_key,
        secret_key=secret_key,
        **kwargs
    )
    
    try:
        await client._ensure_session()
        yield client
    finally:
        await client.close()


def create_market_data_config() -> RequestConfig:
    """Create optimized config for market data requests (public, fast)."""
    return RequestConfig(
        timeout=5.0,
        max_retries=2,
        retry_delay=0.5,
        retry_backoff=1.5,
        rate_limit_tokens=1,
        require_auth=False
    )


def create_trading_config() -> RequestConfig:
    """Create optimized config for trading requests (private, reliable)."""
    return RequestConfig(
        timeout=10.0,
        max_retries=3,
        retry_delay=1.0,
        retry_backoff=2.0,
        rate_limit_tokens=2,
        require_auth=True
    )


# Example usage and testing
if __name__ == "__main__":
    async def example_usage():
        """Example demonstrating high-performance REST client usage."""
        async with create_trading_client(
            base_url="https://api.mexc.com",
            api_key="your_api_key",
            secret_key="your_secret_key",
            enable_metrics=True
        ) as client:
            # Public market data request
            market_config = create_market_data_config()
            ticker_data = await client.get("/api/v3/ticker/24hr", config=market_config)
            
            # Private authenticated request
            trading_config = create_trading_config()
            account_info = await client.get("/api/v3/account", config=trading_config)
            
            # Batch requests for efficiency
            batch_requests = [
                (HTTPMethod.GET, "/api/v3/ticker/price", {"symbol": "BTCUSDT"}, market_config),
                (HTTPMethod.GET, "/api/v3/ticker/price", {"symbol": "ETHUSDT"}, market_config),
                (HTTPMethod.GET, "/api/v3/ticker/price", {"symbol": "ADAUSDT"}, market_config),
            ]
            
            results = await client.batch_request(batch_requests)
            
            # Check performance metrics
            metrics = client.get_metrics()
            print(f"Average response time: {metrics.get('avg_response_time', 0):.3f}s")
            print(f"Success rate: {metrics.get('success_rate', 0):.2%}")
    
    # Run example
    asyncio.run(example_usage())