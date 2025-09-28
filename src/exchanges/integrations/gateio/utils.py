"""
Gate.io Direct Utility Functions

Replaces BaseExchangeMapper complexity with simple, direct functions.
No classes, no factories, no dependency injection - just direct transformations.

HFT COMPLIANT: Zero overhead function calls, no object instantiation.
"""

from typing import Dict, Optional
import re
from enum import Enum
from exchanges.structs.common import (
    Side, OrderStatus, OrderType, TimeInForce, AssetName, AssetBalance, Order, Trade, OrderBook, BookTicker, Symbol
)
from exchanges.structs.types import OrderId
from exchanges.structs.enums import KlineInterval


# Event types for Gate.io WebSocket
class EventType(Enum):
    """Gate.io WebSocket event types."""
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    UPDATE = "update"

# Gate.io -> Unified mappings (these could be module-level constants)
_GATEIO_ORDER_STATUS_MAP = {
    'open': OrderStatus.NEW,
    'closed': OrderStatus.FILLED,
    'cancelled': OrderStatus.CANCELED,
    'partial': OrderStatus.PARTIALLY_FILLED,
    'filled': OrderStatus.FILLED,
    'new': OrderStatus.NEW,
    'active': OrderStatus.NEW,
    'inactive': OrderStatus.CANCELED,
}

_GATEIO_SIDE_MAP = {
    'buy': Side.BUY,
    'sell': Side.SELL,
}

_GATEIO_ORDER_TYPE_MAP = {
    'limit': OrderType.LIMIT,
    'market': OrderType.MARKET,
    'stop': OrderType.STOP_MARKET,
    'stop_limit': OrderType.STOP_LIMIT,
}

_GATEIO_TIF_MAP = {
    'gtc': TimeInForce.GTC,
    'ioc': TimeInForce.IOC,
    'fok': TimeInForce.FOK,
}

# Reverse mappings for unified -> Gate.io
_UNIFIED_TO_GATEIO_STATUS = {v: k for k, v in _GATEIO_ORDER_STATUS_MAP.items()}
_UNIFIED_TO_GATEIO_SIDE = {v: k for k, v in _GATEIO_SIDE_MAP.items()}
_UNIFIED_TO_GATEIO_TYPE = {v: k for k, v in _GATEIO_ORDER_TYPE_MAP.items()}
_UNIFIED_TO_GATEIO_TIF = {v: k for k, v in _GATEIO_TIF_MAP.items()}


# Direct conversion functions - no classes needed
def to_order_status(gateio_status: str) -> OrderStatus:
    """Convert Gate.io order status to unified OrderStatus."""
    return _GATEIO_ORDER_STATUS_MAP.get(gateio_status.lower(), OrderStatus.UNKNOWN)


def from_order_status(unified_status: OrderStatus) -> str:
    """Convert unified OrderStatus to Gate.io format."""
    return _UNIFIED_TO_GATEIO_STATUS.get(unified_status, 'new')


def to_side(gateio_side: str) -> Side:
    """Convert Gate.io side to unified Side."""
    return _GATEIO_SIDE_MAP.get(gateio_side.lower(), Side.BUY)


def from_side(unified_side: Side) -> str:
    """Convert unified Side to Gate.io format."""
    return _UNIFIED_TO_GATEIO_SIDE.get(unified_side, 'buy')


def to_order_type(gateio_type: str) -> OrderType:
    """Convert Gate.io order type to unified OrderType."""
    return _GATEIO_ORDER_TYPE_MAP.get(gateio_type.lower(), OrderType.LIMIT)


def from_order_type(unified_type: OrderType) -> str:
    """Convert unified OrderType to Gate.io format."""
    return _UNIFIED_TO_GATEIO_TYPE.get(unified_type, 'limit')


