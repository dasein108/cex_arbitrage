"""MEXC private exchange implementation using composite pattern."""

from typing import Optional, List
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
from exchanges.structs.common import Symbol, Order, WithdrawalRequest, WithdrawalResponse
from exchanges.structs.types import AssetName
from exchanges.structs import Side, OrderType
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig


class MexcCompositePrivateSpotExchange(CompositePrivateSpotExchange):
    pass