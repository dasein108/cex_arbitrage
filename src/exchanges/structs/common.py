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

from msgspec import Struct
from typing import Optional, Dict, List

from .enums import TimeInForce, KlineInterval, OrderStatus, OrderType, Side, WithdrawalStatus, DepositStatus, ExchangeEnum
from .types import ExchangeName, AssetName, OrderId


# Connection setting structures for exchanges


class Symbol(Struct, frozen=True):
    """Trading symbol with composite and quote assets."""
    base: AssetName
    quote: AssetName
    
    def __str__(self) -> str:
        """String representation for compatibility."""
        return f"{self.base}_{self.quote}"

# Core enums used across the system

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
    timestamp: float
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
    exchange: Optional[ExchangeEnum] = None

    @property
    def qty_quote(self) -> Optional[float]:
        """Calculate quantity in quote asset """
        if self.price is not None:
            return self.price * self.quantity
        return None

    @property
    def is_done(self) -> bool:
        """Check if order is done (filled or cancelled)."""
        return self.status in {OrderStatus.FILLED,
                                OrderStatus.CANCELED,
                                OrderStatus.REJECTED,
                                OrderStatus.EXPIRED,
                                OrderStatus.PARTIALLY_CANCELED}

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status in [OrderStatus.FILLED,
                               OrderStatus.PARTIALLY_FILLED,
                               OrderStatus.PARTIALLY_CANCELED]

    def __str__(self):
        return (f"{self.symbol} {self.side.name} "
                f"{self.order_type.name} ({self.quantity}/{self.filled_quantity})@{self.price} status: {self.status.name}")
    
class AssetBalance(Struct):
    """Account balance for a single asset."""
    asset: AssetName
    available: float
    locked: float
    
    @property
    def total(self) -> float:
        """Total balance (free + locked)."""
        return self.available + self.locked

    def __str__(self):
        return f"{self.asset}: {self.total}({self.available}/{self.locked})"

class FuturesBalance(Struct):
    """Futures account balance with margin information for margin trading."""
    asset: AssetName
    total: float                    # Total account balance
    available: float                # Available for new positions
    unrealized_pnl: float          # Unrealized PnL across all positions
    position_margin: float         # Margin allocated to current positions
    order_margin: float            # Margin allocated to open orders
    cross_wallet_balance: Optional[float] = None  # Cross margin wallet balance
    cross_unrealized_pnl: Optional[float] = None  # Cross margin unrealized PnL
    
    @property
    def locked(self) -> float:
        """Total locked balance (position + order margin)."""
        return self.position_margin + self.order_margin
    
    @property
    def equity(self) -> float:
        """Account equity (total + unrealized PnL)."""
        return self.total + self.unrealized_pnl
    
    @property
    def margin_utilization(self) -> float:
        """Margin utilization percentage (0.0 - 1.0)."""
        if self.total <= 0:
            return 1.0
        return self.locked / self.total
    
    def has_available_margin(self, required_margin: float) -> bool:
        """Check if there's sufficient available margin for a new position."""
        return self.available >= required_margin
    
    def __str__(self):
        return (f"{self.asset}: Total={self.total:.6f}, Available={self.available:.6f}, "
                f"PnL={self.unrealized_pnl:.6f}, Margin={self.locked:.6f} "
                f"({self.margin_utilization*100:.2f}%)")

class Position(Struct):
    """Trading position (for margin/futures)."""
    symbol: Symbol
    side: Side  # LONG = BUY, SHORT = SELL
    size: float # size in contracts
    entry_price: float
    qty_base: Optional[float] = None # Quantity in base asset
    mark_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    liquidation_price: Optional[float] = None
    margin: Optional[float] = None
    timestamp: Optional[int] = None

    def __str__(self):
        return f"{self.symbol} {self.side} size: {self.size} entry: {self.entry_price}"

