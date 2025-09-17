import hashlib
import hmac
from typing import Dict, Any
from urllib.parse import urlencode

from core.transport.rest import AuthStrategy, HTTPMethod, AuthenticationData
from core.config.structs import ExchangeConfig


class MexcAuthStrategy(AuthStrategy):
    """MEXC-specific authentication based on ExchangeConfig credentials."""

    def __init__(self, exchange_config: ExchangeConfig):
        """
        Initialize MEXC authentication strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing credentials
        """
        if not exchange_config.credentials.is_configured():
            raise ValueError("MEXC credentials not configured in ExchangeConfig")
        
        self.api_key = exchange_config.credentials.api_key
        self.secret_key = exchange_config.credentials.secret_key.encode('utf-8')
        self.exchange_config = exchange_config

    async def sign_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        timestamp: int
    ) -> AuthenticationData:
        """Generate MEXC authentication data with proper signature handling."""
        # Prepare parameters for signature (include timestamp and recvWindow)
        auth_params = params.copy()
        auth_params['timestamp'] = timestamp
        auth_params['recvWindow'] = 5000  # MEXC default, can be made configurable

        # Create query string for signature (sorted parameters)
        query_string = urlencode(auth_params)

        # Create HMAC SHA256 signature
        signature = hmac.new(
            self.secret_key,
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Return authentication data (ALL params including business params for MEXC)
        # MEXC requires ALL parameters in query string for authenticated requests
        return AuthenticationData(
            headers={
                'X-MEXC-APIKEY': self.api_key,
                'Content-Type': 'application/json'
            },
            params=auth_params | {'signature': signature}
        )

    def requires_auth(self, endpoint: str) -> bool:
        """Check if MEXC endpoint requires authentication."""
        # Private endpoints that require authentication
        private_endpoints = [
            '/api/v3/account',
            '/api/v3/order',
            '/api/v3/openOrders',
            '/api/v3/allOrders',
            '/api/v3/myTrades',
            '/api/v3/userDataStream'
        ]

        return any(endpoint.startswith(private_ep) for private_ep in private_endpoints)
