"""
MEXC Base REST Implementation

Direct implementation pattern replacing strategy composition for HFT performance.
Eliminates ~1.7μs strategy dispatch overhead per request through direct method calls.

Key Features:
- Direct authentication implementation (no strategy dispatch)
- Constructor injection of dependencies (rate_limiter, logger)  
- Fresh timestamp generation for each request
- MEXC-specific error handling and response parsing
- Sub-microsecond overhead compared to strategy pattern

HFT COMPLIANCE: Maintains <50ms latency targets with reduced overhead.
"""

import time
import hashlib
import hmac
from typing import Any, Dict, Optional

import msgspec
from urllib.parse import urlencode

from config.structs import ExchangeConfig
from infrastructure.networking.http.structs import HTTPMethod
from infrastructure.networking.http.base_rest_client import BaseRestClientInterface
from infrastructure.exceptions.exchange import (
    ExchangeRestError, RateLimitErrorRest, RecvWindowError, TooManyRequestsError,
    InvalidApiKeyError, SignatureError, InvalidParameterError, OrderNotFoundError,
    InsufficientBalanceError, InvalidSymbolError, TradingDisabledError, OrderSizeError,
    PositionLimitError, RiskControlError, AccountError, TransferError, WithdrawalError,
    MaintenanceError, ServiceUnavailableError, ExchangeServerError, AuthenticationError,
    InsufficientPermissionsError, IpNotWhitelistedError
)
from exchanges.integrations.mexc.structs.exchange import MexcErrorResponse
from infrastructure.decorators.retry import mexc_retry
from infrastructure.logging import HFTLoggerInterface


