from abc import ABC, abstractmethod
from typing import Dict

import msgspec
from infrastructure.exceptions.exchange import ExchangeRestError
from infrastructure.networking.http.strategies.exception_handler import ExceptionHandlerStrategy


class BaseExchangeExceptionHandler(ExceptionHandlerStrategy, ABC):
    """
    Base exception handler for exchanges with common error mapping patterns.
    
    Provides shared functionality for:
    - JSON error response parsing
    - Fallback error handling
    - Common error mapping patterns
    - Structured error data extraction
    """

    def __init__(self, logger=None, **kwargs):
        """
        Initialize base exchange exception handler.
        
        Args:
            logger: Optional HFT logger injection
            **kwargs: Additional parameters for exchange-specific needs
        """
        # Initialize logger if not provided
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = [self.exchange_name.lower(), 'rest', 'exception_handler']
            logger = get_strategy_logger(f'rest.exception_handler.{self.exchange_name.lower()}', tags)
        self.logger = logger

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        pass

    @abstractmethod
    def get_error_code_mapping(self) -> Dict[int, type]:
        """Get exchange-specific error code to exception mapping."""
        pass

    @abstractmethod
    def parse_error_response(self, response_text: str) -> tuple[int | None, str]:
        """
        Parse exchange-specific error response format.
        
        Args:
            response_text: Raw response text from API
            
        Returns:
            tuple: (error_code, error_message) or (None, fallback_message)
        """
        pass

    def handle_error(self, status_code: int, response_text: str) -> ExchangeRestError:
        """
        Handle exchange-specific API errors and convert to unified exceptions.
        
        Args:
            status_code: HTTP status code from the response
            response_text: Raw response text from the API
            
        Returns:
            Unified exception with appropriate error details
        """
        try:
            # Parse exchange-specific error response
            error_code, error_message = self.parse_error_response(response_text)
            
            if error_code is not None:
                # Try to map to unified exception
                error_mapping = self.get_error_code_mapping()
                if error_code in error_mapping:
                    unified_error = error_mapping[error_code]
                    return unified_error(status_code, f"{self.exchange_name} Error {error_code}: {error_message}")
                else:
                    # Unknown error code
                    return ExchangeRestError(status_code, f"{self.exchange_name} Error {error_code}: {error_message}")
            else:
                # No error code parsed, use message only
                return ExchangeRestError(status_code, f"{self.exchange_name} Error: {error_message}")
                
        except Exception as e:
            # Fallback if error parsing fails
            return ExchangeRestError(
                status_code, 
                f"{self.exchange_name} API Error(Handler fallback): {response_text} reason: {e}"
            )

    def should_handle_error(self, status_code: int, response_text: str) -> bool:
        """Always handle errors (strategy decides internally)."""
        return True

    def _try_parse_json_error(self, response_text: str) -> dict | None:
        """
        Attempt to parse JSON error response with fallback handling.
        
        Returns:
            dict: Parsed JSON data or None if parsing fails
        """
        try:
            return msgspec.json.decode(response_text)
        except Exception:
            return None

    def _extract_error_from_dict(self, error_data: dict) -> tuple[int | None, str]:
        """
        Extract error code and message from parsed error dict.
        Common patterns across exchanges.
        
        Args:
            error_data: Parsed JSON error response
            
        Returns:
            tuple: (error_code, error_message)
        """
        # Common error field patterns
        error_code = None
        error_message = "Unknown error"
        
        # Try common error code fields
        for code_field in ['code', 'error_code', 'errorCode']:
            if code_field in error_data:
                try:
                    error_code = int(error_data[code_field])
                    break
                except (ValueError, TypeError):
                    continue
        
        # Try common message fields
        for msg_field in ['message', 'msg', 'error', 'error_message', 'detail']:
            if msg_field in error_data:
                error_message = str(error_data[msg_field])
                break
        
        return error_code, error_message