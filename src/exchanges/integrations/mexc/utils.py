"""
MEXC Direct Utility Functions

Replaces BaseExchangeMapper complexity with simple, direct functions.
No classes, no factories, no dependency injection - just direct transformations.

HFT COMPLIANT: Zero overhead function calls, no object instantiation.
"""

from typing import Dict, List, Optional
import re

from exchanges.integrations.mexc.structs.exchange import (
    MexcOrderResponse
)
from exchanges.structs import OrderStatus, OrderType
from exchanges.structs.common import (
    Side, OrderStatus, OrderType, TimeInForce, Order, Symbol
)
from exchanges.structs.types import OrderId
from exchanges.structs.enums import WithdrawalStatus

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
    'LIMIT': OrderType.LIMIT,
    'MARKET': OrderType.MARKET,
    'STOP_LOSS': OrderType.STOP_MARKET,
    'STOP_LOSS_LIMIT': OrderType.STOP_LIMIT,
    'TAKE_PROFIT': OrderType.LIMIT_MAKER,  # Best available mapping
    'TAKE_PROFIT_LIMIT': OrderType.STOP_LIMIT,
}

_MEXC_TIF_MAP = {
    'GTC': TimeInForce.GTC,
    'IOC': TimeInForce.IOC,
    'FOK': TimeInForce.FOK,
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
    return 'BUY' if unified_side == Side.BUY else 'SELL'


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
        PrivateWebsocketChannelType.EXECUTION: "spot@private.deals.v3.api",
        PrivateWebsocketChannelType.BALANCE: "spot@private.account.v3.api"
    }
    return _PRIVATE_CHANNEL_MAPPING.get(channel_type, "")


def get_spot_channel_name(channel_type) -> str:
    """Get MEXC-specific spot public channel name."""
    from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
    
    _PUBLIC_CHANNEL_MAPPING = {
        PublicWebsocketChannelType.BOOK_TICKER: "spot@public.aggre.bookTicker.v3.api.pb",
        PublicWebsocketChannelType.ORDERBOOK: "spot@public.increase.depth.v3.api",
        PublicWebsocketChannelType.PUB_TRADE: "spot@public.aggre.deals.v3.api.pb"
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


def rest_to_order(mexc_order_data: MexcOrderResponse) -> Order:
    """Transform MEXC REST order response to unified Order struct."""
    
    # Convert MEXC symbol to unified Symbol
    symbol = to_symbol(mexc_order_data.symbol)
    
    # Calculate fee from fills if available
    fee = 0.0
    if mexc_order_data.fills:
        fee = sum(float(fill.get('commission', 0)) for fill in mexc_order_data.fills)
    
    return Order(
        symbol=symbol,
        side=to_side(mexc_order_data.side),
        order_type=to_order_type(mexc_order_data.type),
        price=float(mexc_order_data.price),
        quantity=float(mexc_order_data.origQty),
        filled_quantity=float(mexc_order_data.executedQty),
        order_id=OrderId(str(mexc_order_data.orderId)),
        status=to_order_status(mexc_order_data.status),
        timestamp=int(mexc_order_data.transactTime),
        fee=fee,
        client_order_id=mexc_order_data.clientOrderId
    )


def rest_to_withdrawal_status(mexc_status: str) -> WithdrawalStatus:
    """Convert MEXC withdrawal status to unified WithdrawalStatus."""
    return _MEXC_WITHDRAW_STATUS_MAP.get(mexc_status.upper(), WithdrawalStatus.UNKNOWN)


# Symbol extraction utility functions for MEXC WebSocket messages
def extract_symbol_from_data(data: Dict[str, any], fields: List[str] = None) -> Optional[str]:
    """Extract symbol from MEXC message data."""
    # MEXC typically uses 'symbol' or 's' fields
    if fields is None:
        fields = ['s', 'symbol', 'currency_pair', 'contract', 'pair', 'market']
    
    for field in fields:
        symbol_str = data.get(field)
        if symbol_str and isinstance(symbol_str, str):
            return symbol_str
    return None


def extract_symbol_from_channel(channel: str) -> Optional[str]:
    """Extract symbol from MEXC channel name."""
    # MEXC format: "spot@public.bookTicker.v3.api@BTCUSDT"
    if '@' in channel and not channel.endswith(')'):
        # Look for symbol pattern at the end
        parts = channel.split('@')
        if parts:
            last_part = parts[-1]
            # MEXC symbols are typically all caps, no separators
            if re.match(r'^[A-Z]{2,10}USDT?$', last_part):
                return last_part
    return None


def convert_symbol_string(symbol_str: str) -> Optional[Symbol]:
    """Convert MEXC symbol string to unified Symbol."""
    return to_symbol(symbol_str)


_WS_ORDER_STATUS_MAPPING = {
    1: OrderStatus.NEW,
    2: OrderStatus.FILLED,
    3: OrderStatus.PARTIALLY_FILLED,
    4: OrderStatus.CANCELED,
}
_WS_ORDER_TYPE_MAPPING = {
    1: OrderType.LIMIT,
    2: OrderType.MARKET,
    3: OrderType.STOP_LIMIT,
    4: OrderType.STOP_MARKET,
}
