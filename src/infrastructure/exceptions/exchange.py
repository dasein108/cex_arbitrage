class ExchangeRestError(Exception):
    """Base exception for all exchange REST API errors."""
    def __init__(self, code: int, message: str, api_code: int | None = None) -> None:
        self.api_code = api_code
        self.message = message
        self.status_code = code
        super().__init__(f"HTTP {code}: {message}")


# Connection and Infrastructure Errors (Retryable)
class ExchangeConnectionRestError(ExchangeRestError):
    """Network connection errors that may be temporary."""
    pass


class ExchangeServerError(ExchangeRestError):
    """Server-side errors (5xx) that may be temporary."""
    pass


class ExchangeTimeoutError(ExchangeRestError):
    """Request timeout errors that may be retryable."""
    pass


# Rate Limiting Errors (Retryable with backoff)
class RateLimitErrorRest(ExchangeRestError):
    """Rate limit exceeded errors."""
    def __init__(self, code: int, message: str, api_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(code, message, api_code)
        self.retry_after = retry_after

    def __str__(self):
        return f"RateLimitError: {self.status_code} - {self.message} - {self.api_code} - {self.retry_after}"


class TooManyRequestsError(RateLimitErrorRest):
    """HTTP 429 Too Many Requests."""
    pass


# Authentication and Authorization Errors (Non-retryable)
class AuthenticationError(ExchangeRestError):
    """Authentication failed - API key, signature, or permission issues."""
    pass


class RecvWindowError(ExchangeRestError):
    """Timestamp/recvWindow validation errors - may be retryable once."""
    pass


class InvalidApiKeyError(AuthenticationError):
    """Invalid API key format or non-existent key."""
    pass


class SignatureError(AuthenticationError):
    """Invalid signature - usually configuration issue."""
    pass


class InsufficientPermissionsError(AuthenticationError):
    """API key lacks required permissions for endpoint."""
    pass


class IpNotWhitelistedError(AuthenticationError):
    """IP address not in whitelist."""
    pass


# Business Logic Errors (Non-retryable)
class InvalidParameterError(ExchangeRestError):
    """Invalid request parameters - client-side error."""
    pass


class OrderNotFoundError(ExchangeRestError):
    """Order not found for given ID."""
    pass


class OrderCancelledOrFilled(ExchangeRestError):
    """Order already cancelled or filled."""
    def __init__(self, code: int, message: str, api_code: int | None = None) -> None:
        super().__init__(code, message, api_code)
        self.is_filled = "filled" in message.lower()
        self.is_cancelled = "cancelled" in message.lower()


class InsufficientBalanceError(ExchangeRestError):
    """Insufficient balance for operation."""
    pass


class InvalidSymbolError(ExchangeRestError):
    """Invalid or non-existent trading symbol."""
    pass


class TradingDisabledError(ExchangeRestError):
    """Trading disabled for symbol or account."""
    pass


class OrderSizeError(ExchangeRestError):
    """Order size too small, too large, or invalid precision."""
    pass


class PositionLimitError(ExchangeRestError):
    """Position limit exceeded."""
    pass


class RiskControlError(ExchangeRestError):
    """Risk control system blocked operation."""
    pass


# Account and Transfer Errors (Mixed retryability)
class AccountError(ExchangeRestError):
    """Account-related errors."""
    pass


class TransferError(ExchangeRestError):
    """Transfer operation errors."""
    pass


class WithdrawalError(ExchangeRestError):
    """Withdrawal operation errors."""
    pass


# System Maintenance Errors (Retryable)
class MaintenanceError(ExchangeRestError):
    """System under maintenance."""
    pass


class ServiceUnavailableError(ExchangeRestError):
    """Service temporarily unavailable."""
    pass


