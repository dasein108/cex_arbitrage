import logging
import time
import msgspec
from typing import List, Any, Dict, Optional, Callable, Awaitable
from exchanges.interface.websocket.base_ws import BaseExchangeWebsocketInterface
from structs.exchange import Symbol, Trade, OrderBook, OrderBookEntry, Side
from exchanges.mexc.common.mexc_config import MexcConfig
from exchanges.mexc.common.mexc_utils import MexcUtils
from common.ws_client import SubscriptionAction, WebSocketConfig
from exchanges.mexc.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
from exchanges.mexc.protobuf.PublicLimitDepthsV3Api_pb2 import PublicLimitDepthsV3Api
from exchanges.mexc.protobuf.PublicAggreDealsV3Api_pb2 import PublicAggreDealsV3Api

class MexcWebsocketPublic(BaseExchangeWebsocketInterface):
    """MEXC public websocket interface for market data streaming"""

    def __init__(
        self, 
        config: WebSocketConfig,
        orderbook_handler: Optional[Callable[[Symbol, OrderBook], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None
    ):
        super().__init__(MexcConfig.EXCHANGE_NAME, config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.orderbook_handler = orderbook_handler
        self.trades_handler = trades_handler

    def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction) -> List[str]:
        """Prepare the connections for subscriptions specific symbol."""
        symbol_str = MexcUtils.symbol_to_pair(symbol)

        # Fixed subscription formats based on MEXC WebSocket API
        subscriptions = [
            f"spot@public.limit.depth.v3.api.pb@{symbol_str}@5",
            f"spot@public.aggre.deals.v3.api.pb@100ms@{symbol_str}"
        ]
        
        self.logger.debug(f"Created subscriptions for {symbol}: {subscriptions}")
        return subscriptions

    async def _on_message(self, message: Dict[str, Any]):
        """Handle incoming messages from the websocket."""
        try:
            # MEXC sends protobuf binary data wrapped in JSON
            if isinstance(message, dict) and 'data' in message:
                # Extract binary protobuf data
                protobuf_data = message['data']
                
                # Parse with protobuf wrapper
                wrapper = PushDataV3ApiWrapper()
                wrapper.ParseFromString(protobuf_data)
                
                # Process based on message type
                if wrapper.HasField('publicLimitDepthsV3Api'):
                    await self._handle_orderbook_update(wrapper.publicLimitDepthsV3Api, message.get('s', ''))
                elif wrapper.HasField('publicAggreDealsV3Api'):
                    await self._handle_trades_update(wrapper.publicAggreDealsV3Api, message.get('s', ''))
                else:
                    self.logger.debug(f"Unknown message type: {wrapper}")
            else:
                # Handle JSON messages (subscriptions, pings, etc.)
                self.logger.debug(f"Received JSON message: {message}")
                
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await self.on_error(e)

    async def _handle_orderbook_update(self, depth_data: PublicLimitDepthsV3Api, symbol_str: str):
        """Handle orderbook depth updates."""
        try:
            # Convert symbol string back to Symbol object
            symbol = MexcUtils.pair_to_symbol(symbol_str)
            
            # Convert protobuf data to unified format
            bids = []
            asks = []
            
            for bid_item in depth_data.bids:
                bids.append(OrderBookEntry(
                    price=float(bid_item.price),
                    size=float(bid_item.quantity)
                ))
            
            for ask_item in depth_data.asks:
                asks.append(OrderBookEntry(
                    price=float(ask_item.price),
                    size=float(ask_item.quantity)
                ))
            
            # Create orderbook
            orderbook = OrderBook(
                bids=bids,
                asks=asks,
                timestamp=time.time()
            )
            
            # Call handler if implemented
            await self.on_orderbook_update(symbol, orderbook)
            
        except Exception as e:
            self.logger.error(f"Error handling orderbook update: {e}")

    async def _handle_trades_update(self, deals_data: PublicAggreDealsV3Api, symbol_str: str):
        """Handle trade updates."""
        try:
            # Convert symbol string back to Symbol object
            symbol = MexcUtils.pair_to_symbol(symbol_str)
            
            # Convert protobuf data to unified format
            trades = []
            
            for deal_item in deals_data.deals:
                # tradeType: 1 = buy, 2 = sell
                side = Side.BUY if deal_item.tradeType == 1 else Side.SELL
                
                trade = Trade(
                    price=float(deal_item.price),
                    amount=float(deal_item.quantity),
                    side=side,
                    timestamp=deal_item.time,
                    is_maker=False  # Aggregated trades don't specify maker/taker
                )
                trades.append(trade)
            
            # Call handler if implemented
            await self.on_trades_update(symbol, trades)
            
        except Exception as e:
            self.logger.error(f"Error handling trades update: {e}")

    async def on_error(self, error: Exception):
        """Handle errors from the websocket."""
        self.logger.error(f"WebSocket error: {error}")

    async def on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Handle orderbook updates using injected handler or default behavior."""
        if self.orderbook_handler:
            await self.orderbook_handler(symbol, orderbook)
        else:
            # Default implementation - just log
            self.logger.info(f"Orderbook update for {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")

    async def on_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """Handle trade updates using injected handler or default behavior."""
        if self.trades_handler:
            await self.trades_handler(symbol, trades)
        else:
            # Default implementation - just log
            self.logger.info(f"Trades update for {symbol}: {len(trades)} trades")