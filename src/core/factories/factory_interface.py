"""
Factory Interface for Exchange Components

Common interface that all exchange factories implement, providing a unified API
for registration, injection, and management of exchange-specific components.

Supports both simple factories (single component types) and composite factories
(strategy sets requiring assembly from multiple components).
"""

from abc import ABC, abstractmethod
from typing import TypeVar, List, Any, Union

from core.structs.common import ExchangeEnum

T = TypeVar('T')


class ExchangeFactoryInterface(ABC):
    """
    Common interface for all exchange factories.
    
    Provides standardized API for component registration, creation, and management.
    Supports both simple factories (symbol mappers) and composite factories (strategy sets).
    
    Type Safety: Each concrete factory specifies its product type T
    """
    
    @classmethod
    @abstractmethod
    def register(cls, exchange: Union[str, ExchangeEnum], implementation: Any, **kwargs) -> None:
        """
        Register implementation for an exchange.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Implementations should convert strings to ExchangeEnum immediately at entry point.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            implementation: Implementation class or configuration dict
            **kwargs: Additional registration parameters
        """
        pass
    
    @classmethod
    @abstractmethod
    def inject(cls, exchange: Union[str, ExchangeEnum], **kwargs) -> Any:
        """
        Create or retrieve component instance for an exchange.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Implementations should convert strings to ExchangeEnum immediately at entry point.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            **kwargs: Creation parameters (config, dependencies, etc.)
            
        Returns:
            Configured component instance
        """
        pass
    
    @classmethod
    @abstractmethod
    def get_registered_exchanges(cls) -> List[str]:
        """
        Get list of registered exchange identifiers.
        
        Returns:
            List of exchange names that have implementations registered
        """
        pass
    
    @classmethod
    @abstractmethod
    def is_registered(cls, exchange: Union[str, ExchangeEnum]) -> bool:
        """
        Check if exchange has registered implementation.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Implementations should convert strings to ExchangeEnum immediately at entry point.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            
        Returns:
            True if implementation exists
        """
        pass