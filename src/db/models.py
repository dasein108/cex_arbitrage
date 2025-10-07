"""
Database Models

Data structures for database operations using msgspec for maximum performance.
Optimized for HFT requirements with zero-copy serialization.
"""

from datetime import datetime
from typing import Optional
from enum import IntEnum
import msgspec

from exchanges.structs.common import Symbol


class SymbolType(IntEnum):
    """Symbol type enumeration for database storage."""
    SPOT = 0
    FUTURES = 1


class Exchange(msgspec.Struct):
    """
    Exchange reference data structure.
    
    Represents supported cryptocurrency exchanges with their
    configuration and metadata for normalized database operations.
    Simplified to store only essential identification fields.
    """
    # Required fields
    name: str                                    # MEXC_SPOT, GATEIO_SPOT, etc.
    enum_value: str                              # Maps to ExchangeEnum
    display_name: str                            # User-friendly name
    market_type: str                             # SPOT, FUTURES, OPTIONS
    
    # Optional database ID
    id: Optional[int] = None
    
    def to_exchange_enum(self) -> "ExchangeEnum":
        """
        Convert to ExchangeEnum for application use.
        
        Returns:
            ExchangeEnum corresponding to this exchange
        """
        from exchanges.structs.enums import ExchangeEnum
        
        # Map enum_value string to ExchangeEnum
        for enum_item in ExchangeEnum:
            if str(enum_item.value) == self.enum_value:
                return enum_item
        
        raise ValueError(f"No ExchangeEnum found for value: {self.enum_value}")
    
    @classmethod
    def from_exchange_enum(cls, exchange_enum: "ExchangeEnum", **kwargs) -> "Exchange":
        """
        Create Exchange from ExchangeEnum with default values.
        
        Args:
            exchange_enum: ExchangeEnum to convert
            **kwargs: Additional field overrides
            
        Returns:
            Exchange instance with enum-based defaults
        """
        name = str(exchange_enum.value)
        
        # Default configurations per exchange
        defaults = {
            "MEXC_SPOT": {
                "display_name": "MEXC Spot Trading",
                "market_type": "SPOT",
                "base_url": "https://api.mexc.com",
                "websocket_url": "wss://wbs.mexc.com/ws",
                "rate_limit_requests_per_second": 100
            },
            "GATEIO_SPOT": {
                "display_name": "Gate.io Spot Trading", 
                "market_type": "SPOT",
                "base_url": "https://api.gateio.ws",
                "websocket_url": "wss://api.gateio.ws/ws/v4/",
                "rate_limit_requests_per_second": 100
            },
            "GATEIO_FUTURES": {
                "display_name": "Gate.io Futures Trading",
                "market_type": "FUTURES", 
                "base_url": "https://api.gateio.ws",
                "websocket_url": "wss://fx-ws.gateio.ws/v4/ws/",
                "rate_limit_requests_per_second": 100
            }
        }
        
        config = defaults.get(name, {})
        config.update(kwargs)
        
        return cls(
            name=name,
            enum_value=name,
            **config
        )
    
    def get_rate_limit_delay(self) -> float:
        """
        Calculate delay between requests to respect rate limits.
        
        Returns:
            Default delay (exchange-specific config should be used elsewhere)
        """
        return 0.01  # Default 100 requests/second
    
    def is_futures_exchange(self) -> bool:
        """Check if this is a futures trading exchange."""
        return self.market_type == "FUTURES"
    
    def is_spot_exchange(self) -> bool:
        """Check if this is a spot trading exchange."""
        return self.market_type == "SPOT"


