"""
Gate.io Base Futures REST Implementation

Direct implementation pattern for Gate.io futures trading REST API.
Inherits from shared BaseRestClient with Gate.io-specific authentication and error handling.

Key Features:
- Direct Gate.io futures authentication implementation (SHA512 HMAC)
- Constructor injection of dependencies (rate_limiter, logger)
- Futures-specific endpoint handling and error parsing
- Sub-microsecond overhead compared to strategy pattern

Gate.io Futures API Specifications:
- Base URL: https://api.gateio.ws
- Authentication: HMAC-SHA512 with specific payload format (same as spot)
- Signature format: method + url_path + query_string + payload_hash + timestamp
- Futures endpoints: /api/v4/futures/* (different from spot /api/v4/spot/*)
- Headers: KEY, SIGN, Timestamp, Content-Type

HFT COMPLIANCE: Maintains <50ms latency targets with reduced overhead.
"""

import time
import hashlib
import hmac
import json
from typing import Any, Dict, Optional

import msgspec
from urllib.parse import urlencode

from infrastructure.networking.http.structs import HTTPMethod
from infrastructure.networking.http.base_rest_client import BaseRestClientInterface
from infrastructure.exceptions.exchange import (
    ExchangeRestError, RateLimitErrorRest, RecvWindowError, OrderNotFoundError,
    AuthenticationError, InvalidApiKeyError, SignatureError, InsufficientPermissionsError,
    IpNotWhitelistedError, InvalidParameterError, OrderCancelledOrFilled,
    InsufficientBalanceError, InvalidSymbolError, TradingDisabledError,
    OrderSizeError, PositionLimitError, RiskControlError, AccountError,
    TransferError, MaintenanceError, ServiceUnavailableError, ExchangeServerError,
    ExchangeConnectionRestError, TooManyRequestsError
)
from exchanges.integrations.gateio.structs.exchange import GateioErrorResponse
from infrastructure.decorators.retry import gateio_retry
from infrastructure.logging import HFTLoggerInterface


