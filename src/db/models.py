"""
Database Models

Data structures for database operations using msgspec for maximum performance.
Optimized for HFT requirements with zero-copy serialization.
"""

from datetime import datetime
from typing import Optional
import msgspec

from exchanges.structs.common import Symbol


class BookTickerSnapshot(msgspec.Struct):
    """
    Book ticker snapshot data structure.
    
    Represents the best bid/ask prices and quantities at a specific moment.
    Optimized for high-frequency storage and retrieval.
    Works with normalized database schema using symbol_id foreign keys.
    """
    # Database fields (normalized schema)
    symbol_id: int
    
    # Book ticker data
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    
    # Timing
    timestamp: datetime
    created_at: Optional[datetime] = None
    id: Optional[int] = None
    
    # Transient fields for convenience (not stored in DB)
    exchange: Optional[str] = None
    symbol_base: Optional[str] = None
    symbol_quote: Optional[str] = None

    @classmethod
    def from_symbol_and_data(
        cls,
        exchange: str,
        symbol: Symbol,
        bid_price: float,
        bid_qty: float,
        ask_price: float,
        ask_qty: float,
        timestamp: datetime,
        symbol_id: Optional[int] = None
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
            symbol_id: Database symbol_id (required for normalized schema)
            
        Returns:
            BookTickerSnapshot instance
        """
        if symbol_id is None:
            raise ValueError("symbol_id is required for normalized database schema")
            
        return cls(
            symbol_id=symbol_id,
            bid_price=bid_price,
            bid_qty=bid_qty,
            ask_price=ask_price,
            ask_qty=ask_qty,
            timestamp=timestamp,
            # Store transient fields for convenience
            exchange=exchange.upper(),
            symbol_base=str(symbol.base),
            symbol_quote=str(symbol.quote)
        )
    
    def to_symbol(self) -> Symbol:
        """
        Convert back to Symbol object.
        
        Returns:
            Symbol object reconstructed from transient base/quote strings
        """
        if not self.symbol_base or not self.symbol_quote:
            raise ValueError("symbol_base and symbol_quote must be populated to create Symbol object")
            
        from exchanges.structs.types import AssetName
        return Symbol(
            base=AssetName(self.symbol_base),
            quote=AssetName(self.symbol_quote),
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


class FundingRateSnapshot(msgspec.Struct):
    """
    Funding rate snapshot data structure.
    
    Represents funding rate data for futures contracts at specific moments.
    Optimized for regular funding rate collection and analysis.
    """
    # Database fields (normalized schema)
    symbol_id: int
    
    # Funding rate data
    funding_rate: float  # Current funding rate (e.g., 0.0001 for 0.01%)
    funding_time: int    # Next funding time (Unix timestamp in milliseconds)
    
    # Timing
    timestamp: datetime
    created_at: Optional[datetime] = None
    id: Optional[int] = None
    
    # Transient fields for convenience (not stored in DB)
    exchange: Optional[str] = None
    symbol_base: Optional[str] = None
    symbol_quote: Optional[str] = None
    
    @classmethod
    def from_symbol_and_data(
        cls,
        exchange: str,
        symbol: Symbol,
        funding_rate: float,
        funding_time: Optional[int],
        timestamp: datetime,
        symbol_id: Optional[int] = None
    ) -> "FundingRateSnapshot":
        """
        Create FundingRateSnapshot from symbol and funding data.
        
        Args:
            exchange: Exchange identifier (GATEIO_FUTURES, etc.)
            symbol: Symbol object with base/quote assets
            funding_rate: Current funding rate (decimal, e.g., 0.0001)
            funding_time: Next funding time (Unix timestamp in milliseconds)
            timestamp: Collection timestamp
            symbol_id: Database symbol_id (required for normalized schema)
            
        Returns:
            FundingRateSnapshot instance
        """
        if symbol_id is None:
            raise ValueError("symbol_id is required for normalized database schema")
        
        # Handle None or invalid funding_time values
        # Database constraint requires funding_time > 0
        if funding_time is None or funding_time <= 0:
            # Use current timestamp + 8 hours as fallback (typical funding interval)
            import time
            funding_time = int(time.time() * 1000) + (8 * 60 * 60 * 1000)
            
        return cls(
            symbol_id=symbol_id,
            funding_rate=funding_rate,
            funding_time=funding_time,
            timestamp=timestamp,
            # Store transient fields for convenience
            exchange=exchange.upper(),
            symbol_base=str(symbol.base),
            symbol_quote=str(symbol.quote)
        )
    
    def to_symbol(self) -> Symbol:
        """
        Convert back to Symbol object.
        
        Returns:
            Symbol object reconstructed from transient base/quote strings
        """
        if not self.symbol_base or not self.symbol_quote:
            raise ValueError("symbol_base and symbol_quote must be populated to create Symbol object")
            
        from exchanges.structs.types import AssetName
        return Symbol(
            base=AssetName(self.symbol_base),
            quote=AssetName(self.symbol_quote),
        )
    
    def get_funding_rate_percentage(self) -> float:
        """
        Get funding rate as percentage.
        
        Returns:
            Funding rate as percentage (e.g., 0.01 for 0.01%)
        """
        return self.funding_rate * 100
    
    def get_funding_rate_bps(self) -> float:
        """
        Get funding rate in basis points.
        
        Returns:
            Funding rate in basis points (e.g., 1.0 for 0.01%)
        """
        return self.funding_rate * 10000
    
    def get_funding_datetime(self) -> datetime:
        """
        Convert funding_time to datetime object.
        
        Returns:
            Funding time as datetime
        """
        return datetime.fromtimestamp(self.funding_time / 1000)


class TradeSnapshot(msgspec.Struct):
    """
    Trade data snapshot structure.
    
    Represents individual trade execution data from exchanges.
    Optimized for high-frequency trade storage and analysis.
    """
    # Database fields
    
    # Exchange and symbol (required)
    exchange: str
    symbol_base: str
    symbol_quote: str
    
    # Trade data (required)
    price: float
    quantity: float
    side: str  # 'buy' or 'sell'
    timestamp: datetime
    
    # Optional fields come after required fields
    trade_id: Optional[str] = None
    created_at: Optional[datetime] = None
    id: Optional[int] = None
    quote_quantity: Optional[float] = None
    is_buyer: Optional[bool] = None
    is_maker: Optional[bool] = None
    
    @classmethod
    def from_trade_struct(
        cls,
        exchange: str,
        trade: "Trade"  # Import from structs.common
    ) -> "TradeSnapshot":
        """
        Create TradeSnapshot from Trade struct.
        
        Args:
            exchange: Exchange identifier (MEXC, GATEIO, etc.)
            trade: Trade struct from structs.common
            
        Returns:
            TradeSnapshot instance
        """
        from exchanges.structs import Side

        return cls(
            exchange=exchange.upper(),
            symbol_base=str(trade.symbol.base),
            symbol_quote=str(trade.symbol.quote),
            price=trade.price,
            quantity=trade.quantity,
            side='buy' if trade.side == Side.BUY else 'sell',
            trade_id=trade.trade_id,
            timestamp=datetime.fromtimestamp(trade.timestamp / 1000) if trade.timestamp else datetime.now(),
            quote_quantity=trade.quote_quantity,
            is_buyer=trade.is_buyer,
            is_maker=trade.is_maker
        )
    
    @classmethod
    def from_symbol_and_data(
        cls,
        exchange: str,
        symbol: Symbol,
        price: float,
        quantity: float,
        side: str,
        timestamp: datetime,
        trade_id: Optional[str] = None,
        quote_quantity: Optional[float] = None,
        is_buyer: Optional[bool] = None,
        is_maker: Optional[bool] = None
    ) -> "TradeSnapshot":
        """
        Create TradeSnapshot from individual components.
        
        Args:
            exchange: Exchange identifier
            symbol: Symbol object with composite/quote assets
            price: Trade execution price
            quantity: Trade quantity
            side: Trade side ('buy' or 'sell')
            timestamp: Trade timestamp
            trade_id: Optional trade ID
            quote_quantity: Optional quote asset quantity
            is_buyer: Optional buyer flag
            is_maker: Optional maker flag
            
        Returns:
            TradeSnapshot instance
        """
        return cls(
            exchange=exchange.upper(),
            symbol_base=str(symbol.base),
            symbol_quote=str(symbol.quote),
            price=price,
            quantity=quantity,
            side=side.lower(),
            trade_id=trade_id,
            timestamp=timestamp,
            quote_quantity=quote_quantity,
            is_buyer=is_buyer,
            is_maker=is_maker
        )
    
    def to_symbol(self) -> Symbol:
        """
        Convert back to Symbol object.
        
        Returns:
            Symbol object reconstructed from composite/quote strings
        """
        from exchanges.structs.types import AssetName
        return Symbol(
            base=AssetName(self.symbol_base),
            quote=AssetName(self.symbol_quote),
        )
    
    def to_trade_struct(self) -> "Trade":
        """
        Convert to Trade struct.
        
        Returns:
            Trade struct from structs.common
        """
        from exchanges.structs.common import Trade
        from exchanges.structs import Side

        return Trade(
            symbol=self.to_symbol(),
            side=Side.BUY if self.side.lower() == 'buy' else Side.SELL,
            quantity=self.quantity,
            price=self.price,
            timestamp=int(self.timestamp.timestamp() * 1000),
            quote_quantity=self.quote_quantity,
            trade_id=self.trade_id,
            is_buyer=self.is_buyer or False,
            is_maker=self.is_maker or False
        )
    
    def get_notional_value(self) -> float:
        """
        Calculate trade notional value (price * quantity).
        
        Returns:
            Notional value in quote currency
        """
        return self.price * self.quantity
    
    def get_symbol_string(self) -> str:
        """
        Get symbol as string for database queries.
        
        Returns:
            Symbol string (e.g., 'BTCUSDT')
        """
        return f"{self.symbol_base}{self.symbol_quote}"


