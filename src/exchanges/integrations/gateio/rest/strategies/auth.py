import hashlib
import hmac
from typing import Dict, Any
from urllib.parse import urlencode

from infrastructure.networking.http import AuthStrategy, HTTPMethod, AuthenticationData
from config.structs import ExchangeConfig


class GateioAuthStrategy(AuthStrategy):
    """Gate.io-specific authentication based on ExchangeConfig credentials."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize Gate.io authentication strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing credentials
            logger: Optional HFT logger injection
            **kwargs: Additional parameters (ignored for compatibility)
        """
        if not exchange_config.credentials.has_private_api:
            raise ValueError("Gate.io credentials not configured in ExchangeConfig")
        
        self.api_key = exchange_config.credentials.api_key
        self.secret_key = exchange_config.credentials.secret_key.encode('utf-8')
        self.exchange_config = exchange_config
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = ['gateio', 'rest', 'auth']
            logger = get_strategy_logger('rest.auth.gateio', tags)
        self.logger = logger

    async def sign_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        json_data: Dict[str, Any],
        timestamp: int
    ) -> AuthenticationData:
        """Generate Gate.io authentication data with HMAC-SHA512 signature."""
        # Use current time.time() as float, following official example
        import time
        current_time = time.time()
        timestamp_str = str(current_time)
        
        # Prepare request body and query string according to Gate.io format
        if method == HTTPMethod.GET:
            # GET requests: use query parameters, empty body
            query_string = urlencode(params) if params else ""
            request_body = ""
        elif method == HTTPMethod.DELETE:
            # DELETE requests: use query parameters for filters like currency_pair, empty body
            query_string = urlencode(params) if params else ""
            request_body = ""
        else:
            # POST/PUT requests: use JSON body from json_data, params go to query string
            query_string = urlencode(params) if params else ""
            if json_data:
                import json
                request_body = json.dumps(json_data, separators=(',', ':'))  # Compact JSON
            else:
                request_body = ""
        
        # Create payload hash
        payload_bytes = request_body.encode('utf-8') if request_body else b''
        hash_of_request_body = hashlib.sha512(payload_bytes).hexdigest()
        
        # Gate.io signature format (from official example):
        # signature_string = method + "\n" + url_path + "\n" + query_string + "\n" + payload_hash + "\n" + timestamp
        # Note: url_path should include the API prefix (e.g., /api/v4/spot/accounts)
        url_path = f"/api/v4{endpoint}" if not endpoint.startswith("/api/v4") else endpoint
        string_to_sign = f"{method.value}\n{url_path}\n{query_string}\n{hash_of_request_body}\n{timestamp_str}"
        
        # Create HMAC SHA512 signature
        signature = hmac.new(
            self.secret_key,
            string_to_sign.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        # Prepare authentication headers
        auth_headers = {
            'KEY': self.api_key,
            'SIGN': signature,
            'Timestamp': timestamp_str,
            'Content-Type': 'application/json'
        }

        # Return authentication data based on method
        if method in [HTTPMethod.GET, HTTPMethod.DELETE]:
            # GET/DELETE requests: params in query string, no body
            return AuthenticationData(
                headers=auth_headers,
                params=params if params else {},
                data=None
            )
        else:
            # POST/PUT requests: data in JSON body, params in query string
            return AuthenticationData(
                headers=auth_headers,
                params=params if params else {},
                data=request_body if request_body else None
            )

    def requires_auth(self, endpoint: str) -> bool:
        """Check if Gate.io endpoint requires authentication."""
        # Private endpoints that require authentication
        private_endpoints = [
            '/spot/accounts',
            '/spot/orders',
            '/spot/fee',
            '/spot/my_trades',
            '/spot/batch_orders',
            '/margin/accounts',
            '/futures'  # All futures endpoints require auth
        ]

        return any(endpoint.startswith(private_ep) for private_ep in private_endpoints)