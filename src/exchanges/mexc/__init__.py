"""
MEXC Exchange Implementation

High-performance MEXC cryptocurrency exchange client optimized for arbitrage trading.
Implements the PublicExchangeInterface with ultra-low latency optimizations.

Features:
- Sub-10ms response times for market data
- Connection pooling and session reuse
- Efficient data transformation with msgspec
- MEXC-specific rate limiting (1200 req/min)
- Comprehensive error handling with retry logic
"""

from .mexc_public import MexcPublicExchange
from .websocket import MexcWebSocketPublicStream

__all__ = ['MexcPublicExchange', 'MexcWebSocketPublicStream']