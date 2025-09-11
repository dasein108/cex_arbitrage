"""
Ultra-Simple High-Performance REST API Client for Cryptocurrency Trading

Streamlined async REST client optimized for ultra-low latency trading with minimal complexity.
Focuses on essential functionality while maintaining maximum performance characteristics.

Key Features:
- Connection pooling and session reuse with aiohttp
- Ultra-fast JSON parsing with msgspec
- Just-in-time auth signature generation
- Simple exponential backoff retry logic
- Aggressive timeout configurations for trading
- Memory-efficient request/response handling
- Generic authentication suitable for most exchanges

Performance Targets:
- Time Complexity: O(1) for all core operations
- Space Complexity: O(1) per request, O(n) for connection pool
- <50ms HTTP request latency, <1ms JSON parsing

Note: Rate limiting removed for simplicity - add externally via decorators/middleware.
"""

import asyncio
import hashlib
import hmac
import time
import urllib.parse
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Dict, Optional, Callable
import logging

import aiohttp
import msgspec
from common.exceptions import ExchangeAPIError, RateLimitError

# Use msgspec for maximum JSON performance
MSGSPEC_ENCODER = msgspec.json.encode


class HTTPMethod(Enum):
    """HTTP methods with performance-optimized string values."""
    GET = "GET"
    POST = "POST" 
    PUT = "PUT"
    DELETE = "DELETE"


class RestConfig(msgspec.Struct):
    """Ultra-simple configuration for REST client."""
    timeout: float = 10.0
    max_retries: int = 3
    retry_delay: float = 1.0
    require_auth: bool = False
    max_concurrent: int = 50


