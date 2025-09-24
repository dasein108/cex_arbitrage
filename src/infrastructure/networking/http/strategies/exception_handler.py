"""
Exception Handler Strategy Interface

Strategy for handling exchange-specific API errors.
Converts exchange-specific error responses to unified exception types.

HFT COMPLIANT: <10μs error processing overhead.
"""

from abc import ABC, abstractmethod

from ....exceptions.exchange import BaseExchangeError


class ExceptionHandlerStrategy(ABC):
    """
    Strategy for handling exchange-specific API errors.
    
    Converts exchange-specific error responses to unified exception types.
    HFT COMPLIANT: <10μs error processing overhead.
    """
    
    @abstractmethod
    def handle_error(self, status_code: int, response_text: str) -> BaseExchangeError:
        """
        Handle exchange-specific API error.
        
        Args:
            status_code: HTTP status code
            response_text: Raw response text from the API
            
        Returns:
            Unified BaseExchangeError or subclass
        """
        pass
    
    @abstractmethod
    def should_handle_error(self, status_code: int, response_text: str) -> bool:
        """
        Check if this strategy should handle the error.
        
        Args:
            status_code: HTTP status code
            response_text: Raw response text from the API
            
        Returns:
            True if this strategy can handle the error
        """
        pass