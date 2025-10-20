# PROJECT GUIDES - CEX Arbitrage Engine

**Critical development rules, design patterns, and implementation requirements for maintaining HFT system integrity.**

## 🚨 MANDATORY DEVELOPMENT RULES

### **1. Separated Domain Architecture (ABSOLUTE)**

**Rule**: Public and private domains are COMPLETELY isolated with zero inheritance.

```python
# ✅ CORRECT - Separated domains
public_exchange = factory.create_public_exchange('mexc_spot')    # Market data only
private_exchange = factory.create_private_exchange('mexc_spot')  # Trading only

# ❌ FORBIDDEN - Domain mixing  
class PrivateExchange(PublicExchange): pass  # NEVER DO THIS
```

**Rationale**: 
- **Security**: Trading operations isolated from market data
- **Authentication Boundary**: Clear separation of authenticated vs non-authenticated
- **HFT Performance**: Independent optimization per domain
- **Compliance**: No real-time data leakage between domains

### **2. HFT Caching Policy (CRITICAL SAFETY)**

**Rule**: NEVER cache real-time trading data. Period.

```python
# ❌ PROHIBITED - Real-time data caching
self._cached_balances = await get_account_balance()  # DANGEROUS
self._cached_orderbook = await get_orderbook(symbol)  # STALE PRICES

# ✅ PERMITTED - Static configuration caching
self._symbol_info = load_symbol_info()  # Static trading rules
self._exchange_config = load_exchange_config()  # Static settings
```

**Rationale**: Stale data causes failed arbitrage, phantom liquidity, compliance violations.

### **3. Struct-First Data Policy (PERFORMANCE)**

**Rule**: msgspec.Struct over dict for ALL data modeling.

```python
# ✅ CORRECT - Type-safe structs
@struct
class OrderBook:
    symbol: Symbol
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: int

# ❌ AVOID - Untyped dictionaries
orderbook = {"symbol": "BTC/USDT", "bids": [...]}  # No validation
```

**Benefits**: 10x+ faster serialization, compile-time validation, zero-copy operations.

### **4. Float-Only Data Policy (PERFORMANCE)**

**Rule**: NEVER use Decimal, ALWAYS use float for all numerical operations.

```python
# ✅ CORRECT - float for all numerical operations
@struct
class PriceLevel:
    price: float      # Fast, HFT-optimized
    quantity: float   # Consistent with price
    timestamp: int

@struct  
class Order:
    symbol: Symbol
    side: Side
    price: float      # Sub-nanosecond arithmetic
    quantity: float   # Hardware-optimized operations
    
# ❌ PROHIBITED - Decimal usage
from decimal import Decimal
@struct
class SlowOrder:
    price: Decimal    # NEVER USE - 100x slower than float
    quantity: Decimal # NEVER USE - memory inefficient
```

**Performance Metrics**:
- **float operations**: ~1ns per operation (hardware-optimized)
- **Decimal operations**: ~100ns+ per operation (100x slower)
- **Memory usage**: float 8 bytes vs Decimal 28+ bytes (3.5x more efficient)
- **Cache efficiency**: float arrays fit better in CPU cache lines

**HFT Rationale**:
- **Hardware Acceleration**: float leverages CPU floating-point units (FPUs)
- **Memory Efficiency**: Smaller memory footprint improves cache performance
- **Precision Sufficient**: 15-17 decimal digits adequate for all cryptocurrency trading
- **System Consistency**: Uniform data types across all numerical operations
- **Latency Critical**: Every nanosecond matters in HFT arbitrage

**Implementation Examples**:
```python
# ✅ CORRECT - Order placement with float precision
async def place_order(self, symbol: Symbol, side: Side, price: float, quantity: float):
    order_data = {
        "symbol": symbol.format_for_exchange(),
        "side": side.value,
        "price": f"{price:.8f}",      # Float formatted to 8 decimals
        "quantity": f"{quantity:.8f}"  # Sufficient precision for crypto
    }
    return await self._rest_client.post("/order", order_data)

# ✅ CORRECT - Price calculations using float arithmetic  
def calculate_arbitrage_profit(self, buy_price: float, sell_price: float, quantity: float) -> float:
    gross_profit = (sell_price - buy_price) * quantity
    fee_cost = (buy_price * 0.001 + sell_price * 0.001) * quantity  # 0.1% fee each side
    return gross_profit - fee_cost  # Pure float arithmetic, sub-nanosecond execution

# ✅ CORRECT - Market data processing with float efficiency
@struct
class OrderBookLevel:
    price: float      # Direct hardware operations
    quantity: float   # No conversion overhead
    
def process_orderbook_update(self, levels: List[OrderBookLevel]) -> float:
    total_volume = sum(level.quantity for level in levels)  # Vectorized float ops
    weighted_price = sum(level.price * level.quantity for level in levels) / total_volume
    return weighted_price  # 1000x faster than Decimal equivalent
```

## 🏗️ CORE DESIGN PATTERNS

### **Configuration System Architecture**

