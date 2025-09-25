"""
Gate.io WebSocket Strategies

Direct strategy class exports without factory registration.
Simplified architecture with constructor-based initialization.
"""

# Public strategies
from exchanges.integrations.gateio.ws.strategies.spot.public import GateioPublicConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.spot.public.subscription import GateioPublicSubscriptionStrategy
from exchanges.integrations.gateio.ws.strategies.spot.public import GateioPublicMessageParser

# Private strategies
from exchanges.integrations.gateio.ws.strategies.spot.private import GateioPrivateConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.spot.private.subscription import GateioPrivateSubscriptionStrategy
from exchanges.integrations.gateio.ws.strategies.spot.private.message_parser import GateioPrivateMessageParser

# Futures strategies
from exchanges.integrations.gateio.ws.strategies.futures.public.connection import GateioPublicFuturesConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.public.subscription import GateioPublicFuturesSubscriptionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.public.message_parser import GateioPublicFuturesMessageParser

# Private futures strategies
from exchanges.integrations.gateio.ws.strategies.futures.private.connection import GateioPrivateFuturesConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.private import GateioPrivateFuturesSubscriptionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.private import GateioPrivateFuturesMessageParser

__all__ = [
    # Public strategies
    'GateioPublicConnectionStrategy',
    'GateioPublicSubscriptionStrategy', 
    'GateioPublicMessageParser',
    
    # Private strategies
    'GateioPrivateConnectionStrategy',
    'GateioPrivateSubscriptionStrategy',
    'GateioPrivateMessageParser',

    # Futures strategies
    'GateioPublicFuturesConnectionStrategy',
    'GateioPublicFuturesSubscriptionStrategy',
    'GateioPublicFuturesMessageParser',

    # Private futures strategies
    'GateioPrivateFuturesConnectionStrategy',
    'GateioPrivateFuturesSubscriptionStrategy',
    'GateioPrivateFuturesMessageParser'
]