def to_time_in_force(gateio_tif: str) -> TimeInForce:
    """Convert Gate.io time in force to unified TimeInForce."""
    return _GATEIO_TIF_MAP.get(gateio_tif.lower(), TimeInForce.GTC)


def from_time_in_force(unified_tif: TimeInForce) -> str:
    """Convert unified TimeInForce to Gate.io format."""
    return _UNIFIED_TO_GATEIO_TIF.get(unified_tif, 'gtc')


# Symbol mapping via direct singleton access
def to_symbol(pair_str: str):
    """Convert Gate.io pair string to Symbol."""
    from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSpotSymbol
    return GateioSpotSymbol.to_symbol(pair_str)


def from_symbol(symbol):
    """Convert Symbol to Gate.io pair string."""
    from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSpotSymbol
    return GateioSpotSymbol.to_pair(symbol)


# Futures-specific symbol mapping
def to_futures_symbol(contract_str: str):
    """Convert Gate.io futures contract string to Symbol."""
    from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbol
    return GateioFuturesSymbol.to_symbol(contract_str)


def from_futures_symbol(symbol):
    """Convert Symbol to Gate.io futures contract string."""
    from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbol
    return GateioFuturesSymbol.to_pair(symbol)


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
    """Get Gate.io-specific spot private channel name."""
    from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType
    
    _PRIVATE_CHANNEL_MAPPING = {
        PrivateWebsocketChannelType.ORDER: "spot.orders",
        PrivateWebsocketChannelType.TRADE: "spot.usertrades",
        PrivateWebsocketChannelType.BALANCE: "spot.balances"
    }
    return _PRIVATE_CHANNEL_MAPPING.get(channel_type, "")


def get_futures_private_channel_name(channel_type) -> str:
    """Get Gate.io-specific futures private channel name."""
    from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType
    
    _FUTURES_PRIVATE_CHANNEL_MAPPING = {
        PrivateWebsocketChannelType.ORDER: "futures.orders",
        PrivateWebsocketChannelType.TRADE: "futures.usertrades",
        PrivateWebsocketChannelType.BALANCE: "futures.balances"
    }
    return _FUTURES_PRIVATE_CHANNEL_MAPPING.get(channel_type, "")


def get_spot_channel_name(channel_type) -> str:
    """Get Gate.io-specific spot public channel name."""
    from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
    
    _SPOT_PUBLIC_CHANNEL_MAPPING = {
        PublicWebsocketChannelType.BOOK_TICKER: "spot.book_ticker",
        PublicWebsocketChannelType.ORDERBOOK: "spot.order_book",
        PublicWebsocketChannelType.TRADES: "spot.trades"
    }
    return _SPOT_PUBLIC_CHANNEL_MAPPING.get(channel_type, "")


def get_futures_channel_name(channel_type) -> str:
    """Get Gate.io-specific futures public channel name."""
    from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
    
    _FUTURES_PUBLIC_CHANNEL_MAPPING = {
        PublicWebsocketChannelType.BOOK_TICKER: "futures.book_ticker",
        PublicWebsocketChannelType.ORDERBOOK: "futures.order_book", 
        PublicWebsocketChannelType.TRADES: "futures.trades"
    }
    return _FUTURES_PUBLIC_CHANNEL_MAPPING.get(channel_type, "")


def from_subscription_action(action) -> str:
    """Convert SubscriptionAction to Gate.io format."""
    from infrastructure.networking.websocket.structs import SubscriptionAction
    
    if action == SubscriptionAction.SUBSCRIBE:
        return "subscribe"
    elif action == SubscriptionAction.UNSUBSCRIBE:
        return "unsubscribe"
    return "subscribe"


def is_subscription_successful(status: str) -> bool:
    """Check if Gate.io subscription was successful."""
    return status.lower() in ["success", "subscribed", "ok"]


def to_pair(symbol) -> str:
    """Convert Symbol to Gate.io pair format."""
    return from_symbol(symbol)


