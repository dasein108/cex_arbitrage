"""
Private exchange dependencies protocol.

This module defines reusable protocols that specify the required dependencies
for private exchange operations, ensuring type safety and clear contracts.
"""

from typing import Protocol, Optional, TypeVar, Generic, TYPE_CHECKING
from infrastructure.logging import HFTLoggerInterface

if TYPE_CHECKING:
    from exchanges.interfaces.rest.interfaces.trading_interface import PrivateTradingInterface
    from exchanges.interfaces import PrivateSpotRest, PrivateFuturesRest

# Generic type variable for REST client types
RestClientT = TypeVar('RestClientT', bound='PrivateTradingInterface')


class PrivateExchangeDependenciesProtocol(Protocol, Generic[RestClientT]):
    """
    Protocol defining required dependencies for private exchange operations.
    
    This protocol ensures that any class implementing private exchange functionality
    has the necessary dependencies for operation:
    - A private REST client for API communication
    - An HFT-compliant logger for performance monitoring
    
    Type Parameters:
        RestClientT: The specific REST client type (spot, futures, etc.)
    
    Usage:
        class MyExchangeMixin(PrivateExchangeDependenciesProtocol[PrivateSpotRest]):
            # Guaranteed to have _private_rest and logger attributes
            pass
    """
    
    # Private REST client for authenticated API operations
    _private_rest: Optional[RestClientT]
    
    # HFT-compliant logger for performance tracking and monitoring
    logger: HFTLoggerInterface


# Convenience type aliases for common use cases
PrivateSpotDependencies = PrivateExchangeDependenciesProtocol['PrivateSpotRest']
"""Type alias for spot exchange dependencies."""

PrivateFuturesDependencies = PrivateExchangeDependenciesProtocol['PrivateFuturesRest']
"""Type alias for futures exchange dependencies."""


class PrivateExchangeValidationMixin:
    """
    Mixin providing runtime validation for private exchange dependencies.
    
    This mixin can be used in conjunction with the protocol to provide
    runtime validation in addition to compile-time type checking.
    """
    
    def _validate_private_dependencies(self) -> None:
        """
        Validate that required private exchange dependencies are available.
        
        Raises:
            TypeError: If required dependencies are missing
        """
        if not hasattr(self, '_private_rest'):
            raise TypeError(f"{self.__class__.__name__} requires _private_rest attribute")
        
        if not hasattr(self, 'logger'):
            raise TypeError(f"{self.__class__.__name__} requires logger attribute")
        
        # Type check for logger
        if not isinstance(getattr(self, 'logger'), HFTLoggerInterface):
            raise TypeError(f"{self.__class__.__name__} requires HFTLoggerInterface logger")


def validate_private_dependencies(instance) -> None:
    """
    Standalone function to validate private exchange dependencies.
    
    Args:
        instance: The object to validate
        
    Raises:
        TypeError: If required dependencies are missing
    """
    if not hasattr(instance, '_private_rest'):
        raise TypeError(f"{instance.__class__.__name__} requires _private_rest attribute")
    
    if not hasattr(instance, 'logger'):
        raise TypeError(f"{instance.__class__.__name__} requires logger attribute")
    
    # Type check for logger
    if not isinstance(getattr(instance, 'logger'), HFTLoggerInterface):
        raise TypeError(f"{instance.__class__.__name__} requires HFTLoggerInterface logger")