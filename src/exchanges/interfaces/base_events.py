"""
Base Event System for Unified Exchange Architecture

Standardized event classes that all WebSocket implementations emit to the
unified exchange orchestration layer. Uses msgspec.Struct for maximum
HFT performance with zero-copy serialization.

Event Flow:
WebSocket Raw Messages → Parse → Standardized Events → Base Interface → State Updates → User Callbacks

HFT Performance:
- <1ms event processing latency  
- Zero-copy msgspec.Struct serialization
- Minimal memory allocation during event handling
- Thread-safe event validation
"""

import time
from typing import Optional, Dict, List, Any, Protocol, runtime_checkable
from msgspec import Struct

from exchanges.structs.common import (
    Symbol, AssetBalance, Order, Position, Trade, OrderBook, Ticker, Kline, BookTicker
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderType, OrderStatus


# ========================================
# Base Event Classes (msgspec.Struct for HFT Performance)
# ========================================

class BaseEvent(Struct, frozen=True, kw_only=True):
    """
    Base class for all exchange events.
    
    Provides common fields for event tracking, validation, and performance monitoring.
    """
    timestamp: float              # Event timestamp (from exchange or local)
    exchange_timestamp: float     # Original exchange timestamp  
    event_id: Optional[str] = None  # Unique event identifier (if provided by exchange)
    sequence: Optional[int] = None  # Sequence number for ordering (if provided)
    
    def __post_init__(self):
        """Post-initialization validation for HFT compliance."""
        if self.timestamp <= 0:
            raise ValueError("Event timestamp must be positive")
        if self.exchange_timestamp <= 0:
            raise ValueError("Exchange timestamp must be positive")


# ========================================
# Public Market Data Events
# ========================================

class OrderbookUpdateEvent(BaseEvent, kw_only=True):
    """
    Orderbook update event from public WebSocket streams.
    
    Emitted when orderbook changes occur (snapshot or incremental update).
    HFT CRITICAL: <1ms processing time required.
    """
    symbol: Symbol
    orderbook: OrderBook
    is_snapshot: bool = False     # True for full snapshot, False for incremental update
    update_type: str = "update"   # "snapshot", "update", "replace"
    
    def __post_init__(self):
        """Validate orderbook event for HFT compliance."""
        super().__post_init__()
        if not self.orderbook.bids and not self.orderbook.asks:
            raise ValueError("Orderbook must have at least bids or asks")
        if len(self.orderbook.bids) > 1000 or len(self.orderbook.asks) > 1000:
            raise ValueError("Orderbook too large - may impact HFT performance")


class TickerUpdateEvent(BaseEvent, kw_only=True):
    """
    Ticker statistics update event from public WebSocket streams.
    
    24hr rolling window statistics for symbol price/volume data.
    """
    symbol: Symbol
    ticker: Ticker
    
    def __post_init__(self):
        """Validate ticker event."""
        super().__post_init__()
        if self.ticker.last_price <= 0:
            raise ValueError("Ticker last_price must be positive")


class TradeUpdateEvent(BaseEvent, kw_only=True):
    """
    Individual trade execution event from public WebSocket streams.
    
    Real-time trade data for market activity monitoring.
    """
    symbol: Symbol
    trade: Trade
    is_buyer_maker: Optional[bool] = None  # True if buyer was market maker
    
    def __post_init__(self):
        """Validate trade event."""
        super().__post_init__()
        if self.trade.price <= 0:
            raise ValueError("Trade price must be positive")
        if self.trade.quantity <= 0:
            raise ValueError("Trade quantity must be positive")


class BookTickerUpdateEvent(BaseEvent, kw_only=True):
    """
    Book ticker (best bid/ask) update event from public WebSocket streams.
    
    HFT CRITICAL: Real-time best bid/ask price updates for arbitrage strategies.
    Processing latency target: <500μs for profitable arbitrage opportunity detection.
    """
    book_ticker: BookTicker
    
    def __post_init__(self):
        """Validate book ticker event for HFT compliance."""
        super().__post_init__()
        if self.book_ticker.bid_price <= 0:
            raise ValueError("Book ticker bid_price must be positive")
        if self.book_ticker.ask_price <= 0:
            raise ValueError("Book ticker ask_price must be positive")
        if self.book_ticker.bid_price >= self.book_ticker.ask_price:
            raise ValueError("Book ticker bid_price must be less than ask_price")
        if self.book_ticker.bid_quantity <= 0 or self.book_ticker.ask_quantity <= 0:
            raise ValueError("Book ticker quantities must be positive")


class KlineUpdateEvent(BaseEvent, kw_only=True):
    """
    Kline/Candlestick update event from public WebSocket streams.
    
    OHLCV data updates for charting and technical analysis.
    """
    symbol: Symbol
    kline: Kline
    interval: str                 # "1m", "5m", "1h", etc.
    is_closed: bool = False      # True if kline period is complete
    
    def __post_init__(self):
        """Validate kline event."""
        super().__post_init__()
        if self.kline.open <= 0 or self.kline.high <= 0 or self.kline.low <= 0 or self.kline.close <= 0:
            raise ValueError("All OHLC prices must be positive")


# ========================================
# Private Trading Data Events  
# ========================================

class OrderUpdateEvent(BaseEvent, kw_only=True):
    """
    Order status update event from private WebSocket streams.
    
    HFT CRITICAL: Real-time order execution updates for trading strategies.
    Processing latency target: <1ms.
    """
    order: Order
    previous_status: Optional[OrderStatus] = None  # Previous order status for delta tracking
    execution_type: str = "NEW"   # "NEW", "FILLED", "PARTIALLY_FILLED", "CANCELED", etc.
    
    def __post_init__(self):
        """Validate order update for HFT compliance."""
        super().__post_init__()
        if not self.order.order_id:
            raise ValueError("Order must have valid order_id")
        if self.order.quantity <= 0:
            raise ValueError("Order quantity must be positive")


class BalanceUpdateEvent(BaseEvent, kw_only=True):
    """
    Account balance update event from private WebSocket streams.
    
    Real-time balance changes from trading activity.
    """
    asset: AssetName
    balance: AssetBalance
    balance_type: str = "spot"    # "spot", "futures", "margin"
    change_reason: Optional[str] = None  # "trade", "deposit", "withdrawal", etc.
    
    def __post_init__(self):
        """Validate balance update."""
        super().__post_init__()
        if self.balance.available < 0:
            raise ValueError("Available balance cannot be negative")


class PositionUpdateEvent(BaseEvent, kw_only=True):
    """
    Position update event from private WebSocket streams (futures/margin).
    
    Real-time position changes for derivatives trading.
    """
    symbol: Symbol  
    position: Position
    change_type: str = "update"   # "open", "update", "close"
    
    def __post_init__(self):
        """Validate position update."""
        super().__post_init__()
        if abs(self.position.quantity) < 1e-8:
            raise ValueError("Position quantity too small")


class ExecutionReportEvent(BaseEvent, kw_only=True):
    """
    Trade execution report event from private WebSocket streams.
    
    Detailed execution information for filled orders.
    HFT CRITICAL: Required for accurate P&L tracking.
    """
    symbol: Symbol
    execution: Trade              # The actual fill/execution
    order_id: OrderId            # Associated order ID  
    execution_id: str            # Unique execution identifier
    commission: Optional[float] = None      # Trading commission paid
    commission_asset: Optional[AssetName] = None  # Asset used for commission
    is_maker: Optional[bool] = None         # True if maker, False if taker
    
    def __post_init__(self):
        """Validate execution report."""
        super().__post_init__()
        if not self.execution_id:
            raise ValueError("Execution must have unique execution_id")
        if self.execution.price <= 0:
            raise ValueError("Execution price must be positive") 
        if self.execution.quantity <= 0:
            raise ValueError("Execution quantity must be positive")


# ========================================
# Connection and System Events
# ========================================

class ConnectionStatusEvent(BaseEvent, kw_only=True):
    """
    WebSocket connection status change event.
    
    Emitted when connection state changes (connected, disconnected, error).
    """
    connection_type: str          # "public_ws", "private_ws", "public_rest", "private_rest"
    is_connected: bool
    error_message: Optional[str] = None
    retry_count: int = 0
    next_retry_delay: Optional[float] = None  # Seconds until next retry attempt
    
    def __post_init__(self):
        """Validate connection status event.""" 
        super().__post_init__()
        if self.connection_type not in ["public_ws", "private_ws", "public_rest", "private_rest"]:
            raise ValueError(f"Invalid connection_type: {self.connection_type}")


class ErrorEvent(BaseEvent, kw_only=True):
    """
    Error event for WebSocket and system errors.
    
    Standardized error reporting across all exchange implementations.
    """
    error_type: str               # "connection", "parsing", "validation", "rate_limit", etc.
    error_code: Optional[str] = None        # Exchange-specific error code
    error_message: str
    context: Optional[Dict[str, Any]] = None  # Additional error context
    is_recoverable: bool = True   # Whether error can be automatically recovered
    
    def __post_init__(self):
        """Validate error event."""
        super().__post_init__()
        if not self.error_message:
            raise ValueError("Error event must have error_message")


class HealthCheckEvent(BaseEvent, kw_only=True):
    """
    System health check event for monitoring.
    
    Periodic health status reports from exchange connections.
    """
    component: str                # "public_rest", "private_rest", "public_ws", "private_ws"  
    is_healthy: bool
    latency_ms: Optional[float] = None      # Last operation latency
    error_rate: Optional[float] = None      # Recent error rate (0.0 - 1.0)
    uptime_seconds: Optional[float] = None  # Connection uptime
    metrics: Optional[Dict[str, Any]] = None # Additional health metrics


# ========================================
# Event Handler Protocols (Type Safety)
# ========================================

@runtime_checkable  
class OrderbookEventHandler(Protocol):
    """Type protocol for orderbook event handlers."""
    async def __call__(self, event: OrderbookUpdateEvent) -> None: ...


@runtime_checkable
class TickerEventHandler(Protocol):
    """Type protocol for ticker event handlers."""
    async def __call__(self, event: TickerUpdateEvent) -> None: ...


@runtime_checkable
class TradeEventHandler(Protocol):
    """Type protocol for trade event handlers.""" 
    async def __call__(self, event: TradeUpdateEvent) -> None: ...


@runtime_checkable
class BookTickerEventHandler(Protocol):
    """Type protocol for book ticker event handlers."""
    async def __call__(self, event: BookTickerUpdateEvent) -> None: ...


@runtime_checkable
class OrderEventHandler(Protocol):
    """Type protocol for order event handlers."""
    async def __call__(self, event: OrderUpdateEvent) -> None: ...


@runtime_checkable
class BalanceEventHandler(Protocol):
    """Type protocol for balance event handlers."""
    async def __call__(self, event: BalanceUpdateEvent) -> None: ...


@runtime_checkable  
class PositionEventHandler(Protocol):
    """Type protocol for position event handlers."""
    async def __call__(self, event: PositionUpdateEvent) -> None: ...


@runtime_checkable
class ExecutionEventHandler(Protocol):
    """Type protocol for execution report handlers."""
    async def __call__(self, event: ExecutionReportEvent) -> None: ...


@runtime_checkable
class ConnectionEventHandler(Protocol):
    """Type protocol for connection status handlers."""
    async def __call__(self, event: ConnectionStatusEvent) -> None: ...


@runtime_checkable
class ErrorEventHandler(Protocol):
    """Type protocol for error event handlers."""
    async def __call__(self, event: ErrorEvent) -> None: ...


# ========================================
# Event Validation Utilities
# ========================================

def validate_event_timestamp(event: BaseEvent, max_age_seconds: float = 10.0) -> bool:
    """
    Validate event timestamp for freshness.
    
    HFT Compliance: Reject events older than max_age_seconds to prevent
    trading on stale data.
    
    Args:
        event: Event to validate
        max_age_seconds: Maximum allowed age for events
        
    Returns:
        True if event is fresh, False if stale
    """
    now = time.time()
    event_age = now - event.timestamp
    return event_age <= max_age_seconds


def validate_event_sequence(events: List[BaseEvent]) -> bool:
    """
    Validate event sequence ordering.
    
    Ensures events are processed in chronological order to maintain
    data consistency.
    
    Args:
        events: List of events to validate
        
    Returns:
        True if events are properly ordered, False otherwise
    """
    if len(events) <= 1:
        return True
    
    for i in range(1, len(events)):
        # Check timestamp ordering
        if events[i].timestamp < events[i-1].timestamp:
            return False
        
        # Check sequence number ordering (if available)
        if (events[i].sequence is not None and events[i-1].sequence is not None):
            if events[i].sequence <= events[i-1].sequence:
                return False
    
    return True


def create_event_metrics(events: List[BaseEvent]) -> Dict[str, Any]:
    """
    Create performance metrics from event list.
    
    Generates statistics for monitoring event processing performance
    and identifying bottlenecks.
    
    Args:
        events: List of processed events
        
    Returns:
        Dictionary with event processing metrics
    """
    if not events:
        return {"count": 0}
    
    now = time.time()
    timestamps = [e.timestamp for e in events]
    
    return {
        "count": len(events),
        "time_span_seconds": max(timestamps) - min(timestamps),
        "avg_age_seconds": now - (sum(timestamps) / len(timestamps)),
        "max_age_seconds": now - min(timestamps),
        "min_age_seconds": now - max(timestamps),
        "events_per_second": len(events) / max(1.0, max(timestamps) - min(timestamps)),
        "event_types": {
            type(e).__name__: sum(1 for ev in events if type(ev) == type(e))
            for e in events
        }
    }