def rest_to_order(gateio_order_data) -> Order:
    """Transform Gate.io REST order response to unified Order struct."""
    
    # Convert Gate.io symbol to unified Symbol
    symbol = to_symbol(gateio_order_data['currency_pair'])
    
    # Calculate fee from order data if available
    fee = float(gateio_order_data.get('fee', '0'))
    
    return Order(
        symbol=symbol,
        side=to_side(gateio_order_data['side']),
        order_type=to_order_type(gateio_order_data['type']),
        price=float(gateio_order_data['price']),
        quantity=float(gateio_order_data['amount']),
        filled_quantity=float(gateio_order_data.get('filled_amount', '0')),
        order_id=OrderId(str(gateio_order_data['id'])),
        status=to_order_status(gateio_order_data['status']),
        timestamp=int(gateio_order_data['create_time_ms']) if gateio_order_data.get('create_time_ms') else None,
        fee=fee
    )


def rest_to_balance(gateio_balance_data) -> AssetBalance:
    """Transform Gate.io REST balance response to unified AssetBalance struct."""
    
    return AssetBalance(
        asset=AssetName(gateio_balance_data['currency']),
        available=float(gateio_balance_data['available']),
        locked=float(gateio_balance_data['locked'])
    )


def get_order_params(order_type, time_in_force) -> dict:
    """Get additional order parameters based on order type and time in force."""
    # This function provided backward compatibility for complex mapper calls
    # Most parameters are handled directly in the place_order method
    return {}


def reverse_lookup_order_type(gateio_type_str: str) -> OrderType:
    """Reverse lookup for Gate.io order type strings to unified OrderType."""
    # This handles the reverse mapping that was in the mapper
    return to_order_type(gateio_type_str)


def rest_to_balance(gate_balance) -> AssetBalance:
    """Transform Gate.io balance response to unified AssetBalance."""
    
    return AssetBalance(
        asset=AssetName(gate_balance.get('currency', '')),
        available=float(gate_balance.get('available', '0')),  # Gate.io uses 'available' for free
        locked=float(gate_balance.get('locked', '0'))
    )


def ws_to_order(gate_ws_order) -> Order:
    """Transform Gate.io WebSocket order data to unified Order."""
    
    # Gate.io WebSocket order format
    symbol = to_symbol(gate_ws_order.get('currency_pair', ''))
    
    return Order(
        order_id=OrderId(gate_ws_order.get('id', '')),
        symbol=symbol,
        side=to_side(gate_ws_order.get('side', 'buy')),
        order_type=to_order_type(gate_ws_order.get('type', 'limit')),
        quantity=float(gate_ws_order.get('amount', '0')),
        price=float(gate_ws_order.get('price', '0')) if gate_ws_order.get('price') else None,
        filled_quantity=float(gate_ws_order.get('filled_amount', '0')),
        remaining_quantity=float(gate_ws_order.get('left', '0')),
        status=to_order_status(gate_ws_order.get('status', 'open')),
        timestamp=int(float(gate_ws_order.get('create_time', '0')) * 1000)
    )


def ws_to_trade(gate_ws_trade, symbol_str: str = None) -> Trade:
    """Transform Gate.io WebSocket trade data to unified Trade.
    
    Gate.io spot format:
    {
        "id": 309143071,
        "create_time": 1606292218,
        "side": "sell",
        "currency_pair": "GT_USDT",
        "amount": "16.4700000000",
        "price": "0.4705000000"
    }
    """
    
    # Get symbol from data or parameter
    if symbol_str:
        symbol = to_symbol(symbol_str)
    elif 'currency_pair' in gate_ws_trade:
        symbol = to_symbol(gate_ws_trade['currency_pair'])
    else:
        symbol = None
    
    # Gate.io provides create_time in seconds, convert to milliseconds
    create_time = gate_ws_trade.get('create_time', 0)
    timestamp = int(create_time * 1000) if create_time else 0
    
    price = float(gate_ws_trade.get('price', '0'))
    quantity = float(gate_ws_trade.get('amount', '0'))
    
    return Trade(
        symbol=symbol,
        price=price,
        quantity=quantity,
        quote_quantity=price * quantity,
        side=to_side(gate_ws_trade.get('side', 'buy')),
        timestamp=timestamp,
        trade_id=str(gate_ws_trade.get('id', '')),
        is_maker=gate_ws_trade.get('role', '') == 'maker'  # May not be available in public trades
    )


