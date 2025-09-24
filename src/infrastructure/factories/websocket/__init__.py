"""
WebSocket Exchange Factory Module

DEPRECATED: WebSocket factories have been consolidated into infrastructure.transport_factory.
Use infrastructure.transport_factory.create_websocket_client() instead.

Example migration:
    OLD:
        from infrastructure.factories.websocket import PublicWebSocketExchangeFactory
        client = PublicWebSocketExchangeFactory.inject(exchange, config=config, **handlers)
    
    NEW:
        from infrastructure.transport_factory import create_websocket_client
        client = create_websocket_client(exchange, config=config, is_private=False, **handlers)
"""

# WebSocket factories have been replaced by the unified transport factory
# Import from infrastructure.transport_factory instead

__all__ = []