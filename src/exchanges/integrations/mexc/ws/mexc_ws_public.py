"""
MEXC Public WebSocket Implementation

Clean implementation using dependency injection similar to REST pattern.
Handles public WebSocket streams for market data including:
- Orderbook depth updates
- Trade stream data
- Real-time market information

Features:
- Dependency injection via composite class (like REST pattern)
- HFT-optimized message processing 
- Event-driven architecture with injected handlers
- Clean separation of concerns
- MEXC-specific protobuf message parsing

MEXC Public WebSocket Specifications:
- Endpoint: wss://wbs.mexc.com/ws
- Protocol: JSON and Protocol Buffers
- Performance: <50ms latency with batch processing

Architecture: Dependency injection with composite class coordination
"""

from typing import List, Optional, Callable, Awaitable

from exchanges.structs.common import Symbol, Trade, OrderBook, BookTicker
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import PublicFuturesWebsocket
from infrastructure.networking.websocket.structs import ConnectionState

# MEXC-specific protobuf imports for message parsing
from exchanges.integrations.mexc.structs.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
from exchanges.integrations.mexc.structs.protobuf.PublicLimitDepthsV3Api_pb2 import PublicLimitDepthsV3Api
from exchanges.integrations.mexc.structs.protobuf.PublicAggreDealsV3Api_pb2 import PublicAggreDealsV3Api


class MexcWebsocketExchangePublicWebsocket(PublicFuturesWebsocket):
    """MEXC public WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        config: ExchangeConfig,
        orderbook_diff_handler: Optional[Callable[[any, Symbol], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
        book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
        state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
    ):
        """
        Initialize MEXC public WebSocket with dependency injection.
        
        Base class handles all strategy creation, WebSocket manager setup, and dependency injection.
        Only MEXC-specific initialization logic goes here.
        """
        # Validate MEXC-specific requirements
        if not config.websocket_url:
            raise ValueError("MEXC exchange configuration missing WebSocket URL")
        
        # Initialize via composite class dependency injection (like REST pattern)
        super().__init__(
            config=config,
            orderbook_diff_handler=orderbook_diff_handler,
            trades_handler=trades_handler,
            book_ticker_handler=book_ticker_handler,
            state_change_handler=state_change_handler
        )

        self.logger.info("MEXC public WebSocket initialized with dependency injection")

    # MEXC-specific message handling can be added here if needed
    # Base class handles all common WebSocket operations:
    # - initialize(), close(), is_connected(), get_performance_metrics()
    # - Message routing for ORDERBOOK, TRADE, HEARTBEAT, etc.
    # - Default event handlers with dependency injection support
    
    # Override default handlers if MEXC needs specific behavior
    async def on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """MEXC-specific orderbook update handler."""
        self.logger.info(f"MEXC orderbook update for {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")

    async def on_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """MEXC-specific trade update handler."""
        self.logger.info(f"MEXC trades update for {symbol}: {len(trades)} trades")
