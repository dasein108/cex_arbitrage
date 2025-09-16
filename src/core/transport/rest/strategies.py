"""
REST Transport Strategy Interfaces

HFT-compliant strategy interfaces for REST request management, rate limiting,
retry logic, and authentication using composition pattern.

HFT COMPLIANCE: Sub-millisecond strategy execution, zero-copy patterns.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from typing import List, Dict, Optional, Any, Callable, Union
import asyncio
import logging

import msgspec

from .structs import HTTPMethod
from core.exceptions.exchange import BaseExchangeError


@dataclass(frozen=True)
class RequestContext:
    """Request configuration context."""
    base_url: str
    timeout: float
    max_concurrent: int
    connection_timeout: float = 2.0
    read_timeout: float = 5.0
    keepalive_timeout: float = 60.0
    default_headers: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class RateLimitContext:
    """Rate limiting configuration for endpoints."""
    requests_per_second: float
    burst_capacity: int
    endpoint_weight: int = 1
    global_weight: int = 1
    cooldown_period: float = 0.1


@dataclass(frozen=True)
class AuthenticationData:
    """Authentication data containing headers and parameters."""
    headers: Dict[str, str]
    params: Dict[str, Any]


@dataclass(frozen=True)
class PerformanceTargets:
    """HFT performance targets for exchange."""
    max_latency_ms: float = 50.0
    max_retry_attempts: int = 3
    connection_timeout_ms: float = 2000.0
    read_timeout_ms: float = 5000.0
    target_throughput_rps: float = 100.0


@dataclass
class RequestMetrics:
    """HFT-compliant request performance metrics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    rate_limit_hits: int = 0
    sub_50ms_requests: int = 0
    latency_violations: int = 0