class SymbolInfo(Struct, frozen=True):
    """Symbol trading information."""
    symbol: Symbol
    base_precision: int
    quote_precision: int
    min_base_quantity: float
    min_quote_quantity: float
    maker_commission: float = 0.0
    taker_commission: float = 0.0
    inactive: bool = False
    tick: float = 0.0  # Minimum price increment
    step: float = 0.0  # Minimum quantity increment
    is_futures: bool = False
    quanto_multiplier: float = 1  # For futures


    def round_quote(self, amount: float) -> float:
        """Round price to the symbol's price/quote precision."""
        return round(amount, self.quote_precision)

    def round_base(self, quantity: float) -> float:
        """Round quantity to the symbol's base precision."""
        return round(quantity, self.base_precision)

    def base_to_contracts(self, quantity: float) -> float:
        """Adjust quantity to meet minimum and step size requirements."""
        if  self.is_futures and self.quanto_multiplier:
            return round(quantity / self.quanto_multiplier) * self.quanto_multiplier

        return self.round_base(quantity)

    def contracts_to_base(self, quantity: float) -> float:
        """Adjust quantity to meet minimum and step size requirements."""
        if  self.is_futures and self.quanto_multiplier:
            return quantity * self.quanto_multiplier

        return self.round_base(quantity)

    def get_min_base_quantity_from_quote(self, price: float) -> float:
        """Convert quote asset amount to base asset quantity."""
        base_qty = (self.min_quote_quantity / price) * self.quanto_multiplier * 1.1 # add 10% buffer
        return self.round_base(base_qty)

    def get_min_base_quantity(self, price: float) -> float:
        """Get minimum base quantity."""
        if self.min_base_quantity:
            return self.min_base_quantity #* self.quanto_multiplier
        else:
            return self.get_min_base_quantity_from_quote(price)

    def get_abs_min_quantity(self, price):
        """Get absolute minimum quantity considering both base and quote minimums."""
        return max(self.get_min_base_quantity(price), self.get_min_base_quantity_from_quote(price))

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
    contract_address: Optional[str] = None
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
    price_change_percent: float # TODO: remove
    weighted_avg_price: float # TODO: remove
    prev_close_price: float # TODO: remove
    last_price: float
    last_qty: float
    open_price: float # TODO: remove
    high_price: float # TODO: remove
    low_price: float # TODO: remove
    volume: float
    quote_volume: float
    open_time: Optional[int]=None # TODO: remove
    close_time: Optional[int]=None # TODO: remove
    count: Optional[int] = None # TODO: remove
    bid_price: Optional[float] = None
    bid_qty: Optional[float] = None
    ask_price: Optional[float] = None
    ask_qty: Optional[float] = None
    first_id: Optional[int] = None # TODO: remove
    last_id: Optional[int] = None # TODO: remove

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

    @property
    def spread(self) -> float:
        """Calculate the bid-ask spread."""
        return self.ask_price - self.bid_price

    @property
    def spread_percentage(self) -> float:
        """Calculate the spread as a percentage """
        return (self.spread / self.bid_price) * 100 if self.bid_price != 0 else 0.0

    def __str__(self):
        return (f"{self.symbol} Bid: {self.bid_price}@{self.bid_quantity} / Ask: {self.ask_price}@{self.ask_quantity} "
                f"spread: {self.spread} ({self.spread_percentage:.4f}%)")

class FuturesTicker(Struct):
    """Futures ticker with comprehensive market data including funding rates."""
    symbol: Symbol
    price: float
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    funding_rate: Optional[float] = None
    funding_rate_indicative: Optional[float] = None
    funding_time: Optional[int] = None  # Timestamp of next funding
    bid_price: Optional[float] = None
    bid_qty: Optional[float] = None
    ask_price: Optional[float] = None
    ask_qty: Optional[float] = None
# Configuration structures

class Fees(Struct):
    maker_fee: float = 0.0  # Maker fee rate
    taker_fee: float = 0.0  # Taker fee rate

# TODO: Legacy
class TradingFee(Struct):
    """Trading fee information for a user."""
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

# Withdrawal structures

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


class DepositAddress(Struct):
    """Deposit address information for receiving funds."""
    asset: AssetName
    address: str
    network: str
    memo: Optional[str] = None  # Required for some coins (XRP, EOS, etc.)
    min_confirmations: Optional[int] = None
    warning: Optional[str] = None  # Exchange warnings about deposits

class DepositResponse(Struct):
    """Deposit operation response."""
    deposit_id: str
    asset: AssetName
    amount: float
    address: str
    status: DepositStatus
    timestamp: int
    network: Optional[str] = None
    memo: Optional[str] = None
    tx_id: Optional[str] = None  # Transaction ID when available
    confirmations: Optional[int] = None  # Current confirmations
    unlock_confirmations: Optional[int] = None  # Required confirmations