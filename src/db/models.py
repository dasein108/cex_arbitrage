"""
Database Models

Data structures for database operations using msgspec for maximum performance.
Optimized for HFT requirements with zero-copy serialization.
"""

from datetime import datetime
from typing import Optional
import msgspec

from exchanges.structs.common import Symbol


class Exchange(msgspec.Struct):
    """
    Exchange reference data structure.
    
    Represents supported cryptocurrency exchanges with their
    configuration and metadata for normalized database operations.
    """
    # Required fields first
    name: str                                    # MEXC_SPOT, GATEIO_SPOT, etc.
    enum_value: str                              # Maps to ExchangeEnum
    display_name: str                            # User-friendly name
    market_type: str                             # SPOT, FUTURES, OPTIONS
    
    # Optional fields with defaults
    id: Optional[int] = None
    is_active: bool = True
    base_url: Optional[str] = None
    websocket_url: Optional[str] = None
    rate_limit_requests_per_second: Optional[int] = None
    precision_default: int = 8
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
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
            Delay in seconds between requests
        """
        if self.rate_limit_requests_per_second:
            return 1.0 / self.rate_limit_requests_per_second
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
    """
    # Required fields first
    exchange_id: int                                 # Foreign key to exchanges table
    symbol_base: str                                # Base asset (BTC, ETH, etc.)
    symbol_quote: str                               # Quote asset (USDT, BTC, etc.)
    exchange_symbol: str                            # Exchange-specific symbol format
    
    # Optional fields with defaults
    id: Optional[int] = None
    is_active: bool = True
    is_futures: bool = False
    min_order_size: Optional[float] = None
    max_order_size: Optional[float] = None
    price_precision: int = 8
    quantity_precision: int = 8
    tick_size: Optional[float] = None
    step_size: Optional[float] = None
    min_notional: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
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
            exchange_symbol=exchange_symbol,
            is_futures=symbol.is_futures if hasattr(symbol, 'is_futures') else False,
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
            quote=AssetName(self.symbol_quote),
            is_futures=self.is_futures
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
        return "FUTURES" if self.is_futures else "SPOT"
    
    def is_valid_order_size(self, quantity: float) -> bool:
        """
        Check if order quantity meets symbol constraints.
        
        Args:
            quantity: Order quantity to validate
            
        Returns:
            True if quantity is valid
        """
        if self.min_order_size and quantity < self.min_order_size:
            return False
        if self.max_order_size and quantity > self.max_order_size:
            return False
        return True
    
    def round_price(self, price: float) -> float:
        """
        Round price to symbol precision.
        
        Args:
            price: Raw price value
            
        Returns:
            Price rounded to symbol precision
        """
        return round(price, self.price_precision)
    
    def round_quantity(self, quantity: float) -> float:
        """
        Round quantity to symbol precision.
        
        Args:
            quantity: Raw quantity value
            
        Returns:
            Quantity rounded to symbol precision
        """
        return round(quantity, self.quantity_precision)


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
            symbol: Symbol object with composite/quote assets
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
            Symbol object reconstructed from composite/quote strings
        """
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


