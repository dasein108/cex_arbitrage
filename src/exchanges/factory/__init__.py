"""
Exchange Factory Components

Direct instantiation factories for REST and WebSocket clients.
Eliminates strategy pattern overhead through constructor injection.
"""

from .rest_factory import create_rest_client, create_rate_limiter

__all__ = [
    'create_rest_client',
    'create_rate_limiter'
]