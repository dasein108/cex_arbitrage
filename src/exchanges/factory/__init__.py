"""
Exchange Factory Module

Unified factory system for creating all exchange components.
Provides single entry point with clear component type selection.
"""

# UNIFIED EXCHANGE FACTORY - Single entry point for all exchange components
from .exchange_factory import (
    create_exchange_component,
    create_rest_client,
    create_websocket_client,
    create_composite_exchange,
    create_public_handlers,
    create_private_handlers,
    get_supported_exchanges,
    is_exchange_supported,
    get_supported_component_types,
    clear_cache,
    get_cache_stats,
    validate_component_request,
    get_component_decision_matrix,
)

from .symbol_mapper_factory import get_symbol_mapper

__all__ = [
    # MAIN FACTORY FUNCTION
    'create_exchange_component',     # Main factory with explicit component type selection
    
    # CONVENIENCE FUNCTIONS (backward compatible)
    'create_rest_client',            # REST client convenience function
    'create_websocket_client',       # WebSocket client convenience function  
    'create_composite_exchange',     # Composite exchange convenience function

    # HANDLER CREATION
    'create_public_handlers',        # Public WebSocket handlers
    'create_private_handlers',       # Private WebSocket handlers
    
    # UTILITY FUNCTIONS
    'get_supported_exchanges',       # List of supported exchanges
    'is_exchange_supported',         # Check exchange support
    'get_supported_component_types', # List of component types
    'validate_component_request',    # Validate request before creation
    'get_component_decision_matrix', # Decision matrix for component selection
    
    # CACHE MANAGEMENT
    'clear_cache',                   # Clear component cache
    'get_cache_stats',                # Get cache statistics,
    'get_symbol_mapper'               # Symbol mapper factory function
]