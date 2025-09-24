"""
Gate.io Futures WebSocket Strategies

Strategy implementations for Gate.io futures WebSocket connections.
Extends spot strategies with futures-specific endpoints and message handling.
"""

from exchanges.integrations.gateio.ws.strategies.futures.public.connection import GateioPublicFuturesConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.public.message_parser import GateioPublicFuturesMessageParser
from exchanges.integrations.gateio.ws.strategies.futures.public.subscription import GateioPublicFuturesSubscriptionStrategy

__all__ = [
    "GateioPublicFuturesConnectionStrategy",
    "GateioPublicFuturesMessageParser",
    "GateioPublicFuturesSubscriptionStrategy"
]