class Symbol(msgspec.Struct):
    """
    Symbol reference data structure.
    
    Represents trading pairs across exchanges with their configuration
    and metadata for normalized database operations.
    Simplified to store only essential identification fields.
    """
    # Required fields first (part of unique key)
    exchange_id: int                                 # Foreign key to exchanges table
    symbol_base: str                                # Base asset (BTC, ETH, etc.)
    symbol_quote: str                               # Quote asset (USDT, BTC, etc.)
    symbol_type: SymbolType                         # SPOT or FUTURES
    exchange_symbol: str                            # Exchange-specific symbol format
    
    # Optional fields
    id: Optional[int] = None
    is_active: bool = True                          # Whether symbol is currently traded
    
    @classmethod
    def from_symbol_and_exchange(
        cls, 
        exchange_id: int,
        symbol: "Symbol",  # From exchanges.structs.common
        exchange_symbol: str,
        **kwargs
    ) -> "Symbol":
        """
        Create Symbol from exchange ID and Symbol struct.
        
        Args:
            exchange_id: Database exchange ID
            symbol: Symbol object from exchanges.structs.common
            exchange_symbol: Exchange-specific symbol format
            **kwargs: Additional field overrides
            
        Returns:
            Symbol instance
        """
        return cls(
            exchange_id=exchange_id,
            symbol_base=str(symbol.base),
            symbol_quote=str(symbol.quote),
            symbol_type=SymbolType.FUTURES if (hasattr(symbol, 'is_futures') and symbol.is_futures) else SymbolType.SPOT,
            exchange_symbol=exchange_symbol,
            **kwargs
        )
    
    def to_common_symbol(self) -> "Symbol":
        """
        Convert to common Symbol struct.
        
        Returns:
            Symbol object from exchanges.structs.common
        """
        from exchanges.structs.types import AssetName
        from exchanges.structs.common import Symbol as CommonSymbol
        
        return CommonSymbol(
            base=AssetName(self.symbol_base),
            quote=AssetName(self.symbol_quote)
        )
    
    def get_symbol_string(self) -> str:
        """
        Get standardized symbol string.
        
        Returns:
            Symbol string (e.g., 'BTCUSDT')
        """
        return f"{self.symbol_base}{self.symbol_quote}"
    
    def get_market_type(self) -> str:
        """
        Get market type for this symbol.
        
        Returns:
            'FUTURES' if futures symbol, 'SPOT' otherwise
        """
        return "FUTURES" if self.symbol_type == SymbolType.FUTURES else "SPOT"
    
    def is_futures(self) -> bool:
        """
        Check if this is a futures symbol.
        
        Returns:
            True if symbol type is FUTURES
        """
        return self.symbol_type == SymbolType.FUTURES
    
    def is_spot(self) -> bool:
        """
        Check if this is a spot symbol.
        
        Returns:
            True if symbol type is SPOT
        """
        return self.symbol_type == SymbolType.SPOT
    
    def is_valid_order_size(self, quantity: float) -> bool:
        """
        Check if order quantity meets symbol constraints.
        
        Args:
            quantity: Order quantity to validate
            
        Returns:
            True (constraints should be checked elsewhere)
        """
        return True
    
    def round_price(self, price: float) -> float:
        """
        Round price to default precision.
        
        Args:
            price: Raw price value
            
        Returns:
            Price rounded to default precision
        """
        return round(price, 8)  # Default precision
    
    def round_quantity(self, quantity: float) -> float:
        """
        Round quantity to default precision.
        
        Args:
            quantity: Raw quantity value
            
        Returns:
            Quantity rounded to default precision
        """
        return round(quantity, 8)  # Default precision


class BookTickerSnapshot(msgspec.Struct):
    """
    Book ticker snapshot data structure.
    
    Represents the best bid/ask prices and quantities at a specific moment.
    Optimized for high-frequency storage and retrieval using normalized symbol_id.
    """
    # Database fields
    symbol_id: int                              # Foreign key to symbols table
    
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
    def from_symbol_id_and_data(
        cls,
        symbol_id: int,
        bid_price: float,
        bid_qty: float,
        ask_price: float,
        ask_qty: float,
        timestamp: datetime
    ) -> "BookTickerSnapshot":
        """
        Create BookTickerSnapshot from symbol ID and ticker data.
        
        Args:
            symbol_id: Database symbol ID
            bid_price: Best bid price
            bid_qty: Best bid quantity
            ask_price: Best ask price
            ask_qty: Best ask quantity
            timestamp: Exchange timestamp
            
        Returns:
            BookTickerSnapshot instance
        """
        return cls(
            symbol_id=symbol_id,
            bid_price=bid_price,
            bid_qty=bid_qty,
            ask_price=ask_price,
            ask_qty=ask_qty,
            timestamp=timestamp
        )
    
    @classmethod
    def from_symbol_and_data(
        cls,
        exchange: str,
        symbol: "Symbol",  # From exchanges.structs.common
        bid_price: float,
        bid_qty: float,
        ask_price: float,
        ask_qty: float,
        timestamp: datetime
    ) -> "BookTickerSnapshot":
        """
        Create BookTickerSnapshot from exchange/symbol data (legacy compatibility).
        
        This method is provided for backward compatibility but requires symbol resolution.
        Use from_symbol_id_and_data for better performance.
        
        Args:
            exchange: Exchange identifier (e.g., 'MEXC', 'GATEIO_FUTURES')
            symbol: Symbol object with base/quote assets
            bid_price: Best bid price
            bid_qty: Best bid quantity
            ask_price: Best ask price
            ask_qty: Best ask quantity
            timestamp: Exchange timestamp
            
        Returns:
            BookTickerSnapshot instance with resolved symbol_id
            
        Raises:
            ValueError: If symbol cannot be resolved to symbol_id
        """
        from exchanges.structs.enums import ExchangeEnum
        from db.cache_operations import cached_resolve_symbol_by_exchange_string
        
        # Parse exchange enum
        try:
            exchange_enum = ExchangeEnum(exchange)
        except ValueError:
            raise ValueError(f"Invalid exchange: {exchange}")
        
        # Create exchange_symbol from symbol data
        exchange_symbol = f"{symbol.base}{symbol.quote}".upper()
        
        # Resolve symbol using exchange_symbol lookup
        db_symbol = cached_resolve_symbol_by_exchange_string(exchange_enum, exchange_symbol)
        if not db_symbol:
            raise ValueError(f"Cannot resolve symbol {exchange_symbol} on {exchange}")
        
        return cls(
            symbol_id=db_symbol.id,
            bid_price=bid_price,
            bid_qty=bid_qty,
            ask_price=ask_price,
            ask_qty=ask_qty,
            timestamp=timestamp
        )
    
    def to_symbol(self) -> Symbol:
        """
        Convert back to Symbol object using database cache lookup.
        
        Returns:
            Symbol object reconstructed from symbol_id
        """
        from db.cache_operations import cached_get_symbol_by_id
        
        db_symbol = cached_get_symbol_by_id(self.symbol_id)
        if not db_symbol:
            raise ValueError(f"Cannot resolve symbol_id {self.symbol_id} from cache")
        
        return db_symbol.to_common_symbol()
    
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


