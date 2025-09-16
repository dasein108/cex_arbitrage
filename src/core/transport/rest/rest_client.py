"""
High-Performance REST API Client with Strategy-Based Transport

DEPRECATED: Legacy RestClient - Use RestTransportManager with strategies for new code.

Maintained for backward compatibility with existing exchange implementations.
New implementations should use the strategy-based transport system for flexible
rate limiting, authentication, and retry policies.

Migration Path:
- RestClient (legacy) → RestTransportManager + RestStrategySet
- Fixed RestConfig → Flexible strategy composition
- No rate limiting → Integrated RateLimitStrategy
- No auth support → AuthStrategy for private endpoints

Performance Targets:
- Time Complexity: O(1) for all core operations
- Space Complexity: O(1) per request, O(n) for connection pool
- <50ms HTTP request latency, <1ms JSON parsing
"""

import asyncio
from enum import Enum
from typing import Any, Dict, Optional, Callable
import logging

import aiohttp

import msgspec
from core.exceptions.exchange import BaseExchangeError, RateLimitErrorBase, ExchangeConnectionError
from core.transport.rest.structs import HTTPMethod
from core.config.structs import ExchangeConfig, ExchangeCredentials, NetworkConfig
from .transport_manager import RestTransportManager
from .strategies import RestStrategyFactory

# Use msgspec for maximum JSON performance
# Note: msgspec.json.encode returns bytes, but aiohttp expects string serializer
MSGSPEC_ENCODER = lambda obj: msgspec.json.encode(obj).decode('utf-8')


class RestConfig(msgspec.Struct):
    """Ultra-simple configuration for REST client."""
    timeout: float = 10.0
    max_retries: int = 3
    retry_delay: float = 1.0
    max_concurrent: int = 50
    headers: Optional[Dict[str, str]] = None  # Custom headers to add/override


