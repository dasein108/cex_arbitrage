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
        symbol_str = MexcUtils.symbol_to_pair(symbol).upper()  # MEXC requires UPPERCASE

        # MEXC WebSocket subscription formats (from official documentation)
        # https://mexcdevelop.github.io/apidocs/spot_v3_en/#partial-book-depth-streams
        # Format: spot@public.limit.depth.v3.api.pb@<symbol>@<level>
        # Format: spot@public.aggre.deals.v3.api.pb@<interval>@<symbol>
        subscriptions = [
            f"spot@public.limit.depth.v3.api.pb@{symbol_str}@5",     # Correct format: symbol@level
            f"spot@public.aggre.deals.v3.api.pb@100ms@{symbol_str}"  # Aggregated trades at 100ms
        ]
        
        self.logger.debug(f"Created subscriptions for {symbol}: {subscriptions}")
        return subscriptions

    async def _on_message(self, message):
        """Handle incoming messages from the websocket."""
        try:
            # MEXC sends different types of messages
            if isinstance(message, bytes):
                # Binary message - could be JSON or protobuf
                try:
                    # Try JSON first
                    json_msg = msgspec.json.decode(message)
                    await self._handle_json_message(json_msg)
                except:
                    # Not JSON, try protobuf
                    self.logger.debug(f"Received binary message, trying protobuf")
                    await self._handle_protobuf_message(message)
            elif isinstance(message, str):
                # String message - parse as JSON
                json_msg = msgspec.json.decode(message.encode())
                await self._handle_json_message(json_msg)
            elif isinstance(message, dict):
                # Already parsed dict
                await self._handle_json_message(message)
            else:
                self.logger.debug(f"Unknown message type: {type(message)}")
                
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await self.on_error(e)
    
    async def _handle_json_message(self, msg: dict):
        """Handle JSON formatted messages from MEXC."""
        try:
            # Log for debugging
            self.logger.debug(f"JSON message: {msg}")
            
            # Check message type
            if 'code' in msg:
                # Subscription response
                if msg['code'] == 0:
                    self.logger.info(f"Subscription confirmed")
                else:
                    self.logger.warning(f"Subscription error: {msg}")
            elif 'c' in msg:
                # Channel data message
                channel = msg['c']
                symbol_str = msg.get('s', '')
                data = msg.get('d', {})
                
                if 'depth' in channel:
                    await self._handle_json_orderbook(data, symbol_str)
                elif 'deals' in channel:
                    await self._handle_json_trades(data, symbol_str)
                else:
                    self.logger.debug(f"Unknown channel: {channel}")
            elif 'ping' in msg:
                self.logger.debug("Received ping")
            else:
                self.logger.debug(f"Unhandled message: {msg}")
                
        except Exception as e:
            self.logger.error(f"Error handling JSON: {e}")
    
    async def _handle_protobuf_message(self, data: bytes):
        """Handle protobuf messages."""
        try:
            wrapper = PushDataV3ApiWrapper()
            wrapper.ParseFromString(data)
            
            # Extract symbol from the wrapper if available
            symbol_str = ""
            if hasattr(wrapper, 'symbol') and wrapper.symbol:
                symbol_str = wrapper.symbol
            
            if wrapper.HasField('publicLimitDepths'):
                depth_data = wrapper.publicLimitDepths
                # Try to extract symbol from the depth data if not in wrapper
                if not symbol_str and hasattr(depth_data, 'symbol') and depth_data.symbol:
                    symbol_str = depth_data.symbol
                await self._handle_orderbook_update(depth_data, symbol_str)
            elif wrapper.HasField('publicAggreDeals'):
                deals_data = wrapper.publicAggreDeals
                # Try to extract symbol from the deals data if not in wrapper
                if not symbol_str and hasattr(deals_data, 'symbol') and deals_data.symbol:
                    symbol_str = deals_data.symbol
                await self._handle_trades_update(deals_data, symbol_str)
                
        except Exception as e:
            self.logger.error(f"Error handling protobuf: {e}")
            # Log more details for debugging
            self.logger.debug(f"Protobuf data length: {len(data)} bytes")
            self.logger.debug(f"Protobuf data (first 100 bytes): {data[:100].hex()}")
    
    async def _handle_json_orderbook(self, data: dict, symbol_str: str):
        """Handle JSON orderbook data."""
        try:
            symbol = MexcUtils.pair_to_symbol(symbol_str)
            
            bids = []
            asks = []
            
            # Parse bids
            for bid in data.get('bids', []):
                if isinstance(bid, list) and len(bid) >= 2:
                    bids.append(OrderBookEntry(
                        price=float(bid[0]),
                        size=float(bid[1])
                    ))
            
            # Parse asks  
            for ask in data.get('asks', []):
                if isinstance(ask, list) and len(ask) >= 2:
                    asks.append(OrderBookEntry(
                        price=float(ask[0]),
                        size=float(ask[1])
                    ))
            
            orderbook = OrderBook(
                bids=bids,
                asks=asks,
                timestamp=time.time()
            )
            
            await self.on_orderbook_update(symbol, orderbook)
            
        except Exception as e:
            self.logger.error(f"Error handling JSON orderbook: {e}")
    
    async def _handle_json_trades(self, data: dict, symbol_str: str):
        """Handle JSON trade data."""
        try:
            symbol = MexcUtils.pair_to_symbol(symbol_str)
            trades = []
            
            for deal in data.get('deals', []):
                side = Side.BUY if deal.get('t') == 1 else Side.SELL
                
                trade = Trade(
                    price=float(deal.get('p', 0)),
                    amount=float(deal.get('q', 0)),
                    side=side,
                    timestamp=int(deal.get('T', time.time() * 1000)),
                    is_maker=False
                )
                trades.append(trade)
            
            if trades:
                await self.on_trades_update(symbol, trades)
                
        except Exception as e:
            self.logger.error(f"Error handling JSON trades: {e}")

    async def _handle_orderbook_update(self, depth_data: PublicLimitDepthsV3Api, symbol_str: str):
        """Handle orderbook depth updates."""
        try:
            # Handle cases where symbol might not be provided
            if not symbol_str:
                self.logger.warning("No symbol provided for orderbook update, skipping")
                return
            
            # Convert symbol string back to Symbol object
            try:
                symbol = MexcUtils.pair_to_symbol(symbol_str.upper())
            except Exception as e:
                self.logger.error(f"Failed to parse symbol '{symbol_str}': {e}")
                return
            
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
            
            self.logger.debug(f"Processed orderbook update for {symbol}: {len(bids)} bids, {len(asks)} asks")
            
            # Call handler if implemented
            await self.on_orderbook_update(symbol, orderbook)
            
        except Exception as e:
            self.logger.error(f"Error handling orderbook update: {e}")
            self.logger.debug(f"Symbol: '{symbol_str}', Data fields: {[field.name for field in depth_data.DESCRIPTOR.fields]}")

    async def _handle_trades_update(self, deals_data: PublicAggreDealsV3Api, symbol_str: str):
        """Handle trade updates."""
        try:
            # Handle cases where symbol might not be provided
            if not symbol_str:
                self.logger.warning("No symbol provided for trades update, skipping")
                return
            
            # Convert symbol string back to Symbol object
            try:
                symbol = MexcUtils.pair_to_symbol(symbol_str.upper())
            except Exception as e:
                self.logger.error(f"Failed to parse symbol '{symbol_str}': {e}")
                return
            
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
            
            self.logger.debug(f"Processed {len(trades)} trades for {symbol}")
            
            # Call handler if implemented
            if trades:  # Only call if we have trades
                await self.on_trades_update(symbol, trades)
            
        except Exception as e:
            self.logger.error(f"Error handling trades update: {e}")
            self.logger.debug(f"Symbol: '{symbol_str}', Data fields: {[field.name for field in deals_data.DESCRIPTOR.fields]}")

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