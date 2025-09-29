import hashlib
from typing import Dict, Any, List
from urllib.parse import urlencode

from exchanges.interfaces.rest.strategies import BaseExchangeAuthStrategy
from infrastructure.networking.http import HTTPMethod, AuthenticationData
from config.structs import ExchangeConfig
from infrastructure.data_structures.connection import RestConnectionSettings

# HFT Logger Integration
from infrastructure.logging import LoggingTimer


class MexcAuthStrategy(BaseExchangeAuthStrategy):
    """MEXC-specific authentication based on ExchangeConfig credentials."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None):
        """
        Initialize MEXC authentication strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing credentials
            logger: Optional HFT logger injection
        """
        super().__init__(exchange_config, logger)
        
        # Log strategy initialization (move to DEBUG per logging spec)
        self.logger.debug("MEXC auth strategy initialized",
                         api_key_configured=bool(self.api_key),
                         recv_window=5000)
        
        self.logger.metric("rest_auth_strategies_created", 1,
                          tags={"exchange": "mexc", "type": "private"})

    @property
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        return "MEXC"

    def get_signature_algorithm(self) -> str:
        """MEXC uses SHA256 for HMAC signatures."""
        return "sha256"

    def get_auth_headers(self, signature: str, timestamp: str) -> Dict[str, str]:
        """Get MEXC-specific authentication headers."""
        return {
            'X-MEXC-APIKEY': self.api_key,
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
        """Prepare MEXC signature string format."""
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
        
        # Use the timestamp provided by the base class
        try:
            # Convert timestamp string to int and add offset
            timestamp_int = int(float(timestamp)) + int(self._time_offset)
        except (ValueError, TypeError):
            # Fallback to original timestamp
            timestamp_int = int(timestamp) if isinstance(timestamp, str) else timestamp
            
        auth_params['timestamp'] = timestamp_int
        auth_params['recvWindow'] = rest_settings.recv_window

        # Create query string for signature (sorted parameters) 
        return urlencode(auth_params)

    def _prepare_auth_data(
        self,
        auth_headers: Dict[str, str],
        params: Dict[str, Any],
        json_data: Dict[str, Any],
        signature: str
    ) -> AuthenticationData:
        """Prepare MEXC authentication data with signature in query params."""
        # MEXC puts everything in query params, including the signature
        auth_params = {}
        
        # Add query parameters if any
        if params:
            auth_params.update(params)
        
        # Add JSON data parameters if any (MEXC requirement)
        if json_data:
            auth_params.update(json_data)
        
        # Add required MEXC auth parameters and signature
        rest_settings = RestConnectionSettings(
            recv_window=5000,  # MEXC default
            timeout=30,
            max_retries=3
        )
        
        timestamp_str = self.get_current_timestamp()
        try:
            timestamp_int = int(float(timestamp_str)) + int(self._time_offset)
        except (ValueError, TypeError):
            timestamp_int = int(timestamp_str) if isinstance(timestamp_str, str) else timestamp_str
            
        auth_params['timestamp'] = timestamp_int
        auth_params['recvWindow'] = rest_settings.recv_window
        auth_params['signature'] = signature

        return AuthenticationData(
            headers=auth_headers,
            params=auth_params,
            data=None  # MEXC uses query parameters, not request body
        )

    async def sign_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        json_data: Dict[str, Any],
        timestamp: int
    ) -> AuthenticationData:
        """Generate MEXC authentication data with proper signature handling and performance tracking."""
        try:
            with LoggingTimer(self.logger, "mexc_auth_signature_generation") as timer:
                # Use the base class implementation with performance tracking
                auth_data = await super().sign_request(method, endpoint, params, json_data, timestamp)
            
            # Track signature generation metrics
            self.logger.metric("rest_auth_signatures_generated", 1,
                              tags={"exchange": "mexc", "endpoint": endpoint, "method": method.value})
            
            self.logger.metric("rest_auth_signature_time_us", timer.elapsed_ms * 1000,
                              tags={"exchange": "mexc", "endpoint": endpoint})
            
            self.logger.debug("MEXC authentication signature generated",
                            endpoint=endpoint,
                            method=method.value,
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

    def get_private_endpoints(self) -> List[str]:
        """Get list of private endpoint prefixes that require authentication."""
        return [
            '/api/v3/account',
            '/api/v3/order',
            '/api/v3/openOrders',
            '/api/v3/allOrders',
            '/api/v3/myTrades',
            '/api/v3/userDataStream',
            '/api/v3/capital/config/getall'
        ]
    
    def _get_sync_offset(self) -> float:
        """Get MEXC synchronization offset."""
        return 0.5  # 500ms forward adjustment for MEXC

    def _format_timestamp(self, timestamp: float) -> str:
        """Format timestamp as integer milliseconds for MEXC."""
        return str(int(timestamp * 1000))  # MEXC expects milliseconds
