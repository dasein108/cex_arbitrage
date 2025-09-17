from cex.mexc.ws import MexcWebsocketPrivate, MexcWebsocketPublic
from cex.gateio.ws import GateioWebsocketPrivate, GateioWebsocketPublic
from cex.mexc.rest import MexcPrivateSpotRest

def get_exchange_websocket_classes(exchange_name: str, is_private: bool=False):
    """Get the appropriate WebSocket and REST classes for the exchange."""
    exchange_classes = {
        'MEXC': (MexcWebsocketPrivate, MexcWebsocketPublic, MexcPrivateSpotRest),
        'GATEIO': (GateioWebsocketPrivate, GateioWebsocketPublic, None),
    }

    exchange_upper = exchange_name.upper()
    if exchange_upper not in exchange_classes:
        available = list(exchange_classes.keys())
        raise ValueError(f"Exchange {exchange_name} not supported. Available: {available}")

    ws_private, ws_public, rest_private = exchange_classes[exchange_upper]
    if is_private:
        return ws_private, rest_private
    else:
        return ws_public, None
