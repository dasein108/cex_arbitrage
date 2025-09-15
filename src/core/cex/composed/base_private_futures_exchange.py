from abc import abstractmethod
from typing import Dict
from structs.exchange import (Symbol, Position)

from core.cex.composed.base_private_exchange import BasePrivateExchangeInterface


class BasePrivateFuturesExchangeInterface(BasePrivateExchangeInterface):

    @abstractmethod
    async def positions(self) -> Dict[Symbol, Position]:
        """Get current open positions (for futures)"""
        return {}


