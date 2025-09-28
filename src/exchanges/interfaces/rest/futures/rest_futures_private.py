"""Private futures REST interface."""

from abc import ABC, abstractmethod
from typing import List, Optional
from exchanges.structs.common import Symbol, Position
from exchanges.interfaces.rest.interfaces import PrivateTradingInterface, PrivateFuturesInterface


class PrivateFuturesRest(PrivateTradingInterface, PrivateFuturesInterface, ABC):
    """Abstract interface for private futures REST operations."""
    pass