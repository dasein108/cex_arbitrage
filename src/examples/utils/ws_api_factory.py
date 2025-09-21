from exchanges.mexc.ws import MexcWebsocketPrivate, MexcWebsocketPublic
from exchanges.gateio.ws import GateioWebsocketPrivate, GateioWebsocketPublic
from exchanges.gateio.ws.gateio_ws_public_futures import GateioWebsocketPublicFutures
from exchanges.mexc.rest import MexcPrivateSpotRest

def get_exchange_websocket_classes(exchange_name: str, is_private: bool=False, is_futures: bool=False):
    """Get the appropriate WebSocket and REST classes for the exchange."""
    exchange_classes = {
        'MEXC': (MexcWebsocketPrivate, MexcWebsocketPublic, MexcPrivateSpotRest),
        'GATEIO': (GateioWebsocketPrivate, GateioWebsocketPublic, None),
        'GATEIO_FUTURES': (None, GateioWebsocketPublicFutures, None),  # Futures support
    }

    exchange_upper = exchange_name.upper()
    
    # Handle futures request
    if is_futures and exchange_upper == 'GATEIO':
        exchange_upper = 'GATEIO_FUTURES'
    
    if exchange_upper not in exchange_classes:
        available = list(exchange_classes.keys())
        raise ValueError(f"Exchange {exchange_name} not supported. Available: {available}")

    ws_private, ws_public, rest_private = exchange_classes[exchange_upper]
    
    if is_private:
        if ws_private is None:
            raise ValueError(f"Private WebSocket not supported for {exchange_name}" + (" futures" if is_futures else ""))
        return ws_private, rest_private
    else:
        if ws_public is None:
            raise ValueError(f"Public WebSocket not supported for {exchange_name}" + (" futures" if is_futures else ""))
        return ws_public, None
