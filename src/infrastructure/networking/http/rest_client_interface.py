"""
New REST Base Implementation

Shared base class for all exchange REST implementations with direct implementation pattern.
Eliminates strategy dispatch overhead while providing common infrastructure.

Key Features:
- Direct method calls (no strategy pattern)
- Constructor injection for dependencies
- Shared session management and connection handling
- Abstract methods for exchange-specific logic
- HFT-optimized with sub-millisecond overhead targets
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import aiohttp
import msgspec

from infrastructure.networking.http.structs import HTTPMethod
from infrastructure.exceptions.exchange import ExchangeRestError, RateLimitErrorRest
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, get_logger
from infrastructure.decorators.retry import retry_decorator
from exchanges.interfaces.rest import BaseExchangeRateLimit
class BaseRestClientInterface(ABC):
    """
    Abstract base class for exchange REST implementations.
    
    Provides shared infrastructure while keeping exchange-specific logic abstract.
    Designed for HFT performance with minimal overhead.
    """
    
    def __init__(self, config: ExchangeConfig, rate_limiter: BaseExchangeRateLimit,
                 logger: Optional[HFTLoggerInterface] = None, is_private: bool = False):
        """
        Initialize base REST client with constructor injection.
        
        Args:
            config: Exchange configuration
            rate_limiter: Rate limiter instance (injected)
            logger: HFT logger instance (injected)
            is_private: Whether this client handles private/authenticated endpoints
        """
        self.config = config
        self.rate_limiter = rate_limiter
        self.logger = logger or get_logger(f'rest.client.{config.name.lower()}')
        self.is_private = is_private
        
        # Shared session management
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        
        # Performance tracking
        self._request_count = 0
        self._total_latency = 0.0
        
        # Auth credentials (only for private clients)
        self.api_key = config.credentials.api_key if is_private and config.credentials else None
        self.secret_key = config.credentials.secret_key if is_private and config.credentials else None
        
        self.logger.debug(f"{self.exchange_name} REST client initialized",
                         exchange=self.exchange_name.lower(),
                         api_type="private" if is_private else "public",
                         has_credentials=bool(self.api_key))
    
    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        pass
    
    def _get_timestamp_with_offset(self, offset_ms: int = 0, use_seconds: bool = False) -> str:
        """
        Generate timestamp with exchange-specific offset and format.
        
        Args:
            offset_ms: Millisecond offset to add to current time
            use_seconds: If True, return seconds; if False, return milliseconds
            
        Returns:
            Timestamp string in requested format
        """
        current_time = time.time()
        # Add offset to prevent timing issues
        adjusted_time = current_time + (offset_ms / 1000.0)
        
        if use_seconds:
            return str(int(adjusted_time))
        else:
            return str(int(adjusted_time * 1000))
    
    def _track_auth_performance(self, start_time: float, endpoint: str, method: HTTPMethod) -> float:
        """
        Track authentication performance metrics.
        
        Args:
            start_time: Performance counter value at auth start
            endpoint: API endpoint being authenticated
            method: HTTP method
            
        Returns:
            Authentication time in microseconds
        """
        auth_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        self.logger.debug(
            f"{self.exchange_name} authentication completed",
            endpoint=endpoint,
            auth_time_us=auth_time_us
        )
        
        # Metrics
        exchange_lower = self.exchange_name.lower().replace(" ", "_").replace(".", "")
        self.logger.metric(f"{exchange_lower}_auth_signatures_generated", 1,
                          tags={"endpoint": endpoint, "method": method.value})
        self.logger.metric(f"{exchange_lower}_auth_time_us", auth_time_us,
                          tags={"endpoint": endpoint})
        
        return auth_time_us
    
    @abstractmethod
    async def _authenticate(self, method: HTTPMethod, endpoint: str, 
                          params: Dict[str, Any], data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate authentication data for the request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            
        Returns:
            Dictionary with 'headers', 'params', and optionally 'data' keys
        """
        pass
    
    @abstractmethod
    def _handle_error(self, status: int, response_text: str) -> Exception:
        """
        Handle exchange-specific error responses.
        
        Args:
            status: HTTP status code
            response_text: Response body text
            
        Returns:
            Appropriate exception for the error
        """
        pass
    
    def _parse_response(self, response_text: str) -> Any:
        """
        Parse response text to JSON using msgspec for performance.
        
        Args:
            response_text: Raw response text
            
        Returns:
            Parsed JSON data
            
        Raises:
            ExchangeRestError: If response cannot be parsed
        """
        if not response_text:
            return None
            
        try:
            return msgspec.json.decode(response_text)
        except Exception as e:
            raise ExchangeRestError(400, f"Invalid JSON response: {response_text[:100]}...")
    
    async def _ensure_session(self):
        """Ensure aiohttp session is created with optimal configuration."""
        if self._session is None or self._session.closed:
            # Create optimized TCP connector
            self._connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=20,
                ttl_dns_cache=300,
                use_dns_cache=True,
                verify_ssl=True,
                keepalive_timeout=30,
                force_close=False,
            )
            
            # Create timeout configuration
            timeout = aiohttp.ClientTimeout(
                total=30,
                connect=10,
                sock_read=20,
                sock_connect=10,
            )
            
            # Prepare default headers
            default_headers = {
                'User-Agent': 'HFTArbitrageEngine/1.0',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            # Create session with optimized settings
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                json_serialize=lambda obj: msgspec.json.encode(obj).decode('utf-8'),
                headers=default_headers
            )
    
    @retry_decorator(
        max_attempts=3,
        backoff="exponential",
        base_delay=0.1,
        max_delay=2.0,
        exceptions=(aiohttp.ClientConnectionError, asyncio.TimeoutError)
    )
    async def _request(self, method: HTTPMethod, endpoint: str,
                      params: Optional[Dict[str, Any]] = None,
                      data: Optional[Dict[str, Any]] = None) -> Any:
        """
        Core request implementation with shared logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            
        Returns:
            Parsed response data
            
        Raises:
            ExchangeRestError: For API errors
            RateLimitErrorRest: For rate limit errors
        """
        # Rate limiting
        await self.rate_limiter.acquire_permit(endpoint)
        
        try:
            # Ensure session is ready
            await self._ensure_session()
            
            # Authentication (exchange-specific)
            auth_data = await self._authenticate(method, endpoint, params or {}, data)
            
            # Merge authentication data
            final_headers = auth_data.get('headers', {})
            final_params = auth_data.get('params') or params
            final_data = auth_data.get('data') or data
            send_as_text = auth_data.get('send_as_text', False)
            
            # Build URL
            url = f"{self.config.base_url}{endpoint}"
            
            # Execute request with proper data format
            if send_as_text and final_data:
                # Send pre-encoded JSON string as raw text data
                async with self._session.request(
                    method.value, url,
                    params=final_params,
                    data=final_data,  # Raw text data
                    headers=final_headers
                ) as response:
                    response_text = await response.text()
                    
                    # Handle errors
                    if response.status >= 400:
                        if response.status == 429:
                            raise RateLimitErrorRest(response.status, f"Rate limit exceeded: {response_text}")
                        else:
                            raise self._handle_error(response.status, response_text)
                    
                    # Parse and return response
                    return self._parse_response(response_text)
            else:
                # Send data as JSON object (aiohttp will encode)
                async with self._session.request(
                    method.value, url,
                    params=final_params,
                    json=final_data,  # JSON object
                    headers=final_headers
                ) as response:
                    response_text = await response.text()
                    
                    # Handle errors
                    if response.status >= 400:
                        if response.status == 429:
                            raise RateLimitErrorRest(response.status, f"Rate limit exceeded: {response_text}")
                        else:
                            raise self._handle_error(response.status, response_text)
                    
                    # Parse and return response
                    return self._parse_response(response_text)
                
        finally:
            self.rate_limiter.release_permit(endpoint)
    
    async def request(self, method: HTTPMethod, endpoint: str,
                     params: Optional[Dict[str, Any]] = None,
                     data: Optional[Dict[str, Any]] = None) -> Any:
        """
        Public request method with performance tracking.
        
        Args:
            method: HTTP method
            endpoint: API endpoint  
            params: Query parameters
            data: Request body data
            
        Returns:
            Parsed response data
        """
        start_time = time.perf_counter()
        
        try:
            result = await self._request(method, endpoint, params, data)
            
            # Performance tracking
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._request_count += 1
            self._total_latency += duration_ms
            
            # Metrics
            self.logger.metric(f"{self.exchange_name.lower()}_request_duration_ms", duration_ms,
                             tags={"endpoint": endpoint, "method": method.value, "status": "success"})
            
            # HFT compliance check
            if duration_ms > 50.0:
                self.logger.warning(f"HFT latency violation: {duration_ms:.2f}ms > 50ms for {method.value} {endpoint}")
            
            return result
            
        except Exception as e:
            # Error tracking
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            self.logger.metric(f"{self.exchange_name.lower()}_request_errors", 1,
                             tags={"endpoint": endpoint, "method": method.value, 
                                  "error": type(e).__name__})
            
            self.logger.error(f"{self.exchange_name} request failed",
                            exchange=self.exchange_name.lower(),
                            method=method.value,
                            endpoint=endpoint,
                            error_type=type(e).__name__,
                            error_message=str(e),
                            duration_ms=duration_ms)
            
            raise
    
    async def close(self):
        """Clean up resources and close connections."""
        if self._session and not self._session.closed:
            await self._session.close()
            
        if self._connector:
            await self._connector.close()
            
        # Log performance summary
        if self._request_count > 0:
            avg_latency = self._total_latency / self._request_count
            self.logger.info(f"{self.exchange_name} REST client closed",
                           exchange=self.exchange_name.lower(),
                           total_requests=self._request_count,
                           avg_latency_ms=avg_latency)
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring."""
        if self._request_count == 0:
            return {"requests": 0, "avg_latency_ms": 0.0}
            
        return {
            "requests": self._request_count,
            "avg_latency_ms": self._total_latency / self._request_count,
            "total_latency_ms": self._total_latency
        }