class NormalizedBookTickerSnapshot(msgspec.Struct):
    """
    Normalized book ticker snapshot using foreign key relationships.
    
    Uses exchange_id and symbol_id instead of string-based identification
    for optimal database performance and referential integrity.
    """
    # Foreign key relationships
    exchange_id: int                                # Foreign key to exchanges table
    symbol_id: int                                  # Foreign key to symbols table
    
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
    def from_legacy_snapshot(
        cls,
        legacy_snapshot: "BookTickerSnapshot",
        exchange_id: int,
        symbol_id: int
    ) -> "NormalizedBookTickerSnapshot":
        """
        Create normalized snapshot from legacy snapshot.
        
        Args:
            legacy_snapshot: Legacy BookTickerSnapshot
            exchange_id: Resolved exchange database ID
            symbol_id: Resolved symbol database ID
            
        Returns:
            NormalizedBookTickerSnapshot instance
        """
        return cls(
            exchange_id=exchange_id,
            symbol_id=symbol_id,
            bid_price=legacy_snapshot.bid_price,
            bid_qty=legacy_snapshot.bid_qty,
            ask_price=legacy_snapshot.ask_price,
            ask_qty=legacy_snapshot.ask_qty,
            timestamp=legacy_snapshot.timestamp,
            created_at=legacy_snapshot.created_at,
            id=legacy_snapshot.id
        )
    
    def get_spread(self) -> float:
        """Calculate bid-ask spread."""
        return self.ask_price - self.bid_price
    
    def get_spread_percentage(self) -> float:
        """Calculate bid-ask spread as percentage."""
        mid_price = (self.bid_price + self.ask_price) / 2
        return (self.get_spread() / mid_price) * 100 if mid_price > 0 else 0.0
    
    def get_mid_price(self) -> float:
        """Calculate mid price."""
        return (self.bid_price + self.ask_price) / 2