class RestClient:
    """
    Ultra-simple high-performance REST API client for cryptocurrency trading.
    
    Features:
    - Single execution path with unified request handling
    - Connection pooling with persistent sessions
    - Ultra-fast JSON parsing with msgspec
    - Simple exponential backoff retry logic
    - Exchange-agnostic HTTP operations with custom headers support
    """

    def __init__(
            self,
            base_url: str,
            config: Optional[RestConfig] = None,
            custom_exception_handler: Optional[Callable[[int, str], BaseExchangeError]] = None
    ):
        self.base_url = base_url.rstrip('/')
        self.config = config or RestConfig()
        self.custom_exception_handler = custom_exception_handler

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
            raise BaseExchangeError(400, f"Invalid JSON response: {response_text[:100]}...")

    async def request(
            self,
            method: HTTPMethod,
            endpoint: str,
            params: Optional[Dict[str, Any]] = None,
            json_data: Optional[Dict[str, Any]] = None,
            config: Optional[RestConfig] = None,
            headers: Optional[Dict[str, str]] = None  # Additional headers for this request
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
                    # Prepare headers - start with cex headers
                    request_headers = {}

                    # Add config headers if provided
                    if config and config.headers:
                        request_headers.update(config.headers)

                    # Add request-specific headers if provided (these override config headers)
                    if headers:
                        request_headers.update(headers)

                    # Use provided parameters as-is (authentication handled by exchange implementations)
                    request_params = params.copy() if params else {}

                    # Prepare request parameters
                    request_kwargs = {
                        'timeout': aiohttp.ClientTimeout(total=config.timeout),
                        'headers': request_headers,  # Use the merged headers
                    }

                    # Add data based on method
                    if method == HTTPMethod.GET:
                        if request_params:
                            request_kwargs['params'] = request_params
                    elif json_data:
                        # For explicit JSON data, set appropriate content type
                        request_headers['Content-Type'] = 'application/json'
                        request_kwargs['json'] = json_data
                    elif request_params and method != HTTPMethod.GET:
                        # For POST/PUT/DELETE with parameters, use query parameters by default
                        # Individual cex can override this behavior via headers/json_data
                        request_kwargs['params'] = request_params

                    # Execute request
                    async with self._session.request(method.value, url, **request_kwargs) as response:
                        response_text = await response.text()
                        # Handle HTTP errors
                        if response.status >= 400:
                            if response.status == 429:  # Rate limited
                                raise RateLimitErrorBase(response.status, f"Rate limit exceeded: {response_text}")

                            # Use custom exception handler if provided
                            if self.custom_exception_handler:
                                # Create a mock exception with HTTP info for custom handler
                                raise self.custom_exception_handler(response.status, response_text)
                            else:
                                raise BaseExchangeError(
                                    response.status,
                                    f"HTTP {response.status}: {response_text}"
                                )

                        # Parse and return successful response
                        return self._parse_response(response_text)

                except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                    if attempt == config.max_retries:
                        raise ExchangeConnectionError(500,
                                                      f"Connection failed after {config.max_retries} retries: {str(e)}")

                    # Simple exponential backoff
                    delay = config.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

                except RateLimitErrorBase:
                    if attempt == config.max_retries:
                        raise

                    # Longer delay for rate limits
                    delay = config.retry_delay * (2 ** (attempt + 1))
                    await asyncio.sleep(delay)

                except BaseExchangeError:
                    raise

                except Exception as e:
                    if attempt == config.max_retries:
                        raise ExchangeConnectionError(500,
                                                      f"Connection failed after {config.max_retries} retries: {str(e)}")

                    await asyncio.sleep(config.retry_delay)

    # Convenience HTTP method wrappers

    async def get(
            self,
            endpoint: str,
            params: Optional[Dict[str, Any]] = None,
            config: Optional[RestConfig] = None,
            headers: Optional[Dict[str, str]] = None
    ) -> Any:
        """Execute GET request with optional custom headers."""
        return await self.request(HTTPMethod.GET, endpoint, params=params, config=config, headers=headers)

    async def post(
            self,
            endpoint: str,
            json_data: Optional[Dict[str, Any]] = None,
            params: Optional[Dict[str, Any]] = None,
            config: Optional[RestConfig] = None,
            headers: Optional[Dict[str, str]] = None
    ) -> Any:
        """Execute POST request with optional custom headers."""
        return await self.request(
            HTTPMethod.POST, endpoint, params=params, json_data=json_data, config=config, headers=headers
        )

    async def put(
            self,
            endpoint: str,
            json_data: Optional[Dict[str, Any]] = None,
            params: Optional[Dict[str, Any]] = None,
            config: Optional[RestConfig] = None,
            headers: Optional[Dict[str, str]] = None
    ) -> Any:
        """Execute PUT request with optional custom headers."""
        return await self.request(
            HTTPMethod.PUT, endpoint, params=params, json_data=json_data, config=config, headers=headers
        )

    async def delete(
            self,
            endpoint: str,
            params: Optional[Dict[str, Any]] = None,
            config: Optional[RestConfig] = None,
            headers: Optional[Dict[str, str]] = None
    ) -> Any:
        """Execute DELETE request with optional custom headers."""
        return await self.request(HTTPMethod.DELETE, endpoint, params=params, config=config, headers=headers)

    async def close(self):
        """Clean up resources with proper connection closure."""
        if self._session and not self._session.closed:
            await self._session.close()

        if self._connector:
            await self._connector.close()

        self.logger.info("RestClient closed successfully")


def create_transport_manager(
    exchange: str,
    is_private: bool = False,
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    **kwargs
) -> RestTransportManager:
    """
    Factory function to create RestTransportManager with exchange strategies.
    
    Preferred method for creating REST transport with integrated rate limiting,
    authentication, and retry policies.
    
    Args:
        exchange: Exchange name ('mexc', 'gateio')
        is_private: Whether to use private API (requires credentials)
        api_key: API key for private endpoints
        secret_key: Secret key for private endpoints
        **kwargs: Additional strategy configuration
        
    Returns:
        RestTransportManager with configured strategies
        
    Example:
        # Public API
        transport = create_transport_manager("mexc", is_private=False)
        
        # Private API
        transport = create_transport_manager(
            "mexc", is_private=True, 
            api_key="your_key", secret_key="your_secret"
        )
        
        # Use with context manager
        async with transport:
            response = await transport.get("/api/v3/ticker/24hr", 
                                         params={"symbol": "BTCUSDT"})
    """
    if is_private and (not api_key or not secret_key):
        raise ValueError("API key and secret key required for private API access")
    
    # Add credentials to kwargs for strategy creation
    strategy_kwargs = kwargs.copy()
    if api_key:
        strategy_kwargs['api_key'] = api_key
    if secret_key:
        strategy_kwargs['secret_key'] = secret_key
    
    # Create strategy set
    strategy_set = RestStrategyFactory.create_strategies(
        exchange=exchange,
        is_private=is_private,
        **strategy_kwargs
    )
    
    # Create and return transport manager
    return RestTransportManager(strategy_set)


def create_transport_from_config(
    exchange_config: ExchangeConfig,
    is_private: bool = False,
    **kwargs
) -> RestTransportManager:
    """
    Factory function to create RestTransportManager from ExchangeConfig.
    
    Integrates with the centralized configuration system for consistent
    exchange setup across the application.
    
    Args:
        exchange_config: Complete exchange configuration
        is_private: Whether to use private API
        **kwargs: Additional strategy configuration (overrides config values)
        
    Returns:
        RestTransportManager with configured strategies
        
    Example:
        # Using ExchangeConfig
        config = ExchangeConfig(
            name="mexc",
            credentials=ExchangeCredentials(api_key="...", secret_key="..."),
            base_url="https://api.mexc.com",
            websocket_url="wss://wbs.mexc.com/ws",
            network=NetworkConfig(
                request_timeout=8.0,
                connect_timeout=2.0,
                max_retries=3,
                retry_delay=0.5
            )
        )
        
        transport = create_transport_from_config(config, is_private=True)
    """
    if is_private and not exchange_config.has_credentials():
        raise ValueError(f"Exchange {exchange_config.name} requires credentials for private API access")
    
    # Extract strategy configuration from ExchangeConfig
    strategy_kwargs = kwargs.copy()
    
    # Add credentials if available and needed
    if is_private and exchange_config.has_credentials():
        strategy_kwargs['api_key'] = exchange_config.credentials.api_key
        strategy_kwargs['secret_key'] = exchange_config.credentials.secret_key
    
    # Override with network configuration if provided
    if exchange_config.network:
        # Map NetworkConfig to strategy parameters
        strategy_kwargs.setdefault('request_timeout', exchange_config.network.request_timeout)
        strategy_kwargs.setdefault('connect_timeout', exchange_config.network.connect_timeout)
        strategy_kwargs.setdefault('max_retries', exchange_config.network.max_retries)
        strategy_kwargs.setdefault('retry_delay', exchange_config.network.retry_delay)
    
    # Override with rate limit configuration if provided
    if exchange_config.rate_limit:
        strategy_kwargs.setdefault('requests_per_second', float(exchange_config.rate_limit.requests_per_second))
    
    # Override base URL if needed
    strategy_kwargs.setdefault('base_url', exchange_config.base_url)
    
    # Create strategy set
    strategy_set = RestStrategyFactory.create_strategies(
        exchange=exchange_config.name,
        is_private=is_private,
        **strategy_kwargs
    )
    
    # Create and return transport manager
    return RestTransportManager(strategy_set)
