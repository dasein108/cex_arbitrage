"""
Exchange interface protocols.

This module contains reusable protocols that define contracts for exchange
components, ensuring type safety and clear dependency requirements.
"""

from .private_dependencies import (
    PrivateExchangeDependenciesProtocol,
    PrivateSpotDependencies,
    PrivateFuturesDependencies
)

__all__ = [
    'PrivateExchangeDependenciesProtocol',
    'PrivateSpotDependencies', 
    'PrivateFuturesDependencies'
]