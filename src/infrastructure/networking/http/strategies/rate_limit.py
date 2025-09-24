"""
Rate Limit Strategy Interface

Strategy for request rate limiting and traffic coordination.
Manages request permits and endpoint-specific rate limits.

HFT COMPLIANT: <50μs permit acquisition.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

from .structs import RateLimitContext


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