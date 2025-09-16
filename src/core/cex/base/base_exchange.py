from abc import ABC, abstractmethod

from structs.exchange import ExchangeName
from core.config.structs import ExchangeConfig


class BaseExchangeInterface(ABC):
    exchange_name: ExchangeName = "abstract"

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def initialize(self, *args, **kwargs) -> None:
        """Initialize exchange"""

        if self._initialized:
            self.logger.warning("Exchange already initialized")
            return
        pass

    def __init__(self, config: ExchangeConfig):
        self._config = config
        self._initialized = False
        self.logger = config.get_logger(self.exchange_name)
