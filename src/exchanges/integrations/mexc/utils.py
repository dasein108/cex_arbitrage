"""
MEXC Direct Utility Functions

Replaces BaseExchangeMapper complexity with simple, direct functions.
No classes, no factories, no dependency injection - just direct transformations.

HFT COMPLIANT: Zero overhead function calls, no object instantiation.
"""

from typing import Dict
from exchanges.structs.common import (
    Side, OrderStatus, OrderType, TimeInForce, AssetBalance, Order, Trade, OrderBook, BookTicker
)
from exchanges.structs.types import OrderId, AssetName
from exchanges.structs.enums import KlineInterval, WithdrawalStatus

# MEXC -> Unified mappings (these could be module-level constants)
_MEXC_ORDER_STATUS_MAP = {
    'new': OrderStatus.NEW,
    'filled': OrderStatus.FILLED,
    'partially_filled': OrderStatus.PARTIALLY_FILLED,
    'cancelled': OrderStatus.CANCELED,
    'pending_cancel': OrderStatus.CANCELED,
    'rejected': OrderStatus.REJECTED,
    'expired': OrderStatus.EXPIRED,
    'open': OrderStatus.NEW,
    'partial': OrderStatus.PARTIALLY_FILLED,
}

_MEXC_SIDE_MAP = {
    'buy': Side.BUY,
    'sell': Side.SELL,
    'bid': Side.BUY,
    'ask': Side.SELL,
}

_MEXC_ORDER_TYPE_MAP = {
    'limit': OrderType.LIMIT,
    'market': OrderType.MARKET,
    'stop_loss': OrderType.STOP_MARKET,
    'stop_loss_limit': OrderType.STOP_LIMIT,
    'take_profit': OrderType.LIMIT_MAKER,  # Best available mapping
    'take_profit_limit': OrderType.STOP_LIMIT,
}

_MEXC_TIF_MAP = {
    'gtc': TimeInForce.GTC,
    'ioc': TimeInForce.IOC,
    'fok': TimeInForce.FOK,
}

# MEXC WebSocket Status Mapping (Unified enum -> MEXC integer)
_WS_STATUS_MAPPING = {
    1: OrderStatus.NEW,
    2: OrderStatus.PARTIALLY_FILLED,
    3: OrderStatus.FILLED,
    4: OrderStatus.CANCELED,
    5: OrderStatus.PARTIALLY_CANCELED,
    6: OrderStatus.REJECTED,
    7: OrderStatus.EXPIRED
}


# MEXC WebSocket Type Mapping (MEXC integer -> Unified enum)
_WS_TYPE_MAPPING = {
    1: OrderType.LIMIT,
    2: OrderType.MARKET,
    3: OrderType.LIMIT_MAKER,
    4: OrderType.IMMEDIATE_OR_CANCEL,
    5: OrderType.FILL_OR_KILL,
    6: OrderType.STOP_LIMIT,
    7: OrderType.STOP_MARKET
}


_MEXC_WITHDRAW_STATUS_MAP = {
    "APPLY": WithdrawalStatus.PENDING,
    "AUDITING": WithdrawalStatus.PENDING,
    "WAIT" : WithdrawalStatus.PENDING,
    "PROCESSING": WithdrawalStatus.PROCESSING,
    "WAIT_PACKAGING": WithdrawalStatus.PROCESSING,
    "WAIT_CONFIRM": WithdrawalStatus.PROCESSING,
    "SUCCESS": WithdrawalStatus.COMPLETED,
    "FAILED": WithdrawalStatus.FAILED,
    "CANCEL": WithdrawalStatus.CANCELED,
    "MANUAL": WithdrawalStatus.MANUAL_REVIEW
}

# Reverse mappings for unified -> MEXC
_UNIFIED_TO_MEXC_STATUS = {v: k for k, v in _MEXC_ORDER_STATUS_MAP.items()}
_UNIFIED_TO_MEXC_SIDE = {v: k for k, v in _MEXC_SIDE_MAP.items()}
_UNIFIED_TO_MEXC_TYPE = {v: k for k, v in _MEXC_ORDER_TYPE_MAP.items()}
_UNIFIED_TO_MEXC_TIF = {v: k for k, v in _MEXC_TIF_MAP.items()}



# Direct conversion functions - no classes needed
def to_order_status(mexc_status: str) -> OrderStatus:
    """Convert MEXC order status to unified OrderStatus."""
    return _MEXC_ORDER_STATUS_MAP.get(mexc_status.lower(), OrderStatus.UNKNOWN)


def from_order_status(unified_status: OrderStatus) -> str:
    """Convert unified OrderStatus to MEXC format."""
    return _UNIFIED_TO_MEXC_STATUS.get(unified_status, 'new')


