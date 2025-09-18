"""
Exchange-Agnostic Mapping Service Interface

Provides abstract interface and base implementation for converting between
unified exchange types and exchange-specific API formats. Designed for
dependency injection into REST and WebSocket clients.

HFT COMPLIANCE: Sub-microsecond mapping operations, zero-copy patterns.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

from structs.common import (
    Symbol, Order, OrderStatus, OrderType, Side,
    TimeInForce, KlineInterval
)

from core.cex.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface


class ExchangeMappingsInterface(ABC):
    """
    Abstract interface for exchange-specific data mapping operations.
    
    Provides standardized methods for converting between unified data types
    and exchange-specific API formats. Implementations handle exchange-specific
    mapping dictionaries and transformation logic.
    """
    
    def __init__(self, symbol_mapper: SymbolMapperInterface):
        """Initialize with injected symbol mapper dependency."""
        self._symbol_mapper = symbol_mapper

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

    # Order Status Mapping
    @abstractmethod
    def get_unified_order_status(self, exchange_status: str) -> OrderStatus:
        """Convert exchange order status to unified OrderStatus."""
        pass
    
    @abstractmethod
    def get_exchange_order_status(self, unified_status: OrderStatus) -> str:
        """Convert unified OrderStatus to exchange format."""
        pass
    
    # Order Type Mapping
    @abstractmethod
    def get_exchange_order_type(self, unified_type: OrderType) -> str:
        """Convert unified OrderType to exchange format."""
        pass
    
    @abstractmethod
    def get_unified_order_type(self, exchange_type: str) -> OrderType:
        """Convert exchange order type to unified OrderType."""
        pass
    
    # Side Mapping
    @abstractmethod
    def get_exchange_side(self, unified_side: Side) -> str:
        """Convert unified Side to exchange format."""
        pass
    
    @abstractmethod
    def get_unified_side(self, exchange_side: str) -> Side:
        """Convert exchange side to unified Side."""
        pass
    
    # Time In Force Mapping
    @abstractmethod
    def get_exchange_time_in_force(self, unified_tif: TimeInForce) -> str:
        """Convert unified TimeInForce to exchange format."""
        pass
    
    @abstractmethod
    def get_unified_time_in_force(self, exchange_tif: str) -> TimeInForce:
        """Convert exchange time in force to unified TimeInForce."""
        pass
    
    # Interval Mapping
    @abstractmethod
    def get_exchange_kline_interval(self, interval: KlineInterval) -> str:
        """Convert unified KlineInterval to exchange format."""
        pass
    
    # Formatting Methods
    @abstractmethod
    def format_quantity(self, quantity: float, precision: int = 8) -> str:
        """Format quantity to exchange precision requirements."""
        pass
    
    @abstractmethod
    def format_price(self, price: float, precision: int = 8) -> str:
        """Format price to exchange precision requirements."""
        pass
    
    # Symbol Conversion
    def pair_to_symbol(self, pair_str: str) -> Symbol:
        """Convert exchange pair string to unified Symbol."""
        return self._symbol_mapper.to_symbol(pair_str)
    
    def symbol_to_pair(self, symbol: Symbol) -> str:
        """Convert unified Symbol to exchange pair string."""
        return self._symbol_mapper.to_pair(symbol)
    
    # Order Transformation
    @abstractmethod
    def transform_exchange_order_to_unified(self, exchange_order: Any) -> Order:
        """Transform exchange order response to unified Order."""
        pass


class MappingConfiguration:
    """
    Configuration container for exchange-specific mapping dictionaries.
    
    Stores all mapping dictionaries used by an exchange implementation.
    Enables configuration-driven mapping without code changes.
    """
    
    def __init__(
        self,
        order_status_mapping: Dict[str, OrderStatus],
        order_type_mapping: Dict[OrderType, str],
        side_mapping: Dict[Side, str],
        time_in_force_mapping: Dict[TimeInForce, str],
        kline_interval_mapping: Dict[KlineInterval, str]
    ):
        # Forward mappings (unified -> exchange)
        self.order_status_mapping = order_status_mapping
        self.order_type_mapping = order_type_mapping
        self.side_mapping = side_mapping
        self.time_in_force_mapping = time_in_force_mapping
        self.kline_interval_mapping = kline_interval_mapping
        
        # Reverse mappings (exchange -> unified)
        self.order_status_reverse = {v: k for k, v in order_status_mapping.items()}
        self.order_type_reverse = {v: k for k, v in order_type_mapping.items()}
        self.side_reverse = {v: k for k, v in side_mapping.items()}
        self.time_in_force_reverse = {v: k for k, v in time_in_force_mapping.items()}


class BaseExchangeMappings(ExchangeMappingsInterface):
    """
    Base implementation providing common mapping utilities.
    
    Implements shared functionality using configuration-driven approach.
    Exchange-specific implementations inherit and provide configuration.
    """
    
    def __init__(self, symbol_mapper: SymbolMapperInterface, config: MappingConfiguration):
        """Initialize with symbol mapper and mapping configuration."""
        super().__init__(symbol_mapper)
        self._config = config
    
    # Order Status Mapping Implementation
    def get_unified_order_status(self, exchange_status: str) -> OrderStatus:
        """Convert exchange order status to unified OrderStatus."""
        return self._config.order_status_mapping.get(exchange_status, OrderStatus.UNKNOWN)
    
    def get_exchange_order_status(self, unified_status: OrderStatus) -> str:
        """Convert unified OrderStatus to exchange format."""
        return self._config.order_status_reverse.get(unified_status, 'UNKNOWN')
    
    # Order Type Mapping Implementation
    def get_exchange_order_type(self, unified_type: OrderType) -> str:
        """Convert unified OrderType to exchange format."""
        return self._config.order_type_mapping.get(unified_type, 'LIMIT')
    
    def get_unified_order_type(self, exchange_type: str) -> OrderType:
        """Convert exchange order type to unified OrderType."""
        return self._config.order_type_reverse.get(exchange_type, OrderType.LIMIT)
    
    # Side Mapping Implementation
    def get_exchange_side(self, unified_side: Side) -> str:
        """Convert unified Side to exchange format."""
        return self._config.side_mapping.get(unified_side, 'BUY')
    
    def get_unified_side(self, exchange_side: str) -> Side:
        """Convert exchange side to unified Side."""
        return self._config.side_reverse.get(exchange_side, Side.BUY)
    
    # Time In Force Mapping Implementation
    def get_exchange_time_in_force(self, unified_tif: TimeInForce) -> str:
        """Convert unified TimeInForce to exchange format."""
        return self._config.time_in_force_mapping.get(unified_tif, 'GTC')
    
    def get_unified_time_in_force(self, exchange_tif: str) -> TimeInForce:
        """Convert exchange time in force to unified TimeInForce."""
        return self._config.time_in_force_reverse.get(exchange_tif, TimeInForce.GTC)
    
    # Interval Mapping Implementation
    def get_exchange_kline_interval(self, interval: KlineInterval) -> str:
        """Convert unified KlineInterval to exchange format."""
        return self._config.kline_interval_mapping.get(interval, "1h")
    
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
    def transform_exchange_order_to_unified(self, exchange_order: Any) -> Order:
        """Transform exchange order response to unified Order."""
        pass