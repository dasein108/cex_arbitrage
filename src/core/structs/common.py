"""
Common data structures used across the entire CEX arbitrage system.

This module contains the core data structures that are shared between
exchanges, arbitrage logic, and transport layers. All structures use
msgspec.Struct for optimal performance and type safety.

Design Principles:
- Zero-copy data structures using msgspec.Struct
- Frozen structures for thread safety and immutability  
- Type safety with comprehensive validation
- Memory-efficient with pre-compiled constants
- HFT-optimized for sub-millisecond processing
"""

from enum import Enum, IntEnum
from msgspec import Struct
from typing import NewType, Optional, Dict, List, Any

# Connection setting structures for exchanges

# Type aliases for improved type safety
ExchangeName = NewType('Exchange', str)
AssetName = NewType('AssetName', str)
OrderId = NewType("OrderId", str)

class Symbol(Struct, frozen=True):
    """Trading symbol with base and quote assets."""
    base: AssetName
    quote: AssetName
    is_futures: bool = False
    
    def __str__(self) -> str:
        """String representation for compatibility."""
        return f"{self.base}{self.quote}"

# Core enums used across the system

class ExchangeEnum(Enum):
    """
    Enumeration of supported centralized exchanges.

    Used throughout the system for type-safe exchange identification
    and consistent naming across all components.
    """
    MEXC = ExchangeName("MEXC_SPOT")
    GATEIO = ExchangeName("GATEIO_SPOT")  
    GATEIO_FUTURES = ExchangeName("GATEIO_FUTURES")

class ExchangeStatus(IntEnum):
    """Exchange connection status."""
    CONNECTING = 0
    ACTIVE = 1
    CLOSING = 2
    INACTIVE = 3
    ERROR = 4

class OrderStatus(IntEnum):
    """Order execution status."""
    UNKNOWN = -1
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELED = 4
    PARTIALLY_CANCELED = 5
    EXPIRED = 6
    REJECTED = 7

class OrderType(IntEnum):
    """Order type definitions."""
    LIMIT = 1
    MARKET = 2
    LIMIT_MAKER = 3
    IMMEDIATE_OR_CANCEL = 4
    FILL_OR_KILL = 5
    STOP_LIMIT = 6
    STOP_MARKET = 7

class Side(IntEnum):
    """Order side."""
    BUY = 1
    SELL = 2

# Backward compatibility alias
OrderSide = Side

class TimeInForce(IntEnum):
    """Time in force for orders."""
    GTC = 1  # Good Till Cancelled
    IOC = 2  # Immediate or Cancel
    FOK = 3  # Fill or Kill
    GTD = 4  # Good Till Date

class OrderbookUpdateType(Enum):
    """Type of orderbook update."""
    SNAPSHOT = "snapshot"
    DIFF = "diff"

class KlineInterval(IntEnum):
    """Kline/candlestick interval definitions."""
    MINUTE_1 = 1    # 1m
    MINUTE_5 = 2    # 5m  
    MINUTE_15 = 3   # 15m
    MINUTE_30 = 4   # 30m
    HOUR_1 = 5      # 1h
    HOUR_4 = 6      # 4h
    HOUR_12 = 7     # 12h
    DAY_1 = 8       # 1d
    WEEK_1 = 9      # 1w/7d
    MONTH_1 = 10    # 1M/30d

# Core data structures

class OrderBookEntry(Struct, frozen=True):
    """Individual orderbook entry."""
    price: float
    size: float

class OrderBook(Struct):
    symbol: Symbol
    """Complete orderbook state."""
    bids: List[OrderBookEntry]
    asks: List[OrderBookEntry]
    timestamp: int
    last_update_id: Optional[int] = None

class Order(Struct):
    """Order representation."""
    symbol: Symbol
    order_id: OrderId
    side: Side
    order_type: OrderType
    quantity: float  # Primary quantity attribute
    client_order_id: Optional[str] = None
    price: Optional[float] = None
    filled_quantity: float = 0.0  # Primary filled quantity attribute
    remaining_quantity: Optional[float] = None
    status: OrderStatus = OrderStatus.NEW
    timestamp: Optional[int] = None
    average_price: Optional[float] = None
    fee: Optional[float] = None
    fee_asset: Optional[AssetName] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    
    # Backward compatibility aliases
    @property
    def amount(self) -> float:
        """Alias for quantity for backward compatibility."""
        return self.quantity
    
    @property 
    def amount_filled(self) -> float:
        """Alias for filled_quantity for backward compatibility."""
        return self.filled_quantity

