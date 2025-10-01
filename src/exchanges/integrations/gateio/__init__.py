"""
Gate.io Exchange Implementation

High-performance Gate.io cryptocurrency exchange client optimized for HFT arbitrage trading.
Implements unified PublicExchangeInterface and PrivateExchangeInterface with comprehensive
trading capabilities and ultra-low latency optimizations.

Architecture:
- Public Exchange: Market data operations (no authentication required)
- Private Exchange: Trading operations (authentication required)
- REST Client: High-performance REST client with connection pooling
- WebSocket: Real-time data streaming with strategy pattern
- Services: Auto-registered symbol mappers and utility services
- Strategies: Exchange-specific REST and WebSocket strategies

Key Features:
- Comprehensive spot trading API coverage
- Real-time WebSocket data streaming
- Type-safe data structures using msgspec.Struct
- HFT compliance with no real-time data caching
- Unified exception handling and error recovery
- Auto-registration of services and strategies

Performance Optimizations:
- Zero-copy JSON parsing with msgspec
- Object pooling for reduced allocation overhead
- Persistent HTTP sessions with intelligent reuse
- Pre-compiled symbol mappings for O(1) lookups
- Gate.io-specific rate limiting and optimization

Trading Capabilities:
- Spot trading (public and private)
- Real-time orderbook and trade streaming
- Order management and position tracking
- Balance monitoring and updates
- Comprehensive API endpoint coverage

Exchange-Specific Features:
- Underscore-separated symbol format (BTC_USDT)
- Extended quote asset support (USDT, USDC, BTC, ETH, DAI, USD)
- Gate.io-specific authentication and rate limiting
- WebSocket ping/pong keep-alive management

The module follows SOLID principles with clear separation of concerns,
dependency injection, and interface-driven design for maximum maintainability
and extensibility.
"""

# Exchange clients for direct access
from .rest.gateio_rest_spot_public import GateioPublicSpotRestInterface
from .rest.gateio_rest_spot_private import GateioPrivateSpotRestInterface
from .rest.gateio_rest_futures_public import GateioPublicFuturesRestInterface
from .rest.gateio_rest_futures_private import GateioPrivateFuturesRestInterface
from .ws.gateio_ws_public import GateioPublicSpotWebsocket
from .ws.gateio_ws_private import GateioPrivateSpotWebsocket
from .ws.gateio_ws_public_futures import GateioPublicFuturesWebsocket
from .ws.gateio_ws_private_futures import GateioPrivateFuturesWebsocket


__all__ = [
    # Direct client access
    'GateioPublicSpotRestInterface',
    'GateioPrivateSpotRestInterface',
    'GateioPublicSpotWebsocket',
    'GateioPrivateSpotWebsocket',
    'GateioPublicFuturesRestInterface',
    'GateioPrivateFuturesRestInterface',
    'GateioPublicFuturesWebsocket',
    'GateioPrivateFuturesWebsocket',
]