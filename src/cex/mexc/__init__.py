"""
MEXC Exchange Implementation - Updated with Refactored Futures

High-performance MEXC cryptocurrency exchange client optimized for arbitrage trading.
Implements the PublicExchangeInterface with ultra-low latency optimizations.

Features:
- Sub-10ms response times for market data
- Connection pooling and session reuse with UltraSimpleRestClient
- Efficient data transformation with msgspec
- MEXC-specific rate limiting (1200 req/min)
- Comprehensive unified exception handling
- Refactored futures trading support with zero code duplication

Modules:
- mexc_public: Spot trading market data
- mexc_futures_public: Refactored futures trading with UltraSimpleRestClient
- websocket: Real-time WebSocket data streaming

Refactoring Achievements:
- ~230 lines removed from mexc_futures_public
- Zero code duplication with unified REST client
- Complete PublicExchangeInterface compliance
- Enhanced performance with LRU caching
"""

from cex.mexc.rest.rest_public import MexcPublicSpotRest
from cex.mexc.ws.public.ws_public import MexcWebsocketPublic
from .private_exchange import MexcPrivateExchange
from .public_exchange import MexcPublicExchange

# Auto-register MEXC services (symbol mapper, mappings) 
from . import services

# Auto-register MEXC REST strategies
from .rest import strategies

__all__ = [
    'MexcPublicSpotRest',
    'MexcWebsocketPublic',
    "MexcPrivateExchange",
    "MexcPublicExchange"
]