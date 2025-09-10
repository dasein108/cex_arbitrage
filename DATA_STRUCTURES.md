# Data Structures Documentation

## Overview

The `src/structs/exchange.py` module provides complete, production-ready data structures for cryptocurrency trading operations. All structures use `msgspec.Struct` for maximum performance (3-5x faster than `dataclasses`) and are designed for hashability, type safety, and zero-copy JSON parsing.

## Recent Major Updates (2025)

### 🔧 **Critical Fixes**
- **Fixed Missing OrderSide Enum**: Added `OrderSide = Side` backward compatibility alias to resolve import errors
- **Complete Trading Enums**: Added TimeInForce, KlineInterval for comprehensive order and market data support  
- **Enhanced Market Data**: Added Ticker and Kline structures for 24hr statistics and OHLCV data
- **Account Management**: Added TradingFee and AccountInfo structures for complete account operations
- **Production Coverage**: All essential trading operations now supported with proper type safety

## Core Type Aliases

### **NewType Aliases** (Zero Runtime Overhead)
```python
ExchangeName = NewType('Exchange', str)      # Exchange identifier
AssetName = NewType('AssetName', str)        # Asset/currency identifier  
OrderId = NewType("OrderId", str)            # Order identifier
```

**Usage**:
```python
exchange = ExchangeName("MEXC")
asset = AssetName("BTC") 
order_id = OrderId("12345")
```

## Enums (Performance-Optimized)

### **OrderStatus (IntEnum for Fast Comparisons)**
```python
class OrderStatus(IntEnum):
    UNKNOWN = -1
    NEW = 1                    # Order placed but not filled
    FILLED = 2                 # Order completely filled
    PARTIALLY_FILLED = 3       # Order partially filled
    CANCELED = 4               # Order canceled by user/system
    PARTIALLY_CANCELED = 5     # Partial fill then canceled
    EXPIRED = 6                # Order expired (GTD/FOK)
    REJECTED = 7               # Order rejected by exchange
```

### **OrderType (Standard Trading Types)**
```python
class OrderType(Enum):
    LIMIT = "LIMIT"                        # Limit order
    MARKET = "MARKET"                      # Market order
    LIMIT_MAKER = "LIMIT_MAKER"            # Post-only limit order
    IMMEDIATE_OR_CANCEL = "IMMEDIATE_OR_CANCEL"  # IOC order
    FILL_OR_KILL = "FILL_OR_KILL"          # FOK order
    STOP_LIMIT = "STOP_LIMIT"              # Stop-loss limit
    STOP_MARKET = "STOP_MARKET"            # Stop-loss market
```

### **Side/OrderSide (Trade Direction)**
```python
class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"

# Backward compatibility alias (FIXED 2025)
OrderSide = Side
```

### **TimeInForce (NEW 2025)**
```python
class TimeInForce(Enum):
    """Time in force for orders"""
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate or Cancel  
    FOK = "FOK"  # Fill or Kill
    GTD = "GTD"  # Good Till Date
```

### **KlineInterval (NEW 2025)**  
```python
class KlineInterval(Enum):
    """Kline/Candlestick chart intervals"""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m" 
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"
```

### **StreamType (WebSocket Stream Categories)**
```python
class StreamType(Enum):
    ORDERBOOK = "orderbook"    # Order book updates
    TRADES = "trades"          # Real-time trades
    TICKER = "ticker"          # 24hr ticker data
    KLINE = "kline"           # Candlestick data
    ACCOUNT = "account"        # Account updates
    ORDERS = "orders"          # Order updates
    BALANCE = "balance"        # Balance updates
```

## Core Data Structures

### **Symbol (Hashable, Frozen)**
```python
class Symbol(Struct, frozen=True):
    base: AssetName           # Base asset (e.g., BTC)
    quote: AssetName          # Quote asset (e.g., USDT)
    is_futures: bool = False  # Futures vs spot
```