class AssetBalance(Struct):
    """Account balance for a single asset."""
    asset: AssetName
    free: float
    locked: float
    
    @property
    def total(self) -> float:
        """Total balance (free + locked)."""
        return self.free + self.locked

class Position(Struct):
    """Trading position (for margin/futures)."""
    symbol: Symbol
    side: Side  # LONG = BUY, SHORT = SELL
    size: float
    entry_price: float
    mark_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    liquidation_price: Optional[float] = None
    margin: Optional[float] = None
    timestamp: Optional[int] = None

class SymbolInfo(Struct, frozen=True):
    """Symbol trading information."""
    symbol: Symbol
    base_precision: int
    quote_precision: int
    min_base_amount: float
    min_quote_amount: float
    is_futures: bool = False
    maker_commission: float = 0.0
    taker_commission: float = 0.0
    inactive: bool = False

# Type alias for collections
SymbolsInfo = Dict[Symbol, SymbolInfo]

class NetworkInfo(Struct, frozen=True):
    """Deposit/withdraw details for a specific network of an asset."""
    network: str
    deposit_enable: bool
    withdraw_enable: bool
    withdraw_fee: float
    withdraw_min: float
    withdraw_max: Optional[float] = None
    min_confirmations: Optional[int] = None
    address_regex: Optional[str] = None
    memo_regex: Optional[str] = None
    deposit_desc: Optional[str] = None
    withdraw_desc: Optional[str] = None
    address: Optional[str] = None
    memo: Optional[str] = None

class AssetInfo(Struct, frozen=True):
    """Currency information across all supported networks."""
    asset: AssetName
    name: str
    deposit_enable: bool
    withdraw_enable: bool
    networks: Dict[str, NetworkInfo]  

    
class Trade(Struct):
    """Individual trade/transaction."""
    symbol: Symbol
    side: Side
    quantity: float  # Primary quantity attribute
    price: float
    timestamp: int
    quote_quantity: Optional[float] = None  # Quote asset quantity (price * quantity)
    trade_id: Optional[str] = None
    order_id: Optional[OrderId] = None
    fee: Optional[float] = None
    fee_asset: Optional[AssetName] = None
    is_buyer: bool = False
    is_maker: bool = False
    
    # Backward compatibility alias
    @property
    def amount(self) -> float:
        """Alias for quantity for backward compatibility."""
        return self.quantity

class Ticker(Struct):
    """24hr ticker statistics."""
    symbol: Symbol
    price_change: float
    price_change_percent: float
    weighted_avg_price: float
    prev_close_price: float
    last_price: float
    last_qty: float
    open_price: float
    high_price: float
    low_price: float
    volume: float
    quote_volume: float
    open_time: int
    close_time: int
    count: int
    bid_price: Optional[float] = None
    bid_qty: Optional[float] = None
    ask_price: Optional[float] = None
    ask_qty: Optional[float] = None
    first_id: Optional[int] = None
    last_id: Optional[int] = None

class Kline(Struct):
    """Kline/candlestick data."""
    symbol: Symbol
    interval: KlineInterval
    open_time: int          # Unix timestamp (milliseconds)
    close_time: int         # Unix timestamp (milliseconds)
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float           # Base asset volume
    quote_volume: float     # Quote asset volume
    trades_count: int = 0   # Number of trades (when available)

class BookTicker(Struct):
    """Best bid/ask price information (book ticker)."""
    symbol: Symbol
    bid_price: float
    bid_quantity: float
    ask_price: float
    ask_quantity: float
    timestamp: int
    update_id: Optional[int] = None  # Gate.io provides this, MEXC doesn't

class FuturesTicker(Struct):
    """Futures ticker with comprehensive market data including funding rates."""
    symbol: Symbol
    last_price: float
    mark_price: float
    index_price: float
    funding_rate: float
    funding_rate_indicative: float
    high_24h: float
    low_24h: float
    change_price: float
    change_percentage: float
    volume_24h: float
    volume_24h_base: float
    volume_24h_quote: float
    volume_24h_settle: float
    total_size: float  # Open interest
    timestamp: int
    quanto_base_rate: str = ""
    price_type: str = "last"
    change_from: str = "24h"

# Configuration structures

class ExchangeCredentials(Struct, frozen=True):
    """Exchange API credentials."""
    api_key: str
    secret_key: str

    def is_configured(self) -> bool:
        """Check if both credentials are provided."""
        return bool(self.api_key) and bool(self.secret_key)

    def get_preview(self) -> str:
        """Get safe preview of credentials for logging."""
        if not self.api_key:
            return "Not configured"
        if len(self.api_key) > 8:
            return f"{self.api_key[:4]}...{self.api_key[-4:]}"
        return "***"

