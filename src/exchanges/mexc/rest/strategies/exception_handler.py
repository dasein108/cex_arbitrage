from core.exceptions.exchange import (
    BaseExchangeError, RateLimitErrorBase, TradingDisabled,
    InsufficientPosition, OversoldException, ExchangeOrderCancelledOrNotExist
)
import msgspec
from exchanges.mexc.structs.exchange import MexcErrorResponse
from core.transport.rest.strategies.exception_handler import ExceptionHandlerStrategy

ERROR_CODE_MAPPING = {
    -2011: ExchangeOrderCancelledOrNotExist,  # Order cancelled
    -2013: ExchangeOrderCancelledOrNotExist,  # Order not exist
    429: RateLimitErrorBase,  # Too many requests
    418: RateLimitErrorBase,  # I'm a teapot (rate limit)
    10007: TradingDisabled,  # Symbol not support API
    700003: BaseExchangeError,  # Timestamp outside recvWindow
    30016: TradingDisabled,  # Trading disabled
    10203: BaseExchangeError,  # Order processing error
    30004: InsufficientPosition,  # Insufficient balance
    30005: OversoldException,  # Oversold
    30002: OversoldException,  # Minimum transaction volume
}


class MexcExceptionHandlerStrategy(ExceptionHandlerStrategy):
    """MEXC-specific exception handling strategy."""
    
    def __init__(self):
        """
        Initialize MEXC exception handler strategy.
        
        No parameters needed - uses static error code mappings.
        """
        pass  # No initialization needed - static error mappings

    def handle_error(self, status_code: int, response_text: str) -> BaseExchangeError:
        """
        Handle MEXC-specific API errors and convert to unified exceptions.

        Args:
            status_code: HTTP status code from the response
            response_text: Raw response text from the API

        Returns:
            Unified exception with appropriate error details
        """
        try:
            # Try to parse MEXC error response
            error_data = msgspec.json.decode(response_text)
            mexc_error = msgspec.convert(error_data, MexcErrorResponse)

            # Map MEXC error codes to unified exceptions
            error_code = mexc_error.code
            error_msg = mexc_error.msg

            if error_code in ERROR_CODE_MAPPING:
                unified_error = ERROR_CODE_MAPPING[error_code]
                return unified_error(status_code, f"MEXC Error {error_code}: {error_msg}", mexc_error.code)
            else:
                return BaseExchangeError(status_code, f"MEXC Error {error_code}: {error_msg}")
        except Exception as e:
            # Fallback if error parsing fails
            return BaseExchangeError(status_code, f"MEXC API Error(Handler fallback): {response_text} reason: {e}")

    def should_handle_error(self, status_code: int, response_text: str) -> bool:
        """Always handle errors for MEXC (strategy will decide internally)."""
        return True  # MEXC handler can handle all error types
