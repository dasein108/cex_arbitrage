"""Gate.io WebSocket Implementations"""

from .gateio_ws_public import GateioWebsocketPublic
from .gateio_ws_private import GateioWebsocketPrivate
from .gateio_ws_public_futures import GateioWebsocketPublicFutures
# from .strategies import (
#     GateioPublicConnectionStrategy,
#     GateioPublicSubscriptionStrategy,
#     GateioPublicMessageParser,
#     GateioPrivateConnectionStrategy,
#     GateioPrivateSubscriptionStrategy,
#     GateioPrivateMessageParser
#
# )

# Import registration to trigger auto-registration with factories
from . import registration

__all__ = ['GateioWebsocketPublic', 'GateioWebsocketPrivate', 'GateioWebsocketPublicFutures']