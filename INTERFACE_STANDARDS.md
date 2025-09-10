# CEX Arbitrage Engine Interface Standards

## Overview

This document establishes comprehensive interface standards for the CEX arbitrage engine to ensure consistency, performance, and maintainability across all exchange implementations. These standards address the current architectural fragmentation and provide a unified approach for all future development.

## Table of Contents

- [Architecture Decision](#architecture-decision)
- [MANDATORY Architectural Rules (2025 Update)](#mandatory-architectural-rules-2025-update)
- [Unified Interface Hierarchy](#unified-interface-hierarchy)
- [Data Structure Standards](#data-structure-standards)
- [Exception Handling Standards](#exception-handling-standards)
- [Performance Requirements](#performance-requirements)
- [Implementation Guidelines](#implementation-guidelines)
- [Migration Strategy](#migration-strategy)
- [Quality Assurance](#quality-assurance)

## Architecture Decision

**DECISION**: We standardize on the **`src/` directory architecture** as the unified interface standard, deprecating the `raw/` directory approach.

### Rationale

1. **Performance Optimized**: Uses `msgspec.Struct` for 3-5x performance improvement
2. **Type Safety**: Comprehensive type annotations and modern Python patterns
3. **Async-First**: Designed for high-frequency trading with proper async/await patterns
4. **Modular Design**: Clean separation between public and private interfaces
5. **Extensibility**: Abstract Factory pattern allows easy addition of new exchanges

## MANDATORY Architectural Rules (2025 Update)

These rules are **CRITICAL** for maintaining clean architecture and preventing circular import dependencies that break the module system.

### Rule 1: Abstract Interface Separation

**MANDATORY REQUIREMENT**: Abstract interfaces MUST NOT import concrete exchange implementations.

#### 1.1 The Problem: Circular Import Dependencies

Circular imports occur when modules depend on each other, creating import loops that break Python's module system:

```
PublicExchangeInterface imports MexcWebSocketPublicStream
        ↓
MexcWebSocketPublicStream imports MexcPublicExchange  
        ↓
MexcPublicExchange imports PublicExchangeInterface
        ↓
[CIRCULAR DEPENDENCY - IMPORT FAILURE]
```

#### 1.2 The Solution: Pure Abstract Interfaces

**CORRECT PATTERN** - Abstract interfaces remain pure:

```python
# ✅ CORRECT: exchanges/interface/public_exchange.py
from abc import ABC, abstractmethod
from structs.exchange import Symbol, OrderBook, Trade  # ✅ Only import data structures

class PublicExchangeInterface(ABC):
    """Pure abstract interface - NO concrete implementation imports"""
    
    @abstractmethod
    async def get_orderbook(self, symbol: Symbol) -> OrderBook:
        """Abstract method - no implementation knowledge"""
        pass
    
    # ✅ NO WebSocket imports here - each exchange handles its own
```

**INCORRECT PATTERN** - Abstract interfaces importing concrete implementations:

```python
# ❌ FORBIDDEN: This creates circular imports
from abc import ABC, abstractmethod
from structs.exchange import Symbol, OrderBook
from exchanges.mexc.websocket import MexcWebSocketPublicStream  # ❌ CIRCULAR IMPORT

class PublicExchangeInterface(ABC):
    """ANTI-PATTERN: Abstract importing concrete"""
    
    def __init__(self):
        # ❌ Abstract interface should not know about specific implementations
        self.websocket = MexcWebSocketPublicStream()  # ❌ BREAKS SEPARATION
```

#### 1.3 Implementation Requirements

**Each Exchange Handles Its Own Integration**:

```python
# ✅ CORRECT: exchanges/mexc/mexc_public.py
from exchanges.interface.public_exchange import PublicExchangeInterface
from exchanges.mexc.websocket import MexcWebSocketPublicStream  # ✅ OK here

class MexcPublicExchange(PublicExchangeInterface):
    """Concrete implementation handles its own WebSocket integration"""
    
    def __init__(self):
        # ✅ Concrete implementation can integrate WebSocket functionality
        self.websocket = MexcWebSocketPublicStream()
        super().__init__()
```

#### 1.4 Benefits of Separation

1. **Eliminates Circular Imports**: Clean dependency graph
2. **True Abstract Interfaces**: Pure contracts without implementation knowledge
3. **Flexible Integration**: Each exchange can implement WebSocket differently
4. **Maintainable Architecture**: Clear separation of concerns
5. **Easy Testing**: Interfaces can be mocked without concrete dependencies

### Rule 2: Import Path Standardization

**MANDATORY REQUIREMENT**: NEVER use `src.` prefix in import statements.

#### 2.1 The Standard: Relative to src Directory

Since `src` is the base folder, all imports should be relative to it:

```python
# ✅ CORRECT: Import paths relative to src/
from exchanges.mexc.mexc_public import MexcPublicExchange
from exchanges.interface.public_exchange import PublicExchangeInterface
from structs.exchange import Symbol, OrderBook, Trade
from common.exceptions import ExchangeAPIError, RateLimitError
from common.rest import HighPerformanceRestClient
```

```python
# ❌ INCORRECT: Using src. prefix
from src.exchanges.mexc.mexc_public import MexcPublicExchange
from src.exchanges.interface.public_exchange import PublicExchangeInterface
from src.structs.exchange import Symbol, OrderBook, Trade
from src.common.exceptions import ExchangeAPIError
```

#### 2.2 Rationale for Standardization

1. **Consistency**: All imports follow the same pattern across the codebase
2. **Clarity**: Shorter, cleaner import statements
3. **Flexibility**: Easier to refactor and reorganize modules
4. **Python Best Practices**: Standard approach for package imports
5. **IDE Support**: Better autocomplete and navigation

#### 2.3 Migration Requirements

**All existing code MUST be updated** to remove `src.` prefixes:

```bash
# Command to find files with src. imports
grep -r "from src\." src/
grep -r "import src\." src/
```

### Rule 3: WebSocket Integration Architecture

**MANDATORY REQUIREMENT**: Each exchange implementation handles its own WebSocket functionality.

#### 3.1 Architectural Principle

**Abstract interfaces define the contract but don't implement WebSocket logic**:

```python
# ✅ CORRECT: Pure interface contract
class PublicExchangeInterface(ABC):
    """Defines what exchanges must provide - not how they implement it"""
    
    @abstractmethod
    async def get_orderbook(self, symbol: Symbol) -> OrderBook:
        """Contract: exchanges must provide orderbooks"""
        pass
    
    # ✅ No WebSocket implementation details in abstract interface
```

#### 3.2 Exchange-Specific Implementation

**Concrete implementations add WebSocket features as needed**:

```python
# ✅ CORRECT: exchanges/mexc/mexc_public.py
class MexcPublicExchange(PublicExchangeInterface):
    """MEXC-specific implementation with its own WebSocket integration"""
    
    def __init__(self):
        # ✅ MEXC handles its own WebSocket setup
        self.websocket = MexcWebSocketPublicStream(
            exchange=self.EXCHANGE_NAME,
            on_message=self._handle_websocket_message,
            on_error=self._handle_websocket_error
        )
        
    async def get_orderbook(self, symbol: Symbol) -> OrderBook:
        """Implementation can use REST API or WebSocket as appropriate"""
        # Can choose between REST endpoint or cached WebSocket data
        return await self._get_orderbook_via_rest(symbol)
        
    def _handle_websocket_message(self, message: dict):
        """MEXC-specific WebSocket message handling"""
        # Process MEXC protobuf messages, update local caches, etc.
        pass
```

#### 3.3 Benefits of This Architecture

1. **Exchange Flexibility**: Each exchange can implement WebSocket differently
2. **No Circular Dependencies**: Clear separation between interfaces and implementations
3. **Maintainable Code**: WebSocket logic is contained within specific exchange implementations
4. **Easy Testing**: Can test REST and WebSocket functionality independently
5. **Performance Optimization**: Each exchange can optimize its own WebSocket handling

#### 3.4 Implementation Guidelines

**For New Exchange Implementations**:

1. **Implement the abstract interface first** (REST API methods)
2. **Add WebSocket functionality internally** within the exchange implementation
3. **Use WebSocket data to enhance REST responses** (caching, real-time updates)
4. **Keep WebSocket integration separate** from the abstract interface contract
5. **Document WebSocket-specific features** in exchange-specific documentation

## Unified Interface Hierarchy

### Core Interface Structure

```
src/exchanges/interface/
├── base_exchange.py          # Base exchange interface (unified)
├── public_exchange.py        # Public market data interface
├── private_exchange.py       # Private trading interface  
├── public_ws.py             # Public WebSocket interface
├── private_ws.py            # Private WebSocket interface
└── ws_base.py               # Base WebSocket interface
```

### 1. Public Exchange Interface

All exchanges MUST implement `PublicExchangeInterface`:

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from src.structs.exchange import (
    Symbol, SymbolInfo, OrderBook, Trade, ExchangeName
)

class PublicExchangeInterface(ABC):
    """Abstract interface for public exchange operations (market data)"""
    
    @property
    @abstractmethod
    def exchange_name(self) -> ExchangeName:
        """Return the exchange name identifier"""
        pass

    @abstractmethod
    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
        """Get exchange trading rules and symbol information"""
        pass
    
    @abstractmethod
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """Get order book for a symbol"""
        pass
    
    @abstractmethod
    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """Get recent trades for a symbol"""
        pass
    
    @abstractmethod
    async def get_server_time(self) -> int:
        """Get server timestamp in milliseconds"""
        pass
    
    @abstractmethod
    async def ping(self) -> bool:
        """Test connectivity to the exchange"""
        pass
```

### 2. Private Exchange Interface

All exchanges MUST implement `PrivateExchangeInterface`:

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from src.structs.exchange import (
    Symbol, Order, OrderId, OrderType, Side, 
    AssetBalance, AssetName, ExchangeName
)

class PrivateExchangeInterface(ABC):
    """Abstract interface for private exchange operations"""
    
    @property
    @abstractmethod
    def exchange_name(self) -> ExchangeName:
        """Return the exchange name identifier"""
        pass
    
    @abstractmethod
    async def get_account_balance(self) -> Dict[AssetName, AssetBalance]:
        """Get account balance for all assets"""
        pass
    
    @abstractmethod
    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        order_type: OrderType,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        time_in_force: Optional[str] = None,
    ) -> Order:
        """Place a new order"""
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: str) -> Order:
        """Cancel an active order"""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """Get all open orders for account or symbol"""
        pass
```

### 3. WebSocket Interface Standards

#### Base WebSocket Interface

```python
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Dict, Any
import asyncio

class BaseWebSocketInterface(ABC):
    """Base WebSocket interface for real-time data streaming"""
    
    def __init__(
        self,
        exchange: ExchangeName,
        on_message: Callable[[Dict[str, Any]], None],
        on_error: Optional[Callable[[Exception], None]] = None,
        on_close: Optional[Callable[[], None]] = None
    ):
        self.exchange = exchange
        self.on_message = on_message
        self.on_error = on_error
        self.on_close = on_close
        
    @abstractmethod
    async def connect(self) -> bool:
        """Establish WebSocket connection"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close WebSocket connection"""
        pass
    
    @abstractmethod
    async def subscribe(self, streams: List[str]) -> None:
        """Subscribe to data streams"""
        pass
    
    @abstractmethod
    async def unsubscribe(self, streams: List[str]) -> None:
        """Unsubscribe from data streams"""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status"""
        pass
```

## Data Structure Standards

### 1. Core Data Structures

All exchanges MUST use the unified data structures from `src/structs/exchange.py`:

#### Symbol Definition
```python
class Symbol(Struct):
    base: AssetName          # Base asset (e.g., "BTC")
    quote: AssetName         # Quote asset (e.g., "USDT")  
    is_futures: bool = False # Futures vs spot
```

#### Order Structure
```python
class Order(Struct):
    symbol: Symbol
    side: Side
    order_type: OrderType
    price: float
    amount: float
    amount_filled: float = 0.0
    order_id: Optional[OrderId] = None
    status: OrderStatus = OrderStatus.NEW
    timestamp: Optional[datetime] = None
    fee: float = 0.0
```

#### OrderBook Structure
```python
class OrderBookEntry(Struct):
    price: float
    size: float

class OrderBook(Struct):
    bids: list[OrderBookEntry]
    asks: list[OrderBookEntry]
    timestamp: float
```

### 2. Performance Requirements

- **MUST use `msgspec.Struct`**: Never use `@dataclass` for performance-critical structures
- **MUST use `IntEnum`**: For status codes to enable fast integer comparisons
- **MUST use `NewType`**: For type aliases without runtime overhead
- **MUST use modern type hints**: `list[T]` instead of `List[T]`

## Exception Handling Standards

### 1. Unified Exception Hierarchy

All exchanges MUST use the standardized exception hierarchy from `src/common/exceptions.py`:

```python
class ExchangeAPIError(Exception):
    """Base exception for exchange API errors"""
    def __init__(self, code: int, message: str, api_code: int | None = None):
        self.code = code
        self.message = message
        self.api_code = api_code

class RateLimitError(ExchangeAPIError):
    """Rate limit exceeded exception"""
    def __init__(self, code: int, message: str, api_code: int | None = None, 
                 retry_after: int | None = None):
        super().__init__(code, message, api_code)
        self.retry_after = retry_after

class TradingDisabled(ExchangeAPIError):
    """Trading is disabled for symbol/account"""
    pass

class InsufficientBalance(ExchangeAPIError):
    """Insufficient balance for operation"""
    pass
```

### 2. Exception Mapping Standards

Each exchange MUST implement a standardized error mapping function:

```python
def map_exchange_error(status_code: int, error_response: dict) -> ExchangeAPIError:
    """
    Map exchange-specific errors to standardized exceptions.
    
    Args:
        status_code: HTTP status code
        error_response: Exchange error response
        
    Returns:
        Appropriate standardized exception
    """
    # Implementation specific to each exchange
    pass
```

### 3. Error Handling Requirements

- **NEVER catch generic `Exception`**: Always use specific exception types
- **MUST include structured error information**: code, message, api_code
- **MUST preserve original error context**: Include exchange-specific error codes
- **MUST implement retry logic**: For transient errors with exponential backoff

### 4. Exception Propagation Standards

**MANDATORY RULE**: Exceptions MUST NOT be wrapped in try-catch blocks at individual method level unless there is specific recovery logic. Instead, exceptions should bubble up to the application/caller level for proper handling with full traceback information.

#### 4.1 Anti-Pattern (FORBIDDEN)

```python
async def ping(self) -> bool:
    """
    ANTI-PATTERN: Do NOT catch and suppress exceptions at method level
    """
    try:
        config = create_market_data_config()
        await self.client.get(self.ENDPOINTS['ping'], config=config)
        return True
        
    except (RateLimitError, ExchangeAPIError) as e:
        self.logger.warning(f"API error during ping: {str(e)}")
        return False
    except Exception as e:
        self.logger.warning(f"Unexpected error during ping: {str(e)}")
        return False
```

**Problems with this approach:**
- Loses valuable traceback information needed for debugging
- Hides real errors from the application layer
- Makes error diagnosis and monitoring difficult
- Prevents proper error handling strategies at higher levels

#### 4.2 Correct Pattern (REQUIRED)

```python
async def ping(self) -> bool:
    """
    CORRECT: Let exceptions bubble up naturally
    """
    config = create_market_data_config()
    config.timeout = 3.0
    config.max_retries = 1
    
    await self.client.get(self.ENDPOINTS['ping'], config=config)
    return True
```

#### 4.3 Application-Level Error Handling (REQUIRED)

Handle exceptions at the application/caller level with proper traceback:

```python
async def test_exchange_connectivity():
    """
    Application-level error handling with full traceback
    """
    try:
        is_connected = await exchange.ping()
        if is_connected:
            logger.info("Exchange connection successful")
        else:
            logger.warning("Exchange connection failed")
            
    except (RateLimitError, ExchangeAPIError) as e:
        logger.error(f"Exchange API error: {e}")
        traceback.print_exc()  # REQUIRED: Full traceback for debugging
        
    except Exception as e:
        logger.error(f"Unexpected error testing connectivity: {e}")
        traceback.print_exc()  # REQUIRED: Full traceback for debugging
```

#### 4.4 When Method-Level Exception Handling is Allowed

Exception handling at method level is ONLY permitted when:

1. **Specific Recovery Logic**: The method can meaningfully recover from the error
```python
async def get_cached_data(self, symbol: Symbol) -> Optional[Data]:
    try:
        return await self._fetch_fresh_data(symbol)
    except RateLimitError:
        # VALID: Specific recovery - return cached data
        return self._get_from_cache(symbol)
```

2. **Resource Cleanup**: Method needs to clean up resources before re-raising
```python
async def process_with_lock(self):
    await self._acquire_lock()
    try:
        return await self._do_work()
    finally:
        # VALID: Resource cleanup while preserving exception
        await self._release_lock()
```

3. **Error Transformation**: Converting to more specific exception types
```python
async def parse_response(self, response: dict):
    try:
        return msgspec.convert(response, ResponseType)
    except msgspec.ValidationError as e:
        # VALID: Transform to domain-specific exception
        raise ExchangeAPIError(400, f"Invalid response format: {e}")
```

#### 4.5 Implementation Requirements

All exchange implementations MUST:

- **Remove existing try-catch anti-patterns** from methods like `ping()`, `get_orderbook()`, etc.
- **Let exceptions propagate naturally** to application level
- **Use `traceback.print_exc()`** in application-level error handlers
- **Only catch exceptions when specific recovery logic exists**
- **Preserve full error context** including original stack traces

This approach ensures proper error diagnosis, monitoring, and debugging capabilities essential for high-frequency trading systems.

## Performance Requirements

### 1. Latency Requirements

- **JSON parsing**: <1ms per message
- **HTTP request latency**: <50ms end-to-end  
- **WebSocket → detection**: <50ms end-to-end
- **Order book updates**: Sub-millisecond processing
- **API response transformation**: <5ms per response

### 2. Throughput Requirements

- **Support 10-20 exchanges** simultaneously
- **Process 1000+ messages/second** per exchange
- **Maintain >95% connection uptime**
- **Handle 100+ concurrent requests** per exchange

### 3. Memory Requirements

- **O(1) memory per request**
- **Connection reuse hit rate >95%**
- **LRU cache cleanup** for auth signatures
- **Bounded memory usage** for metrics collection

## Implementation Guidelines

### 1. Exchange Class Structure

Every exchange implementation MUST follow this structure:

```
src/exchanges/{exchange_name}/
├── __init__.py
├── public.py              # PublicExchangeInterface implementation
├── private.py             # PrivateExchangeInterface implementation  
├── ws_public.py           # Public WebSocket implementation
├── ws_private.py          # Private WebSocket implementation
└── utils.py               # Exchange-specific utilities
```

### 2. File Naming Conventions

- **Exchange directories**: Lowercase with underscores (`mexc`, `binance`, `okx`)
- **Class files**: Descriptive names (`public.py`, `private.py`, `ws_public.py`)
- **Class names**: `{ExchangeName}{Interface}` (e.g., `MexcPublicExchange`)

### 3. Import Standards (UPDATED - 2025)

**CRITICAL**: Following the new import path standardization rules:

```python
# ✅ REQUIRED imports for all exchange implementations (NO src. prefix)
from exchanges.interface.public_exchange import PublicExchangeInterface
from exchanges.interface.private_exchange import PrivateExchangeInterface
from structs.exchange import (
    Symbol, SymbolInfo, OrderBook, Trade, Order, 
    AssetBalance, ExchangeName, AssetName
)
from common.exceptions import ExchangeAPIError, RateLimitError
from common.rest import HighPerformanceRestClient, RequestConfig

# ❌ FORBIDDEN - Old imports with src. prefix (MUST BE REMOVED)
# from src.exchanges.interface.public_exchange import PublicExchangeInterface
# from src.structs.exchange import Symbol
# from src.common.exceptions import ExchangeAPIError
```

**Verification Command**: Use this to find and fix old import patterns:
```bash
# Find files with prohibited src. imports
grep -r "from src\." src/ --include="*.py"
grep -r "import src\." src/ --include="*.py"
```

### 4. REST Client Integration

All exchanges MUST use the standardized `HighPerformanceRestClient`:

```python
class ExchangePublicImplementation(PublicExchangeInterface):
    def __init__(self):
        # Standard REST client configuration
        self.client = HighPerformanceRestClient(
            base_url=self.BASE_URL,
            connection_config=self._get_connection_config(),
            max_concurrent_requests=40,
            enable_metrics=True
        )
        
        # Setup exchange-specific rate limiters
        self._setup_rate_limiters()
```

### 5. Symbol Conversion Standards

Every exchange MUST implement these standard methods:

```python
@staticmethod
def symbol_to_pair(symbol: Symbol) -> str:
    """Convert Symbol to exchange-specific trading pair string"""
    # Implementation specific to exchange format
    
@staticmethod  
def pair_to_symbol(pair: str) -> Symbol:
    """Convert exchange-specific trading pair string to Symbol"""
    # Implementation with fallback logic for unknown pairs
```

### 6. Response Transformation Standards

Use `msgspec` structures for exchange responses:

```python
# Define exchange-specific response structures
class ExchangeOrderBookResponse(msgspec.Struct):
    bids: list[list[str]]  # [price, quantity] pairs
    asks: list[list[str]]  # [price, quantity] pairs
    timestamp: int

# Transform to unified format
def _transform_orderbook(self, response: ExchangeOrderBookResponse) -> OrderBook:
    """Transform exchange response to unified OrderBook format"""
    bids = [OrderBookEntry(price=float(bid[0]), size=float(bid[1])) 
            for bid in response.bids]
    asks = [OrderBookEntry(price=float(ask[0]), size=float(ask[1]))
            for ask in response.asks]
    
    return OrderBook(
        bids=bids,
        asks=asks,
        timestamp=float(response.timestamp)
    )
```

## Authentication and Rate Limiting Standards

### 1. Authentication Implementation

Each exchange MUST implement standardized authentication:

```python
def _prepare_auth_headers(self, method: str, endpoint: str, 
                         params: Dict[str, Any]) -> Dict[str, str]:
    """
    Prepare authentication headers using exchange-specific signature method.
    MUST utilize signature caching for performance.
    """
    # Implementation using HighPerformanceRestClient auth features
    pass
```

### 2. Rate Limiting Configuration

Standard rate limiting setup for all exchanges:

```python
def _setup_rate_limiters(self):
    """Configure exchange-specific rate limiters"""
    # Public endpoints - higher limits
    self.client.set_endpoint_rate_limit('/api/v3/depth', 50, 50)
    self.client.set_endpoint_rate_limit('/api/v3/trades', 30, 30)
    
    # Private endpoints - more conservative
    self.client.set_endpoint_rate_limit('/api/v3/order', 10, 5)
    self.client.set_endpoint_rate_limit('/api/v3/account', 5, 1)
```

## WebSocket Standards

### 1. Connection Management

All WebSocket implementations MUST include:

```python
class ExchangeWebSocket(BaseWebSocketInterface):
    async def _handle_reconnection(self):
        """Implement intelligent reconnection with exponential backoff"""
        pass
    
    async def _process_message(self, message: dict):
        """Process incoming messages with error handling"""
        try:
            # Transform to unified format
            unified_data = self._transform_message(message)
            await self.on_message(unified_data)
        except Exception as e:
            if self.on_error:
                await self.on_error(e)
```

### 2. Message Transformation

WebSocket messages MUST be transformed to unified formats:

```python
def _transform_orderbook_message(self, message: dict) -> OrderBook:
    """Transform exchange WebSocket orderbook message to unified format"""
    # Implementation specific to exchange message format
    pass

def _transform_trade_message(self, message: dict) -> Trade:
    """Transform exchange WebSocket trade message to unified format"""
    # Implementation specific to exchange message format
    pass
```

## Testing Standards

### 1. Required Test Coverage

Every exchange implementation MUST include:

- **Unit tests** for all interface methods
- **Integration tests** with mock exchange responses
- **Performance tests** verifying latency requirements
- **Error handling tests** for all exception scenarios
- **Rate limiting tests** verifying compliance

### 2. Test Structure

```
tests/exchanges/{exchange_name}/
├── test_public.py         # Public interface tests
├── test_private.py        # Private interface tests
├── test_websocket.py      # WebSocket tests
├── test_performance.py    # Performance benchmarks
└── fixtures/              # Mock response data
```

### 3. Performance Benchmarks

Each exchange MUST pass performance benchmarks:

```python
@pytest.mark.benchmark
async def test_orderbook_latency():
    """Verify orderbook retrieval meets <50ms requirement"""
    async with create_exchange_client() as client:
        start = time.time()
        orderbook = await client.get_orderbook(symbol)
        latency = (time.time() - start) * 1000
        
        assert latency < 50  # 50ms requirement
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0
```

## Quality Assurance

### 1. Code Review Requirements

All exchange implementations MUST pass:

- **Interface compliance check**: Implements all required methods
- **Performance requirements**: Meets latency and throughput targets  
- **Error handling**: Proper exception mapping and retry logic
- **Type safety**: Full type annotation coverage
- **Documentation**: Comprehensive docstrings and examples

### 2. Automated Checks

CI/CD pipeline MUST include:

```bash
# Type checking
mypy src/exchanges/{exchange_name}/

# Performance profiling
pytest tests/exchanges/{exchange_name}/test_performance.py --benchmark

# Interface compliance
python scripts/verify_interface_compliance.py {exchange_name}

# Integration testing
pytest tests/exchanges/{exchange_name}/ --integration
```

### 3. Performance Monitoring

Production deployments MUST include:

- **Latency monitoring**: P95, P99 response times
- **Error rate tracking**: Exception rates by type
- **Rate limit monitoring**: Token bucket utilization
- **Connection health**: WebSocket uptime and reconnection rates

## Migration Strategy

### Phase 1: Standardization (Immediate)

1. **Deprecate `raw/` directory**: Mark as legacy, no new development
2. **Standardize existing `src/` implementations**: Ensure MEXC implementation fully complies
3. **Create interface compliance checker**: Automated validation tool
4. **Update documentation**: Comprehensive migration guide

### Phase 2: Legacy Migration (1-2 weeks)

1. **Migrate critical components** from `raw/` to `src/` standards
2. **Update import statements** throughout codebase
3. **Consolidate exception handling** to unified hierarchy
4. **Performance test all migrations**: Ensure no regressions

### Phase 3: New Exchange Development (Ongoing)

1. **All new exchanges** use these standards exclusively
2. **Template-based development**: Standardized exchange template
3. **Automated compliance checking**: Pre-commit hooks
4. **Continuous performance monitoring**: Production metrics

## Compliance Checklist (Updated 2025)

For each new exchange implementation, verify:

### MANDATORY Architectural Compliance (2025 Rules)
- [ ] **Abstract Interface Separation**: Abstract interfaces do NOT import concrete implementations
- [ ] **Import Path Standardization**: NO `src.` prefixes in any import statements
- [ ] **WebSocket Integration**: Each exchange handles its own WebSocket functionality internally
- [ ] **Circular Import Prevention**: No circular dependencies in module structure

### Core Interface Compliance
- [ ] **Implements required interfaces**: PublicExchangeInterface, PrivateExchangeInterface
- [ ] **Uses unified data structures**: All structs from `structs/exchange.py`
- [ ] **Follows exception standards**: Proper error mapping and handling
- [ ] **Implements exception propagation**: No try-catch anti-patterns, exceptions bubble to application level
- [ ] **Meets performance requirements**: <50ms latency, >95% uptime
- [ ] **Includes comprehensive tests**: Unit, integration, performance tests
- [ ] **Uses HighPerformanceRestClient**: Standardized HTTP client
- [ ] **Implements proper rate limiting**: Exchange-specific limits configured
- [ ] **Provides symbol conversion**: Standard `symbol_to_pair`/`pair_to_symbol` methods
- [ ] **Supports WebSocket streams**: Real-time data with reconnection logic
- [ ] **Includes monitoring hooks**: Metrics and health check integration

### Verification Commands

```bash
# Check for prohibited src. imports
grep -r "from src\." src/ --include="*.py" | wc -l  # Should return 0

# Check for circular imports
python -m py_compile src/exchanges/interface/public_exchange.py  # Should succeed

# Verify interface compliance
python scripts/verify_interface_compliance.py {exchange_name}
```

## Example Implementation Reference

See `/Users/dasein/dev/cex_arbitrage/src/exchanges/mexc/public.py` for a complete reference implementation that demonstrates all standards in practice.

## Conclusion

These interface standards provide the foundation for a scalable, high-performance CEX arbitrage engine. By enforcing consistency across all exchange implementations, we ensure:

- **Predictable performance** across all exchanges
- **Easy addition of new exchanges** with minimal overhead
- **Maintainable codebase** with clear separation of concerns
- **Production-ready reliability** with comprehensive error handling
- **Type safety and correctness** throughout the system

All future development MUST adhere to these standards to maintain system integrity and performance characteristics.

## Comprehensive Examples and Anti-Patterns (2025 Update)

### Example 1: Correct Abstract Interface Design

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/interface/public_exchange.py`

```python
# ✅ CORRECT: Pure abstract interface with no concrete dependencies
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

# ✅ CORRECT: Only import data structures and base interfaces
from structs.exchange import (
    Symbol, SymbolInfo, OrderBook, Trade, ExchangeName
)
from exchanges.interface.base_exchange import BaseExchangeInterface

class PublicExchangeInterface(BaseExchangeInterface):
    """Pure abstract interface - NO concrete implementation knowledge"""
    
    def __init__(self, exchange: ExchangeName, base_url: str):
        self.exchange = exchange
        self.base_url = base_url
        self.logger = logging.getLogger(f"public_exchange_{exchange}")
        # ✅ NO WebSocket imports or instantiation here
    
    @abstractmethod
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """Abstract contract - no implementation details"""
        pass
```

### Example 2: Correct Exchange Implementation

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/mexc/public.py`

```python
# ✅ CORRECT: Concrete implementation with proper imports

# ✅ CORRECT: No src. prefixes
from structs.exchange import Symbol, SymbolInfo, OrderBook, Trade, ExchangeName
from common.exceptions import ExchangeAPIError, RateLimitError
from common.rest import HighPerformanceRestClient, create_market_data_config
from exchanges.interface.public_exchange import PublicExchangeInterface

# ✅ CORRECT: Exchange-specific WebSocket import in concrete implementation
from exchanges.mexc.websocket import MexcWebSocketPublicStream

class MexcPublicExchange(PublicExchangeInterface):
    """Concrete MEXC implementation with internal WebSocket integration"""
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        super().__init__(ExchangeName("MEXC"), "https://api.mexc.com")
        
        # ✅ CORRECT: Concrete implementation handles its own WebSocket
        self.websocket = MexcWebSocketPublicStream(
            on_message=self._handle_websocket_message
        )
        
        # ✅ CORRECT: Uses standardized REST client
        self.client = HighPerformanceRestClient(
            base_url=self.BASE_URL,
            api_key=api_key,
            secret_key=secret_key
        )
    
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """Implementation using REST API (could also use WebSocket cache)"""
        # Implementation details...
        pass
    
    def _handle_websocket_message(self, message: dict):
        """Handle MEXC-specific WebSocket messages internally"""
        # MEXC protobuf processing, cache updates, etc.
        pass
```

### Anti-Pattern 1: Circular Import Violation

**File**: `exchanges/interface/public_exchange.py` (FORBIDDEN)

```python
# ❌ FORBIDDEN: This creates circular imports
from abc import ABC, abstractmethod
from structs.exchange import Symbol, OrderBook

# ❌ CIRCULAR IMPORT: Abstract importing concrete
from exchanges.mexc.websocket import MexcWebSocketPublicStream  # BREAKS ARCHITECTURE

class PublicExchangeInterface(ABC):
    """ANTI-PATTERN: Abstract interface importing concrete implementations"""
    
    def __init__(self):
        # ❌ VIOLATION: Abstract interface should not know about specific implementations
        self.websocket = MexcWebSocketPublicStream()  # CREATES CIRCULAR DEPENDENCY
```

### Anti-Pattern 2: Incorrect Import Paths

**File**: Any implementation file (FORBIDDEN)

```python
# ❌ FORBIDDEN: Using src. prefixes
from src.exchanges.interface.public_exchange import PublicExchangeInterface  # OLD STYLE
from src.structs.exchange import Symbol, OrderBook  # DEPRECATED
from src.common.exceptions import ExchangeAPIError  # REMOVE src.

# ✅ CORRECT: Standardized import paths
from exchanges.interface.public_exchange import PublicExchangeInterface
from structs.exchange import Symbol, OrderBook
from common.exceptions import ExchangeAPIError
```

### Migration Command Examples

**Fix Import Paths Automatically**:

```bash
# Find and replace src. imports throughout codebase
find src/ -name "*.py" -exec sed -i 's/from src\./from /g' {} \;
find src/ -name "*.py" -exec sed -i 's/import src\./import /g' {} \;

# Verify no src. imports remain
grep -r "from src\." src/ --include="*.py" || echo "All imports fixed!"
```

**Verify Circular Import Resolution**:

```bash
# Test that all modules can be imported without circular dependency errors
python -c "from exchanges.interface.public_exchange import PublicExchangeInterface; print('✅ Interface imports successfully')"
python -c "from exchanges.mexc.public import MexcPublicExchange; print('✅ Implementation imports successfully')"
```

### Summary: Critical Rules for 2025

1. **Rule 1**: Abstract interfaces NEVER import concrete implementations
2. **Rule 2**: Import paths NEVER use `src.` prefix
3. **Rule 3**: Each exchange handles its own WebSocket integration internally

These rules are **MANDATORY** and prevent the circular import issues that break the module system. All existing code must be updated to comply, and all new code must follow these standards from the start.