"""
Protocol interfaces for state machines to avoid heavy exchange dependencies.

This module defines minimal protocol interfaces that state machines can use
without importing the full exchange infrastructure, enabling standalone testing
and reducing import dependencies.
"""

from typing import Protocol, Optional, Dict, Any, List
from abc import abstractmethod


class SymbolProtocol(Protocol):
    """Protocol for trading symbol interface."""
    base: str
    quote: str
    is_futures: bool


class OrderProtocol(Protocol):
    """Protocol for trading order interface."""
    order_id: str
    symbol: SymbolProtocol
    side: str  # "BUY" or "SELL"
    quantity: float
    filled_quantity: float
    price: float
    average_price: float
    fee: Optional[float]


class BookTickerProtocol(Protocol):
    """Protocol for book ticker interface."""
    bid_price: float
    ask_price: float


class SymbolInfoProtocol(Protocol):
    """Protocol for symbol information interface."""
    tick: float  # Minimum price increment


class ExchangeProtocol(Protocol):
    """Base protocol for exchange interfaces."""
    
    @abstractmethod
    async def close(self) -> None:
        """Close exchange connection."""
        pass


class PublicExchangeProtocol(ExchangeProtocol):
    """Protocol for public exchange interface (market data)."""
    
    symbols_info: Dict[SymbolProtocol, SymbolInfoProtocol]
    
    @abstractmethod
    async def initialize(self, symbols: List[SymbolProtocol], channels: List[Any]) -> None:
        """Initialize exchange with symbols and channels."""
        pass
    
    @abstractmethod
    async def get_book_ticker(self, symbol: SymbolProtocol) -> BookTickerProtocol:
        """Get current book ticker for symbol."""
        pass


class PrivateExchangeProtocol(ExchangeProtocol):
    """Protocol for private exchange interface (trading operations)."""
    
    @abstractmethod
    async def initialize(self, symbols_info: Dict[SymbolProtocol, SymbolInfoProtocol], channels: List[Any]) -> None:
        """Initialize exchange with symbol info and channels."""
        pass
    
    @abstractmethod
    async def place_market_order(
        self, 
        symbol: SymbolProtocol, 
        side: str, 
        quote_quantity: float, 
        ensure: bool = True
    ) -> OrderProtocol:
        """Place a market order."""
        pass
    
    @abstractmethod
    async def place_limit_order(
        self,
        symbol: SymbolProtocol,
        side: str,
        quantity: float,
        price: float,
        time_in_force: Optional[str] = None
    ) -> OrderProtocol:
        """Place a limit order."""
        pass
    
    @abstractmethod
    async def get_order(self, symbol: SymbolProtocol, order_id: str) -> OrderProtocol:
        """Get order status."""
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: SymbolProtocol, order_id: str) -> OrderProtocol:
        """Cancel an order."""
        pass


class LoggerProtocol(Protocol):
    """Protocol for logger interface."""
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        pass
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        pass
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        pass


# Simple implementations for testing and standalone use
class SimpleSymbol:
    """Simple symbol implementation for testing."""
    
    def __init__(self, base: str, quote: str, is_futures: bool = False):
        self.base = base
        self.quote = quote
        self.is_futures = is_futures
    
    def __str__(self):
        return f"{self.base}/{self.quote}"
    
    def __repr__(self):
        return f"SimpleSymbol({self.base}, {self.quote}, {self.is_futures})"


class SimpleOrder:
    """Simple order implementation for testing."""
    
    def __init__(
        self,
        order_id: str,
        symbol: SymbolProtocol,
        side: str,
        quantity: float,
        price: float,
        fee: Optional[float] = None
    ):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.filled_quantity = quantity  # Assume filled for testing
        self.price = price
        self.average_price = price
        self.fee = fee or 0.0
    
    def __str__(self):
        return f"Order({self.order_id}, {self.side}, {self.quantity}@{self.price})"


class SimpleBookTicker:
    """Simple book ticker implementation for testing."""
    
    def __init__(self, bid_price: float, ask_price: float):
        self.bid_price = bid_price
        self.ask_price = ask_price


class SimpleSymbolInfo:
    """Simple symbol info implementation for testing."""
    
    def __init__(self, tick: float = 0.01):
        self.tick = tick


class SimpleLogger:
    """Simple logger implementation for testing."""
    
    def __init__(self, name: str = "test_logger"):
        self.name = name
    
    def info(self, message: str, **kwargs):
        print(f"INFO [{self.name}]: {message}")
        if kwargs:
            print(f"  {kwargs}")
    
    def error(self, message: str, **kwargs):
        print(f"ERROR [{self.name}]: {message}")
        if kwargs:
            print(f"  {kwargs}")
    
    def warning(self, message: str, **kwargs):
        print(f"WARNING [{self.name}]: {message}")
        if kwargs:
            print(f"  {kwargs}")