"""
MEXC Public WebSocket Implementation

Clean implementation using handler objects for organized message processing.
Handles public WebSocket streams for market data including:
- Orderbook depth updates
- Trade stream data
- Real-time market information

Features:
- Handler object pattern for clean organization
- HFT-optimized message processing 
- Event-driven architecture with structured handlers
- Clean separation of concerns
- MEXC-specific protobuf message parsing

MEXC Public WebSocket Specifications:
- Endpoint: wss://wbs.mexc.com/ws
- Protocol: JSON and Protocol Buffers
- Performance: <50ms latency with batch processing

Architecture: Handler objects with composite class coordination
"""
from typing import Dict, Any

from websockets import connect

from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSpotSymbol
from exchanges.interfaces.ws import BasePublicWebsocketPrivate
from exchanges.integrations.mexc.structs.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
from exchanges.integrations.mexc.structs.protobuf.PublicLimitDepthsV3Api_pb2 import PublicLimitDepthsV3Api
from exchanges.integrations.mexc.structs.protobuf.PublicAggreDealsV3Api_pb2 import PublicAggreDealsV3Api
from exchanges.structs import Symbol, OrderBook, BookTicker, Trade, Side
from infrastructure.networking.websocket.structs import SubscriptionAction, WebsocketChannelType
from exchanges.integrations.mexc.utils import from_subscription_action
from exchanges.integrations.mexc.ws.protobuf_parser import MexcProtobufParser
from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol
from common.orderbook_entry_pool import OrderBookEntryPool

import msgspec

from utils import get_current_timestamp


class MexcPublicSpotWebsocket(BasePublicWebsocketPrivate):
    """MEXC public WebSocket client using dependency injection pattern."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entry_pool = OrderBookEntryPool(initial_size=200, max_size=500)

    async def _handle_message(self, raw_message: Any) -> None:
        try:
            # Check if it's bytes (protobuf) or string/dict (JSON)
            if isinstance(raw_message, bytes):
                # Handle protobuf message - simple approach
                return await self._parse_protobuf_message(raw_message)
            else:
                # {'code': 0, 'id': 0,
                #  'msg': 'Not Subscribed successfully! '
                #         '[spot@public.increase.depth.v3.api@BTCUSDT,'
                #         'spot@public.aggre.deals.v3.api.pb@BTCUSDT,'
                #         'spot@public.aggre.bookTicker.v3.api.pb@BTCUSDT].  Reason： Blocked! '}

                if isinstance(raw_message, str):
                    message = msgspec.json.decode(raw_message)
                else:
                        # If it's already a dict, use it directly
                    message = raw_message

            self.logger.info(f'Received non-protobuf message on private channel {message}')

        except Exception as e:
            self.logger.error(f"Error parsing private message: {e}",
                              exchange="mexc",
                              error_type="message_parse_error")

    def _prepare_subscription_message(self, action: SubscriptionAction, symbol: Symbol, channel: WebsocketChannelType,
                                      **kwargs) -> Dict[str, Any]:
        method = from_subscription_action(action)


        exchange_symbol = GateioSpotSymbol.to_pair(symbol)
        params = []  # Reset params for each symbol
        if WebsocketChannelType.BOOK_TICKER == channel:
            params.append(f"spot@public.aggre.bookTicker.v3.api.pb@10ms@{exchange_symbol}")

        elif WebsocketChannelType.ORDERBOOK == channel:
            params.append(f"spot@public.increase.depth.v3.api@10ms@{exchange_symbol}")

        elif WebsocketChannelType.TRADES == channel:
            params.append(f"spot@public.aggre.deals.v3.api.pb@10ms@{exchange_symbol}")

        if self.logger:
            self.logger.debug(f"Added channels for {symbol}: {exchange_symbol}",
                            symbol=str(symbol),
                            exchange_symbol=exchange_symbol,
                            exchange="mexc")

        message = {
            "method": method,
            "params": params
        }

        return message

    async def _create_websocket(self):
        return await connect(
            self.config.websocket_url,
            # Performance optimizations for MEXC
            ping_interval=self.config.websocket.ping_interval,
            ping_timeout=self.config.websocket.ping_timeout,
            max_queue=self.config.websocket.max_queue_size,
            # Disable compression for CPU optimization in HFT
            compression=None,
            max_size=self.config.websocket.max_message_size,
        )

    async def _parse_protobuf_message(self, raw_message: bytes) -> None:
        wrapper = MexcProtobufParser.parse_wrapper_message(raw_message)
        symbol_str = MexcProtobufParser.extract_symbol_from_protobuf(raw_message)
        symbol = MexcSymbol.to_symbol(symbol_str)

        if wrapper.HasField('publicAggreDeals'):
            deals_data = wrapper.publicAggreDeals

            # TODO: Pass batch of trades to handler for efficiency
            # trades = []
            for deal_item in deals_data.deals:
                # Direct parsing from protobuf fields - deal_item already has parsed data
                trade = Trade(
                    symbol=MexcSymbol.to_symbol(symbol_str),
                    price=float(deal_item.price),
                    quantity=float(deal_item.quantity),
                    timestamp=int(deal_item.time),
                    side=Side.BUY if deal_item.tradeType == 1 else Side.SELL,
                    # trade_id=str(deal_item.time)  # Use timestamp as trade ID
                )

                await self.handle_trade(trade)

        elif wrapper.HasField('publicAggreDepths'):
            depth_data = wrapper.publicAggreDepths
            # bid_updates = []
            # for bid_item in depth_data.bids:
            #     price = float(bid_item.price)
            #     size = float(bid_item.quantity)
            #     bid_updates.append((price, size))
            #
            # ask_updates = []
            # for ask_item in depth_data.asks:
            #     price = float(ask_item.price)
            #     size = float(ask_item.quantity)
            #     ask_updates.append((price, size))
            # Direct parsing from protobuf fields - bid_item/ask_item already have parsed price/quantity
            bids = []
            asks = []

            for bid_item in depth_data.bids:
                bids.append(self.entry_pool.get_entry(
                    price=float(bid_item.price),
                    size=float(bid_item.quantity)
                ))

            for ask_item in depth_data.asks:
                asks.append(self.entry_pool.get_entry(
                    price=float(ask_item.price),
                    size=float(ask_item.quantity)
                ))

            orderbook = OrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=get_current_timestamp()
            )

            await self.handle_orderbook(orderbook)
        elif wrapper.HasField('publicAggreBookTicker'):
                book_ticker_data = wrapper.publicAggreBookTicker

                # Direct parsing from protobuf fields - book_ticker_data already has parsed price/quantity fields
                symbol = MexcSymbol.to_symbol(symbol_str)

                book_ticker = BookTicker(
                    symbol=symbol,
                    bid_price=float(book_ticker_data.bidPrice),
                    bid_quantity=float(book_ticker_data.bidQuantity),
                    ask_price=float(book_ticker_data.askPrice),
                    ask_quantity=float(book_ticker_data.askQuantity),
                    timestamp=get_current_timestamp(),  # MEXC protobuf doesn't include timestamp
                    update_id=None  # MEXC protobuf doesn't include update_id
                )

                await self.handle_book_ticker(book_ticker)