class RestClient:
    """
    Ultra-simple high-performance REST API client for cryptocurrency trading.
    
    Features:
    - Single execution path with unified request handling
    - Generic authentication (HMAC-SHA256)
    - Connection pooling with persistent sessions
    - Ultra-fast JSON parsing with msgspec
    - Simple exponential backoff retry logic
    - Customizable signature generation
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        signature_generator: Optional[Callable] = None,
        config: Optional[RestConfig] = None,
        exception_handler: Optional[Callable] = None
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.secret_key = secret_key
        self.signature_generator = signature_generator
        self.config = config or RestConfig()
        self.exception_handler = exception_handler
        
        # Connection management
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
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
            # Create optimized TCP connector
            self._connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                use_dns_cache=True,
                verify_ssl=True,
                keepalive_timeout=60,
                force_close=False,
            )
            
            # Create timeout configuration
            timeout = aiohttp.ClientTimeout(
                total=self.config.timeout,
                connect=2.0,
                sock_read=5.0,
                sock_connect=2.0,
            )
            
            # Create session with optimized settings
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                json_serialize=MSGSPEC_ENCODER,
                headers={
                    'User-Agent': 'UltraSimpleTrader/1.0',
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }
            )
    

    def _parse_response(self, response_text: str) -> Any:
        """Ultra-high-performance JSON parsing using msgspec directly on strings."""
        if not response_text:
            return None
            
        try:
            return msgspec.json.decode(response_text)
        except Exception:
            raise ExchangeAPIError(400, f"Invalid JSON response: {response_text[:100]}...")
    
    async def request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        config: Optional[RestConfig] = None
    ) -> Any:
        """
        Execute HTTP request with unified handling.
        Single execution path with simple error handling and retries.
        """
        config = config or self.config
        params = params or {}
        
        # Ensure session is ready
        await self._ensure_session()
        
        url = f"{self.base_url}{endpoint}"
        
        async with self._semaphore:  # Limit concurrent requests
            for attempt in range(config.max_retries + 1):
                try:
                    # Prepare headers
                    headers = {}
                    
                    # For authenticated requests, add signature to params (not headers for MEXC)
                    request_params = params.copy()
                    if config.require_auth:
                        # MEXC requires API key in headers but signature in query params
                        if self.api_key:
                            headers['X-MEXC-APIKEY'] = self.api_key
                        
                        # CRITICAL FOR MEXC: Preserve parameter insertion order for signature generation
                        # Add timestamp and recvWindow to params first
                        request_params['timestamp'] = round(time.time() * 1000) # Ensure int type
                        request_params['recvWindow'] = 15000
                        
                        # Generate signature
                        request_params['signature'] = self.signature_generator(request_params)
                    
                    # Prepare request parameters
                    request_kwargs = {
                        'timeout': aiohttp.ClientTimeout(total=config.timeout),
                        'headers': headers,
                    }
                    
                    # Add data based on method
                    if method == HTTPMethod.GET:
                        if request_params:
                            request_kwargs['params'] = request_params
                    elif json_data:
                        # For explicit JSON data, set appropriate content type
                        headers['Content-Type'] = 'application/json'
                        request_kwargs['json'] = json_data
                    elif request_params and method != HTTPMethod.GET:
                        # CRITICAL FIX: MEXC requires specific Content-Type header AND query parameters
                        if config.require_auth:
                            # MEXC authenticated POST requests require:
                            # 1. Content-Type: application/json header
                            # 2. Parameters in query string (NOT body)
                            headers['Content-Type'] = 'application/json'
                            request_kwargs['params'] = request_params
                        else:
                            # For non-authenticated requests, use standard JSON
                            headers['Content-Type'] = 'application/json'
                            request_kwargs['json'] = request_params
                    
                    # Execute request
                    async with self._session.request(method.value, url, **request_kwargs) as response:
                        response_text = await response.text()
                        
                        # Handle HTTP errors
                        if response.status >= 400:
                            if response.status == 429:  # Rate limited
                                raise RateLimitError(response.status, f"Rate limit exceeded: {response_text}")
                            
                            # Use custom exception handler if provided
                            if self.exception_handler:
                                # Create a mock exception with HTTP info for custom handler
                                class HTTPError(Exception):
                                    def __init__(self, status, response_text):
                                        self.status = status
                                        self.response_text = response_text
                                        super().__init__(f"HTTP {status}: {response_text}")
                                
                                http_error = HTTPError(response.status, response_text)
                                raise self.exception_handler(http_error)
                            else:
                                raise ExchangeAPIError(
                                    response.status,
                                    f"HTTP {response.status}: {response_text}"
                                )
                        
                        # Parse and return successful response
                        return self._parse_response(response_text)
                
                except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                    if attempt == config.max_retries:
                        raise ExchangeAPIError(500, f"Connection failed after {config.max_retries} retries: {str(e)}")
                    
                    # Simple exponential backoff
                    delay = config.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                
                except RateLimitError:
                    if attempt == config.max_retries:
                        raise
                    
                    # Longer delay for rate limits
                    delay = config.retry_delay * (2 ** (attempt + 1))
                    await asyncio.sleep(delay)
                
                except ExchangeAPIError:
                    raise
                
                except Exception as e:
                    if attempt == config.max_retries:
                        # Use custom exception handler if provided
                        if self.exception_handler:
                            raise self.exception_handler(e)
                        else:
                            raise ExchangeAPIError(500, f"Unexpected error: {str(e)}")
                    
                    await asyncio.sleep(config.retry_delay)
    
    # Convenience HTTP method wrappers
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[RestConfig] = None
    ) -> Any:
        """Execute GET request."""
        return await self.request(HTTPMethod.GET, endpoint, params=params, config=config)
    
    async def post(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[RestConfig] = None
    ) -> Any:
        """Execute POST request."""
        return await self.request(
            HTTPMethod.POST, endpoint, params=params, json_data=json_data, config=config
        )
    
    async def put(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[RestConfig] = None
    ) -> Any:
        """Execute PUT request."""
        return await self.request(
            HTTPMethod.PUT, endpoint, params=params, json_data=json_data, config=config
        )
    
    async def delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[RestConfig] = None
    ) -> Any:
        """Execute DELETE request."""
        return await self.request(HTTPMethod.DELETE, endpoint, params=params, config=config)
    
    async def close(self):
        """Clean up resources with proper connection closure."""
        if self._session and not self._session.closed:
            await self._session.close()
        
        if self._connector:
            await self._connector.close()
        
        self.logger.info("RestClient closed successfully")