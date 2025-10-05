class ArbitrageEngineError(Exception):
    pass


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
