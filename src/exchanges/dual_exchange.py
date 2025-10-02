from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, get_logger
from .exchange_factory import get_composite_implementation

class DualExchange:
    def __init__(self, config: ExchangeConfig, logger: HFTLoggerInterface = None):
        """
        Initialize dual exchange with public and private composites.
        Args:
            config: Exchange configuration
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        self.logger = logger or get_logger(f'dual_exchange.{config.name.lower()}')
        self.private = get_composite_implementation(config, is_private=True)
        self.public = get_composite_implementation(config, is_private=False)