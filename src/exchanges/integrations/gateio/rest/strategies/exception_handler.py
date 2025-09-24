from infrastructure.exceptions.exchange import (
    BaseExchangeError, RateLimitErrorBase, TradingDisabled,
    InsufficientPosition, OversoldException, ExchangeOrderCancelledOrNotExist,
)
import msgspec
from infrastructure.networking.http.strategies.exception_handler import ExceptionHandlerStrategy

# Gate.io specific error code mappings based on their API documentation
ERROR_CODE_MAPPING = {
    # Rate limiting errors
    429: RateLimitErrorBase,  # Too Many Requests
    
    # Trading errors
    1: BaseExchangeError,  # Invalid request
    2: BaseExchangeError,  # Service temporarily unavailable
    3: BaseExchangeError,  # Invalid signature
    4: BaseExchangeError,  # Invalid key
    5: BaseExchangeError,  # Invalid timestamp
    6: BaseExchangeError,  # Invalid nonce
    
    # Order errors
    1001: ExchangeOrderCancelledOrNotExist,  # Order not found
    1002: BaseExchangeError,  # Invalid order id
    1003: BaseExchangeError,  # Invalid order status
    1004: BaseExchangeError,  # Order already cancelled
    1005: BaseExchangeError,  # Order already filled
    
    # Balance/Trading errors
    2001: InsufficientPosition,  # Insufficient balance
    2002: TradingDisabled,  # Trading disabled for this pair
    2003: BaseExchangeError,  # Invalid amount
    2004: BaseExchangeError,  # Invalid price
    2005: OversoldException,  # Amount too small
    2006: OversoldException,  # Price too low
    2007: OversoldException,  # Price too high
    
    # Account errors
    3001: BaseExchangeError,  # Account suspended
    3002: BaseExchangeError,  # Account not verified
    3003: BaseExchangeError,  # Account locked
    
    # System errors
    4001: BaseExchangeError,  # System maintenance
    4002: BaseExchangeError,  # System overload
}


class GateioExceptionHandlerStrategy(ExceptionHandlerStrategy):
    """Gate.io-specific exception handling strategy."""
    
    def __init__(self):
        """
        Initialize Gate.io exception handler strategy.
        
        No parameters needed - uses static error code mappings.
        """
        pass  # No initialization needed - static error mappings

    def handle_error(self, status_code: int, response_text: str) -> BaseExchangeError:
        """
        Handle Gate.io-specific API errors and convert to unified exceptions.

        Args:
            status_code: HTTP status code from the response
            response_text: Raw response text from the API

        Returns:
            Unified exception with appropriate error details
        """
        try:
            # Try to parse Gate.io error response
            # Gate.io error format: {"label": "ERROR_LABEL", "message": "Error description"}
            error_data = msgspec.json.decode(response_text)
            
            # Gate.io returns different error formats
            if isinstance(error_data, dict):
                if "label" in error_data and "message" in error_data:
                    # Standard Gate.io error format
                    error_label = error_data.get("label", "UNKNOWN_ERROR")
                    error_message = error_data.get("message", "Unknown error")
                    
                    # Try to map based on HTTP status code first
                    if status_code in ERROR_CODE_MAPPING:
                        unified_error = ERROR_CODE_MAPPING[status_code]
                        return unified_error(status_code, f"Gate.io Error {error_label}: {error_message}")
                    
                    # Check for specific error labels
                    if "INVALID_KEY" in error_label:
                        return BaseExchangeError(status_code, f"Gate.io Authentication Error: {error_message}")
                    elif "INSUFFICIENT_BALANCE" in error_label:
                        return InsufficientPosition(status_code, f"Gate.io Balance Error: {error_message}")
                    elif "ORDER_NOT_FOUND" in error_label:
                        return ExchangeOrderCancelledOrNotExist(status_code, f"Gate.io Order Error: {error_message}")
                    elif "RATE_LIMIT" in error_label or "TOO_MANY_REQUESTS" in error_label:
                        return RateLimitErrorBase(status_code, f"Gate.io Rate Limit: {error_message}")
                    elif "TRADING_DISABLED" in error_label or "MARKET_CLOSED" in error_label:
                        return TradingDisabled(status_code, f"Gate.io Trading Error: {error_message}")
                    else:
                        return BaseExchangeError(status_code, f"Gate.io Error {error_label}: {error_message}")
                        
                elif "detail" in error_data:
                    # Alternative Gate.io error format
                    error_detail = error_data.get("detail", "Unknown error")
                    return BaseExchangeError(status_code, f"Gate.io Error: {error_detail}")
                    
                elif "error" in error_data:
                    # Another alternative format
                    error_msg = error_data.get("error", "Unknown error")
                    return BaseExchangeError(status_code, f"Gate.io Error: {error_msg}")
                else:
                    # Unstructured error response
                    return BaseExchangeError(status_code, f"Gate.io Error: {str(error_data)}")
            else:
                # Non-dict response
                return BaseExchangeError(status_code, f"Gate.io Error: {response_text}")
                
        except Exception as e:
            # Fallback if error parsing fails
            return BaseExchangeError(status_code, f"Gate.io API Error(Handler fallback): {response_text} reason: {e}")

    def should_handle_error(self, status_code: int, response_text: str) -> bool:
        """Always handle errors for Gate.io (strategy will decide internally)."""
        return True  # Gate.io handler can handle all error types