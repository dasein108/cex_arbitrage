"""
REST Transport Manager

High-performance REST transport manager with strategy composition for HFT systems.
Coordinates all REST strategies while maintaining sub-50ms latency targets.

HFT COMPLIANCE: <1ms coordination overhead, <50ms end-to-end latency.
"""

import asyncio
import time
import logging
from typing import Any, Dict, Optional
from collections import deque

import aiohttp
import msgspec

from ...exceptions.exchange import ExchangeRestError, RateLimitErrorRest, ExchangeConnectionRestError, RecvWindowError
from .strategies import RestStrategySet, RequestMetrics, PerformanceTargets, AuthenticationData
from .structs import HTTPMethod


class RestManager:
    """
    High-performance REST transport manager with strategy composition.
    
    Coordinates all REST strategies while maintaining HFT performance characteristics.
    Provides unified interface for making authenticated and unauthenticated requests.
    """
    
    def __init__(
        self,
        strategy_set: RestStrategySet):
        self.strategy_set = strategy_set

        # Session management
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        
        # Performance monitoring
        self._metrics = RequestMetrics()
        self._performance_targets = strategy_set.get_performance_targets()
        self._latency_samples = deque(maxlen=1000)  # Rolling window for percentiles
        
        # Request context cache
        self._request_context: Optional[Any] = None
        
        self.logger = logging.getLogger(__name__)
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with proper cleanup."""
        await self.close()
    
    async def _ensure_session(self):
        """Ensure aiohttp session is created with optimal configuration."""
        if self._session is None or self._session.closed:
            # Get request context from strategy
            if self._request_context is None:
                self._request_context = await self.strategy_set.request_strategy.create_request_context()
            
            context = self._request_context
            
            # Create optimized TCP connector
            self._connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=context.max_concurrent,
                ttl_dns_cache=300,
                use_dns_cache=True,
                verify_ssl=True,
                keepalive_timeout=context.keepalive_timeout,
                force_close=False,
            )
            
            # Create timeout configuration
            timeout = aiohttp.ClientTimeout(
                total=context.timeout,
                connect=context.connection_timeout,
                sock_read=context.read_timeout,
                sock_connect=context.connection_timeout,
            )
            
            # Prepare default headers
            default_headers = {
                'User-Agent': 'HFTArbitrageEngine/1.0',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            if context.default_headers:
                default_headers.update(context.default_headers)
            
            # Create session with optimized settings
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                json_serialize=lambda obj: msgspec.json.encode(obj).decode('utf-8'),
                headers=default_headers
            )
            
            # Create semaphore for concurrency control
            self._semaphore = asyncio.Semaphore(context.max_concurrent)
    
    def _parse_response(self, response_text: str) -> Any:
        """Ultra-high-performance JSON parsing using msgspec."""
        if not response_text:
            return None
        
        try:
            return msgspec.json.decode(response_text)
        except Exception:
            raise ExchangeRestError(400, f"Invalid JSON response: {response_text[:100]}...")
    
    def _update_metrics(self, latency_ms: float, success: bool, rate_limited: bool = False):
        """Update performance metrics with HFT compliance tracking."""
        self._metrics.total_requests += 1
        
        if success:
            self._metrics.successful_requests += 1
        else:
            self._metrics.failed_requests += 1
        
        if rate_limited:
            self._metrics.rate_limit_hits += 1
        
        # Track HFT compliance
        if latency_ms <= 50.0:
            self._metrics.sub_50ms_requests += 1
        else:
            self._metrics.latency_violations += 1
        
        # Update latency tracking
        self._latency_samples.append(latency_ms)
        
        # Calculate rolling averages
        if self._latency_samples:
            sorted_samples = sorted(self._latency_samples)
            n = len(sorted_samples)
            
            self._metrics.avg_latency_ms = sum(sorted_samples) / n
            self._metrics.p95_latency_ms = sorted_samples[int(0.95 * n)] if n > 0 else 0.0
            self._metrics.p99_latency_ms = sorted_samples[int(0.99 * n)] if n > 0 else 0.0
    
    async def request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Any:
        """
        Execute request with full strategy coordination.
        
        HFT COMPLIANT: <50ms execution target with sub-1ms overhead.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Request parameters
            json_data: JSON data for POST/PUT requests
            headers: Additional headers

        Returns:
            Parsed response data
        """
        # Performance tracking start
        start_time = time.perf_counter()
        success = False
        rate_limited = False
        
        # Ensure session is ready
        await self._ensure_session()
        
        # Get request context
        if self._request_context is None:
            self._request_context = await self.strategy_set.request_strategy.create_request_context()
        
        context = self._request_context
        url = f"{context.base_url}{endpoint}"
        
        async with self._semaphore:  # Limit concurrent requests
            # Step 1: Rate limiting (via RateLimitStrategy)
            await self.strategy_set.rate_limit_strategy.acquire_permit(endpoint)
            
            try:
                # Step 2: Request preparation (via RequestStrategy)
                request_params = await self.strategy_set.request_strategy.prepare_request(
                    method, endpoint, params or {}, headers or {}
                )
                
                # Step 3: Authentication if required (via AuthStrategy)
                if self.strategy_set.auth_strategy:
                    if not self.strategy_set.auth_strategy.requires_auth(endpoint):
                        # Skip auth if strategy says it's not needed
                        pass
                    else:
                        auth_data = await self.strategy_set.auth_strategy.sign_request(
                            method, endpoint, params or {}, json_data, int(time.time() * 1000)
                        )
                        # Apply authentication headers
                        request_params.setdefault('headers', {}).update(auth_data.headers)
                        # Apply authentication parameters
                        request_params.setdefault('params', {}).update(auth_data.params)
                        # Apply authentication data if provided (Gate.io needs this for POST/PUT)
                        if auth_data.data is not None:
                            request_params['data'] = auth_data.data
                
                # Step 4: Execute with retry logic (via RetryStrategy)
                response = await self._execute_with_retry(method, url, request_params)
                success = True
                return response
                
            except RateLimitErrorRest:
                rate_limited = True
                raise
            finally:
                # Step 5: Release rate limit permit
                self.strategy_set.rate_limit_strategy.release_permit(endpoint)
                
                # Step 6: Performance tracking
                execution_time_ms = (time.perf_counter() - start_time) * 1000
                self._update_metrics(execution_time_ms, success, rate_limited)
                
                # Log performance violations in debug mode
                if execution_time_ms > self._performance_targets.max_latency_ms:
                    self.logger.warning(
                        f"Latency violation: {execution_time_ms:.2f}ms > {self._performance_targets.max_latency_ms}ms "
                        f"for {method.value} {endpoint}"
                    )
    
    async def _execute_with_retry(
        self,
        method: HTTPMethod,
        url: str,
        request_params: Dict[str, Any]
    ) -> Any:
        """Execute request with retry logic coordination."""
        retry_strategy = self.strategy_set.retry_strategy
        max_attempts = self._performance_targets.max_retry_attempts
        
        for attempt in range(1, max_attempts + 1):
            try:
                # Execute the actual HTTP request
                async with self._session.request(method.value, url, **request_params) as response:
                    response_text = await response.text()
                    
                    # Handle HTTP errors
                    if response.status >= 400:
                        if response.status == 429:  # Rate limited
                            # Get rate limit delay from strategy
                            delay = retry_strategy.handle_rate_limit(dict(response.headers))
                            if delay > 0:
                                await asyncio.sleep(delay)
                            raise RateLimitErrorRest(response.status, f"Rate limit exceeded: {response_text}")
                        
                        # Use exception handler strategy if available, fallback to legacy handler
                        if self.strategy_set.exception_handler_strategy:
                            raise self.strategy_set.exception_handler_strategy.handle_error(response.status, response_text)
                        else:
                            raise ExchangeRestError(response.status, f"HTTP {response.status}: {response_text}"
                                                                     f"\nparams:{request_params.get('params', {})},"
                                                                     f"data: {request_params.get('data', {})}")
                    
                    # Parse and return successful response
                    return self._parse_response(response_text)
            
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                if not retry_strategy.should_retry(attempt, e) or attempt == max_attempts:
                    raise ExchangeConnectionRestError(
                        500, f"Connection failed after {attempt} attempts: {str(e)}"
                    )
                
                # Calculate retry delay
                delay = await retry_strategy.calculate_delay(attempt, e)
                await asyncio.sleep(delay)
            
            except RateLimitErrorRest as e:
                if not retry_strategy.should_retry(attempt, e) or attempt == max_attempts:
                    raise
                
                # Calculate retry delay for rate limits
                delay = await retry_strategy.calculate_delay(attempt, e)
                await asyncio.sleep(delay)
            
            except RecvWindowError as e:
                if not retry_strategy.should_retry(attempt, e) or attempt == max_attempts:
                    raise
                
                # Handle timestamp synchronization for recvWindow errors
                self.logger.warning(f"RecvWindow error on attempt {attempt}, synchronizing timestamp")
                
                # Force timestamp refresh for next auth attempt
                if self.strategy_set.auth_strategy:
                    await self.strategy_set.auth_strategy.refresh_timestamp()
                
                # Short delay before retry (timestamp sync errors should retry quickly)
                await asyncio.sleep(0.1)  # 100ms delay for timestamp sync
            
            except ExchangeRestError:
                # Don't retry on other application-level errors
                raise
            
            except Exception as e:
                if not retry_strategy.should_retry(attempt, e) or attempt == max_attempts:
                    raise ExchangeConnectionRestError(
                        500, f"Request failed after {attempt} attempts: {str(e)}"
                    )
                
                delay = await retry_strategy.calculate_delay(attempt, e)
                await asyncio.sleep(delay)
        
        # Should never reach here
        raise ExchangeConnectionRestError(500, "Maximum retry attempts exceeded")
    
    # Convenience HTTP method wrappers
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Execute GET request."""
        return await self.request(
            HTTPMethod.GET, endpoint, params=params, headers=headers
        )
    
    async def post(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Execute POST request."""
        return await self.request(
            HTTPMethod.POST, endpoint, params=params, json_data=json_data, 
            headers=headers
        )
    
    async def put(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Execute PUT request."""
        return await self.request(
            HTTPMethod.PUT, endpoint, params=params, json_data=json_data,
            headers=headers
        )
    
    async def delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Any:
        """Execute DELETE request."""
        return await self.request(
            HTTPMethod.DELETE, endpoint, params=params, headers=headers
        )
    
    def get_metrics(self) -> RequestMetrics:
        """Get current performance metrics."""
        return self._metrics
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get HFT compliance summary."""
        total = self._metrics.total_requests
        if total == 0:
            return {"status": "no_requests", "hft_compliance": "unknown"}
        
        hft_compliance_rate = (self._metrics.sub_50ms_requests / total) * 100
        
        return {
            "total_requests": total,
            "success_rate": (self._metrics.successful_requests / total) * 100,
            "hft_compliance_rate": hft_compliance_rate,
            "avg_latency_ms": self._metrics.avg_latency_ms,
            "p95_latency_ms": self._metrics.p95_latency_ms,
            "p99_latency_ms": self._metrics.p99_latency_ms,
            "rate_limit_hits": self._metrics.rate_limit_hits,
            "latency_violations": self._metrics.latency_violations,
            "hft_compliant": hft_compliance_rate >= 95.0,  # 95% of requests under 50ms
            "targets": {
                "max_latency_ms": self._performance_targets.max_latency_ms,
                "target_throughput_rps": self._performance_targets.target_throughput_rps
            }
        }
    
    def reset_metrics(self):
        """Reset performance metrics."""
        self._metrics = RequestMetrics()
        self._latency_samples.clear()
    
    async def close(self):
        """Clean up resources with proper connection closure."""
        if self._session and not self._session.closed:
            await self._session.close()
        
        if self._connector:
            await self._connector.close()
        
        self.logger.debug("RestTransportManager closed successfully")

