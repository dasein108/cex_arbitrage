from abc import ABC, abstractmethod

class ExchangeServerInterface(ABC):
    @abstractmethod
    async def get_server_time(self) -> int:
        """Get server timestamp"""
        pass

    @abstractmethod
    async def ping(self) -> bool:
        """Test connectivity to the exchange"""
        pass