class ExchangeConfig(Struct):
    """Exchange configuration."""
    name: ExchangeName
    enabled: bool = True
    credentials: Optional[ExchangeCredentials] = None
    rate_limits: Dict[str, int] = {}
    timeouts: Dict[str, float] = {}
    extra_config: Dict[str, Any] = {}

    def has_credentials(self) -> bool:
        """Check if exchange has valid credentials."""
        return self.credentials is not None and self.credentials.is_configured()

# Arbitrage-specific structures

class OpportunityType(IntEnum):
    """Arbitrage opportunity classification."""
    SPOT_SPOT = 1           # Cross-exchange spot arbitrage
    FUNDING_RATE = 2        # Funding rate arbitrage
    FUTURES_BASIS = 3       # Futures basis arbitrage
    CROSS_MARGIN = 4        # Cross-margin arbitrage
    STATISTICAL = 5         # Statistical arbitrage
    TRIANGULAR = 6          # Triangular arbitrage

class ArbitrageOpportunity(Struct):
    """Detected arbitrage opportunity."""
    opportunity_id: str
    opportunity_type: OpportunityType
    symbol: Symbol
    buy_exchange: ExchangeName
    sell_exchange: ExchangeName
    buy_price: float
    sell_price: float
    spread: float
    spread_percentage: float
    max_quantity: float
    estimated_profit: float
    confidence_score: float
    timestamp: int
    expiry_time: Optional[int] = None
    execution_time_estimate: Optional[float] = None  # milliseconds

class TradingFee(Struct):
    """Trading fee information for a user."""
    exchange: ExchangeName
    maker_rate: float = 0.0  # Maker fee rate (e.g., 0.001 for 0.1%)
    taker_rate: float = 0.0  # Taker fee rate (e.g., 0.001 for 0.1%)
    spot_maker: Optional[float] = None  # Spot maker fee (if different)
    spot_taker: Optional[float] = None  # Spot taker fee (if different)
    futures_maker: Optional[float] = None  # Futures maker fee (if different)
    futures_taker: Optional[float] = None  # Futures taker fee (if different)
    thirty_day_volume: Optional[float] = None  # 30-day trading volume in USDT
    point_type: Optional[str] = None  # Fee tier/level
    symbol: Optional[Symbol] = None  # Symbol these fees apply to (None = account-level)
    
    @property
    def maker_percentage(self) -> float:
        """Get maker fee as percentage (e.g., 0.1 for 0.1%)."""
        return self.maker_rate * 100
    
    @property
    def taker_percentage(self) -> float:
        """Get taker fee as percentage (e.g., 0.1 for 0.1%)."""
        return self.taker_rate * 100

class ArbitrageExecution(Struct):
    """Arbitrage execution record."""
    opportunity_id: str
    execution_id: str
    status: str  # "pending", "executing", "completed", "failed", "cancelled"
    start_timestamp: int
    buy_order: Optional[Order] = None
    sell_order: Optional[Order] = None
    actual_profit: Optional[float] = None
    execution_time: Optional[float] = None  # milliseconds
    end_timestamp: Optional[int] = None
    failure_reason: Optional[str] = None

# Withdrawal structures

class WithdrawalStatus(IntEnum):
    """Withdrawal status enumeration."""
    PENDING = 1      # Awaiting processing
    PROCESSING = 2   # Being processed
    COMPLETED = 3    # Successfully completed
    FAILED = 4       # Failed/rejected
    CANCELED = 5     # User canceled

class WithdrawalRequest(Struct, frozen=True):
    """Withdrawal request parameters."""
    asset: AssetName
    amount: float
    address: str
    network: Optional[str] = None  # Network/chain (required for multi-chain assets)
    memo: Optional[str] = None     # Memo/tag for coins requiring it
    withdrawal_order_id: Optional[str] = None  # Custom identifier
    remark: Optional[str] = None   # Additional notes

class WithdrawalResponse(Struct):
    """Withdrawal operation response."""
    withdrawal_id: str
    asset: AssetName
    amount: float
    fee: float
    address: str
    status: WithdrawalStatus
    timestamp: int
    network: Optional[str] = None
    memo: Optional[str] = None
    remark: Optional[str] = None
    tx_id: Optional[str] = None  # Transaction ID when available