# Exchange Integration Guide

**Definitive blueprint for integrating new cryptocurrency exchanges into the HFT arbitrage engine.**

## Table of Contents

1. [Overview](#overview)
2. [Architecture Foundation](#architecture-foundation)
3. [Interface System](#interface-system)
4. [Factory Pattern Implementation](#factory-pattern-implementation)
5. [Step-by-Step Integration Process](#step-by-step-integration-process)
6. [Implementation Standards](#implementation-standards)
7. [Data Structure Standards](#data-structure-standards)
8. [Quality Standards & Testing](#quality-standards--testing)
9. [Reference Implementation: MEXC](#reference-implementation-mexc)
10. [Templates & Code Examples](#templates--code-examples)

## Overview

This guide provides comprehensive instructions for integrating new cryptocurrency exchanges into our ultra-high-performance CEX arbitrage engine. The system follows a clean, factory-pattern-based architecture with unified interfaces and SOLID principles compliance.

### Core Integration Principles

**CRITICAL HFT CACHING POLICY**
- **NEVER cache real-time trading data** (orderbooks, balances, order status, trades)
- **ONLY cache static configuration data** (symbol mappings, exchange info, trading rules)
- **RATIONALE**: Real-time data caching causes stale price execution and regulatory violations

**Unified Interface System**
- ALL exchanges MUST implement `BasePrivateExchangeInterface` from `src/interfaces/cex/base/`
- ALL data structures MUST use `msgspec.Struct` from `src/structs/common.py`
- ALL components MUST use base classes from `src/core/cex/`

**Factory Pattern Architecture**
- Exchange creation via `ExchangeFactory` from `src/cex/factories/`
- Type-safe exchange selection using `ExchangeEnum`
- Automatic dependency injection and service registration
- SOLID principles compliance throughout

## Architecture Foundation

### Core Components

The modern architecture is built on three foundational layers:

**1. Interface Layer** (`src/interfaces/cex/base/`)
```
BaseExchangeInterface (connection & state management)
├── BasePublicExchangeInterface (market data operations)
└── BasePrivateExchangeInterface (trading operations + market data)
```

**2. Core Base Classes** (`src/core/cex/`)
```
src/core/cex/
├── rest/
│   ├── spot/
│   │   ├── base_rest_spot_public.py
│   │   └── base_rest_spot_private.py
│   └── futures/
│       ├── base_rest_futures_public.py
│       └── base_rest_futures_private.py
├── websocket/
│   └── spot/
│       ├── base_ws_public.py
│       └── base_ws_private.py
└── services/
    ├── symbol_mapper/
    └── unified_mapper/
```

**3. Common Data Structures** (`src/structs/common.py`)
```python
# All exchanges use these unified structures
Symbol, OrderBook, Order, AssetBalance, Position
Trade, Ticker, Kline, SymbolInfo, etc.
```

### SOLID Principles Implementation

**Single Responsibility**
- `BasePublicExchangeInterface`: Market data only
- `BasePrivateExchangeInterface`: Trading operations + market data
- REST clients: HTTP operations only
- WebSocket clients: Real-time streaming only

**Open/Closed**
- Interfaces are closed for modification
- New exchanges extend interfaces without changing them

**Liskov Substitution**
- All exchange implementations are fully interchangeable
- Factory pattern ensures consistent behavior

**Interface Segregation**
- Clean separation between public and private operations
- Components depend only on interfaces they need

**Dependency Inversion**
- Depend on abstractions (`BaseExchangeInterface`)
- Factory provides concrete implementations

## Interface System

### Interface Hierarchy

```python
# src/interfaces/cex/base/base_exchange.py
class BaseExchangeInterface(ABC):
    """Foundation interface with connection and state management."""
    async def initialize(self, **kwargs) -> None
    async def close(self) -> None
    @property
    def is_connected(self) -> bool
    @property
    def config(self) -> ExchangeConfig
```

```python
# src/interfaces/cex/base/base_public_exchange.py
class BasePublicExchangeInterface(BaseExchangeInterface):
    """Public market data operations (no authentication)."""
    @property
    @abstractmethod
    def orderbooks(self) -> Dict[Symbol, OrderBook]
    
    @abstractmethod
    async def add_symbol(self, symbol: Symbol) -> None
    
    @abstractmethod
    async def remove_symbol(self, symbol: Symbol) -> None
    
    @abstractmethod
    async def _get_orderbook_snapshot(self, symbol: Symbol) -> OrderBook
```

```python
# src/interfaces/cex/base/base_private_exchange.py
class BasePrivateExchangeInterface(BasePublicExchangeInterface):
    """Trading operations + market data (requires authentication)."""
    @property
    @abstractmethod
    def balances(self) -> Dict[Symbol, AssetBalance]
    
    @property
    @abstractmethod
    def open_orders(self) -> Dict[Symbol, List[Order]]
    
    @abstractmethod
    async def place_limit_order(self, symbol: Symbol, side: str, 
                               quantity: float, price: float) -> Order
    
    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: str) -> bool
```

### Implementation Requirements

**ALL exchanges MUST:**
1. Inherit from `BasePrivateExchangeInterface` (includes public functionality)
2. Use composition to delegate to specialized REST/WebSocket components
3. Implement all abstract methods from both public and private interfaces
4. Use only data structures from `src/structs/common.py`
5. Never cache real-time trading data (HFT compliance)

**Exchange Implementation Pattern:**
```python
# src/cex/{exchange}/{exchange}_exchange.py
class ExchangePrivateExchange(BasePrivateExchangeInterface):
    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        # Composition: delegate to specialized components
        self._rest_client = RestPrivateClient(config)
        self._ws_client = WebSocketPrivateClient(config)
        self._public_client = PublicClient()
```

## Factory Pattern Implementation

### Exchange Factory Architecture

```python
# src/cex/factories/exchange_factory.py
class ExchangeFactory:
    """Factory for creating CEX exchange instances with proper configuration."""
    
    @classmethod
    def create_public_exchange(
        cls,
        exchange: ExchangeEnum,
        symbols: Optional[List[Union[str, Symbol]]] = None
    ) -> PublicExchangeInterface:
        """Create a public exchange instance for market data operations."""
        
    @classmethod
    def create_private_exchange(
        cls,
        exchange: ExchangeEnum,
        config: ExchangeConfig,
        symbols: Optional[List[Union[str, Symbol]]] = None
    ) -> PrivateExchangeInterface:
        """Create a private exchange instance for trading operations."""
```

### Factory Benefits

**Type Safety**
- `ExchangeEnum` ensures only supported exchanges
- Compile-time validation of exchange types
- No string-based exchange selection

**Automatic Dependency Injection**
- REST and WebSocket clients automatically configured
- Symbol mappers and service mappings registered
- Authentication configuration handled securely

**Error Handling**
- Validation of configuration and credentials
- Graceful handling of missing implementations
- Clear error messages for debugging

### Usage Patterns

```python
# Public exchange creation (no credentials required)
exchange = ExchangeFactory.create_public_exchange(
    exchange=ExchangeEnum.MEXC,
    symbols=[Symbol("BTC", "USDT"), Symbol("ETH", "USDT")]
)

# Private exchange creation (requires credentials)
config = ExchangeConfig(
    name=ExchangeName("mexc"),
    credentials=ExchangeCredentials(api_key="...", secret_key="...")
)
exchange = ExchangeFactory.create_private_exchange(
    exchange=ExchangeEnum.MEXC,
    config=config,
    symbols=[Symbol("BTC", "USDT")]
)
```

## Step-by-Step Integration Process

### Phase 1: Research and Planning

**1. Exchange API Analysis**
- REST API documentation review
- WebSocket API capabilities assessment
- Authentication mechanism analysis
- Rate limiting policies understanding
- Data format identification (JSON/protobuf/binary)

**2. Exchange Enum Registration**
```python
# src/cex/__init__.py
class ExchangeEnum(Enum):
    MEXC = "mexc"
    GATEIO = "gateio"
    NEW_EXCHANGE = "new_exchange"  # Add here
```

### Phase 2: Base Structure Creation

**1. Create Exchange Directory Structure**
```
src/cex/new_exchange/
├── __init__.py
├── new_exchange_exchange.py     # Main exchange implementation
├── public_exchange.py           # Public operations
├── private_exchange.py          # Private operations
├── rest/
│   ├── __init__.py
│   ├── new_exchange_rest_public.py
│   └── new_exchange_rest_private.py
├── ws/
│   ├── __init__.py
│   ├── new_exchange_ws_public.py
│   └── new_exchange_ws_private.py
└── services/
    ├── __init__.py
    ├── mapper.py
    └── symbol_mapper.py
```

**2. Implement Base REST Clients**
```python
# src/cex/new_exchange/rest/new_exchange_rest_public.py
from core.cex.rest.spot.base_rest_spot_public import BaseRestSpotPublic

class NewExchangeRestPublic(BaseRestSpotPublic):
    def __init__(self):
        super().__init__(
            base_url="https://api.newexchange.com",
            rate_limits={...},
            timeouts={...}
        )
    
    async def get_exchange_info(self) -> Dict:
        """Get exchange trading rules and symbol information."""
        return await self._request("GET", "/api/v1/exchangeInfo")
    
    async def get_orderbook(self, symbol: str, limit: int = 100) -> Dict:
        """Get orderbook snapshot."""
        return await self._request("GET", "/api/v1/depth", {
            "symbol": symbol,
            "limit": limit
        })
```

### Phase 3: Interface Implementation

**1. Main Exchange Class**
```python
# src/cex/new_exchange/new_exchange_exchange.py
from interfaces.cex.base.base_private_exchange import BasePrivateExchangeInterface
from structs.common import *

class NewExchangePrivateExchange(BasePrivateExchangeInterface):
    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        
        # Composition: delegate to specialized components
        self._rest_public = NewExchangeRestPublic()
        self._rest_private = NewExchangeRestPrivate(config)
        self._ws_public = NewExchangeWebSocketPublic()
        self._ws_private = NewExchangeWebSocketPrivate(config)
        self._symbol_mapper = NewExchangeSymbolMapper()
    
    # Implement all abstract methods from BasePrivateExchangeInterface
    @property
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        return self._orderbooks
    
    @property 
    def balances(self) -> Dict[Symbol, AssetBalance]:
        return self._balances
    
    async def place_limit_order(self, symbol: Symbol, side: str, 
                               quantity: float, price: float) -> Order:
        # HFT COMPLIANT: No caching - fresh API call
        response = await self._rest_private.place_order(
            symbol=self._symbol_mapper.to_exchange_format(symbol),
            side=side,
            type="LIMIT",
            quantity=quantity,
            price=price
        )
        return self._transform_order(response, symbol)
```

### Phase 4: Factory Integration

**1. Update Factory Methods**
```python
# src/cex/factories/exchange_factory.py
@classmethod
def create_private_exchange(cls, exchange: ExchangeEnum, config: ExchangeConfig, 
                          symbols: Optional[List[Union[str, Symbol]]] = None) -> PrivateExchangeInterface:
    if exchange == ExchangeEnum.NEW_EXCHANGE:
        from ..new_exchange import NewExchangePrivateExchange
        return NewExchangePrivateExchange(config=config, symbols=symbols or [])
    # ... existing implementations
```

**2. Update Validation Methods**
```python
@classmethod
def validate_exchange_availability(cls, exchange: ExchangeEnum) -> bool:
    try:
        if exchange == ExchangeEnum.NEW_EXCHANGE:
            from ..new_exchange import NewExchangePublicExchange, NewExchangePrivateExchange
            return True
        # ... existing validations
    except ImportError:
        return False
```

## Implementation Standards

### REST Client Standards

**Base Class Usage**
```python
# ALL REST clients MUST inherit from core base classes
from core.cex.rest.spot.base_rest_spot_public import BaseRestSpotPublic
from core.cex.rest.spot.base_rest_spot_private import BaseRestSpotPrivate

class ExchangeRestPublic(BaseRestSpotPublic):
    def __init__(self):
        super().__init__(
            base_url="https://api.exchange.com",
            rate_limits={"requests_per_second": 20},
            timeouts={"connect": 5.0, "read": 10.0}
        )
```

**HFT Performance Requirements**
- Connection pooling with persistent sessions
- Aggressive timeout configurations (5-10 seconds max)
- Rate limiting compliance via base class
- No caching of real-time trading data

### WebSocket Client Standards

**Base Class Usage**
```python
from core.cex.websocket.spot.base_ws_public import BaseWebSocketPublic

class ExchangeWebSocketPublic(BaseWebSocketPublic):
    def __init__(self):
        super().__init__(
            ws_url="wss://stream.exchange.com/ws",
            ping_interval=20,
            ping_timeout=10
        )
    
    async def _on_message(self, message):
        # msgspec-exclusive JSON processing
        data = msgspec.json.decode(message)
        if self._is_orderbook_update(data):
            await self._handle_orderbook_update(data)
```

**Real-time Data Handling**
- Automatic reconnection with exponential backoff
- Message type detection and routing
- HFT-compliant orderbook diff processing
- No buffering or caching of trading data

## Data Structure Standards

### Unified Structures from `src/structs/common.py`

**ALL exchanges MUST use these exact structures:**

```python
from structs.common import (
    Symbol, OrderBook, OrderBookEntry,
    Order, AssetBalance, Position,
    Trade, Ticker, Kline, SymbolInfo
)

# Example: Converting exchange response to unified structure
def _transform_order(self, exchange_response: Dict, symbol: Symbol) -> Order:
    return Order(
        symbol=symbol,
        order_id=OrderId(exchange_response["orderId"]),
        side=Side.BUY if exchange_response["side"] == "BUY" else Side.SELL,
        order_type=OrderType.LIMIT,
        quantity=float(exchange_response["origQty"]),
        price=float(exchange_response["price"]),
        filled_quantity=float(exchange_response["executedQty"]),
        status=self._map_order_status(exchange_response["status"])
    )
```

### Symbol Mapping Requirements

**Unified Symbol Format**
```python
# All internal operations use Symbol struct
symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))

# Exchange-specific formatting via symbol mapper
class ExchangeSymbolMapper:
    def to_exchange_format(self, symbol: Symbol) -> str:
        # Convert Symbol to exchange-specific string format
        return f"{symbol.base}{symbol.quote}"  # e.g., "BTCUSDT"
    
    def from_exchange_format(self, exchange_symbol: str) -> Symbol:
        # Parse exchange string to Symbol struct
        # Implementation depends on exchange format
        pass
```

## Quality Standards & Testing

### Integration Testing

**Test Categories**
1. **REST API Integration**: All endpoints with real API responses
2. **WebSocket Streaming**: Real-time data processing validation
3. **Order Management**: Complete trading lifecycle testing
4. **Error Handling**: Network failures and API errors
5. **Performance Testing**: Latency and throughput validation

**Test Implementation Pattern**
```python
# src/examples/integration_tests/test_new_exchange.py
import pytest
from cex.factories.exchange_factory import ExchangeFactory
from structs.common import Symbol, ExchangeEnum

class TestNewExchangeIntegration:
    @pytest.mark.asyncio
    async def test_public_orderbook_streaming(self):
        """Test real-time orderbook updates."""
        exchange = ExchangeFactory.create_public_exchange(
            ExchangeEnum.NEW_EXCHANGE,
            symbols=[Symbol("BTC", "USDT")]
        )
        
        await exchange.initialize()
        
        # Wait for initial orderbook
        await asyncio.sleep(2)
        
        orderbooks = exchange.orderbooks
        assert Symbol("BTC", "USDT") in orderbooks
        
        orderbook = orderbooks[Symbol("BTC", "USDT")]
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0
        
        await exchange.close()
```

### Performance Validation

**Latency Requirements**
- REST API calls: <50ms average
- WebSocket message processing: <5ms
- Symbol resolution: <1μs
- Order placement: <100ms end-to-end

**Benchmark Implementation**
```python
import time
import asyncio
from statistics import mean

async def benchmark_order_placement():
    """Benchmark order placement latency."""
    exchange = ExchangeFactory.create_private_exchange(...)
    
    latencies = []
    for _ in range(100):
        start_time = time.perf_counter()
        
        # Place and immediately cancel order
        order = await exchange.place_limit_order(
            Symbol("BTC", "USDT"), "buy", 0.001, 30000.0
        )
        await exchange.cancel_order(Symbol("BTC", "USDT"), order.order_id)
        
        latency = time.perf_counter() - start_time
        latencies.append(latency * 1000)  # Convert to milliseconds
    
    print(f"Average latency: {mean(latencies):.2f}ms")
    print(f"95th percentile: {sorted(latencies)[95]:.2f}ms")
```

## Reference Implementation: MEXC

### Architecture Overview

MEXC serves as the reference implementation demonstrating all architectural patterns:

```
src/cex/mexc/
├── mexc_exchange.py              # Main implementation
├── public_exchange.py            # Public operations
├── private_exchange.py           # Private operations  
├── rest/
│   ├── mexc_rest_public.py      # Public REST client
│   └── mexc_rest_private.py     # Private REST client
├── ws/
│   ├── mexc_ws_public.py        # Public WebSocket
│   ├── mexc_ws_private.py       # Private WebSocket
│   └── protobuf_parser.py       # Protobuf message handling
└── services/
    ├── mapper.py                # Service mappings
    └── symbol_mapper.py         # Symbol format conversion
```

### Key Implementation Patterns

**Composition over Inheritance**
```python
class MexcPrivateExchange(BasePrivateExchangeInterface):
    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        
        # Delegate to specialized components
        self._rest_private = MexcRestPrivate(config)
        self._ws_private = MexcWebSocketPrivate(config)
        self._public = MexcPublicExchange()
        self._symbol_mapper = MexcSymbolMapper()
```

**Protocol Buffer Handling**
```python
# MEXC uses protobuf for WebSocket messages
from .protobuf_parser import ProtobufParser

class MexcWebSocketPrivate(BaseWebSocketPrivate):
    async def _on_message(self, message):
        if isinstance(message, bytes):
            # Protobuf binary message
            parsed = self._protobuf_parser.parse_message(message)
            await self._handle_parsed_message(parsed)
        else:
            # JSON message fallback
            data = msgspec.json.decode(message)
            await self._handle_json_message(data)
```

## Templates & Code Examples

### Exchange Implementation Template

```python
# Template: src/cex/{exchange}/{exchange}_exchange.py
from interfaces.cex.base.base_private_exchange import BasePrivateExchangeInterface
from core.config.structs import ExchangeConfig
from structs.common import *
from typing import Dict, List, Optional

class {Exchange}PrivateExchange(BasePrivateExchangeInterface):
    """
    {Exchange} private exchange implementation.
    
    Provides trading operations and market data via {Exchange} API.
    Implements composition pattern with specialized REST/WebSocket clients.
    """
    
    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        
        # Import exchange-specific components
        from .rest.{exchange}_rest_public import {Exchange}RestPublic
        from .rest.{exchange}_rest_private import {Exchange}RestPrivate
        from .ws.{exchange}_ws_public import {Exchange}WebSocketPublic
        from .ws.{exchange}_ws_private import {Exchange}WebSocketPrivate
        from .services.symbol_mapper import {Exchange}SymbolMapper
        
        # Composition: delegate to specialized components
        self._rest_public = {Exchange}RestPublic()
        self._rest_private = {Exchange}RestPrivate(config)
        self._ws_public = {Exchange}WebSocketPublic()
        self._ws_private = {Exchange}WebSocketPrivate(config)
        self._symbol_mapper = {Exchange}SymbolMapper()
        
        # Initialize state
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._balances: Dict[Symbol, AssetBalance] = {}
        self._open_orders: Dict[Symbol, List[Order]] = {}
        self._positions: Dict[Symbol, Position] = {}
    
    # Public Interface Implementation
    @property
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        """HFT COMPLIANT: Real-time orderbooks, no caching."""
        return self._orderbooks
    
    async def add_symbol(self, symbol: Symbol) -> None:
        """Start streaming data for a symbol."""
        if symbol not in self._active_symbols:
            self._active_symbols.append(symbol)
            
            # Load initial snapshot
            await self._load_orderbook_snapshot(symbol)
            
            # Start real-time streaming
            await self._ws_public.subscribe_orderbook(symbol)
    
    # Private Interface Implementation
    @property
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """HFT COMPLIANT: Real-time balances, no caching."""
        return self._balances
    
    @property
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """HFT COMPLIANT: Real-time orders, no caching."""
        return self._open_orders
    
    async def place_limit_order(self, symbol: Symbol, side: str, 
                               quantity: float, price: float, **kwargs) -> Order:
        """Place a limit order."""
        # HFT COMPLIANT: Fresh API call, no caching
        response = await self._rest_private.place_order(
            symbol=self._symbol_mapper.to_exchange_format(symbol),
            side=side.upper(),
            type="LIMIT",
            quantity=quantity,
            price=price,
            **kwargs
        )
        
        # Transform to unified Order structure
        order = self._transform_order(response, symbol)
        
        # Update internal state
        self._update_order(order)
        
        return order
    
    async def cancel_order(self, symbol: Symbol, order_id: str) -> bool:
        """Cancel an existing order."""
        try:
            response = await self._rest_private.cancel_order(
                symbol=self._symbol_mapper.to_exchange_format(symbol),
                order_id=order_id
            )
            
            # Update internal state
            if response.get("status") == "CANCELED":
                self._remove_order(symbol, order_id)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    # Data Loading Implementation
    async def _load_symbols_info(self) -> None:
        """Load symbol information from REST API."""
        response = await self._rest_public.get_exchange_info()
        self._symbols_info = self._transform_symbols_info(response)
    
    async def _load_balances(self) -> None:
        """Load account balances from REST API."""
        response = await self._rest_private.get_account()
        self._balances = self._transform_balances(response)
    
    # Transformation Methods
    def _transform_order(self, exchange_response: Dict, symbol: Symbol) -> Order:
        """Transform exchange order response to unified Order structure."""
        return Order(
            symbol=symbol,
            order_id=OrderId(exchange_response["orderId"]),
            side=Side.BUY if exchange_response["side"] == "BUY" else Side.SELL,
            order_type=self._map_order_type(exchange_response["type"]),
            quantity=float(exchange_response["origQty"]),
            price=float(exchange_response.get("price", 0.0)),
            filled_quantity=float(exchange_response["executedQty"]),
            status=self._map_order_status(exchange_response["status"]),
            timestamp=int(exchange_response["time"])
        )
    
    def _map_order_status(self, exchange_status: str) -> OrderStatus:
        """Map exchange-specific order status to unified enum."""
        status_mapping = {
            "NEW": OrderStatus.NEW,
            "FILLED": OrderStatus.FILLED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "CANCELED": OrderStatus.CANCELED,
            # Add exchange-specific mappings
        }
        return status_mapping.get(exchange_status, OrderStatus.UNKNOWN)
```

### REST Client Template

```python
# Template: src/cex/{exchange}/rest/{exchange}_rest_private.py
from core.cex.rest.spot.base_rest_spot_private import BaseRestSpotPrivate
from core.config.structs import ExchangeConfig
from typing import Dict, List, Optional

class {Exchange}RestPrivate(BaseRestSpotPrivate):
    """
    {Exchange} private REST API client.
    
    Handles authenticated operations including order management,
    account data, and trading operations.
    """
    
    def __init__(self, config: ExchangeConfig):
        super().__init__(
            base_url="https://api.{exchange}.com",
            config=config,
            rate_limits={
                "requests_per_second": 20,
                "orders_per_second": 10,
                "orders_per_day": 200000
            },
            timeouts={
                "connect": 5.0,
                "read": 10.0,
                "write": 5.0
            }
        )
    
    # Account Operations
    async def get_account(self) -> Dict:
        """Get account information including balances."""
        return await self._request_signed("GET", "/api/v3/account")
    
    async def get_trading_fees(self, symbol: Optional[str] = None) -> Dict:
        """Get trading fees for account."""
        params = {"symbol": symbol} if symbol else {}
        return await self._request_signed("GET", "/api/v3/tradeFee", params)
    
    # Order Management
    async def place_order(self, symbol: str, side: str, type: str,
                         quantity: float, price: Optional[float] = None,
                         **kwargs) -> Dict:
        """Place a new order."""
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": str(quantity),
            **kwargs
        }
        
        if price is not None:
            params["price"] = str(price)
        
        return await self._request_signed("POST", "/api/v3/order", params)
    
    async def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Cancel an existing order."""
        params = {
            "symbol": symbol,
            "orderId": order_id
        }
        return await self._request_signed("DELETE", "/api/v3/order", params)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open orders."""
        params = {"symbol": symbol} if symbol else {}
        return await self._request_signed("GET", "/api/v3/openOrders", params)
    
    async def get_order_history(self, symbol: str, limit: int = 500) -> List[Dict]:
        """Get order history for a symbol."""
        params = {
            "symbol": symbol,
            "limit": limit
        }
        return await self._request_signed("GET", "/api/v3/allOrders", params)
```

This comprehensive guide provides everything needed to integrate a new exchange following the clean, factory-pattern-based architecture with SOLID principles compliance and HFT safety standards.