class GateioBaseFuturesRestInterface(BaseRestClientInterface):
    """
    Base REST client for Gate.io Futures with direct implementation pattern.
    
    Provides unified request handling for both public and private Gate.io futures endpoints
    with optimized authentication and error handling directly implemented.
    
    Constructor injection pattern ensures all dependencies are provided at creation.
    """
    
    # Gate.io API constants
    _TIMESTAMP_OFFSET = 500  # 500ms forward offset for Gate.io
    
    def __init__(self, config,  logger: Optional[HFTLoggerInterface] = None, is_private: bool = False):
        """
        Initialize Gate.io base futures REST client with internal rate limiter creation.
        
        Args:
            config: Exchange configuration with URL and credentials
            logger: HFT logger interface (injected)
            is_private: Whether this client handles private endpoints
        """
        # Create internal rate limiter for Gate.io futures

        from exchanges.integrations.gateio.rest.rate_limit import GateioRateLimit
        rate_limiter = GateioRateLimit(config, logger)

        # Initialize base class with shared infrastructure
        super().__init__(config, rate_limiter, logger, is_private)
        
        # Gate.io futures-specific performance tracking
        self._total_auth_time_us = 0.0
        
        # Metrics
        self.logger.metric("gateio_base_futures_rest_clients_created", 1,
                          tags={"is_private": str(is_private)})
    
    @property
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        return "Gate.io Futures"
    
    def _get_fresh_timestamp(self) -> str:
        """
        Generate fresh timestamp for Gate.io authentication.
        
        Uses decimal seconds format as required by Gate.io API specification.
        
        Returns:
            Timestamp string in decimal seconds format (e.g., "1541993715.5")
        """
        # Note: Gate.io uses decimal seconds in float format
        current_time = time.time()
        adjusted_time = current_time + (self._TIMESTAMP_OFFSET / 1000.0)
        return str(adjusted_time)  # Keep as decimal seconds for Gate.io
    
    async def _authenticate(
        self, 
        method: HTTPMethod, 
        endpoint: str, 
        params: Dict, 
        data: Dict
    ) -> Dict[str, Any]:
        """
        Direct Gate.io futures authentication implementation.
        
        Uses the same authentication as spot but with futures-specific endpoint handling.
        Generates fresh timestamp and HMAC-SHA512 signature according to Gate.io specification.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (futures-specific)
            params: Query parameters
            data: Request body data
            
        Returns:
            Dictionary with 'headers', 'params', and 'data' for authenticated request
        """
        if not self.is_private or not self.api_key or not self.secret_key:
            return {'headers': {}, 'params': params or {}, 'data': data}
        
        # Performance tracking
        start_time = time.perf_counter()
        
        try:
            # Generate fresh timestamp for this request
            timestamp = self._get_fresh_timestamp()
            
            # Prepare request components according to Gate.io format
            if method in [HTTPMethod.GET, HTTPMethod.DELETE]:
                # GET/DELETE: use query parameters, empty body
                query_string = urlencode(params) if params else ""
                request_body = ""
            else:
                # POST/PUT: use JSON body from data, params in query string
                query_string = urlencode(params) if params else ""
                if data:
                    request_body = json.dumps(data, separators=(',', ':'))  # Compact JSON
                else:
                    request_body = ""
            
            # Create payload hash (Gate.io requirement)
            payload_bytes = request_body.encode('utf-8') if request_body else b''
            payload_hash = hashlib.sha512(payload_bytes).hexdigest()
            
            # Build signature string (Gate.io format) - futures endpoints use /api/v4/futures/...
            # Ensure proper futures endpoint format
            if endpoint.startswith('/api/v4/'):
                url_path = endpoint
            elif endpoint.startswith('/futures/'):
                url_path = f"/api/v4{endpoint}"
            else:
                # Add /api/v4 prefix if missing, assume futures endpoint
                url_path = f"/api/v4/futures{endpoint}" if not endpoint.startswith('/') else f"/api/v4/futures{endpoint}"
            
            signature_string = f"{method.value}\n{url_path}\n{query_string}\n{payload_hash}\n{timestamp}"
            
            # Generate HMAC-SHA512 signature
            signature = hmac.new(
                self.secret_key.encode('utf-8'),
                signature_string.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()
            
            # Prepare authentication headers (Gate.io format)
            auth_headers = {
                'KEY': self.api_key,
                'SIGN': signature,
                'Timestamp': timestamp,
                'Content-Type': 'application/json'
            }
            
            # Track performance
            auth_time_us = (time.perf_counter() - start_time) * 1_000_000
            self._total_auth_time_us += auth_time_us
            
            self.logger.debug(
                "Gate.io futures authentication completed",
                endpoint=endpoint,
                auth_time_us=auth_time_us,
                timestamp=timestamp,
                url_path=url_path
            )
            
            # Metrics
            self.logger.metric("gateio_futures_auth_signatures_generated", 1,
                              tags={"endpoint": endpoint, "method": method.value})
            self.logger.metric("gateio_futures_auth_time_us", auth_time_us,
                              tags={"endpoint": endpoint})
            
            # Return properly formatted data for aiohttp
            # When request_body exists (JSON string), we need to send it as raw text data
            # When request_body is empty, send original data as JSON object
            if request_body:
                # Send pre-encoded JSON string as raw text data
                return {
                    'headers': auth_headers,
                    'params': params or {},
                    'data': request_body,
                }
            else:
                # Send original data object for JSON encoding by aiohttp
                return {
                    'headers': auth_headers,
                    'params': params or {},
                    'data': data
                }
            
        except Exception as e:
            self.logger.error(
                "Gate.io futures authentication failed",
                endpoint=endpoint,
                method=method.value,
                error_type=type(e).__name__,
                error_message=str(e)
            )
            
            self.logger.metric("gateio_futures_auth_failures", 1,
                              tags={"endpoint": endpoint, "error": type(e).__name__})
            raise
    
    def _handle_error(self, status: int, response_text: str) -> Exception:
        """
        Comprehensive Gate.io futures error handling implementation using msgspec.Struct.
        
        Maps Gate.io-specific error labels and messages to appropriate exceptions
        based on the official Gate.io API documentation, with extensive futures-specific
        error handling for margin, positions, leverage, and risk management operations.
        
        Futures-Specific Error Categories:
        - Contract & Symbol Validation (Non-retryable)
        - Position Management (Non-retryable)
        - Leverage & Margin (Non-retryable)
        - Risk Control & Liquidation (Non-retryable)
        - Futures-specific Trading Operations (Non-retryable)
        
        Args:
            status: HTTP status code
            response_text: Response body text
            
        Returns:
            Appropriate exception instance for proper retry logic categorization
        """
        try:
            # Parse using msgspec.Struct for HFT performance
            error_response = msgspec.json.decode(response_text, type=GateioErrorResponse)
            message = error_response.message if error_response.message is not None else response_text
            label = error_response.label if error_response.label is not None else ""
            

            # === AUTHENTICATION & AUTHORIZATION ERRORS (Non-retryable) ===
            
            # Authentication failures
            if label == "INVALID_CREDENTIALS":
                return AuthenticationError(status, f"Invalid credentials: {message}")
            elif label == "INVALID_KEY":
                return InvalidApiKeyError(status, f"Invalid API key: {message}")
            elif label == "INVALID_SIGNATURE":
                return SignatureError(status, f"Invalid signature: {message}")
            elif label == "REQUEST_EXPIRED":
                return RecvWindowError(status, f"Request timestamp expired: {message}")
            elif label == "MISSING_REQUIRED_HEADER":
                return AuthenticationError(status, f"Missing required header: {message}")
            
            # Authorization failures
            elif label == "IP_FORBIDDEN":
                return IpNotWhitelistedError(status, f"IP not whitelisted: {message}")
            elif label == "READ_ONLY":
                return InsufficientPermissionsError(status, f"API key is read-only: {message}")
            elif label == "FORBIDDEN":
                return InsufficientPermissionsError(status, f"No permission for operation: {message}")
            
            # === PARAMETER VALIDATION ERRORS (Non-retryable) ===
            
            # Request format errors
            elif label in ["INVALID_PARAM_VALUE", "INVALID_PROTOCOL", "INVALID_ARGUMENT", 
                          "INVALID_REQUEST_BODY", "MISSING_REQUIRED_PARAM", "BAD_REQUEST",
                          "INVALID_CONTENT_TYPE", "NOT_ACCEPTABLE", "METHOD_NOT_ALLOWED"]:
                return InvalidParameterError(status, f"Invalid request parameter: {message}")
            elif label == "NOT_FOUND":
                return ExchangeRestError(status, f"Endpoint not found: {message}")
            elif label == "INVALID_CLIENT_ORDER_ID":
                return InvalidParameterError(status, f"Invalid client order ID: {message}")
            
            # === FUTURES-SPECIFIC CONTRACT & SYMBOL VALIDATION (Non-retryable) ===
            
            elif label == "CONTRACT_NOT_FOUND":
                return InvalidSymbolError(status, f"Futures contract not found: {message}")
            elif label in ["INVALID_CURRENCY", "INVALID_CURRENCY_PAIR"]:
                return InvalidSymbolError(status, f"Invalid futures trading pair: {message}")
            elif label == "INVALID_PRECISION":
                return InvalidParameterError(status, f"Invalid precision: {message}")
            
            # === FUTURES TRADING & ORDER OPERATION ERRORS (Non-retryable) ===
            
            # Order management
            elif label == "ORDER_NOT_FOUND":
                return OrderNotFoundError(status, f"Futures order not found: {message}")
            elif label in ["ORDER_CLOSED", "ORDER_CANCELLED"]:
                return OrderCancelledOrFilled(status, f"Futures order already closed/cancelled: {message}")
            elif label == "ORDER_EXISTS":
                return ExchangeRestError(status, f"Futures order already exists: {message}")
            elif label == "CANCEL_FAIL":
                return ExchangeRestError(status, f"Futures order cancel failed: {message}")
            
            # Order size and quantity validation
            elif label in ["AMOUNT_TOO_LITTLE", "AMOUNT_TOO_MUCH"]:
                return OrderSizeError(status, f"Invalid futures order amount: {message}")
            elif label == "QUANTITY_NOT_ENOUGH":
                return OrderSizeError(status, f"Futures quantity not enough: {message}")
            
            # Trading restrictions
            elif label == "TRADE_RESTRICTED":
                return TradingDisabledError(status, f"Futures trading restricted: {message}")
            elif label == "TRADING_DISABLED":
                return TradingDisabledError(status, f"Futures trading disabled: {message}")
            
            # Order execution specific errors
            elif label == "POC_FILL_IMMEDIATELY":
                return ExchangeRestError(status, f"POC futures order would fill immediately: {message}")
            elif label == "FOK_NOT_FILL":
                return ExchangeRestError(status, f"FOK futures order cannot be filled completely: {message}")
            elif label == "INCREASE_POSITION":
                return ExchangeRestError(status, f"POC order will increase position: {message}")
            
            # === FUTURES BALANCE & MARGIN ERRORS (Non-retryable) ===
            
            # Balance errors
            elif label in ["INSUFFICIENT_AVAILABLE", "BALANCE_NOT_ENOUGH"]:
                return InsufficientBalanceError(status, f"Insufficient futures balance: {message}")
            elif label == "FUTURES_BALANCE_NOT_ENOUGH":
                return InsufficientBalanceError(status, f"Insufficient futures balance: {message}")
            elif label == "TOO_MUCH_FUTURES_AVAILABLE":
                return RiskControlError(status, f"Futures balance exceeds maximum: {message}")
            elif label == "MARGIN_BALANCE_NOT_ENOUGH":
                return InsufficientBalanceError(status, f"Insufficient margin balance: {message}")
            
            # === FUTURES LEVERAGE & RISK MANAGEMENT (Non-retryable) ===
            
            # Leverage control
            elif label in ["LEVERAGE_TOO_HIGH", "LEVERAGE_TOO_LOW"]:
                return RiskControlError(status, f"Futures leverage error: {message}")
            elif label == "INITIAL_MARGIN_TOO_LOW":
                return RiskControlError(status, f"Initial margin too low: {message}")
            
            # Risk control and liquidation
            elif label == "LIQUIDATE_IMMEDIATELY":
                return RiskControlError(status, f"Operation may cause liquidation: {message}")
            elif label == "RISK_LIMIT_EXCEEDED":
                return PositionLimitError(status, f"Risk limit exceeded: {message}")
            
            # === FUTURES POSITION MANAGEMENT ERRORS (Non-retryable) ===
            
            # Position state errors
            elif label == "POSITION_NOT_FOUND":
                return ExchangeRestError(status, f"Position not found: {message}")
            elif label == "POSITION_EMPTY":
                return ExchangeRestError(status, f"Position is empty: {message}")
            elif label == "POSITION_IN_LIQUIDATION":
                return RiskControlError(status, f"Position is being liquidated: {message}")
            elif label == "POSITION_IN_CLOSE":
                return ExchangeRestError(status, f"Position is closing: {message}")
            
            # Position mode and operation restrictions
            elif label == "POSITION_DUAL_MODE":
                return ExchangeRestError(status, f"Operation forbidden in dual-mode: {message}")
            elif label == "POSITION_HOLDING":
                return ExchangeRestError(status, f"Operation forbidden with holding position: {message}")
            elif label == "POSITION_CROSS_MARGIN":
                return ExchangeRestError(status, f"Margin updating not allowed in cross margin: {message}")
            
            # === ACCOUNT & TRANSFER ERRORS (Mixed retryability) ===
            
            # Account errors
            elif label == "ACCOUNT_LOCKED":
                return AccountError(status, f"Futures account is locked: {message}")
            elif label in ["SUB_ACCOUNT_NOT_FOUND", "SUB_ACCOUNT_LOCKED"]:
                return AccountError(status, f"Sub-account error: {message}")
            elif label in ["MARGIN_BALANCE_EXCEPTION", "ACCOUNT_EXCEPTION"]:
                return AccountError(status, f"Futures account exception: {message}")
            elif label == "USER_NOT_FOUND":
                return AccountError(status, f"User not found: {message}")
            
            # Transfer operations
            elif label in ["MARGIN_TRANSFER_FAILED", "SUB_ACCOUNT_TRANSFER_FAILED"]:
                return TransferError(status, f"Futures transfer failed: {message}")
            elif label in ["INVALID_WITHDRAW_ID", "INVALID_WITHDRAW_CANCEL_STATUS"]:
                return InvalidParameterError(status, f"Invalid withdrawal operation: {message}")
            
            # === BATCH OPERATION ERRORS (Non-retryable) ===
            
            elif label in ["TOO_MANY_CURRENCY_PAIRS", "TOO_MANY_ORDERS", "MIXED_ACCOUNT_TYPE"]:
                return InvalidParameterError(status, f"Batch operation error: {message}")
            elif label == "NO_MERGEABLE_ORDERS":
                return ExchangeRestError(status, f"No mergeable orders found: {message}")
            elif label == "DUPLICATE_REQUEST":
                return ExchangeRestError(status, f"Duplicate request: {message}")
            
            # === SYSTEM & SERVICE ERRORS (Retryable) ===
            
            # System availability
            elif label in ["INTERNAL", "SERVER_ERROR"]:
                return ExchangeServerError(status, f"Internal server error: {message}")
            elif label == "ORDER_BOOK_NOT_FOUND":
                return ServiceUnavailableError(status, f"Insufficient liquidity: {message}")
            elif label == "FAILED_RETRIEVE_ASSETS":
                return ServiceUnavailableError(status, f"Failed to retrieve assets: {message}")
            
            # === FALLBACK PATTERNS FOR LEGACY MESSAGE FORMATS ===
            
            elif 'RATE_LIMIT' in message.upper() or 'TOO_MANY_REQUESTS' in message.upper():
                return TooManyRequestsError(status, f"Gate.io futures rate limit: {message}")
            elif 'INVALID_SIGNATURE' in message.upper() or 'SIGNATURE_INVALID' in message.upper():
                return SignatureError(status, f"Gate.io futures signature validation failed: {message}")
            elif 'TIMESTAMP' in message.upper() and 'EXPIRED' in message.upper():
                return RecvWindowError(status, f"Gate.io futures timestamp expired: {message}")
            elif 'INSUFFICIENT' in message.upper() and ('BALANCE' in message.upper() or 'MARGIN' in message.upper()):
                return InsufficientBalanceError(status, f"Gate.io futures insufficient balance/margin: {message}")
            elif 'POSITION' in message.upper() and ('NOT_FOUND' in message.upper() or 'INVALID' in message.upper() or 'EMPTY' in message.upper()):
                return ExchangeRestError(status, f"Gate.io futures position error: {message}")
            elif 'ORDER_NOT_FOUND' in message.upper():
                return OrderNotFoundError(status, f"Gate.io futures order not found: {message}")
            elif 'TRADING' in message.upper() and 'DISABLED' in message.upper():
                return TradingDisabledError(status, f"Gate.io futures trading disabled: {message}")
            elif 'LEVERAGE' in message.upper() and ('HIGH' in message.upper() or 'EXCEED' in message.upper() or 'LOW' in message.upper()):
                return RiskControlError(status, f"Gate.io futures leverage error: {message}")
            elif 'LIQUIDAT' in message.upper():
                return RiskControlError(status, f"Gate.io futures liquidation risk: {message}")
            elif 'CONTRACT' in message.upper() and 'NOT_FOUND' in message.upper():
                return InvalidSymbolError(status, f"Gate.io futures contract not found: {message}")

            # HTTP status code based categorization first
            elif status == 429:
                return TooManyRequestsError(status, f"Gate.io futures rate limit exceeded: {message}")
            elif status == 401:
                return AuthenticationError(status, f"Gate.io futures authentication failed: {message}")
            elif status == 403:
                return InsufficientPermissionsError(status, f"Gate.io futures forbidden: {message}")
            elif status == 404:
                return ExchangeRestError(status, f"Gate.io futures not found: {message}")
            elif status >= 500:
                return ExchangeServerError(status, f"Gate.io futures server error: {message}")
            else:
                # Generic error with label information for debugging
                label_info = f" [Label: {label}]" if label else ""
                return ExchangeRestError(status, f"Gate.io futures API error{label_info}: {message}")

        except (msgspec.DecodeError, msgspec.ValidationError):
            # Fallback for non-JSON or malformed responses
            if status == 429:
                return TooManyRequestsError(status, f"Gate.io futures rate limit: {response_text}")
            elif status >= 500:
                return ExchangeServerError(status, f"Gate.io futures server error {status}: {response_text}")
            elif status == 401:
                return AuthenticationError(status, f"Gate.io futures authentication error: {response_text}")
            elif status == 403:
                return InsufficientPermissionsError(status, f"Gate.io futures forbidden: {response_text}")
            else:
                return ExchangeRestError(status, f"Gate.io futures HTTP {status}: {response_text}")
    
    
    @gateio_retry(max_attempts=3)
    async def _request(
        self, 
        method: HTTPMethod, 
        endpoint: str, 
        params: Optional[Dict] = None, 
        data: Optional[Dict] = None
    ) -> Any:
        """
        Core request implementation with direct handling.
        
        Eliminates strategy dispatch overhead through direct implementation of:
        - Rate limiting
        - Authentication (with futures-specific endpoint handling)
        - Error handling
        - Response parsing
        
        Args:
            method: HTTP method
            endpoint: API endpoint (futures-specific)
            params: Query parameters
            data: Request body data
            
        Returns:
            Parsed response data
        """
        # Delegate to base class implementation
        return await super()._request(method, endpoint, params, data)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get Gate.io futures-specific performance statistics.
        
        Returns:
            Dictionary with performance metrics including Gate.io auth timing
        """
        base_stats = super().get_performance_stats()
        
        # Add Gate.io futures-specific metrics
        avg_auth_time_us = (
            self._total_auth_time_us / self._request_count 
            if self._request_count > 0 else 0
        )
        
        base_stats.update({
            "avg_auth_time_us": avg_auth_time_us,
            "exchange": "gateio",
            "market_type": "futures"
        })
        
        return base_stats