class MexcBaseRestInterface(BaseRestClientInterface):
    """
    Base REST client for MEXC with direct implementation pattern.
    
    Provides unified request handling for both public and private MEXC endpoints
    with optimized authentication and error handling directly implemented.
    
    Constructor injection pattern ensures all dependencies are provided at creation.
    """
    
    # MEXC API constants
    _RECV_WINDOW = 5000  # MEXC default receive window
    _TIMESTAMP_OFFSET = 500  # 500ms forward offset for MEXC
    
    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None, is_private: bool = False):
        """
        Initialize MEXC base REST client with internal rate limiter creation.
        
        Args:
            config: Exchange configuration with URL and credentials
            logger: HFT logger interface (injected)
            is_private: Whether this client handles private endpoints
        """
        # Create internal rate limiter for MEXC
        from exchanges.integrations.mexc.rest.rate_limit import MexcRateLimit
        rate_limiter = MexcRateLimit(config, logger)
        # requests_per_second = config.rate_limit.requests_per_second if config.rate_limit else 20,

        super().__init__(config, rate_limiter, logger, is_private)
        
        # MEXC-specific performance tracking
        self._total_auth_time_us = 0.0
        
        # Metrics
        self.logger.metric("mexc_base_rest_clients_created", 1,
                          tags={"is_private": str(is_private)})
    
    @property
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        return "MEXC"
    
    def _get_fresh_timestamp(self) -> str:
        """
        Generate fresh timestamp for MEXC authentication.
        
        Uses base class helper with MEXC-specific offset.
        
        Returns:
            Timestamp string in milliseconds with MEXC offset
        """
        return self._get_timestamp_with_offset(self._TIMESTAMP_OFFSET, use_seconds=False)
    
    async def _authenticate(
        self, 
        method: HTTPMethod, 
        endpoint: str, 
        params: Dict, 
        data: Dict
    ) -> Dict[str, Any]:
        """
        Direct MEXC authentication implementation.
        
        Generates fresh timestamp and HMAC-SHA256 signature according to MEXC specification.
        Returns headers and params needed for authenticated requests.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            
        Returns:
            Dictionary with 'headers' and 'params' for authenticated request
        """
        if not self.is_private or not self.api_key or not self.secret_key:
            return {'headers': {}, 'params': params or {}}
        
        # Performance tracking
        start_time = time.perf_counter()
        
        try:
            # Generate fresh timestamp for this request
            timestamp = self._get_fresh_timestamp()
            
            # Build signature parameters (MEXC puts everything in query string)
            auth_params = {}
            
            # Add existing query parameters
            if params:
                auth_params.update(params)
            
            # Add JSON data parameters if any (MEXC requirement)
            if data:
                auth_params.update(data)
            
            # Add required MEXC auth parameters  
            auth_params.update({
                'timestamp': int(timestamp),
                'recvWindow': self._RECV_WINDOW
            })
            
            # Generate signature string (URL-encoded sorted parameters)
            signature_string = urlencode(auth_params)
            
            # Generate HMAC-SHA256 signature
            signature = hmac.new(
                self.secret_key.encode('utf-8'),
                signature_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Add signature to parameters
            auth_params['signature'] = signature
            
            # Prepare authentication headers
            auth_headers = {
                'X-MEXC-APIKEY': self.api_key,
                'Content-Type': 'application/json'
            }
            
            # Track performance using base class helper
            auth_time_us = self._track_auth_performance(start_time, endpoint, method)
            self._total_auth_time_us += auth_time_us
            
            return {
                'headers': auth_headers,
                'params': auth_params
            }
            
        except Exception as e:
            self.logger.error(
                "MEXC authentication failed",
                endpoint=endpoint,
                method=method.value,
                error_type=type(e).__name__,
                error_message=str(e)
            )
            
            self.logger.metric("mexc_auth_failures", 1,
                              tags={"endpoint": endpoint, "error": type(e).__name__})
            raise
    
    def _handle_error(self, status: int, response_text: str, params: Any = None) -> Exception:
        """
        Comprehensive MEXC error handling implementation using msgspec.Struct.
        
        Maps MEXC-specific error codes to appropriate exception types for proper retry logic.
        Follows struct-first policy for HFT performance compliance.
        
        Args:
            status: HTTP status code
            response_text: Response body text
            
        Returns:
            Appropriate exception instance based on MEXC error codes
        """
        try:
            # Parse using msgspec.Struct for HFT performance
            error_response = msgspec.json.decode(response_text, type=MexcErrorResponse)
            code = error_response.code if error_response.code is not None else status
            message = error_response.msg if error_response.msg is not None else response_text
            
            # Comprehensive MEXC error code mapping based on official documentation
            # infrastructure.exceptions.exchange.ExchangeRestError: HTTP 500: Withdrawal submission failed: HTTP 400: MEXC no permission for endpoint: No permission to access the endpoint.
            # Rate Limiting Errors (Retryable with backoff)
            if status == 429 or code == 429:
                return TooManyRequestsError(status, f"MEXC rate limit exceeded: {message}", code)

            elif code in [700007]:
                return PermissionError(status, f"MEXC permissions error: {message}", code)
            # Authentication and Authorization Errors (Non-retryable)
            elif code in [400, 700001, 700002, 700003]:
                if code == 400:
                    return InvalidApiKeyError(status, f"MEXC API key required: {message}", code)
                elif code in [700001, 700002]:
                    return SignatureError(status, f"MEXC signature validation failed: {message}", code)
                elif code == 700003:
                    return RecvWindowError(status, f"MEXC timestamp outside recvWindow: {message}", code)
            elif code in [401, 403, 700006, 700007, 10072]:
                if code in [401, 403]:
                    return AuthenticationError(status, f"MEXC access denied: {message}", code)
                elif code == 700006:
                    return IpNotWhitelistedError(status, f"MEXC IP not whitelisted: {message}", code)
                elif code == 700007:
                    return InsufficientPermissionsError(status, f"MEXC no permission for endpoint: {message}", code)
                elif code == 10072:
                    return InvalidApiKeyError(status, f"MEXC invalid access key: {message}", code)
            
            # Parameter and Validation Errors (Non-retryable)
            elif code in [33333, 44444, 700004, 700005, 700008, 10015, 10095, 10096, 10097, 10102, 10222]:
                return InvalidParameterError(status, f"MEXC parameter error: {message} \r\n{params}", code)
            
            # Order-related Errors (Non-retryable)
            elif code in [-2011, -2013, 22222, 700004]:
                if code == -2011 or code == -2013:
                    return OrderNotFoundError(status, f"MEXC unknown order: {message}", code)
                elif code == 22222:
                    return OrderNotFoundError(status, f"MEXC order not found: {message}", code)
            
            # Balance and Position Errors (Non-retryable)
            elif code in [10101, 30004, 30005]:
                if code == 10101:
                    return InsufficientBalanceError(status, f"MEXC insufficient balance: {message}", code)
                elif code in [30004, 30005]:
                    return InsufficientBalanceError(status, f"MEXC insufficient position: {message}", code)
            
            # Symbol and Trading Errors (Non-retryable)
            elif code in [10007, 30014, 30021, 10232]:
                return InvalidSymbolError(status, f"MEXC invalid symbol: {message}", code)
            elif code in [30000, 30016, 30018, 30019, 30020]:
                return TradingDisabledError(status, f"MEXC trading disabled: {message}", code)
            elif code in [30001, 30041]:
                return TradingDisabledError(status, f"MEXC order type not allowed: {message}", code)
            
            # Order Size and Limit Errors (Non-retryable)
            elif code in [30002, 30003, 30029, 30032]:
                if code in [30002, 30003]:
                    return OrderSizeError(status, f"MEXC order size violation: {message}", code)
                elif code in [30029, 30032]:
                    return PositionLimitError(status, f"MEXC position limit exceeded: {message}", code)
            elif code in [30027, 30028]:
                return PositionLimitError(status, f"MEXC position limit reached: {message}", code)
            
            # Risk Control Errors (Non-retryable)
            elif code in [10098, 60005, 70011, 10265]:
                return RiskControlError(status, f"MEXC risk control: {message}", code)
            
            # Account Errors (Mixed)
            elif code in [10001, 10099, 730100, 730000, 730001, 730002, 730003]:
                return AccountError(status, f"MEXC account error: {message}", code)
            
            # Transfer and Withdrawal Errors (Mixed)
            elif code in [10100, 10103, 10200, 10201, 10202, 10206, 10211]:
                return TransferError(status, f"MEXC transfer error: {message}", code)
            elif code in [10212, 10216, 10219, 10268]:
                return WithdrawalError(status, f"MEXC withdrawal error: {message}", code)
            
            # Server Errors (Retryable)
            elif status in [500, 502, 503, 504] or code in [500, 503, 504, 20002]:
                if status == 503 or code == 503:
                    return ServiceUnavailableError(status, f"MEXC service unavailable: {message}", code)
                else:
                    return ExchangeServerError(status, f"MEXC server error: {message}", code)
            
            # System and Subsystem Errors (Mixed)
            elif code in [20001, 10259]:
                return MaintenanceError(status, f"MEXC system error: {message}", code)
            
            # Catch-all for unmapped errors
            else:
                return ExchangeRestError(status, f"MEXC API error {code}: {message}", code)
                
        except (msgspec.DecodeError, msgspec.ValidationError):
            # Fallback for non-JSON or malformed responses
            if status == 429:
                return TooManyRequestsError(status, f"MEXC rate limit: {response_text}")
            elif status in [500, 502, 503, 504]:
                return ExchangeServerError(status, f"MEXC server error: {response_text}")
            elif status in [401, 403]:
                return AuthenticationError(status, f"MEXC authentication error: {response_text}")
            else:
                return ExchangeRestError(status, f"MEXC HTTP {status}: {response_text}")
    
    
    @mexc_retry(max_attempts=3)
    async def _request(
        self, 
        method: HTTPMethod, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None, 
        data: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        MEXC-specific request implementation with retry decorator.
        
        Applies MEXC-specific retry logic to the base request implementation.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            
        Returns:
            Parsed response data
        """
        # Delegate to base class implementation
        return await super()._request(method, endpoint, params, data)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get MEXC-specific performance statistics.
        
        Returns:
            Dictionary with performance metrics including MEXC auth timing
        """
        base_stats = super().get_performance_stats()
        
        # Add MEXC-specific metrics
        avg_auth_time_us = (
            self._total_auth_time_us / self._request_count 
            if self._request_count > 0 else 0
        )
        
        base_stats.update({
            "avg_auth_time_us": avg_auth_time_us,
            "exchange": "mexc"
        })
        
        return base_stats