def to_side(mexc_side: str) -> Side:
    """Convert MEXC side to unified Side."""
    return _MEXC_SIDE_MAP.get(mexc_side.lower(), Side.BUY)


def from_side(unified_side: Side) -> str:
    """Convert unified Side to MEXC format."""
    return _UNIFIED_TO_MEXC_SIDE.get(unified_side, 'buy')


def to_order_type(mexc_type: str) -> OrderType:
    """Convert MEXC order type to unified OrderType."""
    return _MEXC_ORDER_TYPE_MAP.get(mexc_type.lower(), OrderType.LIMIT)


def from_order_type(unified_type: OrderType) -> str:
    """Convert unified OrderType to MEXC format."""
    return _UNIFIED_TO_MEXC_TYPE.get(unified_type, 'limit')


def to_time_in_force(mexc_tif: str) -> TimeInForce:
    """Convert MEXC time in force to unified TimeInForce."""
    return _MEXC_TIF_MAP.get(mexc_tif.lower(), TimeInForce.GTC)


def from_time_in_force(unified_tif: TimeInForce) -> str:
    """Convert unified TimeInForce to MEXC format."""
    return _UNIFIED_TO_MEXC_TIF.get(unified_tif, 'gtc')


# Symbol mapping via direct singleton access
def to_symbol(pair_str: str):
    """Convert MEXC pair string to Symbol."""
    from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol
    return MexcSymbol.to_symbol(pair_str)


def from_symbol(symbol):
    """Convert Symbol to MEXC pair string."""
    from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol
    return MexcSymbol.to_pair(symbol)


# Additional utility functions for WebSocket and REST operations
def format_quantity(quantity: float, precision: int = 8) -> str:
    """Format quantity with standard precision handling."""
    formatted = f"{quantity:.{precision}f}".rstrip('0').rstrip('.')
    return formatted if formatted else "0"


def format_price(price: float, precision: int = 8) -> str:
    """Format price with standard precision handling."""
    formatted = f"{price:.{precision}f}".rstrip('0').rstrip('.')
    return formatted if formatted else "0"


def get_spot_private_channel_name(channel_type) -> str:
    """Get MEXC-specific spot private channel name."""
    from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType
    
    _PRIVATE_CHANNEL_MAPPING = {
        PrivateWebsocketChannelType.ORDER: "spot@private.orders.v3.api",
        PrivateWebsocketChannelType.TRADE: "spot@private.deals.v3.api",
        PrivateWebsocketChannelType.BALANCE: "spot@private.account.v3.api"
    }
    return _PRIVATE_CHANNEL_MAPPING.get(channel_type, "")


def get_spot_channel_name(channel_type) -> str:
    """Get MEXC-specific spot public channel name."""
    from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
    
    _PUBLIC_CHANNEL_MAPPING = {
        PublicWebsocketChannelType.BOOK_TICKER: "spot@public.aggre.bookTicker.v3.api.pb",
        PublicWebsocketChannelType.ORDERBOOK: "spot@public.increase.depth.v3.api",
        PublicWebsocketChannelType.TRADES: "spot@public.aggre.deals.v3.api.pb"
    }
    return _PUBLIC_CHANNEL_MAPPING.get(channel_type, "")


def from_subscription_action(action) -> str:
    """Convert SubscriptionAction to MEXC format."""
    from infrastructure.networking.websocket.structs import SubscriptionAction
    
    if action == SubscriptionAction.SUBSCRIBE:
        return "SUBSCRIPTION"
    elif action == SubscriptionAction.UNSUBSCRIBE:
        return "UNSUBSCRIPTION"
    return "SUBSCRIPTION"


def is_subscription_successful(status: str) -> bool:
    """Check if MEXC subscription was successful."""
    return status.lower() in ["success", "subscribed", "ok"]


def to_pair(symbol) -> str:
    """Convert Symbol to MEXC pair format."""
    return from_symbol(symbol)


def rest_to_order(mexc_order_data) -> Order:
    """Transform MEXC REST order response to unified Order struct."""
    
    # Convert MEXC symbol to unified Symbol
    symbol = to_symbol(mexc_order_data['symbol'])
    
    # Calculate fee from fills if available
    fee = 0.0
    if 'fills' in mexc_order_data and mexc_order_data['fills']:
        fee = sum(float(fill.get('commission', '0')) for fill in mexc_order_data['fills'])
    
    return Order(
        symbol=symbol,
        side=to_side(mexc_order_data['side']),
        order_type=to_order_type(mexc_order_data['type']),
        price=float(mexc_order_data['price']),
        quantity=float(mexc_order_data['origQty']),
        filled_quantity=float(mexc_order_data['executedQty']),
        order_id=OrderId(str(mexc_order_data['orderId'])),
        status=to_order_status(mexc_order_data['status']),
        timestamp=int(mexc_order_data['transactTime']) if mexc_order_data.get('transactTime') else None,
        fee=fee
    )


