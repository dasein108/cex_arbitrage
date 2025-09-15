from abc import abstractmethod, ABC
from typing import Dict
from structs.exchange import (Symbol, Position)

from core.cex.composed.base_public_exchange import BasePublicExchangeInterface


class BasePublicFuturesExchangeInterface(BasePublicExchangeInterface, ABC):
    pass


