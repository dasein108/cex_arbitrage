from typing import Optional


class ExchangeRestError(Exception):
    def __init__(self, code: int, message: str, api_code: int | None = None) -> None:
        self.api_code = api_code
        self.message = message
        self.status_code = code
    """Default exception."""


class ExchangeConnectionRestError(ExchangeRestError):
   pass

class ExchangeRestOrderCancelledOrNotExist(ExchangeRestError):
   pass

class RateLimitErrorRest(ExchangeRestError):
    def __init__(self, code: int, message: str, api_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(code, message, api_code)
        self.retry_after = retry_after

    def __str__(self):
        return f"RateLimitError: {self.status_code} - {self.message} - {self.api_code} - {self.retry_after}"



class TradingDisabled(ExchangeRestError):
    pass

class InsufficientPosition(ExchangeRestError):
    pass

class OversoldException(ExchangeRestError):
    pass

class UnknownException(ExchangeRestError):
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


class ConfigurationError(Exception):
    """Configuration-specific exception for setup errors."""

    def __init__(self, message: str, setting_name: Optional[str] = None):
        self.setting_name = setting_name
        super().__init__(message)
