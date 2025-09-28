"""
Gate.io futures private composite exchange implementation.

This implementation follows the composite pattern for Gate.io futures
private operations with futures-specific position management, leverage
control, and futures trading functionality.
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
from exchanges.interfaces.composite.futures.base_private_futures_composite import CompositePrivateFuturesExchange
from exchanges.interfaces.rest.futures.rest_futures_private import PrivateFuturesRest
from exchanges.interfaces.ws.futures.ws_private_futures import PrivateFuturesWebsocket
from exchanges.structs.common import Symbol, Order, Position
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers


class GateioFuturesCompositePrivateExchange(CompositePrivateFuturesExchange):
    pass