class RequestStrategy(ABC):
    """
    Strategy for HTTP request configuration and execution.
    
    Handles connection setup, request formatting, and performance targets.
    HFT COMPLIANT: <100μs configuration overhead.
    """
    
    @abstractmethod
    async def create_request_context(self) -> RequestContext:
        """
        Create request configuration.
        
        Returns:
            RequestContext with URL, timeouts, connection limits
        """
        pass
    
    @abstractmethod
    async def prepare_request(
        self, 
        method: HTTPMethod, 
        endpoint: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Prepare request parameters with exchange-specific formatting.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Request parameters
            headers: Request headers
            
        Returns:
            Prepared request parameters for aiohttp
        """
        pass
    
    @abstractmethod
    def get_performance_targets(self) -> PerformanceTargets:
        """
        Get HFT performance targets for this exchange.
        
        Returns:
            PerformanceTargets with latency and throughput requirements
        """
        pass

    def __init__(self, base_url: str, **kwargs):
        self.base_url = base_url


class RateLimitStrategy(ABC):
    """
    Strategy for request rate limiting and traffic coordination.
    
    Manages request permits and endpoint-specific rate limits.
    HFT COMPLIANT: <50μs permit acquisition.
    """
    
    @abstractmethod
    async def acquire_permit(self, endpoint: str, request_weight: int = 1) -> bool:
        """
        Acquire permission to make request with endpoint-specific limits.
        
        Args:
            endpoint: API endpoint
            request_weight: Request weight/cost
            
        Returns:
            True if permit acquired successfully
        """
        pass
    
    @abstractmethod
    def release_permit(self, endpoint: str, request_weight: int = 1) -> None:
        """
        Release request permit.
        
        Args:
            endpoint: API endpoint
            request_weight: Request weight/cost
        """
        pass
    
    @abstractmethod
    def get_rate_limit_context(self, endpoint: str) -> RateLimitContext:
        """
        Get rate limiting configuration for endpoint.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            RateLimitContext with rate limiting parameters
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Get rate limiting statistics for monitoring.
        
        Returns:
            Dictionary with rate limiting metrics
        """
        pass


class RetryStrategy(ABC):
    """
    Strategy for request retry logic and error handling.
    
    Determines retry behavior and backoff calculations.
    HFT COMPLIANT: <10μs retry decision.
    """
    
    @abstractmethod
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """
        Determine if request should be retried.
        
        Args:
            attempt: Current attempt number (1-based)
            error: Exception that caused failure
            
        Returns:
            True if retry should be attempted
        """
        pass
    
    @abstractmethod
    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        """
        Calculate retry delay with exchange-specific backoff.
        
        Args:
            attempt: Current attempt number (1-based)
            error: Exception that caused failure
            
        Returns:
            Delay in seconds before retry
        """
        pass
    
    @abstractmethod
    def handle_rate_limit(self, response_headers: Dict[str, str]) -> float:
        """
        Extract rate limit information from response headers.
        
        Args:
            response_headers: HTTP response headers
            
        Returns:
            Suggested delay in seconds
        """
        pass


class AuthStrategy(ABC):
    """
    Strategy for request authentication and signing.
    
    Handles API key authentication and request signing.
    HFT COMPLIANT: <200μs signature generation.
    """
    
    @abstractmethod
    async def sign_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        timestamp: int
    ) -> AuthenticationData:
        """
        Generate authentication data for request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Request parameters
            timestamp: Request timestamp
            
        Returns:
            AuthenticationData with headers and additional parameters
        """
        pass
    
    @abstractmethod
    def requires_auth(self, endpoint: str) -> bool:
        """
        Check if endpoint requires authentication.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            True if authentication required
        """
        pass


class ExceptionHandlerStrategy(ABC):
    """
    Strategy for handling exchange-specific API errors.
    
    Converts exchange-specific error responses to unified exception types.
    HFT COMPLIANT: <10μs error processing overhead.
    """
    
    @abstractmethod
    def handle_error(self, status_code: int, response_text: str) -> BaseExchangeError:
        """
        Handle exchange-specific API error.
        
        Args:
            status_code: HTTP status code
            response_text: Raw response text from the API
            
        Returns:
            Unified BaseExchangeError or subclass
        """
        pass
    
    @abstractmethod
    def should_handle_error(self, status_code: int, response_text: str) -> bool:
        """
        Check if this strategy should handle the error.
        
        Args:
            status_code: HTTP status code
            response_text: Raw response text from the API
            
        Returns:
            True if this strategy can handle the error
        """
        pass


class RestStrategySet:
    """
    Container for complete REST strategy configuration.
    
    HFT COMPLIANT: Zero-allocation strategy access.
    """
    
    def __init__(
        self,
        request_strategy: RequestStrategy,
        rate_limit_strategy: RateLimitStrategy,
        retry_strategy: RetryStrategy,
        auth_strategy: Optional[AuthStrategy] = None,
        exception_handler_strategy: Optional[ExceptionHandlerStrategy] = None
    ):
        self.request_strategy = request_strategy
        self.rate_limit_strategy = rate_limit_strategy
        self.retry_strategy = retry_strategy
        self.auth_strategy = auth_strategy
        self.exception_handler_strategy = exception_handler_strategy
        
        # HFT Optimization: Pre-validate strategy compatibility
        self._validate_strategies()
        self._performance_targets = request_strategy.get_performance_targets()
        
        self.logger = logging.getLogger(__name__)
    
    def _validate_strategies(self) -> None:
        """Validate strategy compatibility at initialization."""
        if not all([
            self.request_strategy,
            self.rate_limit_strategy,
            self.retry_strategy
        ]):
            raise ValueError("Request, rate limit, and retry strategies must be provided")
    
    def get_performance_targets(self) -> PerformanceTargets:
        """Get performance targets from request strategy."""
        return self._performance_targets


class RestStrategyFactory:
    """
    Factory for creating REST strategy sets with exchange-specific configurations.
    
    HFT COMPLIANT: Fast strategy creation with pre-validated combinations.
    """
    
    _strategy_registry: Dict[str, Dict[str, type]] = {}
    
    @classmethod
    def register_strategies(
        cls,
        exchange: str,
        is_private: bool,
        request_strategy_cls: type,
        rate_limit_strategy_cls: type,
        retry_strategy_cls: type,
        auth_strategy_cls: Optional[type] = None,
        exception_handler_strategy_cls: Optional[type] = None
    ) -> None:
        """
        Register strategy implementations for an exchange.
        
        Args:
            exchange: Exchange name (e.g., 'mexc', 'gateio')
            is_private: True for private API, False for public
            request_strategy_cls: RequestStrategy implementation
            rate_limit_strategy_cls: RateLimitStrategy implementation
            retry_strategy_cls: RetryStrategy implementation
            auth_strategy_cls: AuthStrategy implementation (required for private)
            exception_handler_strategy_cls: ExceptionHandlerStrategy implementation (optional)
        """
        if is_private and auth_strategy_cls is None:
            raise ValueError("AuthStrategy required for private API")
        
        key = f"{exchange}_{'private' if is_private else 'public'}"
        cls._strategy_registry[key] = {
            'request': request_strategy_cls,
            'rate_limit': rate_limit_strategy_cls,
            'retry': retry_strategy_cls,
            'auth': auth_strategy_cls,
            'exception_handler': exception_handler_strategy_cls
        }
    
    @classmethod
    def create_strategies(
        cls,
        exchange: str,
        is_private: bool,
        **kwargs
    ) -> RestStrategySet:
        """
        Create strategy set for an exchange.
        
        Args:
            exchange: Exchange name
            is_private: True for private API
            **kwargs: Strategy constructor arguments
            
        Returns:
            RestStrategySet with configured strategies
        """
        key = f"{exchange}_{'private' if is_private else 'public'}"
        
        if key not in cls._strategy_registry:
            raise ValueError(f"No strategies registered for {key}")
        
        strategies = cls._strategy_registry[key]
        
        # Create auth strategy if available
        auth_strategy = None
        if strategies['auth']:
            auth_strategy = strategies['auth'](**kwargs)
        
        # Create exception handler strategy if available
        exception_handler_strategy = None
        if strategies['exception_handler']:
            exception_handler_strategy = strategies['exception_handler'](**kwargs)
        
        return RestStrategySet(
            request_strategy=strategies['request'](**kwargs),
            rate_limit_strategy=strategies['rate_limit'](**kwargs),
            retry_strategy=strategies['retry'](**kwargs),
            auth_strategy=auth_strategy,
            exception_handler_strategy=exception_handler_strategy
        )
    
    @classmethod
    def list_available_strategies(cls) -> Dict[str, List[str]]:
        """
        List all registered strategy combinations.
        
        Returns:
            Dictionary mapping exchange names to available types
        """
        result = {}
        for key in cls._strategy_registry.keys():
            exchange, api_type = key.rsplit('_', 1)
            if exchange not in result:
                result[exchange] = []
            result[exchange].append(api_type)
        return result