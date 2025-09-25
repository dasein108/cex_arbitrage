"""
Common Order Validators for Exchange Implementations

Provides robust order validation logic that can be shared across exchange implementations
while allowing for exchange-specific customization.

HFT COMPLIANCE: Fast validation with minimal latency impact.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Set
from decimal import Decimal
from exchanges.structs.common import Symbol, OrderType, SymbolsInfo
from exchanges.structs import Side
from infrastructure.logging import HFTLoggerInterface


class OrderValidationError(Exception):
    """Raised when order parameters fail validation."""
    pass


class BaseOrderValidator(ABC):
    """
    Abstract base class for exchange-specific order validators.
    
    Provides common validation patterns while allowing exchange-specific
    customization through template methods.
    """
    
    def __init__(self, symbols_info: Optional[SymbolsInfo] = None, logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize order validator.
        
        Args:
            symbols_info: Symbol trading information (precision, limits, etc.)
            logger: Logger for validation warnings
        """
        self.symbols_info = symbols_info or {}
        self.logger = logger
        self._supported_symbols: Set[Symbol] = set(symbols_info.keys()) if symbols_info else set()
    
    def validate_order(self, symbol: Symbol, side: Side, quantity: float, price: Optional[float], order_type: OrderType) -> None:
        """
        Comprehensive order validation.
        
        Args:
            symbol: Trading symbol
            side: Order side (BUY/SELL)
            quantity: Order quantity
            price: Order price (required for limit orders)
            order_type: Type of order (LIMIT/MARKET)
            
        Raises:
            OrderValidationError: If any validation fails
        """
        # Basic parameter validation
        self._validate_basic_params(symbol, side, quantity, price, order_type)
        
        # Symbol-specific validation
        self._validate_symbol_specific(symbol, side, quantity, price, order_type)
        
        # Exchange-specific validation
        self._validate_exchange_specific(symbol, side, quantity, price, order_type)
    
    def _validate_basic_params(self, symbol: Symbol, side: Side, quantity: float, price: Optional[float], order_type: OrderType) -> None:
        """Validate basic order parameters."""
        if not symbol:
            raise OrderValidationError("Symbol is required")
        
        if not isinstance(side, Side):
            raise OrderValidationError(f"Invalid side type: {type(side)}")
        
        if quantity <= 0:
            raise OrderValidationError(f"Quantity must be positive: {quantity}")
        
        if order_type == OrderType.LIMIT:
            if not price or price <= 0:
                raise OrderValidationError(f"Price must be positive for limit orders: {price}")
        
        # Check for reasonable numeric ranges (prevent overflow/underflow)
        if quantity > 1e15:
            raise OrderValidationError(f"Quantity too large: {quantity}")
        
        if price and price > 1e15:
            raise OrderValidationError(f"Price too large: {price}")
    
    def _validate_symbol_specific(self, symbol: Symbol, side: Side, quantity: float, price: Optional[float], order_type: OrderType) -> None:
        """Validate against symbol trading rules."""
        if not self.symbols_info:
            return  # Skip if no symbol info available
        
        symbol_info = self.symbols_info.get(symbol)
        if not symbol_info:
            if self.logger:
                self.logger.warning(f"No symbol info available for {symbol}")
            return
        
        # Validate quantity precision
        if hasattr(symbol_info, 'quantity_precision'):
            self._validate_precision(quantity, symbol_info.quantity_precision, "quantity")
        
        # Validate price precision
        if price and hasattr(symbol_info, 'price_precision'):
            self._validate_precision(price, symbol_info.price_precision, "price")
        
        # Validate minimum quantity
        if hasattr(symbol_info, 'min_quantity') and quantity < symbol_info.min_quantity:
            raise OrderValidationError(f"Quantity {quantity} below minimum {symbol_info.min_quantity} for {symbol}")
        
        # Validate maximum quantity
        if hasattr(symbol_info, 'max_quantity') and quantity > symbol_info.max_quantity:
            raise OrderValidationError(f"Quantity {quantity} above maximum {symbol_info.max_quantity} for {symbol}")
        
        # Validate minimum notional value
        if price and hasattr(symbol_info, 'min_notional'):
            notional = quantity * price
            if notional < symbol_info.min_notional:
                raise OrderValidationError(f"Order value {notional} below minimum notional {symbol_info.min_notional} for {symbol}")
    
    def _validate_precision(self, value: float, precision: int, field_name: str) -> None:
        """Validate decimal precision."""
        decimal_value = Decimal(str(value))
        decimal_places = abs(decimal_value.as_tuple().exponent)
        
        if decimal_places > precision:
            raise OrderValidationError(f"{field_name.title()} {value} has too many decimal places (max {precision})")
    
    @abstractmethod
    def _validate_exchange_specific(self, symbol: Symbol, side: Side, quantity: float, price: Optional[float], order_type: OrderType) -> None:
        """Exchange-specific validation logic - must be implemented by subclasses."""
        pass