**Usage**:
```python
btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
# Hashable - can be used as dict key or in sets
orderbooks = {btc_usdt: OrderBook(...)}
```

### **SymbolInfo (Exchange Trading Rules)**
```python
class SymbolInfo(Struct):
    exchange: ExchangeName          # Exchange identifier
    symbol: Symbol                  # Trading pair
    base_precision: int = 0         # Base asset decimal places
    quote_precision: int = 0        # Quote asset decimal places
    min_quote_amount: float = 0     # Minimum order value
    min_base_amount: float = 0      # Minimum order quantity
    is_futures: bool = False        # Contract type
    maker_commission: float = 0     # Maker fee rate
    taker_commission: float = 0     # Taker fee rate  
    inactive: bool = False          # Trading disabled
```

### **OrderBookEntry (High-Performance Price Level)**
```python
class OrderBookEntry(Struct, frozen=True):
    price: float    # Price level
    size: float     # Quantity at price level
```

### **OrderBook (Real-time Market Depth)**
```python
class OrderBook(Struct):
    bids: list[OrderBookEntry]     # Buy orders (highest first)
    asks: list[OrderBookEntry]     # Sell orders (lowest first)
    timestamp: float               # Update timestamp
```

**Usage**:
```python
orderbook = OrderBook(
    bids=[OrderBookEntry(50000.0, 1.5), OrderBookEntry(49999.0, 2.0)],
    asks=[OrderBookEntry(50001.0, 1.0), OrderBookEntry(50002.0, 0.5)],
    timestamp=time.time()
)

# Access best bid/ask
best_bid = orderbook.bids[0] if orderbook.bids else None
best_ask = orderbook.asks[0] if orderbook.asks else None
spread = best_ask.price - best_bid.price if best_bid and best_ask else 0
```

### **Order (Complete Order Information)**  
```python
class Order(Struct):
    symbol: Symbol                          # Trading pair
    side: Side                              # BUY or SELL
    order_type: OrderType                   # Order type
    price: float                            # Order price
    amount: float                           # Order quantity
    amount_filled: float = 0.0              # Filled quantity
    order_id: Optional[OrderId] = None      # Exchange order ID
    status: OrderStatus = OrderStatus.NEW   # Order status
    timestamp: Optional[datetime] = None    # Order timestamp
    fee: float = 0.0                       # Trading fee paid
```

### **Trade (Trade Execution Data)**
```python
class Trade(Struct):
    price: float        # Execution price
    amount: float       # Trade quantity
    side: Side          # Trade direction
    timestamp: int      # Trade timestamp (ms)
    is_maker: bool = False  # Maker vs taker
```

### **AssetBalance (Account Balance)**
```python
class AssetBalance(Struct):
    asset: AssetName        # Asset identifier
    free: float             # Available balance
    locked: float = 0.0     # Locked balance (in orders)

    @property
    def total(self) -> float:
        return self.free + self.locked
```

## Market Data Structures (NEW 2025)

### **Ticker (24hr Price Statistics)**
```python
class Ticker(Struct):
    """24hr ticker price change statistics"""
    symbol: Symbol
    price: float                      # Current price
    price_change: float = 0.0         # 24hr price change
    price_change_percent: float = 0.0 # 24hr change percentage
    high_price: float = 0.0           # 24hr high
    low_price: float = 0.0            # 24hr low
    volume: float = 0.0               # 24hr volume (base)
    quote_volume: float = 0.0         # 24hr volume (quote)
    open_price: float = 0.0           # 24hr opening price
    timestamp: float = 0.0            # Statistics timestamp
```

### **Kline (OHLCV Candlestick Data)**
```python
class Kline(Struct):
    """Kline/Candlestick data"""
    symbol: Symbol              # Trading pair
    interval: KlineInterval     # Time interval
    open_time: int             # Period start time
    close_time: int            # Period end time
    open_price: float          # Opening price
    high_price: float          # Highest price
    low_price: float           # Lowest price
    close_price: float         # Closing price
    volume: float              # Volume (base asset)
    quote_volume: float        # Volume (quote asset)
    trades_count: int = 0      # Number of trades
```

