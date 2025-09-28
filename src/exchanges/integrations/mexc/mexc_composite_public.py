"""MEXC public exchange implementation using composite pattern."""

from typing import Optional
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicSpotExchange
from exchanges.interfaces.rest.spot.rest_spot_public import PublicSpotRest
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig


class MexcCompositePublicSpotExchange(CompositePublicSpotExchange):
    pass