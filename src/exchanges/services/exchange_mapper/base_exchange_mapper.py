from abc import ABC, abstractmethod
from typing import Any

from exchanges.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from exchanges.structs.common import (Trade, OrderBook, BookTicker, AssetBalance,
                                      TimeInForce, KlineInterval,  OrderStatus, OrderType, Side)
from .base_exchange_classifier import BaseExchangeClassifiers
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType, SubscriptionAction
from exchanges.structs.common import (
    Symbol, Order
)


class BaseExchangeMapper(ABC):
    """
    Base implementation providing common mapping utilities.

    Implements shared functionality using configuration-driven approach.
    Exchange-specific implementations inherit and provide configuration.
    """

    def __init__(self, symbol_mapper: SymbolMapperInterface, config: BaseExchangeClassifiers):
        """Initialize with symbol mapper and mapping configuration."""
        self._symbol_mapper = symbol_mapper
        self._config = config

    # Symbol Mapping Methods (from BaseExchangeMapper)
    def to_symbol(self, pair: str) -> Symbol:
        """Convert exchange pair string to unified Symbol."""
        return self._symbol_mapper.to_symbol(pair)

    def to_pair(self, symbol: Symbol) -> str:
        """Convert unified Symbol to exchange pair string."""
        return self._symbol_mapper.to_pair(symbol)
    
    def is_supported_pair(self, pair: str) -> bool:
        """Check if trading pair string is supported by this exchange."""
        return self._symbol_mapper.is_supported_pair(pair)
    
    def validate_symbol(self, symbol: Symbol) -> bool:
        """Check if symbol is supported by this exchange."""
        return self._symbol_mapper.validate_symbol(symbol)

    def pair_to_symbol(self, pair_str: str) -> Symbol:
        """Convert exchange pair string to unified Symbol."""
        return self._symbol_mapper.to_symbol(pair_str)
    
    def symbol_to_pair(self, symbol: Symbol) -> str:
        """Convert unified Symbol to exchange pair string."""
        return self._symbol_mapper.to_pair(symbol)

    # Order Status Mapping Implementation
    def to_order_status(self, exchange_status: str) -> OrderStatus:
        """Convert exchange order status to unified OrderStatus."""
        return self._config.order_status_reverse.get(exchange_status, OrderStatus.UNKNOWN)

    def from_order_status(self, unified_status: OrderStatus) -> str:
        """Convert unified OrderStatus to exchange format."""
        return self._config.order_status_mapping.get(unified_status, 'NEW')

    # Order Type Mapping Implementation
    def from_order_type(self, unified_type: OrderType) -> str:
        """Convert unified OrderType to exchange format."""
        return self._config.order_type_mapping.get(unified_type, 'LIMIT')

    def to_order_type(self, exchange_type: str) -> OrderType:
        """Convert exchange order type to unified OrderType."""
        return self._config.order_type_reverse.get(exchange_type, OrderType.LIMIT)

    # Side Mapping Implementation
    def from_side(self, unified_side: Side) -> str:
        """Convert unified Side to exchange format."""
        return self._config.side_mapping.get(unified_side, 'BUY')

    def to_side(self, exchange_side: str) -> Side:
        """Convert exchange side to unified Side."""
        return self._config.side_reverse.get(exchange_side, Side.BUY)

    # Time In Force Mapping Implementation
    def from_time_in_force(self, unified_tif: TimeInForce) -> str:
        """Convert unified TimeInForce to exchange format."""
        return self._config.time_in_force_mapping.get(unified_tif, 'GTC')

    def to_time_in_force(self, exchange_tif: str) -> TimeInForce:
        """Convert exchange time in force to unified TimeInForce."""
        return self._config.time_in_force_reverse.get(exchange_tif, TimeInForce.GTC)

    # Interval Mapping Implementation
    def from_kline_interval(self, interval: KlineInterval) -> str:
        """Convert unified KlineInterval to exchange format."""
        return self._config.kline_interval_mapping.get(interval, "1h")
    
    def to_kline_interval(self, exchange_interval: str) -> KlineInterval:
        """Convert exchange interval to unified KlineInterval."""
        return self._config.kline_interval_reverse.get(exchange_interval, KlineInterval.HOUR_1)

    # Common Formatting Utilities
    def format_quantity(self, quantity: float, precision: int = 8) -> str:
        """Format quantity with standard precision handling."""
        formatted = f"{quantity:.{precision}f}".rstrip('0').rstrip('.')
        return formatted if formatted else "0"

    def format_price(self, price: float, precision: int = 8) -> str:
        """Format price with standard precision handling."""
        formatted = f"{price:.{precision}f}".rstrip('0').rstrip('.')
        return formatted if formatted else "0"

    # Abstract methods that must be implemented by exchanges
    @abstractmethod
    def rest_to_order(self, exchange_order: Any) -> Order:
        """Transform exchange REST order response to unified Order."""
        pass
    
    @abstractmethod
    def ws_to_order(self, ws_order_data: Any) -> Order:
        """Transform exchange WebSocket order data to unified Order."""
        pass
    
    @abstractmethod
    def ws_to_trade(self, ws_trade_data: Any, symbol_str: str = None) -> Trade:
        """Transform exchange WebSocket trade data to unified Trade."""
        pass
    
    @abstractmethod
    def ws_to_balance(self, ws_balance_data: Any) -> AssetBalance:
        """Transform exchange WebSocket balance data to unified AssetBalance."""
        pass
    
    @abstractmethod
    def ws_to_orderbook(self, ws_orderbook_data: Any, symbol_str: str = None) -> OrderBook:
        """Transform exchange WebSocket orderbook data to unified OrderBook."""
        pass
    
    @abstractmethod
    def ws_to_book_ticker(self, ws_ticker_data: Any, symbol_str: str = None) -> BookTicker:
        """Transform exchange WebSocket book ticker data to unified BookTicker."""
        pass
    
    @abstractmethod
    def rest_to_balance(self, rest_balance_data: Any) -> AssetBalance:
        """Transform exchange REST balance response to unified AssetBalance."""
        pass

    # Channel Name Methods for WebSocket subscriptions
    def get_spot_channel_name(self, channel_type: PublicWebsocketChannelType) -> str:
        """Get exchange-specific spot channel name for WebSocket channel type."""
        pass

    def get_futures_channel_subscription(self, channel_type: PublicWebsocketChannelType) -> str:
        """Get exchange-specific futures channel name for WebSocket channel type."""
        pass

    def get_futures_private_channel_name(self, channel_type: PrivateWebsocketChannelType) -> str:
        """Get exchange-specific futures private channel name for WebSocket channel type."""
        pass

    def get_spot_private_channel_name(self, channel_type: PrivateWebsocketChannelType) -> str:
        """Get exchange-specific spot private channel name for WebSocket channel type."""
        pass

    @abstractmethod
    def from_subscription_action(self, action: SubscriptionAction) -> str:
        """Convert unified SubscriptionAction to exchange format."""
        pass
