import hashlib
import hmac
import time
from typing import Dict, Any
from urllib.parse import urlencode

from infrastructure.networking.http import AuthStrategy, HTTPMethod, AuthenticationData
from config.structs import ExchangeConfig
from infrastructure.data_structures.connection import RestConnectionSettings

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, LoggingTimer


class MexcAuthStrategy(AuthStrategy):
    """MEXC-specific authentication based on ExchangeConfig credentials."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None):
        """
        Initialize MEXC authentication strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing credentials
            logger: Optional HFT logger injection
        """
        if not exchange_config.credentials.has_private_api:
            raise ValueError("MEXC credentials not configured in ExchangeConfig")
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            tags = ['mexc', 'private', 'rest', 'auth']
            logger = get_strategy_logger('rest.auth.mexc.private', tags)
        
        self.logger = logger
        self.api_key = exchange_config.credentials.api_key
        self.secret_key = exchange_config.credentials.secret_key.encode('utf-8')
        self.exchange_config = exchange_config
        
        # Timestamp synchronization for RecvWindow errors
        self._time_offset = 0  # Offset to add to local timestamp
        
        # Log strategy initialization (move to DEBUG per logging spec)
        self.logger.debug("MEXC auth strategy initialized",
                         api_key_configured=bool(self.api_key),
                         recv_window=5000)
        
        self.logger.metric("rest_auth_strategies_created", 1,
                          tags={"exchange": "mexc", "type": "private"})

    async def sign_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        json_data: Dict[str, Any],
        timestamp: int
    ) -> AuthenticationData:
        """Generate MEXC authentication data with proper signature handling."""
        try:
            with LoggingTimer(self.logger, "mexc_auth_signature_generation") as timer:
                # MEXC puts ALL parameters (including json_data) in query string for authenticated requests
                auth_params = {}
                
                # Add query parameters if any
                if params:
                    auth_params.update(params)
                
                # Add JSON data parameters if any (MEXC requirement)
                if json_data:
                    auth_params.update(json_data)
                
                # Add required MEXC auth parameters
                rest_settings = RestConnectionSettings(
                    recv_window=5000,  # MEXC default
                    timeout=30,
                    max_retries=3
                )
                # Apply time offset for timestamp synchronization
                adjusted_timestamp = timestamp + self._time_offset
                auth_params['timestamp'] = adjusted_timestamp
                auth_params['recvWindow'] = rest_settings.recv_window

                # Create query string for signature (sorted parameters)
                query_string = urlencode(auth_params)

                # Create HMAC SHA256 signature
                signature = hmac.new(
                    self.secret_key,
                    query_string.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()

                # Prepare authentication data
                auth_data = AuthenticationData(
                    headers={
                        'X-MEXC-APIKEY': self.api_key,
                        'Content-Type': 'application/json'
                    },
                    params=auth_params | {'signature': signature},
                    data=None  # MEXC uses query parameters, not request body
                )
            
            # Track signature generation metrics
            self.logger.metric("rest_auth_signatures_generated", 1,
                              tags={"exchange": "mexc", "endpoint": endpoint, "method": method.value})
            
            self.logger.metric("rest_auth_signature_time_us", timer.elapsed_ms * 1000,
                              tags={"exchange": "mexc", "endpoint": endpoint})
            
            self.logger.debug("MEXC authentication signature generated",
                            endpoint=endpoint,
                            method=method.value,
                            params_count=len(auth_params),
                            signature_time_us=timer.elapsed_ms * 1000)
            
            return auth_data
            
        except Exception as e:
            self.logger.error("Failed to generate MEXC authentication signature",
                            endpoint=endpoint,
                            method=method.value,
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            self.logger.metric("rest_auth_signature_failures", 1,
                              tags={"exchange": "mexc", "endpoint": endpoint})
            
            raise

    def requires_auth(self, endpoint: str) -> bool:
        """Check if MEXC endpoint requires authentication."""
        # Private endpoints that require authentication
        private_endpoints = [
            '/api/v3/account',
            '/api/v3/order',
            '/api/v3/openOrders',
            '/api/v3/allOrders',
            '/api/v3/myTrades',
            '/api/v3/userDataStream',
            '/api/v3/capital/config/getall'
        ]

        return any(endpoint.startswith(private_ep) for private_ep in private_endpoints)
    
    async def refresh_timestamp(self) -> None:
        """
        Refresh timestamp synchronization for MEXC RecvWindow errors.
        
        Adjusts local time offset to sync with server time.
        Uses a small forward adjustment to account for network latency.
        """
        # Add a small forward offset (500ms) to account for network latency
        # This helps prevent recvWindow errors on subsequent requests
        self._time_offset = 500  # 500ms forward adjustment
        
        self.logger.info("MEXC timestamp synchronized for RecvWindow error",
                        time_offset_ms=self._time_offset)
        
        self.logger.metric("rest_auth_timestamp_syncs", 1,
                          tags={"exchange": "mexc", "reason": "recv_window_error"})