**Base Components**:
```python
# Hierarchical configuration with domain separation
HftConfig()
├── ExchangeConfigManager()  # Per-exchange settings
├── DatabaseConfigManager()  # Data persistence
├── NetworkConfigManager()   # Transport layer
└── LoggingConfigManager()   # HFT logging system
```

**Usage Pattern**:
```python
from config.config_manager import HftConfig

config = HftConfig()
exchange_config = config.get_exchange_config('mexc_spot')
db_config = config.get_database_config()
```

### **Factory Pattern (Domain Separation)**

**Core Factory Hierarchy**:
```python
FullExchangeFactory
├── CompositeExchangeFactory  # High-level orchestration
└── TransportFactory          # REST/WebSocket clients
```

**Creation Patterns**:
```python
# Separated domain creation
factory = FullExchangeFactory()
public, private = await factory.create_exchange_pair('mexc_spot', symbols)

# Individual domain creation
public_only = await factory.create_public_exchange('mexc_spot', symbols)
private_only = await factory.create_private_exchange('mexc_spot')
```

### **ExchangeEnum Type System**

**Semantic Naming Convention**:
```python
class ExchangeEnum(Enum):
    MEXC = ExchangeName("MEXC_SPOT")           # MEXC spot trading
    GATEIO = ExchangeName("GATEIO_SPOT")       # Gate.io spot trading  
    GATEIO_FUTURES = ExchangeName("GATEIO_FUTURES")  # Gate.io futures trading
```

**Benefits**: Type-safe exchange identification, consistent naming, compile-time validation.

### **HFT Logging Integration**

**Performance-First Logging**:
```python
from infrastructure.logging import HFTLoggerFactory

# Factory-based injection
logger = HFTLoggerFactory.get_logger("arbitrage.engine")

# Performance tracking
with LoggingTimer(logger, "order_execution") as timer:
    order = await exchange.place_order(...)
    
# Sub-millisecond: 1.16μs avg latency, 859K+ msg/sec
```

## 📐 DESIGN PRINCIPLES

### **Pragmatic SOLID Application**

**Single Responsibility**: Components have ONE clear purpose
```python
# ✅ GOOD - Single responsibility
class OrderBookProcessor:  # ONLY processes orderbooks
class OrderExecutor:       # ONLY executes orders

# ❌ BAD - Multiple responsibilities  
class TradingEngine:       # Does everything
```

**Interface Segregation**: Domain-specific interfaces
```python
# ✅ GOOD - Segregated interfaces
PublicSpotRest      # Market data only
PrivateSpotRest     # Trading only

# ❌ BAD - Fat interface
AllInOneInterface   # Market data + trading mixed
```

**Dependency Inversion**: Factory injection everywhere
```python
# ✅ GOOD - Dependency injection
class MexcExchange:
    def __init__(self, logger: HFTLogger, config: ExchangeConfig):
        
# ❌ BAD - Hard dependencies
class MexcExchange:
    def __init__(self):
        self.logger = print  # Hard-coded
```

### **Cyclomatic Complexity Limits**

**Target**: Keep functions under 10 cyclomatic complexity

```python
# ✅ GOOD - Low complexity (CC: 3)
async def place_order(self, symbol: Symbol, side: Side, quantity: float):
    if not self._validate_params(symbol, side, quantity):
        raise ValidationError("Invalid parameters")
        
    return await self._rest_client.place_order(symbol, side, quantity)

# ❌ BAD - High complexity (CC: 15+)
async def complex_trading_logic(...):
    if condition1:
        if condition2:
            for item in items:
                if item.type == "A":
                    # ... 10+ nested conditions
```

**Tools**: Use complexity analysis in CI/CD, refactor when CC > 10.

### **Error Handling Patterns**

**Composed Exception Hierarchy**:
```python
# Base exceptions
ExchangeError          # Root exchange error
├── ExchangeAPIError   # API communication errors
├── ExchangeAuthError  # Authentication failures
└── ExchangeRateError  # Rate limiting errors

# Usage pattern
try:
    order = await exchange.place_order(...)
except ExchangeAPIError as e:
    logger.error("API error", error=str(e))
    await self._handle_api_error(e)
except ExchangeAuthError as e:
    logger.error("Auth error", error=str(e))
    await self._handle_auth_error(e)
```

## ⚡ HFT PERFORMANCE REQUIREMENTS

### **Latency Targets (MANDATORY)**

- **Order Execution**: <50ms end-to-end
- **Market Data Processing**: <500μs per update  
- **WebSocket Message Routing**: <1ms per message
- **Symbol Resolution**: <1μs per lookup
- **Configuration Access**: <100ns per call
- **Float Operations**: <1ns per calculation (hardware-accelerated)

### **Memory Efficiency**

- **Connection Reuse**: >95% efficiency target
- **Object Pooling**: 75%+ allocation reduction
- **Zero-Copy Operations**: msgspec.Struct throughout
- **Memory Leaks**: Zero tolerance policy
- **Float Precision**: 8 bytes vs 28+ bytes for Decimal (3.5x efficiency)

### **Throughput Requirements**

