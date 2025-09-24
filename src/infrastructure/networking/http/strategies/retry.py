"""
Retry Strategy Interface

Strategy for request retry logic and error handling.
Determines retry behavior and backoff calculations.

HFT COMPLIANT: <10μs retry decision.
"""

from abc import ABC, abstractmethod
from typing import Dict


class RetryStrategy(ABC):
    """
    Strategy for request retry logic and error handling.
    
    Determines retry behavior and backoff calculations.
    HFT COMPLIANT: <10μs retry decision.
    """
    
    @abstractmethod
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """
        Determine if request should be retried.
        
        Args:
            attempt: Current attempt number (1-based)
            error: Exception that caused failure
            
        Returns:
            True if retry should be attempted
        """
        pass
    
    @abstractmethod
    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        """
        Calculate retry delay with exchange-specific backoff.
        
        Args:
            attempt: Current attempt number (1-based)
            error: Exception that caused failure
            
        Returns:
            Delay in seconds before retry
        """
        pass
    
    @abstractmethod
    def handle_rate_limit(self, response_headers: Dict[str, str]) -> float:
        """
        Extract rate limit information from response headers.
        
        Args:
            response_headers: HTTP response headers
            
        Returns:
            Suggested delay in seconds
        """
        pass