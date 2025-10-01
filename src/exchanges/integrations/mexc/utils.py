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
from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol

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
    "WAIT": WithdrawalStatus.PENDING,
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
    return _MEXC_ORDER_TYPE_MAP.get(mexc_type.upper(), OrderType.LIMIT)


def from_order_type(unified_type: OrderType) -> str:
    """Convert unified OrderType to MEXC format."""
    return _UNIFIED_TO_MEXC_TYPE.get(unified_type, 'limit')


def to_time_in_force(mexc_tif: str) -> TimeInForce:
    """Convert MEXC time in force to unified TimeInForce."""
    return _MEXC_TIF_MAP.get(mexc_tif, TimeInForce.GTC)


def from_time_in_force(unified_tif: TimeInForce) -> str:
    """Convert unified TimeInForce to MEXC format."""
    return _UNIFIED_TO_MEXC_TIF.get(unified_tif, 'gtc')


# Additional utility functions for WebSocket and REST operations
def format_quantity(quantity: float, precision: int = 8) -> str:
    """Format quantity with standard precision handling."""
    formatted = f"{quantity:.{precision}f}".rstrip('0').rstrip('.')
    return formatted if formatted else "0"


def format_price(price: float, precision: int = 8) -> str:
    """Format price with standard precision handling."""
    formatted = f"{price:.{precision}f}".rstrip('0').rstrip('.')
    return formatted if formatted else "0"


def from_subscription_action(action) -> str:
    """Convert SubscriptionAction to MEXC format."""
    from infrastructure.networking.websocket.structs import SubscriptionAction

    if action == SubscriptionAction.SUBSCRIBE:
        return "SUBSCRIPTION"
    elif action == SubscriptionAction.UNSUBSCRIBE:
        return "UNSUBSCRIPTION"
    return "SUBSCRIPTION"


def rest_to_order(mexc_order_data: MexcOrderResponse) -> Order:
    """Transform MEXC REST order response to unified Order struct."""

    # Convert MEXC symbol to unified Symbol
    symbol = MexcSymbol.to_symbol(mexc_order_data.symbol)

    # Calculate fee from fills if available
    fee = 0.0
    if mexc_order_data.fills:
        fee = sum(float(fill.get('commission', 0)) for fill in mexc_order_data.fills)

    filled_quantity = float(mexc_order_data.executedQty)
    quantity = float(mexc_order_data.origQty)
    order_type = to_order_type(mexc_order_data.type)

    return Order(
        symbol=symbol,
        side=to_side(mexc_order_data.side),
        order_type=order_type,
        price=float(mexc_order_data.price),
        quantity=filled_quantity if order_type == OrderType.MARKET else quantity,
        filled_quantity=filled_quantity,
        order_id=OrderId(str(mexc_order_data.orderId)),
        status=to_order_status(mexc_order_data.status),
        timestamp=int(mexc_order_data.transactTime),
        fee=fee,
        client_order_id=mexc_order_data.clientOrderId
    )


def rest_to_withdrawal_status(mexc_status: str) -> WithdrawalStatus:
    """Convert MEXC withdrawal status to unified WithdrawalStatus."""
    return _MEXC_WITHDRAW_STATUS_MAP.get(mexc_status.upper(), WithdrawalStatus.UNKNOWN)


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
