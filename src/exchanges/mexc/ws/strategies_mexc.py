"""MEXC WebSocket Strategy Implementations

HFT-compliant strategies for MEXC WebSocket connections.
Extracts connection, subscription, and parsing logic from legacy implementation.

HFT COMPLIANCE: Sub-millisecond strategy execution, zero-copy patterns.
"""

from core.cex.websocket.strategies import (
    WebSocketStrategyFactory
)
from exchanges.mexc.ws.private.connection_strategy import MexcPrivateConnectionStrategy, MexcPrivateSubscriptionStrategy

from exchanges.mexc.ws.private.parser import MexcPrivateMessageParser
from exchanges.mexc.ws.public.connection_strategy import MexcPublicConnectionStrategy, MexcPublicSubscriptionStrategy

from exchanges.mexc.ws.public.parser import MexcPublicMessageParser

# Consolidated protobuf imports for MEXC (used by both public and private)

# === MEXC Private Strategies ===


# Register strategies with factory
WebSocketStrategyFactory.register_strategies(
    'mexc', False,
    MexcPublicConnectionStrategy,
    MexcPublicSubscriptionStrategy,
    MexcPublicMessageParser
)

WebSocketStrategyFactory.register_strategies(
    'mexc', True,
    MexcPrivateConnectionStrategy,
    MexcPrivateSubscriptionStrategy,
    MexcPrivateMessageParser
)