def ws_to_balance(mexc_ws_balance) -> AssetBalance:
    """Transform MEXC WebSocket balance data to unified AssetBalance struct."""
    
    return AssetBalance(
        asset=AssetName(mexc_ws_balance.asset),
        available=float(mexc_ws_balance.available),
        locked=float(mexc_ws_balance.locked)
    )


def ws_to_order(mexc_ws_order) -> Order:
    """Transform MEXC WebSocket order data to unified Order struct."""
    
    # Convert MEXC symbol to unified Symbol
    symbol = to_symbol(mexc_ws_order.symbol)
    
    # Map MEXC status codes to unified statuses
    status = _WS_STATUS_MAPPING.get(mexc_ws_order.status, OrderStatus.UNKNOWN)
    order_type = _WS_TYPE_MAPPING.get(mexc_ws_order.orderType, OrderType.LIMIT)
    
    # Parse side
    side = to_side(mexc_ws_order.side)
    
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


def ws_to_trade(mexc_ws_trade, symbol_str: str = None) -> Trade:
    """Transform MEXC WebSocket trade data to unified Trade struct."""
    
    # Handle both public and private trade structures
    if hasattr(mexc_ws_trade, 'p'):  # Public trade entry (MexcWSTradeEntry)
        side = Side.BUY if mexc_ws_trade.t == 1 else Side.SELL
        return Trade(
            symbol=to_symbol(symbol_str),
            price=float(mexc_ws_trade.p),
            quantity=float(mexc_ws_trade.q),
            quote_quantity=float(mexc_ws_trade.p) * float(mexc_ws_trade.q),
            side=side,
            timestamp=mexc_ws_trade.T,
            trade_id="",
            is_maker=False
        )
    else:  # Private trade data (MexcWSPrivateTradeData)
        side = Side.BUY if mexc_ws_trade.tradeType  == 1 else Side.SELL # Private data uses string side

        
        return Trade(
            symbol=to_symbol(symbol_str if symbol_str else mexc_ws_trade.symbol),
            price=float(mexc_ws_trade.price),
            quantity=float(mexc_ws_trade.quantity),
            quote_quantity=float(mexc_ws_trade.price) * float(mexc_ws_trade.quantity),
            side=side,
            timestamp=getattr(mexc_ws_trade, 'time', 0),
            trade_id="",
            is_maker=getattr(mexc_ws_trade, 'is_maker', False)
        )


def ws_to_orderbook(mexc_ws_orderbook, symbol_str: str = None) -> OrderBook:
    """Transform MEXC WebSocket orderbook data to unified OrderBook."""
    from exchanges.structs.common import OrderBookEntry
    
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
        symbol = to_symbol(symbol_str)
    elif hasattr(mexc_ws_orderbook, 'symbol'):
        symbol = to_symbol(mexc_ws_orderbook.symbol)
    else:
        symbol = None
    
    return OrderBook(
        symbol=symbol,
        bids=bids,
        asks=asks,
        timestamp=getattr(mexc_ws_orderbook, 'timestamp', 0),
        last_update_id=getattr(mexc_ws_orderbook, 'lastUpdateId', None)
    )


def ws_to_book_ticker(mexc_ws_ticker, symbol_str: str = None) -> BookTicker:
    """Transform MEXC WebSocket book ticker data to unified BookTicker."""
    
    # Get symbol from data or parameter
    if symbol_str:
        symbol = to_symbol(symbol_str)
    elif hasattr(mexc_ws_ticker, 'symbol'):
        symbol = to_symbol(mexc_ws_ticker.symbol)
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


def rest_to_balance(mexc_rest_balance) -> AssetBalance:
    """Transform MEXC REST balance response to unified AssetBalance."""
    
    return AssetBalance(
        asset=AssetName(mexc_rest_balance.get('asset', '')),
        available=float(mexc_rest_balance.get('free', '0')),
        locked=float(mexc_rest_balance.get('locked', '0'))
    )


def rest_to_withdrawal_status(mexc_status: str) -> WithdrawalStatus:
    """Convert MEXC withdrawal status to unified WithdrawalStatus."""
    return _MEXC_WITHDRAW_STATUS_MAP.get(mexc_status.upper(), WithdrawalStatus.UNKNOWN)

# All utility functions are directly available - no wrapper classes needed  
# Use direct function calls: to_order_status(), from_side(), etc.
# Use direct symbol mapping: MexcSymbol.to_pair(), MexcSymbol.to_symbol(), etc.