class NormalizedTradeSnapshot(msgspec.Struct):
    """
    Normalized trade snapshot using foreign key relationships.
    
    Uses exchange_id and symbol_id instead of string-based identification
    for optimal database performance and referential integrity.
    """
    # Foreign key relationships
    exchange_id: int                                # Foreign key to exchanges table
    symbol_id: int                                  # Foreign key to symbols table
    
    # Trade data
    price: float
    quantity: float
    side: str                                       # 'buy' or 'sell'
    timestamp: datetime
    
    # Optional fields
    trade_id: Optional[str] = None
    created_at: Optional[datetime] = None
    id: Optional[int] = None
    quote_quantity: Optional[float] = None
    is_buyer: Optional[bool] = None
    is_maker: Optional[bool] = None
    
    @classmethod
    def from_legacy_snapshot(
        cls,
        legacy_snapshot: "TradeSnapshot",
        exchange_id: int,
        symbol_id: int
    ) -> "NormalizedTradeSnapshot":
        """
        Create normalized snapshot from legacy snapshot.
        
        Args:
            legacy_snapshot: Legacy TradeSnapshot
            exchange_id: Resolved exchange database ID
            symbol_id: Resolved symbol database ID
            
        Returns:
            NormalizedTradeSnapshot instance
        """
        return cls(
            exchange_id=exchange_id,
            symbol_id=symbol_id,
            price=legacy_snapshot.price,
            quantity=legacy_snapshot.quantity,
            side=legacy_snapshot.side,
            timestamp=legacy_snapshot.timestamp,
            trade_id=legacy_snapshot.trade_id,
            created_at=legacy_snapshot.created_at,
            id=legacy_snapshot.id,
            quote_quantity=legacy_snapshot.quote_quantity,
            is_buyer=legacy_snapshot.is_buyer,
            is_maker=legacy_snapshot.is_maker
        )
    
    def get_notional_value(self) -> float:
        """Calculate trade notional value."""
        return self.price * self.quantity


class TradeSnapshot(msgspec.Struct):
    """
    Trade data snapshot structure.
    
    Represents individual trade execution data from exchanges.
    Optimized for high-frequency trade storage and analysis using normalized symbol_id.
    """
    # Database fields
    symbol_id: int                              # Foreign key to symbols table
    
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
    def from_symbol_id_and_trade(
        cls,
        symbol_id: int,
        trade: "Trade"  # Import from structs.common
    ) -> "TradeSnapshot":
        """
        Create TradeSnapshot from symbol ID and Trade struct.
        
        Args:
            symbol_id: Database symbol ID
            trade: Trade struct from structs.common
            
        Returns:
            TradeSnapshot instance
        """
        from exchanges.structs import Side

        return cls(
            symbol_id=symbol_id,
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
        Create TradeSnapshot from individual components (legacy compatibility).
        
        This method is provided for backward compatibility but requires symbol resolution.
        Use from_symbol_id_and_trade for better performance.
        
        Args:
            exchange: Exchange identifier (e.g., 'MEXC', 'GATEIO_FUTURES')
            symbol: Symbol object with base/quote assets
            price: Trade execution price
            quantity: Trade quantity
            side: Trade side ('buy' or 'sell')
            timestamp: Trade timestamp
            trade_id: Optional trade ID
            quote_quantity: Optional quote asset quantity
            is_buyer: Optional buyer flag
            is_maker: Optional maker flag
            
        Returns:
            TradeSnapshot instance with resolved symbol_id
            
        Raises:
            ValueError: If symbol cannot be resolved to symbol_id
        """
        from exchanges.structs.enums import ExchangeEnum
        from db.cache_operations import cached_resolve_symbol_by_exchange_string
        
        # Parse exchange enum
        try:
            exchange_enum = ExchangeEnum(exchange)
        except ValueError:
            raise ValueError(f"Invalid exchange: {exchange}")
        
        # Create exchange_symbol from symbol data
        exchange_symbol = f"{symbol.base}{symbol.quote}".upper()
        
        # Resolve symbol using exchange_symbol lookup
        db_symbol = cached_resolve_symbol_by_exchange_string(exchange_enum, exchange_symbol)
        if not db_symbol:
            raise ValueError(f"Cannot resolve symbol {exchange_symbol} on {exchange}")
        
        return cls(
            symbol_id=db_symbol.id,
            price=price,
            quantity=quantity,
            side=side.lower(),
            timestamp=timestamp,
            trade_id=trade_id,
            quote_quantity=quote_quantity,
            is_buyer=is_buyer,
            is_maker=is_maker
        )
    
    def to_symbol(self) -> Symbol:
        """
        Convert back to Symbol object using database cache lookup.
        
        Returns:
            Symbol object reconstructed from symbol_id
        """
        from db.cache_operations import cached_get_symbol_by_id
        
        db_symbol = cached_get_symbol_by_id(self.symbol_id)
        if not db_symbol:
            raise ValueError(f"Cannot resolve symbol_id {self.symbol_id} from cache")
        
        return db_symbol.to_common_symbol()
    
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
        Get symbol as string using database cache lookup.
        
        Returns:
            Symbol string (e.g., 'BTCUSDT')
        """
        from db.cache_operations import cached_get_symbol_by_id
        
        db_symbol = cached_get_symbol_by_id(self.symbol_id)
        if not db_symbol:
            raise ValueError(f"Cannot resolve symbol_id {self.symbol_id} from cache")
        
        return db_symbol.get_symbol_string()


