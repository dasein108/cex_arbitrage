"""
Abstract interface for exchange factory implementations.

This interface enables dependency injection of exchange creation logic,
allowing different exchange factory implementations to be plugged in
based on configuration or runtime requirements.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from enum import Enum

from infrastructure.data_structures.common import Symbol, ExchangeName
from exchanges.interfaces.composite import CompositePrivateExchange


class InitializationStrategy(Enum):
    """Exchange initialization strategies."""
    FAIL_FAST = "fail_fast"          # Fail immediately on any error
    CONTINUE_ON_ERROR = "continue_on_error"  # Skip failed exchanges and continue
    RETRY_WITH_BACKOFF = "retry_with_backoff"  # Retry failed exchanges with exponential backoff


class ExchangeFactoryInterface(ABC):
    """
    Abstract interface for exchange factory implementations.
    
    Provides dependency injection capability for exchange creation logic,
    enabling different factory implementations to be used based on
    configuration, testing needs, or runtime requirements.
    """

    @abstractmethod
    async def create_exchanges(
        self,
        exchange_names: List[ExchangeName],
        strategy: InitializationStrategy = InitializationStrategy.FAIL_FAST,
        symbols: Optional[List[Symbol]] = None
    ) -> Dict[str, CompositePrivateExchange]:
        """
        Create and initialize exchange instances.
        
        Args:
            exchange_names: List of exchange names to create
            strategy: Initialization strategy for error handling
            symbols: Optional symbols to initialize exchanges with
            
        Returns:
            Dictionary mapping exchange names to initialized exchange instances
            
        Raises:
            ExchangeFactoryError: If exchange creation fails (depending on strategy)
        """
        pass

    @abstractmethod
    async def create_exchange(
        self,
        exchange_name: ExchangeName,
        symbols: Optional[List[Symbol]] = None
    ) -> CompositePrivateExchange:
        """
        Create a single exchange instance.
        
        Args:
            exchange_name: Name of exchange to create
            symbols: Optional symbols to initialize exchange with
            
        Returns:
            Initialized exchange instance
            
        Raises:
            ExchangeFactoryError: If exchange creation fails
        """
        pass

    @abstractmethod
    async def close_all(self) -> None:
        """
        Close all managed exchange instances.
        
        Should be called during shutdown to ensure proper cleanup
        of exchange connections and resources.
        """
        pass

    @abstractmethod
    def get_supported_exchanges(self) -> List[ExchangeName]:
        """
        Get list of supported exchange names.
        
        Returns:
            List of exchange names that this factory can create
        """
        pass

    @abstractmethod
    def is_exchange_supported(self, exchange_name: ExchangeName) -> bool:
        """
        Check if an exchange is supported by this factory.
        
        Args:
            exchange_name: Exchange name to check
            
        Returns:
            True if exchange is supported, False otherwise
        """
        pass

    @abstractmethod
    async def health_check(self, exchange_name: ExchangeName) -> bool:
        """
        Perform health check on an exchange.
        
        Args:
            exchange_name: Exchange to health check
            
        Returns:
            True if exchange is healthy, False otherwise
        """
        pass

    @property
    @abstractmethod
    def managed_exchanges(self) -> Dict[str, CompositePrivateExchange]:
        """
        Get currently managed exchange instances.
        
        Returns:
            Dictionary of currently managed exchanges
        """
        pass