def ws_to_balance(gate_ws_balance) -> AssetBalance:
    """Transform Gate.io WebSocket balance data to unified AssetBalance."""
    
    return AssetBalance(
        asset=AssetName(gate_ws_balance.get('currency', '')),
        available=float(gate_ws_balance.get('available', '0')),
        locked=float(gate_ws_balance.get('locked', '0'))
    )


def ws_to_orderbook(gate_ws_orderbook, symbol_str: str = None) -> OrderBook:
    """Transform Gate.io WebSocket orderbook data to unified OrderBook.
    
    Gate.io spot format:
    {
        "t": 1606294781123,
        "s": "BTC_USDT", 
        "U": 48776301,
        "u": 48776306,
        "b": [["19137.74", "0.0001"]],  // [price, amount] arrays
        "a": [["19137.75", "0.6135"]]
    }
    """
    from exchanges.structs.common import OrderBookEntry
    
    bids = []
    asks = []
    
    # Parse Gate.io spot orderbook structure - arrays of [price, amount]
    if 'b' in gate_ws_orderbook and gate_ws_orderbook['b']:
        for bid_data in gate_ws_orderbook['b']:
            if len(bid_data) >= 2:
                price = float(bid_data[0])
                size = float(bid_data[1])
                bids.append(OrderBookEntry(price=price, size=size))
    
    if 'a' in gate_ws_orderbook and gate_ws_orderbook['a']:
        for ask_data in gate_ws_orderbook['a']:
            if len(ask_data) >= 2:
                price = float(ask_data[0])
                size = float(ask_data[1])
                asks.append(OrderBookEntry(price=price, size=size))
    
    # Get symbol from data or parameter
    if symbol_str:
        symbol = to_symbol(symbol_str)
    elif 's' in gate_ws_orderbook:
        symbol = to_symbol(gate_ws_orderbook['s'])  # Gate.io uses 's' for symbol
    else:
        symbol = None
    
    return OrderBook(
        symbol=symbol,
        bids=bids,
        asks=asks,
        timestamp=gate_ws_orderbook.get('t', 0),  # Gate.io uses 't' for timestamp
        last_update_id=gate_ws_orderbook.get('u', None)  # Gate.io uses 'u' for last update ID
    )


def ws_to_book_ticker(gate_ws_ticker, symbol_str: str = None) -> BookTicker:
    """Transform Gate.io WebSocket book ticker data to unified BookTicker."""
    
    # Get symbol from data or parameter
    if symbol_str:
        symbol = to_symbol(symbol_str)
    elif 'currency_pair' in gate_ws_ticker:
        symbol = to_symbol(gate_ws_ticker['currency_pair'])
    else:
        symbol = None
    
    return BookTicker(
        symbol=symbol,
        bid_price=float(gate_ws_ticker.get('b', '0')),
        bid_quantity=float(gate_ws_ticker.get('B', '0')),
        ask_price=float(gate_ws_ticker.get('a', '0')),
        ask_quantity=float(gate_ws_ticker.get('A', '0')),
        timestamp=int(gate_ws_ticker.get('t', 0)),
        update_id=gate_ws_ticker.get('u', 0)
    )


