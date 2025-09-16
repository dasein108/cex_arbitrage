from abc import abstractmethod, ABC
from typing import Dict
from structs.exchange import (Symbol, Position)

from core.cex.base.base_public_exchange import BasePublicExchangeInterface


class BasePublicFuturesExchangeInterface(BasePublicExchangeInterface, ABC):
    # TODO: add funding endpoints, adjust ws endpoints
    pass