- **Market Data**: 10K+ updates/second sustained
- **Order Processing**: 1K+ orders/second peak
- **Log Messages**: 859K+ messages/second (achieved)
- **Symbol Lookups**: 1M+ operations/second
- **Float Calculations**: Hardware-limited (billions/second)

## 🛠️ IMPLEMENTATION CHECKLIST

### **New Exchange Integration**

1. **Domain Separation**: ✅ Implement separated public/private classes
2. **Interface Compliance**: ✅ Extend composite base classes  
3. **Factory Integration**: ✅ Add to factory creation methods
4. **Configuration**: ✅ Add exchange-specific config
5. **Float Data Types**: ✅ Use float for all price/quantity fields
6. **Testing**: ✅ Integration + performance tests
7. **Documentation**: ✅ Update specifications

### **Performance Validation**

1. **Latency Testing**: ✅ Sub-millisecond targets met
2. **Memory Profiling**: ✅ No leaks, efficient allocation
3. **Load Testing**: ✅ Sustained throughput validation
4. **HFT Compliance**: ✅ Real-time data not cached
5. **Float Performance**: ✅ Hardware-accelerated operations verified

### **Code Quality Gates**

1. **Type Checking**: ✅ mypy --strict passes
2. **Complexity Analysis**: ✅ CC < 10 for all functions
3. **Test Coverage**: ✅ >90% line coverage
4. **Performance Benchmarks**: ✅ All targets met
5. **Data Type Validation**: ✅ No Decimal usage detected

## 🎯 CRITICAL SUCCESS FACTORS

1. **Separated Domain Architecture**: NEVER mix public/private domains
2. **HFT Caching Policy**: NEVER cache real-time trading data
3. **Float-Only Policy**: NEVER use Decimal, ALWAYS use float for performance
4. **Performance First**: Sub-millisecond targets are non-negotiable
5. **Type Safety**: msgspec.Struct everywhere, no untyped dicts
6. **Factory Injection**: Dependency injection for all components
7. **Configuration Management**: Hierarchical config with domain support

---

**Remember**: This is a professional HFT trading system. Performance, correctness, and safety are paramount. When in doubt, prioritize safety over optimization, but ALWAYS use float for numerical operations to maintain HFT performance requirements.

### **5. Literal String State System (HFT PERFORMANCE)**

**Rule**: Use Literal string types for ALL state management, NEVER IntEnum.

```python
# ✅ CORRECT - Literal string states for maximum performance
from typing import Literal

TradingStrategyState = Literal[
    'idle', 'executing', 'monitoring', 'adjusting',
    'completed', 'not_started', 'cancelled', 'paused', 'error'
]

ArbitrageState = Literal[
    'idle', 'paused', 'error', 'completed', 'cancelled', 'executing', 'adjusting',
    'initializing', 'monitoring', 'analyzing', 'error_recovery'
]


# State transitions use strings directly
def _transition(self, new_state: str) -> None:
    self.context.status = new_state  # Direct string assignment


# State handlers use string keys with function references  
def get_unified_state_handlers(self) -> Dict[str, StateHandler]:
    return {
        'idle': self._handle_idle,  # Direct function reference
        'executing': self._handle_executing,  # No reflection overhead
        'monitoring': self._handle_monitoring,
        'completed': self._handle_completed
    }


# ❌ PROHIBITED - IntEnum states (100x slower)
from enum import IntEnum


class SlowTradingState(IntEnum):  # NEVER USE
    IDLE = 1  # Enum comparison overhead
    EXECUTING = 2  # Method name string lookup
    COMPLETED = 3  # Runtime reflection for handlers
```

**Performance Metrics**:
- **String state comparisons**: ~1ns with interning optimization
- **IntEnum comparisons**: ~100ns+ with method resolution overhead  
- **Handler lookup**: Direct function reference (0ns) vs string method lookup (~50ns)
- **Memory usage**: Interned strings reuse memory vs enum object allocation

**HFT Benefits**:
- **String Interning**: Python automatically interns string literals for O(1) comparisons
- **Zero Reflection**: Direct function references eliminate runtime method resolution
- **Cache Efficiency**: String constants fit in CPU instruction cache
- **Type Safety**: Literal types provide compile-time validation with zero runtime cost
- **Serialization Speed**: Strings serialize 10x+ faster than enum values

**Implementation Pattern**:

```python
# Base task defines unified handler pattern
class BaseTradingTask:
    def get_unified_state_handlers(self) -> Dict[str, StateHandler]:
        """Override in subclasses with complete state mapping."""
        raise NotImplementedError("Subclasses must implement unified handlers")

    async def execute_once(self) -> TaskExecutionResult:
        # Direct function call - no reflection
        handler = self._state_handlers.get(self.context.status)
        if handler:
            await handler()  # Direct function invocation
```

**Migration from IntEnum**:
- Replace `TradingStrategyState.IDLE` with `'idle'`
- Replace `state == TradingState.EXECUTING` with `state == 'executing'`
- Update all serialization code to handle string states
- Convert handler dictionaries from enum keys to string keys

**Last Updated**: October 2025 - Post-Literal String State System + Enhanced Serialization