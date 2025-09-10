import asyncio


class ExchangeAPIError(Exception):
    def __init__(self, code: int, message: str, api_code: int | None = None) -> None:
        self.mexc_code = api_code
        self.message = message
        self.code = code

    """Default exception."""


class RateLimitError(ExchangeAPIError):
    def __init__(self, code: int, message: str, api_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(code, message, api_code)
        self.retry_after = retry_after

    def __str__(self):
        return f"RateLimitError: {self.code} - {self.message} - {self.mexc_code} - {self.retry_after}"


class BaseAPIError(Exception):
    def __init__(self, message: str, base_exception: Exception | None = None) -> None:
        self.message = message
        self.base_exception = base_exception

    """Default exception."""


class TradingDisabled(BaseAPIError):
    pass


class SkipStepException(BaseAPIError):
    pass


class InsufficientPosition(BaseAPIError):
    pass


class OversoldException(BaseAPIError):
    pass


class UnknownException(BaseAPIError):
    pass


class TooManyRequestsException(BaseAPIError):
    pass


def apply_exception_handler(cls, exception_handler):
    """Apply a given exception handler to all coroutine methods in a class."""
    for attr_name in dir(cls):
        attr = getattr(cls, attr_name)
        if asyncio.iscoroutinefunction(attr):  # Check if it's an async function
            setattr(cls, attr_name, exception_handler(attr))
