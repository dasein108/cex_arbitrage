from .message_parser import MessageParser
from .connection import ConnectionStrategy
from .subscription import SubscriptionStrategy


class WebSocketStrategySet:
    """
    Container for a complete set of WebSocket strategies.

    HFT COMPLIANT: Zero-allocation strategy access.
    """

    def __init__(
        self,
        # connection_strategy: ConnectionStrategy,
        subscription_strategy: SubscriptionStrategy,
        message_parser: MessageParser
    ):
        # self.connection_strategy = connection_strategy
        self.subscription_strategy = subscription_strategy
        self.message_parser = message_parser
        # HFT Optimization: Pre-validate strategy compatibility
        self._validate_strategies()

    def _validate_strategies(self) -> None:
        """Validate strategy compatibility at initialization."""
        if not all([
            # self.connection_strategy,
            self.subscription_strategy,
            self.message_parser
        ]):
            raise ValueError("All strategies must be provided")
