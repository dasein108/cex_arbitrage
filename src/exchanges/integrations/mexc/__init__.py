"""
MEXC Exchange Implementation

High-performance MEXC cryptocurrency exchange client optimized for HFT arbitrage trading.
Implements unified PublicExchangeInterface and PrivateExchangeInterface with ultra-low 
latency optimizations and comprehensive trading capabilities.

Architecture:
- Public Exchange: Market data operations (no authentication required)
- Private Exchange: Trading operations (authentication required)  
- REST Client: Ultra-simple REST client with connection pooling
- WebSocket: Real-time data streaming with strategy pattern
- Services: Auto-registered symbol mappers and utility services
- Strategies: Exchange-specific REST and WebSocket strategies

Key Features:
- Sub-10ms response times for market data
- Connection pooling and session reuse optimization
- Efficient data transformation with msgspec structures
- MEXC-specific rate limiting (1200 req/min)
- Unified exception handling and error recovery
- Futures trading support with zero code duplication
- Auto-registration of services and strategies

Performance Optimizations:
- Zero-copy JSON parsing with msgspec
- Object pooling for reduced allocation overhead
- Persistent HTTP sessions with intelligent reuse
- Pre-compiled symbol mappings for O(1) lookups
- HFT-compliant caching policies (no real-time data caching)

Trading Capabilities:
- Spot trading (public and private)
- Futures trading (public market data)
- Real-time orderbook and trade streaming
- Order management and position tracking
- Balance monitoring and updates

The module follows SOLID principles with clear separation of concerns,
dependency injection, and interface-driven design for maximum maintainability
and extensibility.
"""

# Core exchange implementations

# REST and WebSocket clients for direct access
from exchanges.integrations.mexc.rest.mexc_rest_spot_public import MexcPublicSpotRest
from exchanges.integrations.mexc.ws.mexc_ws_public import MexcSpotWebsocketPublic
# Auto-register MEXC services (symbol mapper, mappings) 
from . import services

# Auto-register MEXC REST strategies
from .rest import strategies

# Auto-register MEXC WebSocket strategies (triggers registration)
from .ws import strategies as ws_strategies

__all__ = [
    # Direct client access
    'MexcPublicSpotRest',
    'MexcSpotWebsocketPublic',
]