# Futures-specific transformation functions
def futures_ws_to_order(gate_ws_order) -> Order:
    """Transform Gate.io futures WebSocket order data to unified Order.
    
    Gate.io futures format uses 'contract' field and 'size' for quantity.
    """
    
    # Use futures symbol mapper
    symbol = to_futures_symbol(gate_ws_order.get('contract', ''))
    
    # Convert create_time to milliseconds if needed
    create_time = gate_ws_order.get('create_time', 0)
    timestamp = int(create_time * 1000) if create_time and create_time < 1e10 else int(create_time or 0)
    
    return Order(
        order_id=OrderId(str(gate_ws_order.get('id', ''))),
        symbol=symbol,
        side=to_side(gate_ws_order.get('side', 'buy')),
        order_type=to_order_type(gate_ws_order.get('type', 'limit')),
        quantity=float(gate_ws_order.get('size', '0')),  # Futures uses 'size'
        price=float(gate_ws_order.get('price', '0')) if gate_ws_order.get('price') else None,
        filled_quantity=float(gate_ws_order.get('filled_size', '0')),
        remaining_quantity=float(gate_ws_order.get('left', '0')),
        status=to_order_status(gate_ws_order.get('status', 'open')),
        timestamp=timestamp
    )


def futures_ws_to_trade(gate_ws_trade) -> Trade:
    """Transform Gate.io futures WebSocket trade data to unified Trade.
    
    Gate.io futures format:
    {
        "size": -108,  // Negative means seller
        "id": 27753479,
        "create_time_ms": 1545136464123,
        "price": "96.4",
        "contract": "BTC_USD",
        "is_internal": true
    }
    """
    
    # Use futures symbol mapper
    symbol = to_futures_symbol(gate_ws_trade.get('contract', ''))
    
    # Handle size field - negative means sell, positive means buy
    size = float(gate_ws_trade.get('size', '0'))
    quantity = abs(size)
    side = Side.SELL if size < 0 else Side.BUY
    
    # Use create_time_ms if available, otherwise create_time in seconds
    timestamp = gate_ws_trade.get('create_time_ms', 0)
    if not timestamp:
        create_time = gate_ws_trade.get('create_time', 0)
        timestamp = int(create_time * 1000) if create_time else 0
    
    price = float(gate_ws_trade.get('price', '0'))
    
    return Trade(
        symbol=symbol,
        price=price,
        quantity=quantity,
        quote_quantity=price * quantity,
        side=side,
        timestamp=int(timestamp),
        trade_id=str(gate_ws_trade.get('id', '')),
        is_maker=gate_ws_trade.get('role', '') == 'maker'  # May not be available
    )


def futures_ws_to_orderbook(gate_ws_orderbook, symbol_str: str = None) -> OrderBook:
    """Transform Gate.io futures WebSocket orderbook data to unified OrderBook.
    
    Gate.io futures format:
    {
        "t": 1615366381417,
        "s": "BTC_USD", 
        "U": 2517661101,
        "u": 2517661113,
        "b": [{"p": "54672.1", "s": 0}],  // {price, size} objects
        "a": [{"p": "54743.6", "s": 0}],
        "l": "100"
    }
    """
    from exchanges.structs.common import OrderBookEntry
    
    bids = []
    asks = []
    
    # Parse Gate.io futures orderbook structure - objects with {"p": price, "s": size}
    if 'b' in gate_ws_orderbook and gate_ws_orderbook['b']:
        for bid_data in gate_ws_orderbook['b']:
            if isinstance(bid_data, dict) and 'p' in bid_data and 's' in bid_data:
                price = float(bid_data['p'])
                size = float(bid_data['s'])
                if size > 0:  # Only include non-zero sizes
                    bids.append(OrderBookEntry(price=price, size=size))
    
    if 'a' in gate_ws_orderbook and gate_ws_orderbook['a']:
        for ask_data in gate_ws_orderbook['a']:
            if isinstance(ask_data, dict) and 'p' in ask_data and 's' in ask_data:
                price = float(ask_data['p'])
                size = float(ask_data['s'])
                if size > 0:  # Only include non-zero sizes
                    asks.append(OrderBookEntry(price=price, size=size))
    
    # Get symbol from data or parameter
    if symbol_str:
        symbol = to_futures_symbol(symbol_str)
    elif 's' in gate_ws_orderbook:
        symbol = to_futures_symbol(gate_ws_orderbook['s'])  # Gate.io uses 's' for contract
    else:
        symbol = None
    
    return OrderBook(
        symbol=symbol,
        bids=bids,
        asks=asks,
        timestamp=gate_ws_orderbook.get('t', 0),
        last_update_id=gate_ws_orderbook.get('u', None)
    )


