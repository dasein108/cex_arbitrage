"""
Gate.io Exchange Unified Mappings Implementation

Consolidated Gate.io-specific mapper combining all mapping functionality:
- API format conversions and order transformations
- WebSocket channel mappings
- Error code mappings and exception handling
- Order status, type, and side conversions

HFT COMPLIANCE: Sub-microsecond mapping operations, zero-copy patterns.
"""

from datetime import datetime
from typing import Any, Dict
from enum import Enum

from structs.common import (
    Order, OrderId, OrderStatus, OrderType, Side,
    TimeInForce, KlineInterval, Trade, AssetBalance, AssetName,
    OrderBook, OrderBookEntry, BookTicker, Symbol
)
from core.exchanges.services.exchange_mapper.base_exchange_mapper import BaseExchangeMapper
from core.transport.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from core.exceptions.exchange import (
    BaseExchangeError, RateLimitErrorBase, TradingDisabled,
    InsufficientPosition, OversoldException
)
from .mapping_configuration import GateioMappingConfiguration, create_gateio_mapping_configuration


class GateioUnifiedMappings(BaseExchangeMapper):
    """
    Gate.io-specific unified mapping implementation.
    
    Consolidated mapper combining all Gate.io mapping functionality:
    - API format conversions and order transformations
    - WebSocket channel mappings  
    - Error code mappings and exception handling
    - Order status, type, and side conversions
    """
    
    class EventType(Enum):
        """Gate.io WebSocket event types."""
        SUBSCRIBE = "subscribe"
        UNSUBSCRIBE = "unsubscribe" 
        UPDATE = "update"
        PING = "ping"
        PONG = "pong"
    
    
    # Spot WebSocket channel mappings
    SPOT_CHANNEL_MAPPING: Dict[PublicWebsocketChannelType, str] = {
        PublicWebsocketChannelType.BOOK_TICKER: "spot.book_ticker",
        PublicWebsocketChannelType.TRADES: "spot.trades",
        PublicWebsocketChannelType.ORDERBOOK: "spot.order_book_update",
        PublicWebsocketChannelType.TICKER: "spot.tickers"
    }
    
    # Private WebSocket channel mappings
    PRIVATE_CHANNEL_MAPPING: Dict[PrivateWebsocketChannelType, str] = {
        PrivateWebsocketChannelType.ORDER: "spot.orders",
        PrivateWebsocketChannelType.TRADE: "spot.usertrades_v2", 
        PrivateWebsocketChannelType.BALANCE: "spot.balances"
    }
    
    def __init__(self, symbol_mapper):
        """Initialize Gate.io mappings with exchange-specific configuration."""
        config = create_gateio_mapping_configuration()
        super().__init__(symbol_mapper, config)
        
        # Store external configuration mappings for compatibility
        self._gateio_config = GateioMappingConfiguration
    
    def get_exchange_interval(self, interval: KlineInterval) -> str:
        """Convert unified KlineInterval to Gate.io API format."""
        return self._config.kline_interval_mapping.get(interval, "1m")
    
    def rest_to_balance(self, gate_balance: dict) -> AssetBalance:
        """Transform Gate.io balance response to unified AssetBalance."""
        return AssetBalance(
            asset=AssetName(gate_balance.get('currency', '')),
            free=float(gate_balance.get('available', '0')),  # Gate.io uses 'available' for free
            locked=float(gate_balance.get('locked', '0'))
        )
    
    def ws_to_order(self, gate_ws_order) -> Order:
        """Transform Gate.io WebSocket order data to unified Order."""
        # Gate.io WebSocket order format
        symbol = self.to_symbol(gate_ws_order.get('currency_pair', ''))
        
        return Order(
            order_id=OrderId(gate_ws_order.get('id', '')),
            symbol=symbol,
            side=self.to_side(gate_ws_order.get('side', 'buy')),
            order_type=self.to_order_type(gate_ws_order.get('type', 'limit')),
            quantity=float(gate_ws_order.get('amount', '0')),
            price=float(gate_ws_order.get('price', '0')) if gate_ws_order.get('price') else None,
            filled_quantity=float(gate_ws_order.get('filled_amount', '0')),
            remaining_quantity=float(gate_ws_order.get('left', '0')),
            status=self.to_order_status(gate_ws_order.get('status', 'open')),
            timestamp=int(float(gate_ws_order.get('create_time', '0')) * 1000)
        )
    
    def ws_to_trade(self, gate_ws_trade, symbol_str: str = None) -> Trade:
        """Transform Gate.io WebSocket trade data to unified Trade."""
        # Get symbol from data or parameter
        if symbol_str:
            symbol = self.to_symbol(symbol_str)
        elif gate_ws_trade.get('currency_pair'):
            symbol = self.to_symbol(gate_ws_trade['currency_pair'])
        else:
            symbol = None
        
        # Gate.io trade format
        side = Side.BUY if gate_ws_trade.get('side') == 'buy' else Side.SELL
        price = float(gate_ws_trade.get('price', 0))
        quantity = float(gate_ws_trade.get('amount', 0))
        
        return Trade(
            symbol=symbol,
            price=price,
            quantity=quantity,
            quote_quantity=price * quantity,
            side=side,
            timestamp=int(float(gate_ws_trade.get('create_time_ms', 0))),
            trade_id=str(gate_ws_trade.get('id', '')),
            is_maker=False  # Gate.io doesn't provide maker info in public trades
        )
    
    def ws_to_balance(self, gate_ws_balance) -> AssetBalance:
        """Transform Gate.io WebSocket balance data to unified AssetBalance."""
        return AssetBalance(
            asset=AssetName(gate_ws_balance.get('currency', '')),
            free=float(gate_ws_balance.get('available', '0')),
            locked=float(gate_ws_balance.get('freeze', '0'))  # Gate.io uses 'freeze' for locked
        )
    
    def ws_to_orderbook(self, gate_ws_orderbook, symbol_str: str = None) -> OrderBook:
        """Transform Gate.io WebSocket orderbook data to unified OrderBook."""
        bids = []
        asks = []
        
        # Parse Gate.io orderbook structure
        if gate_ws_orderbook.get('b'):
            for bid_data in gate_ws_orderbook['b']:
                if len(bid_data) >= 2:
                    price = float(bid_data[0])
                    size = float(bid_data[1])
                    bids.append(OrderBookEntry(price=price, size=size))
        
        if gate_ws_orderbook.get('a'):
            for ask_data in gate_ws_orderbook['a']:
                if len(ask_data) >= 2:
                    price = float(ask_data[0])
                    size = float(ask_data[1])
                    asks.append(OrderBookEntry(price=price, size=size))
        
        # Get symbol from data or parameter
        if symbol_str:
            symbol = self.to_symbol(symbol_str)
        elif gate_ws_orderbook.get('s'):
            symbol = self.to_symbol(gate_ws_orderbook['s'])
        else:
            symbol = None
        
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=gate_ws_orderbook.get('t', 0),
            last_update_id=gate_ws_orderbook.get('u')
        )
    
    def ws_to_book_ticker(self, gate_ws_ticker, symbol_str: str = None) -> BookTicker:
        """Transform Gate.io WebSocket book ticker data to unified BookTicker."""
        # Get symbol from data or parameter
        if symbol_str:
            symbol = self.to_symbol(symbol_str)
        elif gate_ws_ticker.get('s'):
            symbol = self.to_symbol(gate_ws_ticker['s'])
        else:
            symbol = None
        
        return BookTicker(
            symbol=symbol,
            bid_price=float(gate_ws_ticker.get('b', 0)),
            bid_quantity=float(gate_ws_ticker.get('B', 0)),
            ask_price=float(gate_ws_ticker.get('a', 0)),
            ask_quantity=float(gate_ws_ticker.get('A', 0)),
            timestamp=int(gate_ws_ticker.get('t', 0)),
            update_id=int(gate_ws_ticker.get('u', 0))
        )
    
    def rest_to_order(self, gate_order: dict) -> Order:
        """Transform Gate.io order response to unified Order."""
        # Extract basic order information
        order_id = OrderId(gate_order.get('id', ''))
        symbol_str = gate_order.get('currency_pair', '')
        symbol = self._symbol_mapper.to_symbol(symbol_str)
        
        # Convert Gate.io status to unified status
        gate_status = gate_order.get('status', 'open')
        status = super().to_order_status(gate_status)
        
        # Convert Gate.io side to unified side
        gate_side = gate_order.get('side', 'buy')
        side = super().to_side(gate_side)
        
        # Convert Gate.io type to unified type
        gate_type = gate_order.get('type', 'limit')
        order_type = super().to_order_type(gate_type)
        
        # Gate.io API fields based on official documentation:
        # - filled_amount: actual filled amount (not filled_total)
        # - left: remaining amount to be filled
        filled_amount = float(gate_order.get('filled_amount', '0'))
        total_amount = float(gate_order.get('amount', '0'))
        remaining_amount = float(gate_order.get('left', total_amount - filled_amount))
        
        return Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=total_amount,
            price=float(gate_order.get('price', '0')) if gate_order.get('price') else None,
            filled_quantity=filled_amount,
            remaining_quantity=remaining_amount,
            status=status,
            timestamp=int(float(gate_order.get('create_time', '0')) * 1000)  # Convert to milliseconds
        )
    
    
    def format_quantity(self, quantity: float) -> str:
        """Format quantity for Gate.io API (typically 8 decimal places)."""
        return f"{quantity:.8f}".rstrip('0').rstrip('.')
    
    def format_price(self, price: float) -> str:
        """Format price for Gate.io API (typically 8 decimal places)."""
        return f"{price:.8f}".rstrip('0').rstrip('.')
    
    def get_order_params(self, order_type: OrderType, time_in_force: TimeInForce) -> dict:
        """Get additional order parameters for specific order types."""
        params = {}
        
        # Gate.io specific parameters based on order type
        if order_type == OrderType.MARKET:
            # Market orders don't need additional parameters in Gate.io
            pass
        elif order_type == OrderType.LIMIT:
            # Limit orders are default, no additional parameters needed
            pass
        elif order_type == OrderType.LIMIT_MAKER:
            # Post-only orders in Gate.io
            params['time_in_force'] = 'poc'  # Post-only
        
        return params
    
    # Channel Name Methods for WebSocket subscriptions
    def get_spot_channel_name(self, channel_type: PublicWebsocketChannelType) -> str:
        """Get Gate.io spot channel name for WebSocket channel type."""
        return self.SPOT_CHANNEL_MAPPING.get(
            channel_type,
            "spot.order_book_update"  # default
        )
    
    def get_futures_channel_name(self, channel_type: PublicWebsocketChannelType) -> str:
        """Get Gate.io futures channel name for WebSocket channel type."""
        # Gate.io futures uses similar structure to spot with futures prefix
        futures_mapping = {
            PublicWebsocketChannelType.BOOK_TICKER: "futures.tickers",
            PublicWebsocketChannelType.TRADES: "futures.trades",
            PublicWebsocketChannelType.ORDERBOOK: "futures.order_book",
            PublicWebsocketChannelType.TICKER: "futures.tickers"
        }
        return futures_mapping.get(channel_type, "futures.order_book")
    
    def get_futures_private_channel_name(self, channel_type: PrivateWebsocketChannelType) -> str:
        """Get Gate.io futures private channel name for WebSocket channel type."""
        # Gate.io futures private channels
        futures_private_mapping = {
            PrivateWebsocketChannelType.ORDER: "futures.orders",
            PrivateWebsocketChannelType.TRADE: "futures.usertrades", 
            PrivateWebsocketChannelType.BALANCE: "futures.balance"
        }
        return futures_private_mapping.get(channel_type, "futures.orders")
    
    def get_spot_private_channel_name(self, channel_type: PrivateWebsocketChannelType) -> str:
        """Get Gate.io spot private channel name for WebSocket channel type."""
        return self.PRIVATE_CHANNEL_MAPPING.get(
            channel_type,
            "spot.orders"  # default
        )
    
    def should_use_post_only(self, order_type: OrderType) -> bool:
        """Check if order type should use post_only flag for Gate.io."""
        return order_type == OrderType.LIMIT_MAKER
    
    # WebSocket event type methods
    def from_subscription_action(self, action) -> str:
        """Convert unified SubscriptionAction to Gate.io format."""
        from core.transport.websocket.structs import SubscriptionAction
        return "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe"
    
    
    def is_subscription_successful(self, status: str) -> bool:
        """Check if subscription status indicates success."""
        return status == "success"
    
    
