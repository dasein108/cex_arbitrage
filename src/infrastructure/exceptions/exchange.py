class ExchangeRestError(Exception):
    def __init__(self, code: int, message: str, api_code: int | None = None) -> None:
        self.api_code = api_code
        self.message = message
        self.status_code = code
    """Default exception."""


class ExchangeConnectionRestError(ExchangeRestError):
   pass

class OrderNotFoundError(ExchangeRestError):
    pass

class OrderCancelledOrFilled(ExchangeRestError):
    def __init__(self, code: int, message: str, api_code: int | None = None) -> None:
        super().__init__(code, message, api_code)

        # TODO: this prob is to broad
        self.is_filled = "filled" in message.lower()
        self.is_cancelled = "cancelled" in message.lower()


class TooManyRequestsError(ExchangeRestError):
    pass

class RateLimitErrorRest(ExchangeRestError):
    def __init__(self, code: int, message: str, api_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(code, message, api_code)
        self.retry_after = retry_after

    def __str__(self):
        return f"RateLimitError: {self.status_code} - {self.message} - {self.api_code} - {self.retry_after}"


class RecvWindowError(ExchangeRestError):
    """Exception for timestamp/recvWindow validation errors."""
    pass


