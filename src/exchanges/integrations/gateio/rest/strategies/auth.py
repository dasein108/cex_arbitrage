import hashlib
from typing import Dict, Any, List
from urllib.parse import urlencode

from exchanges.interfaces.rest.strategies import BaseExchangeAuthStrategy
from infrastructure.networking.http import HTTPMethod, AuthenticationData
from config.structs import ExchangeConfig


class GateioAuthStrategy(BaseExchangeAuthStrategy):
    """Gate.io-specific authentication based on ExchangeConfig credentials."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize Gate.io authentication strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing credentials
            logger: Optional HFT logger injection
            **kwargs: Additional parameters (ignored for compatibility)
        """
        super().__init__(exchange_config, logger, **kwargs)

    @property
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        return "Gate.io"

    def get_signature_algorithm(self) -> str:
        """Gate.io uses SHA512 for HMAC signatures."""
        return "sha512"

    def get_auth_headers(self, signature: str, timestamp: str) -> Dict[str, str]:
        """Get Gate.io-specific authentication headers."""
        return {
            'KEY': self.api_key,
            'SIGN': signature,
            'Timestamp': timestamp,
            'Content-Type': 'application/json'
        }

    def prepare_signature_string(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        json_data: Dict[str, Any],
        timestamp: str
    ) -> str:
        """Prepare Gate.io signature string format."""
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
        return f"{method.value}\n{url_path}\n{query_string}\n{hash_of_request_body}\n{timestamp}"

    def _prepare_auth_data(
        self,
        auth_headers: Dict[str, str],
        params: Dict[str, Any],
        json_data: Dict[str, Any],
        signature: str,
        timestamp_str: str
    ) -> AuthenticationData:
        """Prepare Gate.io authentication data with proper parameter placement."""
        # For GET/DELETE: params in query, no body
        # For POST/PUT: JSON body from json_data, params in query
        # Note: timestamp is already in headers for Gate.io (not in params like MEXC)
        if json_data:
            # POST/PUT requests: data in JSON body, params in query string
            import json
            request_body = json.dumps(json_data, separators=(',', ':'))
            return AuthenticationData(
                headers=auth_headers,
                params=params if params else {},
                data=request_body
            )
        else:
            # GET/DELETE requests: params in query string, no body
            return AuthenticationData(
                headers=auth_headers,
                params=params if params else {},
                data=None
            )

    def get_private_endpoints(self) -> List[str]:
        """Get list of private endpoint prefixes that require authentication."""
        return [
            '/spot/accounts',
            '/spot/orders',
            '/spot/fee',
            '/spot/my_trades',
            '/spot/batch_orders',
            '/margin/accounts',
            '/wallet/withdraw_status',
            '/futures'  # All futures endpoints require auth
        ]
    
    def _get_sync_offset(self) -> float:
        """Get Gate.io synchronization offset."""
        return 0.5  # 500ms forward adjustment for Gate.io