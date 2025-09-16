"""Gate.io Integration Examples

This package contains comprehensive examples demonstrating Gate.io exchange integration:

Public API Examples (No credentials required):
- public_rest_demo.py: REST API market data retrieval
- public_websocket_demo.py: WebSocket real-time streaming
- exchange_public_example.py: High-level exchange cex

Private API Examples (Requires API credentials):
- private_rest_demo.py: REST API trading operations
- exchange_private_example.py: Full exchange trading cex

Usage:
    # Public examples (no credentials needed)
    python -m src.examples.gateio.public_rest_example
    python -m src.examples.gateio.public_websocket_example
    python -m src.examples.gateio.exchange_public_example
    
    # Private examples (requires API credentials in config.yaml)
    python -m src.examples.gateio.private_rest_example
    python -m src.examples.gateio.exchange_private_example
"""

__all__ = [
    'public_rest_demo.py',
    'public_websocket_demo.py',
    'exchange_public_example',
    'private_rest_demo.py',
    'exchange_private_example',
]