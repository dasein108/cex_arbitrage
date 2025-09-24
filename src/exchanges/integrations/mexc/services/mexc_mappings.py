"""
MEXC Exchange Unified Mappings Implementation

Consolidated MEXC-specific mapper combining all mapping functionality:
- API format conversions and order transformations
- WebSocket channel mappings
- Error code mappings and exception handling
- Order status, type, and side conversions

HFT COMPLIANCE: Sub-microsecond mapping operations, zero-copy patterns.
"""

from typing import Any, Dict

from exchanges.structs.common import (
    Order, Trade, AssetBalance, OrderBook, OrderBookEntry, BookTicker, WithdrawalStatus
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import OrderStatus, OrderType, Side
from exchanges.services.exchange_mapper.base_exchange_mapper import BaseExchangeMapper
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from .mapping_configuration import create_mexc_mapping_configuration

class MexcUnifiedMappings(BaseExchangeMapper):
    """
    MEXC-specific unified mapping implementation.
    
    Consolidated mapper combining all MEXC mapping functionality:
    - API format conversions and order transformations
    - WebSocket channel mappings
    - Error code mappings and exception handling
    - Order status, type, and side conversions
    """
    
    
    # Spot WebSocket channel mappings (protobuf format) - mixed approach based on testing feedback
    SPOT_CHANNEL_MAPPING: Dict[PublicWebsocketChannelType, str] = {
        PublicWebsocketChannelType.BOOK_TICKER: "spot@public.aggre.bookTicker.v3.api.pb",
        PublicWebsocketChannelType.TRADES: "spot@public.aggre.deals.v3.api.pb", 
        PublicWebsocketChannelType.ORDERBOOK: "spot@public.aggre.depth.v3.api.pb",
        PublicWebsocketChannelType.TICKER: "spot@public.miniTickers.v3.api.pb"
    }
    
    # Private WebSocket channel mappings (synced with official MEXC docs)
    PRIVATE_CHANNEL_MAPPING: Dict[PrivateWebsocketChannelType, str] = {
        PrivateWebsocketChannelType.ORDER: "spot@private.orders.v3.api",
        PrivateWebsocketChannelType.TRADE: "spot@private.deals.v3.api",
        PrivateWebsocketChannelType.BALANCE: "spot@private.account.v3.api"
    }
    
    def __init__(self, symbol_mapper):
        """Initialize MEXC mappings with exchange-specific configuration."""
        config = create_mexc_mapping_configuration()
        super().__init__(symbol_mapper, config)

    def rest_to_order(self, mexc_order: Any) -> Order:
        """
        Transform MEXC order response to unified Order struct.
        
        Args:
            mexc_order: MEXC order response structure
            
        Returns:
            Unified Order struct
        """
        # Convert MEXC symbol to unified Symbol
        symbol = self.pair_to_symbol(mexc_order.symbol)
        
        # Calculate fee from fills if available
        fee = 0.0
        if hasattr(mexc_order, 'fills') and mexc_order.fills:
            fee = sum(float(fill.get('commission', '0')) for fill in mexc_order.fills)
        
        return Order(
            symbol=symbol,
            side=self.to_side(mexc_order.side),
            order_type=self.to_order_type(mexc_order.type),
            price=float(mexc_order.price),
            quantity=float(mexc_order.origQty),
            filled_quantity=float(mexc_order.executedQty),
            order_id=OrderId(str(mexc_order.orderId)),
            status=self.to_order_status(mexc_order.status),
            timestamp=int(mexc_order.transactTime) if mexc_order.transactTime else None,
            fee=fee
        )
    
    def ws_to_order(self, mexc_ws_order) -> Order:
        """
        Transform MEXC WebSocket order data to unified Order struct.
        
        Args:
            mexc_ws_order: MEXC WebSocket order data (MexcWSPrivateOrderData)
            
        Returns:
            Unified Order struct
        """
        # Use consolidated WebSocket mappings
        
        # Convert MEXC symbol to unified Symbol
        symbol = self.pair_to_symbol(mexc_ws_order.symbol)
        
        # Map MEXC status codes to unified statuses using composite mapper methods where possible
        status = self._config.ws_order_status_reverse.get(mexc_ws_order.status, OrderStatus.UNKNOWN)
        order_type = self._config.ws_order_status_reverse.get(mexc_ws_order.orderType, OrderType.LIMIT)
        
        # Parse side using composite mapper method
        side = self.to_side(mexc_ws_order.side)
        
        return Order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=float(mexc_ws_order.price),
            quantity=float(mexc_ws_order.quantity),
            filled_quantity=float(mexc_ws_order.filled_qty),
            order_id=OrderId(mexc_ws_order.order_id),
            status=status,
            timestamp=mexc_ws_order.updateTime,
            client_order_id=""
        )
    
    def ws_to_trade(self, mexc_ws_trade, symbol_str: str = None) -> Trade:
        """
        Transform MEXC WebSocket trade data to unified Trade struct.
        
        Args:
            mexc_ws_trade: MEXC WebSocket trade data (MexcWSPrivateTradeData or MexcWSTradeEntry)
            
        Returns:
            Unified Trade struct
        """
        # Handle both public and private trade structures
        # TODO: private vs public trade - bug
        if hasattr(mexc_ws_trade, 'p'):  # Public trade entry
            side = Side.BUY if mexc_ws_trade.tradeType == 1 else Side.SELL
            return Trade(
                symbol=self.pair_to_symbol(symbol_str),
                price=float(mexc_ws_trade.price),
                quantity=float(mexc_ws_trade.quantity),
                quote_quantity=float(mexc_ws_trade.price) * float(mexc_ws_trade.quantity),
                side=side,
                timestamp=mexc_ws_trade.time,
                trade_id="",
                is_maker=False
            )
        else:  # Private trade data
            # side = self.to_side(mexc_ws_trade.side)
            side = Side.BUY if mexc_ws_trade.tradeType == 1 else Side.SELL

            return Trade(
                symbol=self.pair_to_symbol(symbol_str),
                price=float(mexc_ws_trade.price),
                quantity=float(mexc_ws_trade.quantity),
                quote_quantity=float(mexc_ws_trade.price) * float(mexc_ws_trade.quantity),
                side=side,
                timestamp=mexc_ws_trade.time,
                trade_id="",
                is_maker=False#mexc_ws_trade.is_maker
            )
    
    def ws_to_balance(self, mexc_ws_balance) -> AssetBalance:
        """
        Transform MEXC WebSocket balance data to unified AssetBalance struct.
        
        Args:
            mexc_ws_balance: MEXC WebSocket balance data (MexcWSPrivateBalanceData)
            
        Returns:
            Unified AssetBalance struct
        """
        return AssetBalance(
            asset=AssetName(mexc_ws_balance.asset),
            free=float(mexc_ws_balance.free),
            locked=float(mexc_ws_balance.locked)
        )
    
    def ws_to_orderbook(self, mexc_ws_orderbook, symbol_str: str = None) -> OrderBook:
        """Transform MEXC WebSocket orderbook data to unified OrderBook."""
        # MEXC orderbook format from WebSocket
        bids = []
        asks = []
        
        # Parse MEXC orderbook structure
        if hasattr(mexc_ws_orderbook, 'bids') and mexc_ws_orderbook.bids:
            for bid_data in mexc_ws_orderbook.bids:
                if len(bid_data) >= 2:
                    price = float(bid_data[0])
                    size = float(bid_data[1])
                    bids.append(OrderBookEntry(price=price, size=size))
        
        if hasattr(mexc_ws_orderbook, 'asks') and mexc_ws_orderbook.asks:
            for ask_data in mexc_ws_orderbook.asks:
                if len(ask_data) >= 2:
                    price = float(ask_data[0])
                    size = float(ask_data[1])
                    asks.append(OrderBookEntry(price=price, size=size))
        
        # Get symbol from data or parameter
        if symbol_str:
            symbol = self.to_symbol(symbol_str)
        elif hasattr(mexc_ws_orderbook, 'symbol'):
            symbol = self.to_symbol(mexc_ws_orderbook.symbol)
        else:
            symbol = None
        
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=getattr(mexc_ws_orderbook, 'timestamp', 0),
            last_update_id=getattr(mexc_ws_orderbook, 'lastUpdateId', None)
        )
    
    def ws_to_book_ticker(self, mexc_ws_ticker, symbol_str: str = None) -> BookTicker:
        """Transform MEXC WebSocket book ticker data to unified BookTicker."""
        # Get symbol from data or parameter
        if symbol_str:
            symbol = self.to_symbol(symbol_str)
        elif hasattr(mexc_ws_ticker, 'symbol'):
            symbol = self.to_symbol(mexc_ws_ticker.symbol)
        else:
            symbol = None
        
        return BookTicker(
            symbol=symbol,
            bid_price=float(getattr(mexc_ws_ticker, 'bidPrice', 0)),
            bid_quantity=float(getattr(mexc_ws_ticker, 'bidQty', 0)),
            ask_price=float(getattr(mexc_ws_ticker, 'askPrice', 0)),
            ask_quantity=float(getattr(mexc_ws_ticker, 'askQty', 0)),
            timestamp=getattr(mexc_ws_ticker, 'timestamp', 0),
            update_id=getattr(mexc_ws_ticker, 'updateId', 0)
        )
    
    def rest_to_balance(self, mexc_rest_balance) -> AssetBalance:
        """Transform MEXC REST balance response to unified AssetBalance."""
        return AssetBalance(
            asset=AssetName(mexc_rest_balance.get('asset', '')),
            free=float(mexc_rest_balance.get('free', '0')),
            locked=float(mexc_rest_balance.get('locked', '0'))
        )
    
    # Channel Name Methods for WebSocket subscriptions
    def get_spot_channel_name(self, channel_type: PublicWebsocketChannelType) -> str:
        """Get MEXC spot channel name for WebSocket channel type.
        
        MEXC uses protobuf messages, but channel types are:
        - spot@public.deals.v3.api@{symbol}
        - spot@public.increase.depth.v3.api@{symbol} 
        """
        return self.SPOT_CHANNEL_MAPPING.get(
            channel_type,
            "spot@public.depth.v3.api.pb"  # default to orderbook
        )
    
    def get_futures_channel_name(self, channel_type: PublicWebsocketChannelType) -> str:
        """Get MEXC futures channel name for WebSocket channel type.
        
        MEXC futures uses similar structure to spot.
        """
        # MEXC futures channels (similar to spot but with futures prefix)
        futures_mapping = {
            PublicWebsocketChannelType.BOOK_TICKER: "futures@public.bookTicker.v3.api",
            PublicWebsocketChannelType.TRADES: "futures@public.aggre.deals.v3.api",
            PublicWebsocketChannelType.ORDERBOOK: "futures@public.depth.v3.api",
            PublicWebsocketChannelType.TICKER: "futures@public.miniTickers.v3.api"
        }
        return futures_mapping.get(
            channel_type,
            "futures@public.depth.v3.api"  # default to orderbook
        )
    
    def get_futures_private_channel_name(self, channel_type: PrivateWebsocketChannelType) -> str:
        """Get MEXC futures private channel name for WebSocket channel type.
        
        MEXC private channels:
        - futures@private.orders.v3.api
        - futures@private.deals.v3.api
        - futures@private.account.v3.api
        """
        # MEXC futures private channels
        futures_private_mapping = {
            PrivateWebsocketChannelType.ORDER: "futures@private.orders.v3.api",
            PrivateWebsocketChannelType.TRADE: "futures@private.deals.v3.api",
            PrivateWebsocketChannelType.BALANCE: "futures@private.account.v3.api"
        }
        return futures_private_mapping.get(
            channel_type,
            "futures@private.orders.v3.api"  # default to orders
        )
    
    def get_spot_private_channel_name(self, channel_type: PrivateWebsocketChannelType) -> str:
        """Get MEXC spot private channel name for WebSocket channel type.
        
        MEXC private channels:
        - spot@private.orders.v3.api
        - spot@private.deals.v3.api
        - spot@private.account.v3.api
        """
        return self.PRIVATE_CHANNEL_MAPPING.get(
            channel_type,
            "spot@private.orders.v3.api"  # default to orders
        )
    
    # WebSocket event type methods
    def from_subscription_action(self, action) -> str:
        """Convert unified SubscriptionAction to MEXC format."""
        from infrastructure.networking.websocket.structs import SubscriptionAction
        return "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION"
    
    
    def is_subscription_successful(self, status: str) -> bool:
        """Check if subscription status indicates success."""
        # MEXC typically uses different status indicators
        return status in ["success", "SUCCESS", "subscribed"]
    
    # WebSocket-specific mapping methods for backward compatibility
    def get_ws_order_status(self, status_code: int) -> OrderStatus:
        """Get unified order status from MEXC WebSocket status code."""
        return self._mexc_config.WS_STATUS_REVERSE.get(status_code, OrderStatus.UNKNOWN)
    
    def get_ws_order_type(self, type_code: int) -> OrderType:
        """Get unified order type from MEXC WebSocket type code."""
        return self._mexc_config.WS_TYPE_REVERSE.get(type_code, OrderType.LIMIT)
    
    # Backward compatibility properties
    @property
    def status_mapping(self):
        """Backward compatibility: access to WebSocket status mapping."""
        return self._mexc_config.WS_STATUS_REVERSE
    
    @property
    def type_mapping(self):
        """Backward compatibility: access to WebSocket type mapping."""
        return self._mexc_config.WS_TYPE_REVERSE


def map_mexc_withdrawal_status(mexc_status: int) -> WithdrawalStatus:
    """
    Map MEXC withdrawal status to our standard enum.

    MEXC status codes:
    0: Email Sent
    1: Cancelled
    2: Awaiting Approval
    3: Rejected
    4: Processing
    5: Failure
    6: Completed

    Args:
        mexc_status: MEXC withdrawal status code

    Returns:
        WithdrawalStatus: Standard withdrawal status enum value
    """
    status_map = {
        0: WithdrawalStatus.PENDING,     # Email Sent
        1: WithdrawalStatus.CANCELED,    # Cancelled
        2: WithdrawalStatus.PENDING,     # Awaiting Approval
        3: WithdrawalStatus.FAILED,      # Rejected
        4: WithdrawalStatus.PROCESSING,  # Processing
        5: WithdrawalStatus.FAILED,      # Failure
        6: WithdrawalStatus.COMPLETED    # Completed
    }
    return status_map.get(mexc_status, WithdrawalStatus.PENDING)