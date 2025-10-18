"""
Gate.io Direct Utility Functions

Replaces BaseExchangeMapper complexity with simple, direct functions.
No classes, no factories, no dependency injection - just direct transformations.

HFT COMPLIANT: Zero overhead function calls, no object instantiation.
"""

from typing import Dict, Optional, Any
from exchanges.structs.common import (
    Side, OrderStatus, OrderType, TimeInForce, AssetName, AssetBalance, FuturesBalance, Order
)
from exchanges.structs.enums import WithdrawalStatus, KlineInterval
from exchanges.structs.types import OrderId
from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSpotSymbol
from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbol


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

_GATEIO_WITHDRAW_STATUS_MAP = {
    "DONE": WithdrawalStatus.COMPLETED,
    "CANCEL": WithdrawalStatus.CANCELED,
    "REQUEST": WithdrawalStatus.PENDING,
    "PEND": WithdrawalStatus.PENDING,
    "VERIFY": WithdrawalStatus.PENDING,
    "MANUAL": WithdrawalStatus.PENDING,
    "REVIEW": WithdrawalStatus.PENDING,
    "EXTPEND": WithdrawalStatus.PROCESSING,
    "PROCES": WithdrawalStatus.PROCESSING,
    "FAIL": WithdrawalStatus.FAILED,
    "INVALID": WithdrawalStatus.FAILED,
    "DMOVE": WithdrawalStatus.PENDING,
    "BCODE": WithdrawalStatus.PROCESSING,
}

# Reverse mappings for unified -> Gate.io
# Gate.io Kline Interval Mapping (moved from symbol mapper)
_GATEIO_KLINE_INTERVAL_MAP = {
    KlineInterval.MINUTE_1: "1m",
    KlineInterval.MINUTE_5: "5m",
    KlineInterval.MINUTE_15: "15m",
    KlineInterval.MINUTE_30: "30m",
    KlineInterval.HOUR_1: "1h",
    KlineInterval.HOUR_4: "4h",
    KlineInterval.HOUR_12: "12h",
    KlineInterval.DAY_1: "1d",
    KlineInterval.WEEK_1: "7d",
    KlineInterval.MONTH_1: "30d"
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


def to_kline_interval(interval: KlineInterval) -> str:
    """Convert unified KlineInterval to Gate.io format."""
    return _GATEIO_KLINE_INTERVAL_MAP.get(interval, "1m")


def from_kline_interval(gateio_interval: str) -> KlineInterval:
    """Convert Gate.io interval string to unified KlineInterval."""
    reverse_map = {v: k for k, v in _GATEIO_KLINE_INTERVAL_MAP.items()}
    return reverse_map.get(gateio_interval, KlineInterval.MINUTE_1)


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

def detect_side_from_size(size: int) -> Side:
    """Determine side from Gate.io futures size."""
    return Side.BUY if size > 0 else Side.SELL


def futures_balance_entry(item: Dict) -> FuturesBalance:
    """
    Normalize futures balance entry into FuturesBalance with full margin information.
    Works for both dict and list entry from Gate.io futures API.
    """
    asset = AssetName(item.get("currency", item.get("asset", "USDT")))
    total = float(item.get("total", item.get("balance", 0)))
    available = float(item.get("available", 0))
    unrealized_pnl = float(item.get("unrealized_pnl", item.get("unrealised_pnl", 0)))
    position_margin = float(item.get("position_margin", 0))
    order_margin = float(item.get("order_margin", 0))
    
    # Optional cross margin fields
    cross_wallet_balance = item.get("cross_wallet_balance")
    cross_unrealized_pnl = item.get("cross_unrealized_pnl") 
    
    return FuturesBalance(
        asset=asset,
        total=total,
        available=available,
        unrealized_pnl=unrealized_pnl,
        position_margin=position_margin,
        order_margin=order_margin,
        cross_wallet_balance=float(cross_wallet_balance) if cross_wallet_balance is not None else None,
        cross_unrealized_pnl=float(cross_unrealized_pnl) if cross_unrealized_pnl is not None else None
    )

# TODO: implement for futures, refactor futures_rest, get rid of fallabacks
def rest_futures_to_order(order_data: Dict[str, Any]) -> Order:
    """Transform Gate.io REST futures order response to unified Order struct."""
    symbol = GateioFuturesSymbol.to_symbol(order_data['contract'])
    #Time in ms
    timestamp = int(order_data['create_time'] * 1000)
    price=float(order_data.get('fill_price', order_data.get('price', '0')))
    remaining_quantity=abs(float(order_data.get('left', '0')))
    quantity = abs(order_data['size'])
    order_type = (
        OrderType.MARKET 
        if price == 0 
        else OrderType.LIMIT)


    filled_quantity = quantity - remaining_quantity

    order_status = order_data.get('status', '').lower()
    if order_status in ['closed', 'finished']:
        if remaining_quantity == 0:
            order_status = OrderStatus.FILLED
        elif filled_quantity > 0:
            order_status = OrderStatus.PARTIALLY_FILLED
        else:
            order_status = OrderStatus.CANCELED
    else:
        order_status = OrderStatus.NEW

    return Order(
        symbol=symbol,
        order_id=OrderId(str(order_data['id'])),
        side=detect_side_from_size(order_data['size']),
        order_type=order_type,
        quantity=quantity,
        price=price,
        filled_quantity = filled_quantity,
        remaining_quantity=remaining_quantity,
        status=order_status,
        timestamp=timestamp,
        fee=float(order_data.get('fee', '0')),
        time_in_force=to_time_in_force(order_data.get('tif'))

    )

def rest_spot_to_order(order_data: Dict[str, Any]) -> Order:
    """Transform Gate.io REST order response to unified Order struct."""
    
    # Convert Gate.io symbol to unified Symbol
    symbol = GateioSpotSymbol.to_symbol(order_data['currency_pair'])
    
    # Calculate fee from order data if available
    fee = float(order_data.get('fee', '0'))
    price=float(order_data.get('fill_price', order_data.get('price', '0')))

    return Order(
        symbol=symbol,
        side=to_side(order_data['side']),
        order_type=to_order_type(order_data['type']),
        price=price,
        quantity=float(order_data['amount']),
        filled_quantity=float(order_data.get('filled_amount', '0')),
        order_id=OrderId(str(order_data['id'])),
        status=to_order_status(order_data['status']),
        timestamp=int(order_data['create_time_ms']) if order_data.get('create_time_ms') else None,
        fee=fee
    )

def to_withdrawal_status(status_str: str) -> WithdrawalStatus:
    """Convert GATEIO withdrawal status to unified WithdrawalStatus."""
    return _GATEIO_WITHDRAW_STATUS_MAP.get(status_str.upper(), WithdrawalStatus.UNKNOWN)

def reverse_lookup_order_type(type_str: str) -> OrderType:
    """Reverse lookup for Gate.io order type strings to unified OrderType."""
    # This handles the reverse mapping that was in the mapper
    return to_order_type(type_str)

