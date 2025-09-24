"""Gate.io WebSocket Implementations"""

from .gateio_ws_public import GateioPublicSpotWebsocket
from .gateio_ws_private import GateioPrivateSpotWebsocket
from .gateio_ws_public_futures import GateioPublicFuturesWebsocket
from .gateio_ws_private_futures import GateioPrivateFuturesWebsocket
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
# from . import registration

__all__ = ['GateioPublicSpotWebsocket', 'GateioPrivateSpotWebsocket', 'GateioPublicFuturesWebsocket',
           'GateioPrivateFuturesWebsocket']