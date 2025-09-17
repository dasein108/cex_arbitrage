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

from structs.exchange import Symbol, Trade, OrderBook
from core.config.structs import ExchangeConfig

# Strategy pattern imports
from core.cex.websocket import BaseExchangePublicWebsocketInterface
from core.transport.websocket.strategies import WebSocketStrategySet
from core.transport.websocket.ws_manager import WebSocketManager, WebSocketManagerConfig
from core.cex.websocket import MessageType, ConnectionState
from cex.mexc.ws.strategies.public import (MexcPublicMessageParser,
                                           MexcPublicSubscriptionStrategy, MexcPublicConnectionStrategy)

from cex.mexc.structs.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
from cex.mexc.structs.protobuf.PublicLimitDepthsV3Api_pb2 import PublicLimitDepthsV3Api
from cex.mexc.structs.protobuf.PublicAggreDealsV3Api_pb2 import PublicAggreDealsV3Api
# from cex.mexc.protobuf.PublicAggreDepthsV3Api_pb2 import PublicAggreDepthsV3Api

# ExchangeFactoryBundle is no longer needed with BaseExchangeFactory infrastructure

class MexcWebsocketPublic(BaseExchangePublicWebsocketInterface):
    """MEXC public WebSocket client using strategy pattern architecture."""

    def __init__(
        self,
        config: ExchangeConfig,
        orderbook_diff_handler: Optional[Callable[[any, Symbol], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
        state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
    ):
        super().__init__(config,
                         orderbook_diff_handler=orderbook_diff_handler,
                         trades_handler=trades_handler,
                         state_change_handler=state_change_handler)

        # Get exchange config with WebSocket configuration
        if not config.websocket:
            raise ValueError("MEXC exchange configuration missing WebSocket settings")
        
        # Use factory to get symbol mapper
        from core.cex.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
        symbol_mapper = ExchangeSymbolMapperFactory.inject('MEXC')
        
        # Create strategy set for MEXC public WebSocket with resolved dependencies
        strategies = WebSocketStrategySet(
            connection_strategy=MexcPublicConnectionStrategy(config),
            subscription_strategy=MexcPublicSubscriptionStrategy(symbol_mapper),
            message_parser=MexcPublicMessageParser(symbol_mapper)
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
            manager_config=manager_config,
            state_change_handler=state_change_handler
        )
        
        # Store factory bundle for potential future use
        self._factory_bundle = factory_bundle
        
        injection_method = "factory-mediated" if factory_bundle else "constructor"
        self.logger.info(f"MEXC public WebSocket initialized with strategy pattern using {injection_method} injection")

    async def _handle_parsed_message(self, parsed_message) -> None:
        """Handle parsed messages from WebSocketManager."""
        try:
            message_type = parsed_message.message_type
            
            if message_type == MessageType.ORDERBOOK:
                if parsed_message.symbol and self.orderbook_diff_handler:
                    # Parse raw message to get diff information
                    message_parser = self.ws_manager.strategies.message_parser
                    if hasattr(message_parser, 'parse_orderbook_diff_message'):
                        diff_update = message_parser.parse_orderbook_diff_message(
                            parsed_message.raw_data, 
                            parsed_message.symbol
                        )
                        if diff_update:
                            await self.orderbook_diff_handler(diff_update, parsed_message.symbol)
                    else:
                        # Fallback to legacy handler
                        await self.orderbook_diff_handler(parsed_message.raw_data, parsed_message.symbol)
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
    
