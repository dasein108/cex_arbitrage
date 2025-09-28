"""
Public exchange interface for high-frequency market data operations.

This module defines the base composite interface for public market data operations
in the separated domain architecture. It orchestrates REST and WebSocket interfaces
to provide unified access to orderbooks, trades, tickers, and symbol information
without requiring authentication.

## Architecture Position

The CompositePublicExchange is a cornerstone of the separated domain pattern:
- **Pure Market Data**: No trading capabilities or protocols
- **Zero Authentication**: All operations are public
- **Domain Isolation**: Complete separation from private/trading operations
- **HFT Optimized**: Sub-millisecond latency for arbitrage detection

## Core Responsibilities

1. **Orderbook Management**: Real-time orderbook streaming and caching
2. **Symbol Resolution**: Ultra-fast symbol mapping and validation
3. **Market Updates**: Broadcasting price changes to arbitrage layer
4. **Connection Lifecycle**: WebSocket connection management and recovery

## Performance Requirements

- **Orderbook Updates**: <5ms propagation to arbitrage layer
- **Symbol Resolution**: <1μs per lookup (1M+ ops/second)
- **WebSocket Latency**: <10ms for market data updates
- **Initialization**: <3 seconds for full symbol loading

## Implementation Pattern

This is an abstract base class using the Template Method pattern:
- Concrete exchanges implement factory methods for REST/WS creation
- Base class handles orchestration and state management
- Eliminates code duplication across exchange implementations

## Integration Notes

- Works with PublicWebsocketHandlers for event injection
- Broadcasts to arbitrage layer via orderbook_update_handlers
- Maintains no trading state (orders, balances, positions)
- Thread-safe for concurrent arbitrage monitoring

See also:
- composite-exchange-architecture.md for complete design
- separated-domain-pattern.md for architectural context
- hft-requirements-compliance.md for performance specs
"""

from abc import ABC
from exchanges.interfaces.composite.base_public_composite import BasePublicComposite
from exchanges.interfaces.rest import PublicSpotRest
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket


class CompositePublicSpotExchange(BasePublicComposite[PublicSpotRest, PublicSpotWebsocket], ABC):
    pass