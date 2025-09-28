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

# Core exchange implementations
from .gateio_composite_private import GateioCompositePrivateSpotExchange
from .gateio_composite_public import GateioCompositePublicSpotExchange

# Futures exchange implementations (separate from spot)
from .gateio_futures_composite_public import GateioFuturesCompositePublicSpotExchange
from .gateio_futures_composite_private import GateioFuturesCompositePrivateExchange
# Auto-register Gate.io services (symbol mapper, mappings) 
from . import services

# Auto-register Gate.io REST strategies
from .rest import strategies

# Auto-register Gate.io WebSocket strategies (triggers registration)
from .ws import strategies as ws_strategies

__all__ = [
    # Core exchange implementations
    'GateioCompositePrivateSpotExchange',
    'GateioCompositePublicSpotExchange',
    'GateioFuturesCompositePublicSpotExchange',
    'GateioFuturesCompositePrivateExchange',
]