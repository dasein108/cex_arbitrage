"""
MEXC Public WebSocket Implementation (Refactored)

Modernized implementation using the new strategy pattern architecture.
Handles public WebSocket streams for market data including:
- Orderbook depth updates
- Trade stream data
- Real-time market information

Features:
- Strategy pattern architecture with composition
- HFT-optimized message processing with WebSocketManager
- Event-driven architecture with dependency injection handlers
- Clean separation of concerns
- Legacy message handling for backward compatibility

MEXC Public WebSocket Specifications:
- Endpoint: wss://wbs.mexc.com/ws
- Protocol: JSON and Protocol Buffers
- Performance: <50ms latency with batch processing

Architecture: Strategy pattern with WebSocketManager coordination
"""

from typing import List, Dict, Optional, Callable, Awaitable
from common.logging import getLogger

from structs.exchange import Symbol, Trade, OrderBook
from core.config.structs import WebSocketConfig, ExchangeConfig

# Strategy pattern imports
from core.cex.websocket import BaseExchangeWebsocketInterface
from core.cex.websocket.strategies import WebSocketStrategySet
from core.cex.websocket.ws_manager import WebSocketManager, WebSocketManagerConfig
from core.cex.websocket import MessageType
from cex.mexc.ws.public.ws_message_parser import MexcPublicMessageParser
from cex.mexc.ws.public.ws_strategies import MexcPublicConnectionStrategy, MexcPublicSubscriptionStrategy

from cex.mexc.structs.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
from cex.mexc.structs.protobuf.PublicLimitDepthsV3Api_pb2 import PublicLimitDepthsV3Api
from cex.mexc.structs.protobuf.PublicAggreDealsV3Api_pb2 import PublicAggreDealsV3Api
# from cex.mexc.protobuf.PublicAggreDepthsV3Api_pb2 import PublicAggreDepthsV3Api

class MexcWebsocketPublic(BaseExchangeWebsocketInterface):
    """MEXC public WebSocket client using strategy pattern architecture."""

    def __init__(
        self,
        config: ExchangeConfig,
        orderbook_handler: Optional[Callable[[Symbol, OrderBook], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None
    ):
        super().__init__(config)
        self.logger = getLogger(f"{__name__}.{self.__class__.__name__}")
        self.orderbook_handler = orderbook_handler
        self.trades_handler = trades_handler
        
        # Get exchange config with WebSocket configuration

        if not config.websocket:
            raise ValueError("MEXC exchange configuration missing WebSocket settings")
        
        # Create strategy set for MEXC public WebSocket
        strategies = WebSocketStrategySet(
            connection_strategy=MexcPublicConnectionStrategy(config),
            subscription_strategy=MexcPublicSubscriptionStrategy(),
            message_parser=MexcPublicMessageParser(self.symbol_mapper)
        )
        
        # Configure manager for HFT performance
        manager_config = WebSocketManagerConfig(
            batch_processing_enabled=True,
            batch_size=100,
            max_pending_messages=1000,
            enable_performance_tracking=True
        )
        
        # Initialize WebSocket manager with WebSocket config from exchange config
        self.ws_manager = WebSocketManager(
            config=config.websocket,
            strategies=strategies,
            message_handler=self._handle_parsed_message,
            manager_config=manager_config
        )
        
        self.logger.info("MEXC public WebSocket initialized with strategy pattern")

    async def _handle_parsed_message(self, parsed_message) -> None:
        """Handle parsed messages from WebSocketManager."""
        try:
            message_type = parsed_message.message_type
            
            if message_type == MessageType.ORDERBOOK:
                if parsed_message.symbol and parsed_message.data and self.orderbook_handler:
                    await self.orderbook_handler(parsed_message.symbol, parsed_message.data)
                elif parsed_message.symbol and parsed_message.data:
                    await self.on_orderbook_update(parsed_message.symbol, parsed_message.data)
                    
            elif message_type == MessageType.TRADE:
                if parsed_message.symbol and parsed_message.data and self.trades_handler:
                    await self.trades_handler(parsed_message.symbol, parsed_message.data)
                elif parsed_message.symbol and parsed_message.data:
                    await self.on_trades_update(parsed_message.symbol, parsed_message.data)
                    
            elif message_type == MessageType.HEARTBEAT:
                self.logger.debug("Received public heartbeat")
                
            elif message_type == MessageType.SUBSCRIPTION_CONFIRM:
                self.logger.info("Public subscription confirmed")
                
            elif message_type == MessageType.ERROR:
                self.logger.error(f"Public WebSocket error: {parsed_message.raw_data}")

        except Exception as e:
            self.logger.error(f"Error handling parsed public message: {e}")

    async def initialize(self, symbols: List[Symbol]) -> None:
        """Initialize public WebSocket connection using strategy pattern."""
        try:
            await self.ws_manager.initialize(symbols)
            self.logger.info(f"Public WebSocket initialized with {len(symbols)} symbols")
        except Exception as e:
            self.logger.error(f"Failed to initialize public WebSocket: {e}")
            raise

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.ws_manager.is_connected()
        
    def get_performance_metrics(self) -> Dict:
        """Get HFT performance metrics."""
        return self.ws_manager.get_performance_metrics()
        
    async def close(self) -> None:
        """Close WebSocket connection."""
        self.logger.info("Stopping public WebSocket connection")
        await self.ws_manager.close()
        self.logger.info("Public WebSocket stopped")


    async def on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Default orderbook update handler."""
        self.logger.info(f"Orderbook update for {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")

    async def on_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """Default trade update handler."""
        self.logger.info(f"Trades update for {symbol}: {len(trades)} trades")