from abc import ABC
from structs.exchange import ExchangeName


class BaseExchangeInterface(ABC):
    """Abstract interface for private exchange operations (trading, account management)"""

    def __init__(self, exchange: ExchangeName, base_url: str):
        self.exchange = exchange
        self.base_url = base_url

    async def close(self):
        """Clean up resources and close connections."""
        if hasattr(self, 'client'):
            await self.client.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()