

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

class ArbitrageEngineError(Exception):
    pass

class ExchangeError(Exception):
    pass

# Arbitrage-specific exceptions
class ArbitrageDetectionError(ArbitrageEngineError):
    """Error during arbitrage opportunity detection."""
    pass

class BalanceManagementError(ArbitrageEngineError):
    """Error in balance management operations."""
    pass

class PositionManagementError(ArbitrageEngineError):
    """Error in position management operations."""
    pass

class OrderExecutionError(ArbitrageEngineError):
    """Error during order execution."""
    pass

class RecoveryError(ArbitrageEngineError):
    """Error during recovery operations."""
    pass

class RiskManagementError(ArbitrageEngineError):
    """Error in risk management operations."""
    pass

class StateTransitionError(ArbitrageEngineError):
    """Error during state transitions."""
    pass