def futures_ws_to_book_ticker(gate_ws_ticker, symbol_str: str = None) -> BookTicker:
    """Transform Gate.io futures WebSocket book ticker data to unified BookTicker.
    
    Gate.io futures format:
    {
        "t": 1615366379123,
        "u": 2517661076,
        "s": "BTC_USD",
        "b": "54696.6",  // Best bid price
        "B": 37000,     // Best bid size (number, not string)
        "a": "54696.7",  // Best ask price
        "A": 47061      // Best ask size (number, not string)
    }
    """
    
    # Get symbol from data or parameter
    if symbol_str:
        symbol = to_futures_symbol(symbol_str)
    elif 's' in gate_ws_ticker:
        symbol = to_futures_symbol(gate_ws_ticker['s'])
    else:
        symbol = None
    
    return BookTicker(
        symbol=symbol,
        bid_price=float(gate_ws_ticker.get('b', '0')),
        bid_quantity=float(gate_ws_ticker.get('B', 0)),  # Futures uses number, not string
        ask_price=float(gate_ws_ticker.get('a', '0')),
        ask_quantity=float(gate_ws_ticker.get('A', 0)),  # Futures uses number, not string
        timestamp=int(gate_ws_ticker.get('t', 0)),
        update_id=gate_ws_ticker.get('u', 0)
    )


def futures_ws_to_balance(gate_ws_balance) -> AssetBalance:
    """Transform Gate.io futures WebSocket balance data to unified AssetBalance."""
    
    return AssetBalance(
        asset=AssetName(gate_ws_balance.get('currency', '')),
        available=float(gate_ws_balance.get('available', '0')),
        locked=float(gate_ws_balance.get('locked', '0'))
    )


# Symbol extraction utility functions for Gate.io WebSocket messages
def extract_symbol_from_data(data: Dict[str, any], fields: list[str] = None) -> Optional[str]:
    """Extract symbol from Gate.io message data."""
    # Gate.io uses different fields for different message types
    if fields is None:
        fields = ['s', 'symbol', 'currency_pair', 'contract', 'pair', 'market']
    
    for field in fields:
        symbol_str = data.get(field)
        if symbol_str and isinstance(symbol_str, str):
            return symbol_str
    return None


def extract_symbol_from_channel(channel: str) -> Optional[str]:
    """Extract symbol from Gate.io channel name."""
    # Gate.io format: "spot.trades.BTC_USDT" or "futures.book_ticker.BTC_USD"
    if '.' in channel:
        parts = channel.split('.')
        if len(parts) >= 3:
            return parts[-1]  # Last part is symbol
    return None


def convert_spot_symbol_string(symbol_str: str) -> Optional[Symbol]:
    """Convert Gate.io spot symbol string to unified Symbol."""
    return to_symbol(symbol_str)


def convert_futures_symbol_string(symbol_str: str) -> Optional[Symbol]:
    """Convert Gate.io futures symbol string to unified Symbol."""
    return to_futures_symbol(symbol_str)


# All utility functions are directly available - no wrapper classes needed
# Use direct function calls: to_order_status(), from_side(), etc.
# Use direct symbol mapping: GateioSpotSymbol.to_pair(), GateioFuturesSymbol.to_symbol(), etc.