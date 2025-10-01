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
    Side, OrderStatus, OrderType, TimeInForce, AssetName, AssetBalance, Order
)
from exchanges.structs.types import OrderId
from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSpotSymbol


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
    """Convert SubscriptionAction to Gate.io format."""
    from infrastructure.networking.websocket.structs import SubscriptionAction
    
    if action == SubscriptionAction.SUBSCRIBE:
        return "subscribe"
    elif action == SubscriptionAction.UNSUBSCRIBE:
        return "unsubscribe"
    return "subscribe"



# TODO: implement for futures, refactor futures_rest, geti rid of fallabacks
def rest_futures_to_order(gateio_order_data) -> Order:
    raise NotImplementedError("Use the defined function below")


def rest_spot_to_order(gateio_order_data) -> Order:
    """Transform Gate.io REST order response to unified Order struct."""
    
    # Convert Gate.io symbol to unified Symbol
    symbol = GateioSpotSymbol.to_symbol(gateio_order_data['currency_pair'])
    
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



def reverse_lookup_order_type(gateio_type_str: str) -> OrderType:
    """Reverse lookup for Gate.io order type strings to unified OrderType."""
    # This handles the reverse mapping that was in the mapper
    return to_order_type(gateio_type_str)

