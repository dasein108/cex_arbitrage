

class ExchangeAPIError(Exception):
    def __init__(self, code: int, message: str, api_code: int | None = None) -> None:
        self.api_code = api_code
        self.message = message
        self.code = code
    """Default exception."""


class RateLimitError(ExchangeAPIError):
    def __init__(self, code: int, message: str, api_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(code, message, api_code)
        self.retry_after = retry_after

    def __str__(self):
        return f"RateLimitError: {self.code} - {self.message} - {self.api_code} - {self.retry_after}"



class TradingDisabled(ExchangeAPIError):
    pass

class InsufficientPosition(ExchangeAPIError):
    pass

class OversoldException(ExchangeAPIError):
    pass

class UnknownException(ExchangeAPIError):
    pass