"""
Authentication Strategy Interface

Strategy for request authentication and signing.
Handles API key authentication and request signing.

HFT COMPLIANT: <200μs signature generation.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

from ..structs import HTTPMethod
from .structs import AuthenticationData


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
        json_data: Dict[str, Any],
        timestamp: int
    ) -> AuthenticationData:
        """
        Generate authentication data for request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Request parameters
            json_data: JSON data for POST/PUT requests
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
    
    async def refresh_timestamp(self) -> None:
        """
        Refresh timestamp synchronization for RecvWindow errors.
        
        Default implementation does nothing.
        Exchange-specific implementations can override for timestamp sync.
        """
        pass