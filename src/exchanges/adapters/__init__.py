"""
Exchange Adapters Module

External adapters for integrating with exchange events without tight coupling.
Implements the external adapter pattern for event handlers.
"""

from .binded_event_handlers_adapter import BindedEventHandlersAdapter

__all__ = [
    'BindedEventHandlersAdapter'
]