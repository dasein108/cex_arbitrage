"""
Abstract interface for symbol mapper factory implementations.

This interface enables dependency injection of symbol mapping logic,
allowing different symbol mapper implementations to be plugged in
based on exchange requirements or testing needs.
"""

from abc import ABC, abstractmethod
from infrastructure.data_structures.common import ExchangeName
from exchanges.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface


class SymbolMapperFactoryInterface(ABC):
    """
    Abstract interface for symbol mapper factory implementations.
    
    Provides dependency injection capability for symbol mapping logic,
    enabling different mapper implementations to be used based on
    exchange-specific requirements or testing scenarios.
    """

    @abstractmethod
    def create_symbol_mapper(self, exchange_name: ExchangeName) -> SymbolMapperInterface:
        """
        Create a symbol mapper for the specified exchange.
        
        Args:
            exchange_name: Name of exchange to create mapper for
            
        Returns:
            Configured symbol mapper instance
            
        Raises:
            UnsupportedExchangeError: If exchange is not supported
        """
        pass

    @abstractmethod
    def get_supported_exchanges(self) -> list[ExchangeName]:
        """
        Get list of supported exchange names.
        
        Returns:
            List of exchange names that this factory can create mappers for
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