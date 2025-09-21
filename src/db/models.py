"""
Database Models

Data structures for database operations using msgspec for maximum performance.
Optimized for HFT requirements with zero-copy serialization.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
import msgspec

from structs.common import Symbol


class BookTickerSnapshot(msgspec.Struct):
    """
    Book ticker snapshot data structure.
    
    Represents the best bid/ask prices and quantities at a specific moment.
    Optimized for high-frequency storage and retrieval.
    """
    # Database fields

    # Exchange and symbol
    exchange: str
    symbol_base: str
    symbol_quote: str
    
    # Book ticker data
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    
    # Timing
    timestamp: datetime
    created_at: Optional[datetime] = None
    id: Optional[int] = None

    @classmethod
    def from_symbol_and_data(
        cls,
        exchange: str,
        symbol: Symbol,
        bid_price: float,
        bid_qty: float,
        ask_price: float,
        ask_qty: float,
        timestamp: datetime
    ) -> "BookTickerSnapshot":
        """
        Create BookTickerSnapshot from symbol and ticker data.
        
        Args:
            exchange: Exchange identifier (MEXC, GATEIO, etc.)
            symbol: Symbol object with base/quote assets
            bid_price: Best bid price
            bid_qty: Best bid quantity
            ask_price: Best ask price
            ask_qty: Best ask quantity
            timestamp: Exchange timestamp
            
        Returns:
            BookTickerSnapshot instance
        """
        return cls(
            exchange=exchange.upper(),
            symbol_base=str(symbol.base),
            symbol_quote=str(symbol.quote),
            bid_price=bid_price,
            bid_qty=bid_qty,
            ask_price=ask_price,
            ask_qty=ask_qty,
            timestamp=timestamp
        )
    
    def to_symbol(self) -> Symbol:
        """
        Convert back to Symbol object.
        
        Returns:
            Symbol object reconstructed from base/quote strings
        """
        from structs.common import AssetName
        return Symbol(
            base=AssetName(self.symbol_base),
            quote=AssetName(self.symbol_quote),
            is_futures=False
        )
    
    def get_spread(self) -> float:
        """
        Calculate bid-ask spread.
        
        Returns:
            Absolute spread (ask_price - bid_price)
        """
        return self.ask_price - self.bid_price
    
    def get_spread_percentage(self) -> float:
        """
        Calculate bid-ask spread as percentage.
        
        Returns:
            Spread percentage relative to mid price
        """
        mid_price = (self.bid_price + self.ask_price) / 2
        return (self.get_spread() / mid_price) * 100 if mid_price > 0 else 0.0
    
    def get_mid_price(self) -> float:
        """
        Calculate mid price (average of bid and ask).
        
        Returns:
            Mid price
        """
        return (self.bid_price + self.ask_price) / 2