class GateioOrderValidator(BaseOrderValidator):
    """Gate.io specific order validator."""
    
    # Gate.io specific constraints
    MAX_ORDERS_PER_SYMBOL = 200
    MIN_ORDER_VALUE_USDT = 1.0  # Minimum order value in USDT
    
    def _validate_exchange_specific(self, symbol: Symbol, side: Side, quantity: float, price: Optional[float], order_type: OrderType) -> None:
        """Gate.io specific validation rules."""
        # Gate.io requires minimum order value
        if price and symbol.quote in ['USDT', 'USDC', 'USD']:
            order_value = quantity * price
            if order_value < self.MIN_ORDER_VALUE_USDT:
                raise OrderValidationError(f"Order value {order_value} below Gate.io minimum {self.MIN_ORDER_VALUE_USDT} {symbol.quote}")
        
        # Additional Gate.io specific checks can be added here
        # Examples: lot size validation, tick size validation, etc.


class MexcOrderValidator(BaseOrderValidator):
    """MEXC specific order validator."""
    
    # MEXC specific constraints
    MAX_ORDERS_PER_SYMBOL = 100
    MIN_ORDER_VALUE_USDT = 5.0  # MEXC typically has higher minimum
    
    def _validate_exchange_specific(self, symbol: Symbol, side: Side, quantity: float, price: Optional[float], order_type: OrderType) -> None:
        """MEXC specific validation rules."""
        # MEXC requires minimum order value
        if price and symbol.quote in ['USDT', 'USDC']:
            order_value = quantity * price
            if order_value < self.MIN_ORDER_VALUE_USDT:
                raise OrderValidationError(f"Order value {order_value} below MEXC minimum {self.MIN_ORDER_VALUE_USDT} {symbol.quote}")
        
        # MEXC has stricter quantity limits for some pairs
        if symbol.quote == 'BTC' and quantity < 0.0001:
            raise OrderValidationError(f"BTC pair minimum quantity is 0.0001, got {quantity}")
        
        # Additional MEXC specific checks can be added here


# Utility function for creating validators
def create_order_validator(exchange_name: str, symbols_info: Optional[SymbolsInfo] = None, logger: Optional[HFTLoggerInterface] = None) -> BaseOrderValidator:
    """
    Factory function to create appropriate order validator for exchange.
    
    Args:
        exchange_name: Name of exchange ("gateio", "mexc", etc.)
        symbols_info: Symbol trading information
        logger: Logger instance
        
    Returns:
        Appropriate order validator instance
        
    Raises:
        ValueError: If exchange_name is not supported
    """
    exchange_name_lower = exchange_name.lower()
    
    if exchange_name_lower in ['gateio', 'gate.io', 'gate']:
        return GateioOrderValidator(symbols_info, logger)
    elif exchange_name_lower in ['mexc']:
        return MexcOrderValidator(symbols_info, logger)
    else:
        raise ValueError(f"Unsupported exchange for order validation: {exchange_name}")