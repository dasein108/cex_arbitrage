# Legacy implementations (to be deprecated)
from .ws_spot_private import PrivateSpotWebsocket as LegacyPrivateSpotWebsocket
from .ws_spot_public import PublicSpotWebsocket as LegacyPublicSpotWebsocket

# New separated domain implementations
from .public_spot_websocket import PublicSpotWebsocket
from .private_spot_websocket import PrivateSpotWebsocket

__all__ = [
    # New separated domain interfaces (preferred)
    'PublicSpotWebsocket',
    'PrivateSpotWebsocket',
    
    # Legacy interfaces (for backward compatibility)
    'LegacyPrivateSpotWebsocket',
    'LegacyPublicSpotWebsocket'
]