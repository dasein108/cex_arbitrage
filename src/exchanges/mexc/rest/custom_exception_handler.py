from core.exceptions.exchange import (
    BaseExchangeError, RateLimitErrorBase, TradingDisabled,
    InsufficientPosition, OversoldException, ExchangeOrderCancelledOrNotExist
)
import msgspec
from exchanges.mexc.common.structs import MexcErrorResponse


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

def handle_custom_exception(status: int, response_text: str) -> BaseExchangeError:
    """
    Handle MEXC-specific API errors and convert to unified exceptions.

    Args:
        status: HTTP status code from the response
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
            return unified_error(status, f"MEXC Error {error_code}: {error_msg}", mexc_error.code)
        else:
            return BaseExchangeError(status, f"MEXC Error {error_code}: {error_msg}")
    except Exception as e:
        # Fallback if error parsing fails
        return BaseExchangeError(status, f"MEXC API Error(Handler fallback): {response_text} reason: {e}")




