import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from infrastructure.networking.http import AuthStrategy, HTTPMethod, AuthenticationData
from config.structs import ExchangeConfig


class BaseExchangeAuthStrategy(AuthStrategy, ABC):
    """
    Base authentication strategy for exchanges with common HMAC signing patterns.
    
    Provides shared functionality for:
    - Timestamp synchronization
    - HMAC signature generation
    - Authentication header management
    - Private endpoint detection
    """

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize base exchange authentication strategy.
        
        Args:
            exchange_config: Exchange configuration containing credentials
            logger: Optional HFT logger injection
            **kwargs: Additional parameters for exchange-specific needs
        """
        if not exchange_config.credentials.has_private_api:
            raise ValueError(f"{self.exchange_name} credentials not configured in ExchangeConfig")
        
        self.api_key = exchange_config.credentials.api_key
        self.secret_key = exchange_config.credentials.secret_key.encode('utf-8')
        self.exchange_config = exchange_config
        
        # Timestamp synchronization for timestamp/recvWindow errors
        self._time_offset = 0.0  # Offset to add to local timestamp (in seconds)
        
        # Initialize logger if not provided
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = [self.exchange_name.lower(), 'rest', 'auth']
            logger = get_strategy_logger(f'rest.auth.{self.exchange_name.lower()}', tags)
        self.logger = logger

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        pass

    @abstractmethod
    def get_signature_algorithm(self) -> str:
        """Get the HMAC algorithm used by this exchange (e.g., 'sha256', 'sha512')."""
        pass

    @abstractmethod
    def get_auth_headers(self, signature: str, timestamp: str) -> Dict[str, str]:
        """Get exchange-specific authentication headers."""
        pass

    @abstractmethod
    def prepare_signature_string(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        json_data: Dict[str, Any],
        timestamp: str
    ) -> str:
        """Prepare the string to be signed for this exchange."""
        pass

    @abstractmethod
    def get_private_endpoints(self) -> List[str]:
        """Get list of private endpoint prefixes that require authentication."""
        pass

    def get_current_timestamp(self) -> str:
        """Get current timestamp with synchronization offset applied."""
        current_time = time.time() + self._time_offset
        return self._format_timestamp(current_time)

    def _format_timestamp(self, timestamp: float) -> str:
        """Format timestamp for this exchange. Override if needed."""
        return str(timestamp)

    def _parse_timestamp_to_int(self, timestamp_str: str) -> int:
        """
        Parse timestamp string to integer with error handling.
        
        Args:
            timestamp_str: Timestamp as string
            
        Returns:
            Timestamp as integer
            
        Raises:
            ValueError: If timestamp cannot be parsed
        """
        try:
            return int(float(timestamp_str))
        except (ValueError, TypeError) as e:
            # Fallback: try direct int conversion
            try:
                return int(timestamp_str) if isinstance(timestamp_str, str) else timestamp_str
            except (ValueError, TypeError):
                raise ValueError(f"Cannot parse timestamp '{timestamp_str}' to integer") from e

    def _get_hash_function(self):
        """Get the appropriate hash function based on the signature algorithm."""
        algorithm = self.get_signature_algorithm().lower()
        if algorithm == 'sha256':
            return hashlib.sha256
        elif algorithm == 'sha512':
            return hashlib.sha512
        else:
            raise ValueError(f"Unsupported signature algorithm: {algorithm}")

    async def sign_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        json_data: Dict[str, Any]
    ) -> AuthenticationData:
        """
        Generate exchange authentication data with HMAC signature.
        
        Always generates a fresh timestamp just before signing to prevent
        stale timestamp errors when there are network delays.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Request parameters
            json_data: JSON data
        
        Returns:
            Authentication data with signature
        """
        # ALWAYS generate fresh timestamp just before signing
        # This prevents stale timestamps when there are delays
        timestamp_str = self.get_current_timestamp()
        
        # Prepare signature string using exchange-specific logic
        signature_string = self.prepare_signature_string(
            method, endpoint, params, json_data, timestamp_str
        )
        
        # Generate HMAC signature
        hash_func = self._get_hash_function()
        signature = hmac.new(
            self.secret_key,
            signature_string.encode('utf-8'),
            hash_func
        ).hexdigest()
        
        # Get exchange-specific headers
        auth_headers = self.get_auth_headers(signature, timestamp_str)
        
        # Return authentication data - subclasses handle parameter placement
        # Pass timestamp_str so the same timestamp used in signature is included in params
        return self._prepare_auth_data(auth_headers, params, json_data, signature, timestamp_str)

    @abstractmethod
    def _prepare_auth_data(
        self,
        auth_headers: Dict[str, str],
        params: Dict[str, Any],
        json_data: Dict[str, Any],
        signature: str,
        timestamp_str: str
    ) -> AuthenticationData:
        """
        Prepare final authentication data with exchange-specific parameter placement.
        
        Args:
            auth_headers: Authentication headers
            params: Request parameters
            json_data: JSON data
            signature: Generated signature
            timestamp_str: The timestamp that was used in the signature
        """
        pass

    def requires_auth(self, endpoint: str) -> bool:
        """Check if endpoint requires authentication."""
        private_endpoints = self.get_private_endpoints()
        return any(endpoint.startswith(private_ep) for private_ep in private_endpoints)

    async def refresh_timestamp(self) -> None:
        """
        Refresh timestamp synchronization for timestamp/recvWindow errors.
        
        Adjusts local time offset to sync with server time.
        Uses a small forward adjustment to account for network latency.
        """
        # Add forward offset to account for network latency
        self._time_offset = self._get_sync_offset()
        
        self.logger.info(f"{self.exchange_name} timestamp synchronized",
                        time_offset_seconds=self._time_offset)
        
        self.logger.metric("rest_auth_timestamp_syncs", 1,
                          tags={"exchange": self.exchange_name.lower(), "reason": "timestamp_error"})

    @abstractmethod
    def _get_sync_offset(self) -> float:
        """Get the synchronization offset for this exchange."""
        pass