## Account Management Structures (NEW 2025)

### **TradingFee (Fee Structure)**
```python
class TradingFee(Struct):
    """Trading fee structure"""
    symbol: Symbol      # Trading pair
    maker_fee: float    # Maker fee rate
    taker_fee: float    # Taker fee rate
```

### **AccountInfo (Account Details)**
```python
class AccountInfo(Struct):
    """Account information"""
    exchange: ExchangeName                  # Exchange identifier
    account_type: str = "SPOT"              # Account type
    can_trade: bool = True                  # Trading enabled
    can_withdraw: bool = True               # Withdrawal enabled
    can_deposit: bool = True                # Deposit enabled
    balances: list[AssetBalance] = []       # Asset balances
    permissions: list[str] = []             # Account permissions
```

## Usage Examples

### **Basic Trading Workflow**
```python
from structs.exchange import *
from exchanges.mexc.mexc_public import MexcPublicExchange

async def trading_example():
    # Initialize exchange
    exchange = MexcPublicExchange()
    
    # Define symbol
    btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    # Get exchange info
    exchange_info = await exchange.get_exchange_info()
    symbol_info = exchange_info[btc_usdt]
    
    print(f"Min order size: {symbol_info.min_base_amount} BTC")
    print(f"Min order value: {symbol_info.min_quote_amount} USDT")
    print(f"Maker fee: {symbol_info.maker_commission:.4f}%")
    
    # Get current orderbook
    orderbook = await exchange.get_orderbook(btc_usdt, limit=10)
    if orderbook.bids and orderbook.asks:
        spread = orderbook.asks[0].price - orderbook.bids[0].price
        print(f"Current spread: ${spread:.2f}")
    
    # Get recent trades
    trades = await exchange.get_recent_trades(btc_usdt, limit=5)
    if trades:
        last_trade = trades[0]
        print(f"Last trade: ${last_trade.price:.2f} @ {last_trade.amount:.4f} BTC")
```

### **Market Data Analysis**
```python
async def market_analysis():
    exchange = MexcPublicExchange()
    symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
    ]
    
    await exchange.init(symbols)
    
    # Monitor real-time orderbooks
    for _ in range(10):
        for symbol in symbols:
            orderbook = exchange.get_realtime_orderbook(symbol)
            if orderbook and orderbook.bids and orderbook.asks:
                spread = orderbook.asks[0].price - orderbook.bids[0].price
                spread_pct = (spread / orderbook.bids[0].price) * 100
                
                print(f"{symbol.base}/{symbol.quote}: "
                      f"Bid: ${orderbook.bids[0].price:.2f}, "
                      f"Ask: ${orderbook.asks[0].price:.2f}, "
                      f"Spread: {spread_pct:.3f}%")
        
        await asyncio.sleep(1)
```

## Performance Characteristics

### **msgspec.Struct Benefits**
- **3-5x faster** than `@dataclass` for serialization/deserialization
- **Zero-copy JSON parsing** with structured validation
- **Memory efficient** with optimized field storage
- **Hashable when frozen** for use as dictionary keys

### **Type Safety Benefits**  
- **NewType aliases** provide type checking without runtime overhead
- **IntEnum for status codes** enables fast integer comparisons vs string matching
- **Comprehensive type annotations** for IDE support and static analysis
- **Frozen structures** prevent accidental mutation in concurrent environments

### **Production Readiness**
- **Complete coverage** of all essential trading operations
- **Exchange-agnostic design** works with any cryptocurrency exchange
- **Performance optimized** for high-frequency trading applications
- **Backward compatible** with existing codebases through aliases

---

**Summary**: The data structures provide a complete, high-performance foundation for cryptocurrency trading applications with full type safety, comprehensive coverage of trading operations, and optimized performance characteristics suitable for production high-frequency trading systems.