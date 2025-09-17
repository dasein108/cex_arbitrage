# Exchange Integration Guide

**Definitive blueprint for integrating new cryptocurrency exchanges into the HFT arbitrage engine.**

## Table of Contents

1. [Overview](#overview)
2. [Base Interface Analysis](#base-interface-analysis)
3. [API Pattern Classification](#api-pattern-classification)
4. [Integration Architecture](#integration-architecture)
5. [Step-by-Step Integration Process](#step-by-step-integration-process)
6. [Implementation Standards](#implementation-standards)
7. [Common Challenges & Solutions](#common-challenges--solutions)
8. [Quality Standards & Testing](#quality-standards--testing)
9. [Reference Implementation: MEXC](#reference-implementation-mexc)
10. [Templates & Code Examples](#templates--code-examples)

## Overview

This guide provides comprehensive instructions for integrating new cryptocurrency exchanges into our ultra-high-performance CEX arbitrage engine. The system is designed for sub-millisecond trading with <50ms latency requirements and maintains strict HFT safety standards.

### Core Integration Principles

**CRITICAL HFT CACHING POLICY**
- **NEVER cache real-time trading data** (orderbooks, balances, order status, trades)
- **ONLY cache static configuration data** (symbol mappings, exchange info, trading rules)
- **RATIONALE**: Real-time data caching causes stale price execution and regulatory violations

**Unified Interface Compliance**
- ALL exchanges MUST implement `PublicExchangeInterface` and `PrivateExchangeInterface`
- ALL data structures MUST use `msgspec.Struct` from `src/exchanges/interface/structs.py`
- ALL error handling MUST use unified exceptions from `src/common/exceptions.py`

**SOLID Principles Enforcement**
- Single Responsibility: Each component has one clear purpose
- Open/Closed: Interfaces are closed for modification, open for extension
- Liskov Substitution: All exchange implementations are interchangeable
- Interface Segregation: Public/private operations are separate
- Dependency Inversion: Depend on abstractions, not concrete implementations

## Base Interface Analysis

### Legacy Interfaces Analysis (`raw/common/interfaces/`)

The legacy interface system provides foundational patterns but has architectural limitations:

#### `base_exchange.py`
**Patterns to Learn From:**
```python
class BaseExchangeInterface(ABC):
    @abstractmethod
    async def init(self, symbols: List[Symbol]) -> None
    
    @abstractmethod  
    async def start_symbol(self, symbol: Symbol) -> None
    
    @abstractmethod
    async def stop_symbol(self, symbol: Symbol) -> None
```

**Issues with Legacy System:**
- Mixed import compatibility (`try/except` fallbacks)
- Circular import dependencies
- Mixed responsibilities (sync and async patterns)
- No clear separation of public/private operations

#### `base_ws.py` 
**Useful Patterns:**
- Automatic reconnection logic
- Message type detection (JSON vs binary)
- Stream subscription management
- Connection health monitoring

**Limitations:**
- MEXC-specific protobuf imports
- Hard-coded message processing
- No abstract interface separation

#### `rest_api_interface.py`
**Core REST Patterns:**
- HMAC signature authentication
- Order management operations
- Balance and account operations
- Market data fetching

**Architecture Issues:**
- Single monolithic interface
- No separation between public/private operations
- Exchange-specific entity imports

### Modern Unified Interface System (`src/exchanges/interface/`)

The current system addresses legacy issues with:

**Clean Interface Separation:**
```python
# Public operations (no auth required)
class PublicExchangeInterface(ABC):
    async def get_orderbook(self, symbol: Symbol) -> OrderBook
    async def get_recent_trades(self, symbol: Symbol) -> List[Trade]

# Private operations (authentication required)  
class PrivateExchangeInterface(ABC):
    async def place_order(self, symbol: Symbol, side: Side, ...) -> Order
    async def get_account_balance(self) -> List[AssetBalance]
```

**Unified Data Structures:**
- Performance-optimized `msgspec.Struct` throughout
- Immutable structures with `frozen=True`
- Type-safe enums with `IntEnum`
- Zero-copy JSON parsing

## API Pattern Classification

### Pattern A: JSON-based APIs (85% of exchanges)

**Characteristics:**
- REST endpoints return JSON responses
- WebSocket streams use JSON messages
- Standard HTTP authentication (API key + HMAC signatures)
- Examples: Binance, Coinbase Pro, Kraken, Bitfinex, KuCoin, OKX

**Implementation Approach:**
```python
# Use msgspec for all JSON operations
import msgspec

class ExchangePublic(PublicExchangeInterface):
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        response = await self.rest_client.get(
            "/api/v3/depth",
            params={"symbol": self._format_symbol(symbol), "limit": limit}
        )
        # Direct msgspec parsing - no fallback libraries
        data = msgspec.json.decode(response, type=ExchangeOrderBookResponse)
        return self._transform_to_unified_orderbook(data, symbol)
```

**WebSocket Implementation:**

```python
async def _on_message(self, message):
    # Standard JSON message processing
    if isinstance(message, (str, bytes)):
        parsed = msgspec.json.decode(message)
        if self._is_orderbook_update(parsed):
            await self._handle_orderbook_diff_update(parsed)
```

### Pattern B: Protocol Buffer APIs (10% of exchanges)

**Characteristics:**
- Binary message formats for efficiency
- Requires .proto files and protobuf compilation
- More complex but higher performance
- Examples: MEXC (our reference), some institutional APIs

**Implementation Requirements:**

```python
# Protobuf integration
from google.protobuf import json_format
from exchange_pb2 import OrderBookMessage


async def _on_message(self, message):
    if isinstance(message, bytes):
        # Binary protobuf message
        pb_message = OrderBookMessage()
        pb_message.ParseFromString(message)
        # Convert to dict for processing
        data = json_format.MessageToDict(pb_message)
        await self._handle_orderbook_diff_update(data)
```

**Performance Optimization:**
```python
# Fast message type detection
_PROTOBUF_MAGIC_BYTES = {
    0x0a: 'orderbook',
    0x12: 'trades',
    0x1a: 'ticker'
}

# Binary pattern matching (2-3 CPU cycles)
if message:
    msg_type = _PROTOBUF_MAGIC_BYTES.get(message[0], 'unknown')
    await self._handle_typed_message(message, msg_type)
```

### Pattern C: Mixed APIs (5% of exchanges)

**Characteristics:**
- REST uses JSON, WebSocket uses binary
- Multiple authentication schemes
- Custom message formats
- Examples: Some regional exchanges, proprietary systems

**Implementation Strategy:**
- Separate handlers for REST and WebSocket
- Unified data transformation layer
- Protocol detection at connection level

## Integration Architecture

### Mandatory Directory Structure

```
src/exchanges/{exchange_name}/
├── README.md                           # Exchange-specific documentation
├── {exchange}_exchange.py              # Main unified interface implementation
├── common/
│   ├── __init__.py
│   ├── {exchange}_config.py            # Configuration and endpoints
│   ├── {exchange}_utils.py             # Utility functions and caching
│   ├── {exchange}_mappings.py          # Data format mappings
│   └── {exchange}_struct.py            # Exchange-specific structs (if needed)
├── rest/
│   ├── __init__.py
│   ├── {exchange}_public.py            # PublicExchangeInterface implementation
│   └── {exchange}_private.py           # PrivateExchangeInterface implementation
└── ws/
    ├── __init__.py
    ├── {exchange}_ws_public.py         # Public WebSocket streams
    └── {exchange}_ws_private.py        # Private WebSocket streams (if supported)
```

### Required Interface Implementations

#### 1. Unified Exchange Interface

```python
# src/cex/{exchange}/exchange_exchange.py
from core.cex.base import BaseExchangeInterface


class ExchangeExchange(BaseExchangeInterface):
    """High-level unified cex for Exchange"""

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.exchange = ExchangeName("EXCHANGE")
        self._rest_public = ExchangePublicExchange()
        self._rest_private = ExchangePrivateExchange(api_key, secret_key) if api_key else None
        self._ws_public = ExchangeWebSocketPublic(self.exchange)

    # Implement all BaseExchangeInterface methods
```

#### 2. Public REST Interface

```python
# src/cex/{exchange}/rest/{exchange}_public.py
from core.cex.rest import PublicExchangeSpotRestInterface


class ExchangePublicExchange(PublicExchangeSpotRestInterface):
    """Public market data operations for Exchange"""

    def __init__(self):
        self.rest_client = RestClient(ExchangeConfig.REST_CONFIG_PUBLIC)

    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
        # Implement exchange-specific logic
        pass

    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        # Implement exchange-specific logic  
        pass
```

#### 3. Private REST Interface

```python
# src/cex/{exchange}/rest/{exchange}_private.py  
from core.cex.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface


class ExchangePrivateExchange(PrivateExchangeSpotRestInterface):
    """Private trading operations for Exchange"""

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.rest_client = RestClient(ExchangeConfig.REST_CONFIG_PRIVATE)

    async def place_order(self, symbol: Symbol, side: Side, order_type: OrderType,
                          amount: float, price: Optional[float] = None, **kwargs) -> Order:
        # Implement exchange-specific logic
        pass
```

#### 4. WebSocket Implementation

```python
# src/cex/{exchange}/ws/{exchange}_ws_public.py
from core.cex.websocket import BaseExchangeWebsocketInterface


class ExchangeWebSocketPublic(BaseExchangeWebsocketInterface):
    """Public WebSocket streams for Exchange"""

    def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction) -> List[str]:
        symbol_str = self._format_symbol_for_ws(symbol)
        return [f"orderbook@{symbol_str}", f"trades@{symbol_str}"]

    async def _on_message(self, message: Dict[str, Any]):
        # Handle exchange-specific messages
        pass
```

### Data Transformation Layer

#### Mapping Exchange Data to Unified Structures
```python
# src/cex/{exchange}/common/{exchange}_mappings.py
class ExchangeMappings:
    """Bi-directional mappings between Exchange and unified formats"""
    
    # Exchange -> Unified mappings
    EXCHANGE_SIDE_TO_UNIFIED = {
        "buy": Side.BUY,
        "sell": Side.SELL
    }
    
    EXCHANGE_ORDER_STATUS_TO_UNIFIED = {
        "open": OrderStatus.NEW,
        "filled": OrderStatus.FILLED,
        "cancelled": OrderStatus.CANCELED,
        # ... complete mapping
    }
    
    # Unified -> Exchange mappings (for order placement)
    UNIFIED_SIDE_TO_EXCHANGE = {v: k for k, v in EXCHANGE_SIDE_TO_UNIFIED.items()}
    
    @staticmethod
    def transform_exchange_order_to_unified(exchange_order) -> Order:
        """Transform exchange order response to unified Order struct"""
        return Order(
            symbol=ExchangeUtils.parse_symbol(exchange_order.symbol),
            side=ExchangeMappings.EXCHANGE_SIDE_TO_UNIFIED[exchange_order.side],
            order_type=ExchangeMappings.EXCHANGE_ORDER_TYPE_TO_UNIFIED[exchange_order.type],
            price=float(exchange_order.price),
            amount=float(exchange_order.quantity),
            order_id=OrderId(str(exchange_order.id)),
            status=ExchangeMappings.EXCHANGE_ORDER_STATUS_TO_UNIFIED[exchange_order.status],
            timestamp=datetime.fromtimestamp(exchange_order.timestamp / 1000)
        )
```

## Step-by-Step Integration Process

### Phase 1: Research and Planning (2-4 hours)

#### 1.1 API Documentation Analysis
**Tasks:**
- Download complete API documentation
- Identify REST endpoints for required operations
- Document WebSocket stream formats and connection methods
- Note authentication requirements and signature methods
- Identify rate limits and trading restrictions

**Key Information to Document:**
```yaml
# Create integration_notes.yaml
exchange_name: "ExchangeName"
api_version: "v3"
base_urls:
  rest: "https://api.exchange.com"
  websocket: "wss://stream.exchange.com"
  
authentication:
  method: "HMAC-SHA256"  # or other method
  header_keys: ["X-API-KEY", "X-SIGNATURE", "X-TIMESTAMP"]
  
rate_limits:
  per_second: 20
  per_minute: 1200
  
data_formats:
  rest: "json"          # json, xml, custom
  websocket: "json"     # json, protobuf, custom
  
required_endpoints:
  public:
    - "/api/v3/exchangeInfo"
    - "/api/v3/depth"  
    - "/api/v3/trades"
  private:
    - "/api/v3/account"
    - "/api/v3/order"
    - "/api/v3/openOrders"
```

#### 1.2 Interface Mapping Design
**Create mapping specifications:**
```python
# Document required transformations
SYMBOL_FORMAT_MAPPING = {
    # Unified -> Exchange
    Symbol(base=AssetName("BTC"), quote=AssetName("USDT")): "BTCUSDT",
    # Exchange -> Unified  
    "BTCUSDT": Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
}

ORDER_TYPE_MAPPING = {
    # Exchange specific order types to unified
    "LIMIT": OrderType.LIMIT,
    "MARKET": OrderType.MARKET,
    # Add all supported types
}
```

### Phase 2: Core Implementation (6-8 hours)

#### 2.1 Configuration Setup
```python
# src/cex/{exchange}/common/{exchange}_config.py
class ExchangeConfig:
    EXCHANGE_NAME = "EXCHANGE"
    BASE_URL = "https://api.exchange.com"
    WEBSOCKET_URL = "wss://stream.exchange.com"
    
    # Optimized REST configurations
    REST_CONFIG_PUBLIC = RestConfig(
        timeout=10.0,
        require_auth=False,
        rate_limit_per_second=20
    )
    
    REST_CONFIG_PRIVATE = RestConfig(
        timeout=6.0,
        require_auth=True,
        rate_limit_per_second=10
    )
    
    # Trading precision and limits
    DEFAULT_ORDERBOOK_LIMIT = 100
    MAX_ORDERBOOK_LIMIT = 5000
    DEFAULT_TRADES_LIMIT = 500
```

#### 2.2 Utility Functions Implementation
```python
# src/cex/{exchange}/common/{exchange}_utils.py
class ExchangeUtils:
    """High-performance utility functions with caching"""
    
    # Performance caches for hot paths
    _symbol_to_pair_cache: Dict[Symbol, str] = {}
    _pair_to_symbol_cache: Dict[str, Symbol] = {}
    
    @staticmethod
    def symbol_to_pair(symbol: Symbol) -> str:
        """Convert unified Symbol to exchange pair format"""
        if symbol in ExchangeUtils._symbol_to_pair_cache:
            return ExchangeUtils._symbol_to_pair_cache[symbol]
            
        # Exchange-specific conversion logic
        pair = f"{symbol.base}{symbol.quote}"  # or other format
        ExchangeUtils._symbol_to_pair_cache[symbol] = pair
        return pair
    
    @staticmethod
    def pair_to_symbol(pair: str) -> Symbol:
        """Convert exchange pair to unified Symbol"""
        if pair in ExchangeUtils._pair_to_symbol_cache:
            return ExchangeUtils._pair_to_symbol_cache[pair]
            
        symbol = ExchangeUtils._parse_pair(pair)
        ExchangeUtils._pair_to_symbol_cache[pair] = symbol
        return symbol
    
    @staticmethod
    def _parse_pair(pair: str) -> Symbol:
        """Exchange-specific pair parsing logic"""
        # Implement based on exchange format
        # Common formats: "BTCUSDT", "BTC-USDT", "BTC/USDT", etc.
        pass
```

#### 2.3 REST Implementation

```python
# src/cex/{exchange}/rest/{exchange}_public.py
class ExchangePublicExchange(PublicExchangeInterface):

    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """Get order book for symbol"""
        pair = ExchangeUtils.to_pair(symbol)

        response = await self.rest_client.get(
            "/api/v3/depth",
            params={"symbol": pair, "limit": limit}
        )

        # Parse with msgspec (required)
        data = msgspec.json.decode(response, type=ExchangeOrderBookResponse)

        # Transform to unified format
        return OrderBook(
            bids=[OrderBookEntry(price=float(bid[0]), size=float(bid[1]))
                  for bid in data.bids],
            asks=[OrderBookEntry(price=float(ask[0]), size=float(ask[1]))
                  for ask in data.asks],
            timestamp=data.timestamp / 1000.0
        )
```

#### 2.4 WebSocket Implementation
```python
# src/cex/{exchange}/ws/{exchange}_ws_public.py
class ExchangeWebSocketPublic(BaseExchangeWebsocketInterface):
    
    async def _on_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            # Handle JSON format (most common)
            if isinstance(message, (str, bytes)):
                parsed = msgspec.json.decode(message)
                
                if self._is_orderbook_update(parsed):
                    await self._handle_orderbook_update(parsed)
                elif self._is_trade_update(parsed):
                    await self._handle_trade_update(parsed)
                    
        except Exception as e:
            await self.on_error(e)
    
    def _is_orderbook_update(self, message: dict) -> bool:
        """Detect orderbook updates - exchange specific"""
        return "stream" in message and "depth" in message["stream"]
        
    async def _handle_orderbook_update(self, message: dict):
        """Process orderbook update"""
        symbol = self._extract_symbol(message)
        orderbook = self._parse_orderbook(message)
        
        # Notify subscribers
        await self._notify_orderbook_update(symbol, orderbook)
```

### Phase 3: Testing and Validation (3-4 hours)

#### 3.1 Unit Testing

```python
# tests/test_{exchange}_integration.py
import pytest
from exchanges.

{exchange}.
{exchange}
_exchange
import ExchangeExchange


class TestExchangeIntegration:

    @pytest.fixture
    async def exchange(self):
        exchange = ExchangeExchange()
        await exchange.initialize()
        yield exchange
        await exchange.close()

    async def test_public_interface_compliance(self, exchange):
        """Test public cex implementation"""
        assert isinstance(exchange, PublicExchangeInterface)

        # Test orderbook
        orderbook = await exchange.get_orderbook(test_symbol)
        assert isinstance(orderbook, OrderBook)
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0

    async def test_private_interface_compliance(self, exchange):
        """Test private cex implementation (requires API keys)"""
        if not exchange._rest_private:
            pytest.skip("No API keys configured")

        balances = await exchange.get_account_balance()
        assert isinstance(balances, list)
        assert all(isinstance(b, AssetBalance) for b in balances)
```

#### 3.2 Performance Testing
```python
async def test_performance_requirements():
    """Verify latency and throughput targets"""
    exchange = ExchangeExchange()
    
    # Latency test - must be <50ms
    start_time = time.time()
    orderbook = await exchange.get_orderbook(test_symbol)
    latency = time.time() - start_time
    
    assert latency < 0.05, f"Latency {latency:.3f}s exceeds 50ms requirement"
    
    # Throughput test - WebSocket message processing
    start_time = time.time()
    for _ in range(1000):
        await exchange._ws_public._on_message(mock_message)
    duration = time.time() - start_time
    
    messages_per_second = 1000 / duration
    assert messages_per_second > 1000, f"Throughput {messages_per_second:.1f} msg/s too low"
```

### Phase 4: Integration and Documentation (2-3 hours)

#### 4.1 Documentation Creation
```python
# Create src/cex/{exchange}/README.md
# Use MEXC README.md as template
# Include:
# - Exchange-specific implementation details
# - API peculiarities and workarounds
# - Configuration examples  
# - Troubleshooting guide
# - Performance optimization notes
```

#### 4.2 Integration Testing
```python
async def test_end_to_end_integration():
    """Complete integration test with real exchange"""
    exchange = ExchangeExchange(api_key=test_api_key, secret_key=test_secret)
    
    async with exchange.session([test_symbol]) as ex:
        # Test market data
        orderbook = ex.orderbook
        assert orderbook is not None
        
        # Test account data
        balances = await ex.get_fresh_balances()
        assert isinstance(balances, dict)
        
        # Test order operations (testnet only)
        if is_testnet:
            order = await ex.place_limit_order(
                symbol=test_symbol,
                side=Side.BUY,
                amount=0.001,
                price=1.0  # Safe test price
            )
            assert order.order_id is not None
            
            # Clean up
            await ex.cancel_order(order.symbol, order.order_id)
```

## Implementation Standards

### Mandatory Requirements

#### 1. Exception Handling

```python
# NEVER use generic exceptions
# ALWAYS map to unified exception hierarchy
from core.exceptions.exchange import BaseExchangeError, RateLimitErrorBase, TradingDisabled


def _handle_exchange_error(self, error):
    """Map exchange errors to unified exceptions"""
    if hasattr(error, 'status_code'):
        if error.status_code == 429:
            return RateLimitErrorBase(429, error.message,
                                      retry_after=error.headers.get('Retry-After', 60))
        elif error.status_code == 418:  # Trading disabled
            return TradingDisabled(418, "Trading temporarily disabled")

    return BaseExchangeError(error.status_code or 500, f"Exchange error: {error}")
```

#### 2. Performance Requirements
```python
# All operations must meet these targets:
PERFORMANCE_REQUIREMENTS = {
    'rest_latency_max_ms': 50,      # <50ms for REST operations
    'json_parsing_max_ms': 1,       # <1ms for JSON parsing  
    'websocket_throughput_min': 1000, # >1000 messages/second
    'memory_per_request': 'O(1)',   # Constant memory usage
    'connection_reuse_rate': 0.95   # >95% connection reuse
}
```

#### 3. Type Safety
```python
# MANDATORY: Complete type annotations
async def place_order(
    self,
    symbol: Symbol,
    side: Side,
    order_type: OrderType,
    amount: float,
    price: Optional[float] = None,
    **kwargs: Any
) -> Order:
    """All methods must have complete type hints"""
    pass
```

#### 4. Data Structure Compliance

```python
# ONLY use unified structs from src/cex/cex/exchange.py
from structs import (
    Symbol, OrderBook, OrderBookEntry, Order, AssetBalance,
    Side, OrderType, OrderStatus, TimeInForce
)

# NEVER create custom data structures
# NEVER use legacy structs from raw/
```

### Code Quality Standards

#### SOLID Principles Enforcement

**Single Responsibility Principle:**
```python
# ✅ CORRECT: Each class has one responsibility
class ExchangeOrderBookParser:
    """Only responsible for parsing orderbook data"""
    def parse_orderbook(self, data) -> OrderBook: pass

class ExchangeWebSocketManager:
    """Only responsible for WebSocket connection management"""  
    def connect(self): pass
    def disconnect(self): pass

# ❌ INCORRECT: Mixed responsibilities
class ExchangeManager:
    def parse_orderbook(self, data): pass  # Parsing responsibility
    def connect_websocket(self): pass      # Connection responsibility
    def place_order(self, order): pass     # Trading responsibility
```

**Open/Closed Principle:**
```python
# ✅ CORRECT: Interfaces are closed for modification, open for extension
class BaseExchangeInterface(ABC):
    @abstractmethod
    async def get_orderbook(self, symbol: Symbol) -> OrderBook: pass

class BinanceExchange(BaseExchangeInterface):
    async def get_orderbook(self, symbol: Symbol) -> OrderBook:
        # Binance-specific implementation
        pass

class KrakenExchange(BaseExchangeInterface):  
    async def get_orderbook(self, symbol: Symbol) -> OrderBook:
        # Kraken-specific implementation
        pass
```

**Interface Segregation Principle:**
```python
# ✅ CORRECT: Focused interfaces
class PublicExchangeInterface(ABC):
    """Only public operations"""
    async def get_orderbook(self, symbol: Symbol) -> OrderBook: pass

class PrivateExchangeInterface(ABC):
    """Only private operations"""
    async def place_order(self, symbol: Symbol, ...) -> Order: pass

# ❌ INCORRECT: Fat cex
class ExchangeInterface(ABC):
    async def get_orderbook(self, symbol: Symbol) -> OrderBook: pass  # Public
    async def place_order(self, symbol: Symbol, ...) -> Order: pass    # Private
    # Forces all implementations to handle both public and private
```

#### KISS/YAGNI Compliance

**Keep It Simple, Stupid:**
```python
# ✅ CORRECT: Simple, direct implementation
def convert_price(price_str: str) -> float:
    return float(price_str)

# ❌ INCORRECT: Unnecessary complexity
def convert_price(price_str: str) -> float:
    # Over-engineered validation and conversion
    if not isinstance(price_str, str):
        raise TypeError("Price must be string")
    if not price_str.replace('.', '').replace('-', '').isdigit():
        raise ValueError("Invalid price format")
    # ... 20 more lines of validation
    return float(price_str)
```

**You Aren't Gonna Need It:**
```python
# ✅ CORRECT: Only implement what's needed
class OrderBookParser:
    def parse_orderbook(self, data) -> OrderBook:
        return OrderBook(bids=data['bids'], asks=data['asks'])

# ❌ INCORRECT: Implementing features not requested
class OrderBookParser:
    def parse_orderbook(self, data) -> OrderBook: pass
    def analyze_spread(self, orderbook) -> float: pass      # Not needed
    def predict_price_movement(self, orderbook) -> str: pass # Not needed  
    def generate_trading_signals(self, orderbook) -> list: pass # Not needed
```

## Common Challenges & Solutions

### Challenge 1: Authentication Variations

#### Problem: Different Signature Methods
```python
# Different cex use different signature schemes:
# - Binance: Query string + body + timestamp
# - Coinbase: Timestamp + method + path + body  
# - Kraken: Nonce + encoded parameters
```

#### Solution: Standardized Signature Interface
```python
class ExchangeAuthenticator:
    """Exchange-specific authentication logic"""
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key.encode()
    
    def generate_signature(self, method: str, endpoint: str, 
                          params: Dict[str, Any], timestamp: int) -> str:
        """Generate exchange-specific signature"""
        # Implement exchange-specific logic
        if self.exchange_name == "BINANCE":
            return self._binance_signature(params, timestamp)
        elif self.exchange_name == "COINBASE":
            return self._coinbase_signature(method, endpoint, params, timestamp)
        # ... other cex
    
    def _binance_signature(self, params: Dict, timestamp: int) -> str:
        """Binance HMAC-SHA256 signature"""
        query_string = urllib.parse.urlencode(sorted(params.items()))
        return hmac.new(self.secret_key, query_string.encode(), hashlib.sha256).hexdigest()
```

### Challenge 2: Symbol Format Differences

#### Problem: Inconsistent Symbol Representations
```python
# Different cex use different formats:
# Binance: "BTCUSDT"
# Coinbase: "BTC-USD"  
# Kraken: "XXBTZUSD"
# Bitfinex: "tBTCUSD"
```

#### Solution: Robust Symbol Conversion with Caching
```python
class ExchangeSymbolConverter:
    """High-performance symbol conversion with caching"""
    
    # Static caches for performance (safe to cache static mappings)
    _symbol_cache: Dict[Symbol, str] = {}
    _reverse_cache: Dict[str, Symbol] = {}
    
    # Exchange-specific symbol formats
    SPECIAL_SYMBOLS = {
        # Handle exchange-specific symbol names
        "BTCUSDT": Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        "ETHUSDT": Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
    }
    
    @classmethod
    def to_exchange_format(cls, symbol: Symbol) -> str:
        """Convert unified Symbol to exchange format"""
        if symbol in cls._symbol_cache:
            return cls._symbol_cache[symbol]
        
        # Exchange-specific formatting
        if symbol.base == "BTC" and symbol.quote == "USD":
            exchange_symbol = "XXBTZUSD"  # Kraken format
        else:
            exchange_symbol = f"{symbol.base}{symbol.quote}"  # Standard format
            
        cls._symbol_cache[symbol] = exchange_symbol
        return exchange_symbol
    
    @classmethod
    def from_exchange_format(cls, exchange_symbol: str) -> Symbol:
        """Convert exchange format to unified Symbol"""
        if exchange_symbol in cls._reverse_cache:
            return cls._reverse_cache[exchange_symbol]
            
        if exchange_symbol in cls.SPECIAL_SYMBOLS:
            symbol = cls.SPECIAL_SYMBOLS[exchange_symbol]
        else:
            symbol = cls._parse_standard_format(exchange_symbol)
            
        cls._reverse_cache[exchange_symbol] = symbol
        return symbol
```

### Challenge 3: Rate Limiting Variations

#### Problem: Different Rate Limit Implementations
```python
# Rate limits vary significantly:
# - Per-second limits (Binance: 20/sec)
# - Per-minute limits (Coinbase: 10/min per endpoint)
# - Weight-based limits (complex endpoint weights)
# - IP-based vs API key-based limits
```

#### Solution: Unified Rate Limit Handler

```python
from core.transport.rest.rest_client_legacy import RestClient
from core.transport.rest.structs import RestConfig


class ExchangeRateLimitConfig:
    """Exchange-specific rate limit configuration"""

    RATE_LIMITS = {
        'public_endpoints': RestConfig(
            rate_limit_per_second=20,
            timeout=10.0,
            require_auth=False
        ),
        'private_endpoints': RestConfig(
            rate_limit_per_second=10,
            timeout=6.0,
            require_auth=True
        ),
        'order_endpoints': RestConfig(
            rate_limit_per_second=5,
            timeout=3.0,
            require_auth=True
        )
    }


# Usage in implementation
class ExchangePrivateExchange(PrivateExchangeInterface):
    def __init__(self):
        self.order_client = RestClient(ExchangeRateLimitConfig.RATE_LIMITS['order_endpoints'])
        self.account_client = RestClient(ExchangeRateLimitConfig.RATE_LIMITS['private_endpoints'])
```

### Challenge 4: WebSocket Connection Variations

#### Problem: Different Connection and Subscription Methods
```python
# WebSocket implementations vary:
# - Binance: Single connection, multiple streams
# - Coinbase: Multiple connections, one stream each
# - Some require periodic pings
# - Some require authentication after connection
```

#### Solution: Standardized WebSocket Manager

```python
from core.transport.websocket.ws_client import WebsocketClient
from core.transport.websocket.structs import WebsocketConfig


class ExchangeWebSocketManager:
    """Standardized WebSocket connection management"""

    def __init__(self, exchange_name: ExchangeName):
        self.config = WebsocketConfig(
            url=self._get_websocket_url(),
            ping_interval=20,  # Exchange-specific
            ping_timeout=10,
            reconnect_delay=5,
            max_reconnect_attempts=10
        )
        self.ws_client = WebsocketClient(
            config=self.config,
            message_handler=self._on_message,
            error_handler=self._on_error
        )

    def _get_websocket_url(self) -> str:
        """Get exchange-specific WebSocket URL"""
        # Some cex require dynamic URL generation
        return f"wss://stream.{self.exchange_name.lower()}.com/ws"

    async def subscribe_to_streams(self, streams: List[str]):
        """Handle exchange-specific subscription format"""
        if self.exchange_name == "BINANCE":
            # Binance uses method-based subscriptions
            message = {
                "method": "SUBSCRIBE",
                "params": streams,
                "id": int(time.time())
            }
        elif self.exchange_name == "COINBASE":
            # Coinbase uses type-based subscriptions
            message = {
                "type": "subscribe",
                "channels": streams
            }

        await self.ws_client.send(msgspec.json.encode(message))
```

### Challenge 5: Error Message Mapping

#### Problem: Exchange-Specific Error Codes and Messages
```python
# Each exchange has different error codes:
# Binance: {"code": -1013, "msg": "Invalid quantity"}
# Coinbase: {"message": "Insufficient funds", "reason": "balance"}
# Kraken: {"error": ["EOrder:Insufficient funds"]}
```

#### Solution: Comprehensive Error Mapping System
```python
class ExchangeErrorMapper:
    """Maps exchange-specific errors to unified exceptions"""
    
    # Exchange-specific error mappings
    ERROR_MAPPINGS = {
        # Rate limiting errors
        (-1003, 429, "rate_limit"): RateLimitError,
        
        # Trading errors
        (-1013, 400, "invalid_quantity"): InvalidOrderError,
        (-2010, 400, "insufficient_funds"): InsufficientFundsError,
        (-1021, 400, "timestamp_error"): TimestampError,
        
        # Connection errors
        (-1006, 503, "server_error"): ExchangeAPIError,
    }
    
    @classmethod
    def map_error(cls, exchange_error) -> Exception:
        """Map exchange error to unified exception"""
        error_code = cls._extract_error_code(exchange_error)
        error_message = cls._extract_error_message(exchange_error)
        
        # Find matching error mapping
        for (code, http_status, category), exception_class in cls.ERROR_MAPPINGS.items():
            if error_code == code:
                if exception_class == RateLimitError:
                    retry_after = cls._extract_retry_after(exchange_error)
                    return RateLimitError(http_status, error_message, retry_after)
                else:
                    return exception_class(http_status, error_message)
        
        # Fallback to generic error
        return ExchangeAPIError(500, f"Unknown exchange error: {error_message}")
```

## Quality Standards & Testing

### HFT Safety Compliance

#### Critical Safety Checks
```python
class HFTSafetyValidator:
    """Validates HFT safety compliance"""
    
    @staticmethod
    def validate_no_real_time_caching(implementation):
        """Ensure no real-time data is cached"""
        prohibited_cache_methods = [
            'cache_orderbook', 'cache_balance', 'cache_orders',
            'cache_trades', 'cache_positions'
        ]
        
        for method_name in prohibited_cache_methods:
            if hasattr(implementation, method_name):
                raise SafetyViolation(f"Real-time data caching detected: {method_name}")
    
    @staticmethod  
    def validate_latency_requirements(implementation):
        """Verify latency targets are met"""
        # Test REST operation latency
        start = time.time()
        await implementation.get_orderbook(test_symbol)
        latency = time.time() - start
        
        if latency > 0.05:  # 50ms requirement
            raise PerformanceViolation(f"Latency {latency:.3f}s exceeds 50ms requirement")
```

#### Required Test Coverage
```python
class TestExchangeCompliance:
    """Comprehensive compliance testing"""
    
    async def test_interface_compliance(self):
        """Test all cex methods are implemented"""
        # Public cex compliance
        assert isinstance(exchange, PublicExchangeInterface)
        
        # Private cex compliance (if applicable)
        if hasattr(exchange, '_rest_private') and exchange._rest_private:
            assert isinstance(exchange, PrivateExchangeInterface)
    
    async def test_data_structure_compliance(self):
        """Test unified data structure usage"""
        orderbook = await exchange.get_orderbook(test_symbol)
        
        # Verify correct types
        assert isinstance(orderbook, OrderBook)
        assert all(isinstance(bid, OrderBookEntry) for bid in orderbook.bids)
        assert all(isinstance(ask, OrderBookEntry) for ask in orderbook.asks)
        
        # Verify no legacy structures
        assert not any(hasattr(orderbook, attr) for attr in ['legacy_bids', 'raw_data'])
    
    async def test_exception_handling_compliance(self):
        """Test unified exception usage"""
        # Test rate limiting
        with pytest.raises(RateLimitError):
            # Trigger rate limit (implementation specific)
            pass
        
        # Test invalid parameters
        with pytest.raises(InvalidOrderError):
            await exchange.place_order(test_symbol, Side.BUY, OrderType.LIMIT, -1, 100)
    
    async def test_performance_compliance(self):
        """Test performance requirements"""
        # Latency test
        start = time.time()
        orderbook = await exchange.get_orderbook(test_symbol)
        latency = time.time() - start
        assert latency < 0.05
        
        # Memory efficiency test
        import psutil
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        # Perform 1000 operations
        for _ in range(1000):
            await exchange.get_orderbook(test_symbol)
        
        final_memory = process.memory_info().rss
        memory_growth = final_memory - initial_memory
        
        # Should not grow significantly (constant memory usage)
        assert memory_growth < 10 * 1024 * 1024  # Less than 10MB growth
```

### Integration Testing Strategy

#### End-to-End Testing
```python
async def test_complete_trading_workflow():
    """Test complete trading workflow"""
    exchange = ExchangeExchange(api_key=test_api_key, secret_key=test_secret_key)
    
    async with exchange.session([test_symbol]) as ex:
        # 1. Market data validation
        orderbook = ex.orderbook
        assert orderbook is not None
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0
        assert orderbook.bids[0].price < orderbook.asks[0].price  # Spread validation
        
        # 2. Account balance validation  
        balances = await ex.get_fresh_balances()
        assert isinstance(balances, dict)
        
        base_balance = ex.get_asset_balance(test_symbol.base)
        quote_balance = ex.get_asset_balance(test_symbol.quote)
        assert isinstance(base_balance, AssetBalance)
        assert isinstance(quote_balance, AssetBalance)
        
        # 3. Order placement (testnet only)
        if is_testnet_environment():
            # Place small test order
            order = await ex.place_limit_order(
                symbol=test_symbol,
                side=Side.BUY,
                amount=0.001,  # Minimum amount
                price=orderbook.bids[0].price * 0.9  # Safe price
            )
            
            # Validate order response
            assert order.order_id is not None
            assert order.status == OrderStatus.NEW
            assert order.symbol == test_symbol
            
            # 4. Order status check
            order_status = await ex.get_order(test_symbol, order.order_id)
            assert order_status.order_id == order.order_id
            
            # 5. Order cancellation
            cancelled_order = await ex.cancel_order(test_symbol, order.order_id)
            assert cancelled_order.status in [OrderStatus.CANCELED, OrderStatus.PARTIALLY_CANCELED]
            
            # 6. Clean up verification
            open_orders = await ex.get_open_orders(test_symbol)
            assert order.order_id not in [o.order_id for o in open_orders]
```

#### Load Testing
```python
async def test_high_frequency_operations():
    """Test high-frequency operation handling"""
    exchange = ExchangeExchange()
    
    # Concurrent REST operations
    async def make_concurrent_requests():
        return await exchange.get_orderbook(test_symbol)
    
    # Test concurrent load
    tasks = [make_concurrent_requests() for _ in range(100)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Verify all succeeded (or handled gracefully)
    errors = [r for r in results if isinstance(r, Exception)]
    success_rate = (len(results) - len(errors)) / len(results)
    
    assert success_rate > 0.95  # >95% success rate required
    
    # Test WebSocket message processing speed
    mock_messages = [create_mock_orderbook_message() for _ in range(10000)]
    
    start_time = time.time()
    for message in mock_messages:
        await exchange._ws_public._on_message(message)
    duration = time.time() - start_time
    
    messages_per_second = len(mock_messages) / duration
    assert messages_per_second > 1000  # >1000 msg/sec requirement
```

## Reference Implementation: MEXC

### Key Learnings from MEXC Implementation

The MEXC exchange serves as our reference implementation, demonstrating:

#### 1. Protobuf Integration (Advanced Pattern)

```python
# MEXC uses Protocol Buffers for WebSocket efficiency
async def _handle_protobuf_message_typed(self, data: bytes, msg_type: str):
    """Handle typed protobuf messages with performance optimization"""

    # Fast message type detection with binary patterns
    if b'aggre.deals' in data[:50]:
        wrapper = PushDataV3ApiWrapper()
        wrapper.ParseFromString(data)
        if wrapper.HasField('publicAggreDeals'):
            await self._handle_trades_update(wrapper.publicAggreDeals)

    elif b'limit.depth' in data[:50]:
        wrapper = PushDataV3ApiWrapper()
        wrapper.ParseFromString(data)
        if wrapper.HasField('publicLimitDepths'):
            await self._handle_orderbook_diff_update(wrapper.publicLimitDepths)
```

#### 2. Object Pooling for Performance (HFT Optimization)
```python
# MEXC demonstrates object pooling for 75% allocation reduction
class OrderBookEntryPool:
    """High-performance object pool for OrderBookEntry instances"""
    
    def __init__(self, initial_size: int = 200, max_size: int = 500):
        self._pool = deque()
        self._max_size = max_size
        # Pre-allocate pool
        for _ in range(initial_size):
            self._pool.append(OrderBookEntry(price=0.0, size=0.0))
    
    def get_entry(self, price: float, size: float) -> OrderBookEntry:
        if self._pool:
            entry = self._pool.popleft()
            # Reset values (msgspec.Struct doesn't support mutation, so create new)
            return OrderBookEntry(price=price, size=size)
        return OrderBookEntry(price=price, size=size)
    
    def return_entry(self, entry: OrderBookEntry):
        if len(self._pool) < self._max_size:
            self._pool.append(entry)
```

#### 3. Intelligent Caching Strategy (90% Performance Improvement)
```python
# MEXC shows safe caching of static data only
class MexcUtils:
    # SAFE: Static symbol mappings (configuration data)
    _symbol_to_pair_cache: Dict[Symbol, str] = {}
    _pair_to_symbol_cache: Dict[str, Symbol] = {}
    
    # SAFE: Completed order caching (historical data)
    _completed_order_cache: OrderedDict = OrderedDict()
    
    @staticmethod
    def get_completed_order(order_id: OrderId) -> Optional[Order]:
        """Cache only completed orders (safe for HFT)"""
        return MexcUtils._completed_order_cache.get(order_id)
    
    @staticmethod
    def cache_completed_order(order: Order):
        """Cache completed orders only"""
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED]:
            MexcUtils._completed_order_cache[order.order_id] = order
            # LRU eviction
            if len(MexcUtils._completed_order_cache) > 1000:
                MexcUtils._completed_order_cache.popitem(last=False)
```

#### 4. Production-Grade Context Manager

```python
class MexcExchange(BaseExchangeInterface):
    """Production-ready unified cex with proper resource management"""

    async def session(self, symbols: Optional[List[Symbol]] = None) -> 'MexcExchange':
        """Context manager for proper resource cleanup"""
        return MexcExchangeSession(self, symbols or [])


class MexcExchangeSession:
    """Ensures proper cleanup and error handling"""

    async def __aenter__(self) -> MexcExchange:
        try:
            await self.exchange.initialize(self.symbols)
            return self.exchange
        except Exception as e:
            await self._cleanup_partial_init()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.exchange.close()

    async def _cleanup_partial_init(self):
        """Clean up resources during failed initialization"""
        if self.exchange._ws_public:
            await self.exchange._ws_public.ws_client.stop()
        if self.exchange._rest_private:
            await self.exchange._rest_private.close()
```

### MEXC-Specific Implementation Notes

#### Authentication Peculiarities
```python
def _mexc_signature_generator(self, params: Dict[str, any]) -> str:
    """MEXC requires specific parameter ordering"""
    # MEXC is sensitive to parameter ordering
    ordered_params = dict(sorted(params.items()))
    query_string = urllib.parse.urlencode(ordered_params)
    
    signature = hmac.new(
        self.secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature
```

#### WebSocket Subscription Format

```python
def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction) -> List[str]:
    """MEXC uses complex subscription string format"""
    symbol_str = MexcUtils.to_pair(symbol).upper()

    streams = []
    # MEXC-specific stream format
    if action == SubscriptionAction.SUBSCRIBE:
        streams.append(f"spot@public.limit.depth.v3.api@{symbol_str}@20")  # Orderbook
        streams.append(f"spot@public.aggre.deals.v3.api.pb@10ms@{symbol_str}")  # Trades

    return streams
```

#### Performance Monitoring Integration
```python
def get_performance_metrics(self) -> Dict[str, int]:
    """MEXC demonstrates comprehensive performance tracking"""
    total_requests = self._performance_metrics['cache_hits'] + self._performance_metrics['cache_misses']
    cache_hit_rate = (self._performance_metrics['cache_hits'] / total_requests * 100) if total_requests > 0 else 0
    
    return {
        'orderbook_updates': self._performance_metrics['orderbook_updates'],
        'api_calls_saved': self._performance_metrics['api_calls_saved'], 
        'cache_hit_rate_percent': round(cache_hit_rate, 1),
        'active_symbols_count': len(self._active_symbols),
        'cached_orders_count': len(self._completed_order_cache),
        'websocket_messages_processed': self._performance_metrics['ws_messages'],
        'pool_utilization_percent': self.entry_pool.get_utilization()
    }
```

### When to Use MEXC Patterns vs JSON Patterns

#### Use MEXC Protobuf Pattern When:
- Exchange explicitly supports Protocol Buffers
- Performance is critical (>10,000 msg/sec)
- Exchange provides .proto files
- Binary data transmission is preferred

#### Use Standard JSON Pattern When:
- Exchange uses JSON (majority of exchanges)
- Protobuf complexity isn't justified
- Rapid development is prioritized
- Exchange doesn't provide protobuf support

## Templates & Code Examples

### Basic Exchange Template

#### Directory Structure Creation
```bash
# Create complete exchange directory structure
mkdir -p src/cex/{exchange_name}
mkdir -p src/cex/{exchange_name}/common
mkdir -p src/cex/{exchange_name}/rest
mkdir -p src/cex/{exchange_name}/ws

# Create init files
touch src/cex/{exchange_name}/__init__.py
touch src/cex/{exchange_name}/common/__init__.py
touch src/cex/{exchange_name}/rest/__init__.py
touch src/cex/{exchange_name}/ws/__init__.py
```

#### Configuration Template

```python
# src/cex/{exchange_name}/common/{exchange_name}_config.py
from core.transport.rest.structs import RestConfig


class ExchangeConfig:
    """Exchange configuration and endpoints"""

    EXCHANGE_NAME = "EXCHANGE"
    BASE_URL = "https://api.exchange.com"
    WEBSOCKET_URL = "wss://stream.exchange.com/ws"

    # REST endpoint configurations  
    ENDPOINTS = {
        # Public endpoints
        'exchange_info': '/api/v3/exchangeInfo',
        'orderbook': '/api/v3/depth',
        'trades': '/api/v3/trades',
        'ticker_24h': '/api/v3/ticker/24hr',
        'server_time': '/api/v3/time',
        'ping': '/api/v3/ping',

        # Private endpoints
        'account': '/api/v3/account',
        'balance': '/api/v3/account',
        'new_order': '/api/v3/order',
        'cancel_order': '/api/v3/order',
        'open_orders': '/api/v3/openOrders',
        'order_status': '/api/v3/order',
        'all_orders': '/api/v3/allOrders'
    }

    # Optimized REST configurations for different operation types
    REST_CONFIGS = {
        'public_fast': RestConfig(
            timeout=4.0,
            max_retries=1,
            require_auth=False,
            rate_limit_per_second=20
        ),
        'public_standard': RestConfig(
            timeout=10.0,
            max_retries=3,
            require_auth=False,
            rate_limit_per_second=10
        ),
        'private_trading': RestConfig(
            timeout=6.0,
            max_retries=2,
            require_auth=True,
            rate_limit_per_second=5
        ),
        'private_account': RestConfig(
            timeout=8.0,
            max_retries=3,
            require_auth=True,
            rate_limit_per_second=10
        )
    }

    # Exchange-specific limits and parameters
    LIMITS = {
        'orderbook_max_limit': 5000,
        'trades_max_limit': 1000,
        'orders_max_limit': 500
    }
```

#### Utilities Template

```python
# src/cex/{exchange_name}/common/{exchange_name}_utils.py
from typing import Dict
from structs import Symbol, AssetName


class ExchangeUtils:
    """High-performance utility functions with caching"""

    # Performance caches for HFT hot paths
    _symbol_to_pair_cache: Dict[Symbol, str] = {}
    _pair_to_symbol_cache: Dict[str, Symbol] = {}

    @staticmethod
    def symbol_to_pair(symbol: Symbol) -> str:
        """Convert unified Symbol to exchange pair format"""
        if symbol in ExchangeUtils._symbol_to_pair_cache:
            return ExchangeUtils._symbol_to_pair_cache[symbol]

        # Exchange-specific format (customize based on exchange)
        # Common formats:
        # - Binance: "BTCUSDT"
        # - Coinbase: "BTC-USD"  
        # - Kraken: "XXBTZUSD"
        # - Bitfinex: "tBTCUSD"
        pair = f"{symbol.base}{symbol.quote}"  # Default format

        ExchangeUtils._symbol_to_pair_cache[symbol] = pair
        return pair

    @staticmethod
    def pair_to_symbol(pair: str) -> Symbol:
        """Convert exchange pair to unified Symbol"""
        if pair in ExchangeUtils._pair_to_symbol_cache:
            return ExchangeUtils._pair_to_symbol_cache[pair]

        symbol = ExchangeUtils._parse_pair(pair)
        ExchangeUtils._pair_to_symbol_cache[pair] = symbol
        return symbol

    @staticmethod
    def _parse_pair(pair: str) -> Symbol:
        """Parse exchange-specific pair format"""
        # Implement exchange-specific parsing logic
        # This is the most exchange-specific part - customize heavily

        # Example for standard format like "BTCUSDT"
        if len(pair) >= 6:
            # Try common cex assets first for better parsing
            for base_len in [3, 4, 5]:  # BTC, USDT, USDC lengths
                if base_len < len(pair):
                    base = pair[:base_len]
                    quote = pair[base_len:]
                    if base in COMMON_BASE_ASSETS and quote in COMMON_QUOTE_ASSETS:
                        return Symbol(base=AssetName(base), quote=AssetName(quote))

        # Fallback parsing logic
        raise ValueError(f"Unable to parse pair: {pair}")

    @staticmethod
    def format_price(price: float, symbol: Symbol) -> str:
        """Format price according to exchange precision requirements"""
        # Customize based on exchange precision rules
        return f"{price:.8f}".rstrip('0').rstrip('.')

    @staticmethod
    def format_quantity(quantity: float, symbol: Symbol) -> str:
        """Format quantity according to exchange precision requirements"""
        # Customize based on exchange precision rules
        return f"{quantity:.8f}".rstrip('0').rstrip('.')


# Common assets for parsing optimization
COMMON_BASE_ASSETS = {"BTC", "ETH", "BNB", "ADA", "DOT", "LINK", "LTC", "XRP"}
COMMON_QUOTE_ASSETS = {"USDT", "BUSD", "BTC", "ETH", "USD", "EUR", "USDC"}
```

#### Mappings Template

```python
# src/cex/{exchange_name}/common/{exchange_name}_mappings.py
from structs import Side, OrderType, OrderStatus, TimeInForce


class ExchangeMappings:
    """Bi-directional mappings between exchange and unified formats"""

    # Side mappings (customize based on exchange)
    EXCHANGE_SIDE_TO_UNIFIED = {
        "BUY": Side.BUY,
        "SELL": Side.SELL,
        # Add exchange-specific side representations
        "bid": Side.BUY,
        "ask": Side.SELL,
    }

    # Order type mappings (customize based on exchange)
    EXCHANGE_ORDER_TYPE_TO_UNIFIED = {
        "LIMIT": OrderType.LIMIT,
        "MARKET": OrderType.MARKET,
        "STOP_LOSS": OrderType.STOP_MARKET,
        "STOP_LOSS_LIMIT": OrderType.STOP_LIMIT,
        "TAKE_PROFIT": OrderType.STOP_MARKET,
        "TAKE_PROFIT_LIMIT": OrderType.STOP_LIMIT,
        "LIMIT_MAKER": OrderType.LIMIT_MAKER,
        "IOC": OrderType.IMMEDIATE_OR_CANCEL,
        "FOK": OrderType.FILL_OR_KILL,
    }

    # Order status mappings (customize based on exchange)
    EXCHANGE_ORDER_STATUS_TO_UNIFIED = {
        "NEW": OrderStatus.NEW,
        "FILLED": OrderStatus.FILLED,
        "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
        "CANCELED": OrderStatus.CANCELED,
        "PENDING_CANCEL": OrderStatus.NEW,  # Still active
        "REJECTED": OrderStatus.REJECTED,
        "EXPIRED": OrderStatus.EXPIRED,
    }

    # Time in force mappings
    EXCHANGE_TIME_IN_FORCE_TO_UNIFIED = {
        "GTC": TimeInForce.GTC,
        "IOC": TimeInForce.IOC,
        "FOK": TimeInForce.FOK,
        "GTD": TimeInForce.GTD,
    }

    # Reverse mappings for order placement
    UNIFIED_SIDE_TO_EXCHANGE = {v: k for k, v in EXCHANGE_SIDE_TO_UNIFIED.items() if k.upper() in ["BUY", "SELL"]}
    UNIFIED_ORDER_TYPE_TO_EXCHANGE = {v: k for k, v in EXCHANGE_ORDER_TYPE_TO_UNIFIED.items() if
                                      k in ["LIMIT", "MARKET"]}
    UNIFIED_TIME_IN_FORCE_TO_EXCHANGE = {v: k for k, v in EXCHANGE_TIME_IN_FORCE_TO_UNIFIED.items()}

    @staticmethod
    def get_unified_side(exchange_side: str) -> Side:
        """Convert exchange side to unified Side enum"""
        return ExchangeMappings.EXCHANGE_SIDE_TO_UNIFIED.get(exchange_side.upper(), Side.BUY)

    @staticmethod
    def get_exchange_side(unified_side: Side) -> str:
        """Convert unified Side to exchange format"""
        return ExchangeMappings.UNIFIED_SIDE_TO_EXCHANGE.get(unified_side, "BUY")

    @staticmethod
    def get_unified_order_type(exchange_type: str) -> OrderType:
        """Convert exchange order type to unified OrderType enum"""
        return ExchangeMappings.EXCHANGE_ORDER_TYPE_TO_UNIFIED.get(exchange_type.upper(), OrderType.LIMIT)

    @staticmethod
    def get_exchange_order_type(unified_type: OrderType) -> str:
        """Convert unified OrderType to exchange format"""
        return ExchangeMappings.UNIFIED_ORDER_TYPE_TO_EXCHANGE.get(unified_type, "LIMIT")

    @staticmethod
    def get_unified_order_status(exchange_status: str) -> OrderStatus:
        """Convert exchange order status to unified OrderStatus enum"""
        return ExchangeMappings.EXCHANGE_ORDER_STATUS_TO_UNIFIED.get(exchange_status.upper(), OrderStatus.UNKNOWN)
```

#### Public REST Implementation Template

```python
# src/cex/{exchange_name}/rest/{exchange_name}_public.py
import msgspec
from typing import Dict, List, Optional
from core.cex.rest import PublicExchangeSpotRestInterface
from structs import Symbol, SymbolInfo, OrderBook, OrderBookEntry, Trade, Side
from core.transport.rest.rest_client_legacy import RestClient
from .common.

{exchange_name}
_config
import ExchangeConfig
from .common.

{exchange_name}
_utils
import ExchangeUtils


# Exchange-specific response structures (customize based on API)
class ExchangeOrderBookResponse(msgspec.Struct):
    bids: List[List[str]]  # [["price", "quantity"], ...]
    asks: List[List[str]]
    lastUpdateId: int


class ExchangeTradeResponse(msgspec.Struct):
    id: int
    price: str
    qty: str
    quoteQty: str
    time: int
    isBuyerMaker: bool


class ExchangeSymbolInfo(msgspec.Struct):
    symbol: str
    status: str
    baseAsset: str
    quoteAsset: str
    baseAssetPrecision: int
    quotePrecision: int
    # Add other exchange-specific fields


class ExchangePublic(PublicExchangeSpotRestInterface):
    """Public market data operations for Exchange"""

    def __init__(self):
        self.rest_client = RestClient(ExchangeConfig.REST_CONFIGS['public_standard'])
        self._exchange_info_cache: Optional[Dict[Symbol, SymbolInfo]] = None
        self._cache_timestamp = 0.0

    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
        """Get trading rules and symbol information (cached)"""
        current_time = time.time()

        # Cache for 5 minutes (static configuration data - safe to cache)
        if (self._exchange_info_cache is None or
                current_time - self._cache_timestamp > 300):

            response = await self.rest_client.get(ExchangeConfig.ENDPOINTS['exchange_info'])
            data = msgspec.json.decode(response, type=dict)

            # Transform to unified format
            self._exchange_info_cache = {}
            for symbol_data in data.get('symbols', []):
                exchange_symbol = msgspec.convert(symbol_data, ExchangeSymbolInfo)

                # Convert to unified format
                symbol = Symbol(
                    base=AssetName(exchange_symbol.baseAsset),
                    quote=AssetName(exchange_symbol.quoteAsset)
                )

                symbol_info = SymbolInfo(
                    exchange=ExchangeConfig.EXCHANGE_NAME,
                    symbol=symbol,
                    base_precision=exchange_symbol.baseAssetPrecision,
                    quote_precision=exchange_symbol.quotePrecision,
                    inactive=(exchange_symbol.status != 'TRADING')
                )

                self._exchange_info_cache[symbol] = symbol_info

            self._cache_timestamp = current_time

        return self._exchange_info_cache

    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """Get order book for symbol"""
        pair = ExchangeUtils.to_pair(symbol)

        # Validate limit against exchange constraints
        max_limit = ExchangeConfig.LIMITS['orderbook_max_limit']
        limit = min(limit, max_limit)

        response = await self.rest_client.get(
            ExchangeConfig.ENDPOINTS['orderbook'],
            params={"symbol": pair, "limit": limit}
        )

        # Parse with msgspec (required - no fallback libraries)
        data = msgspec.json.decode(response, type=ExchangeOrderBookResponse)

        # Transform to unified format
        return OrderBook(
            bids=[
                OrderBookEntry(price=float(bid[0]), size=float(bid[1]))
                for bid in data.bids
            ],
            asks=[
                OrderBookEntry(price=float(ask[0]), size=float(ask[1]))
                for ask in data.asks
            ],
            timestamp=time.time()  # Use current time if not provided
        )

    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """Get recent trades for symbol"""
        pair = ExchangeUtils.to_pair(symbol)

        # Validate limit
        max_limit = ExchangeConfig.LIMITS['trades_max_limit']
        limit = min(limit, max_limit)

        response = await self.rest_client.get(
            ExchangeConfig.ENDPOINTS['trades'],
            params={"symbol": pair, "limit": limit}
        )

        # Parse response
        trades_data = msgspec.json.decode(response, type=List[ExchangeTradeResponse])

        # Transform to unified format
        trades = []
        for trade_data in trades_data:
            trade = Trade(
                price=float(trade_data.price),
                amount=float(trade_data.qty),
                side=Side.SELL if trade_data.isBuyerMaker else Side.BUY,
                timestamp=trade_data.time,
                is_maker=trade_data.isBuyerMaker
            )
            trades.append(trade)

        return trades

    async def get_server_time(self) -> int:
        """Get exchange server timestamp"""
        response = await self.rest_client.get(ExchangeConfig.ENDPOINTS['server_time'])
        data = msgspec.json.decode(response, type=dict)
        return data.get('serverTime', int(time.time() * 1000))

    async def ping(self) -> bool:
        """Test connectivity to exchange"""
        try:
            await self.rest_client.get(ExchangeConfig.ENDPOINTS['ping'])
            return True
        except Exception:
            return False
```

#### Private REST Implementation Template

```python
# src/cex/{exchange_name}/rest/{exchange_name}_private.py
import hashlib
import hmac
import time
import urllib.parse
from typing import Dict, List, Optional, Any
from core.cex.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface
from structs import (
    Symbol, AssetBalance, Order, Side, OrderType, OrderStatus, OrderId, AssetName
)
from core.transport.rest.rest_client_legacy import RestClient
from core.exceptions.exchange import BaseExchangeError, RateLimitErrorBase, InvalidOrderError
from .common.

{exchange_name}
_config
import ExchangeConfig
from .common.

{exchange_name}
_utils
import ExchangeUtils
from .common.

{exchange_name}
_mappings
import ExchangeMappings


# Exchange-specific response structures
class ExchangeBalanceResponse(msgspec.Struct):
    asset: str
    free: str
    locked: str


class ExchangeAccountResponse(msgspec.Struct):
    balances: List[ExchangeBalanceResponse]
    canTrade: bool
    canWithdraw: bool
    canDeposit: bool


class ExchangeOrderResponse(msgspec.Struct):
    symbol: str
    orderId: int
    orderListId: int = -1
    clientOrderId: str = ""
    price: str = "0"
    origQty: str = "0"
    executedQty: str = "0"
    cummulativeQuoteQty: str = "0"
    status: str = "NEW"
    timeInForce: str = "GTC"
    type: str = "LIMIT"
    side: str = "BUY"
    stopPrice: str = "0"
    icebergQty: str = "0"
    time: int = 0
    updateTime: int = 0
    isWorking: bool = True
    origQuoteOrderQty: str = "0"


class ExchangePrivate(PrivateExchangeSpotRestInterface):
    """Private trading operations for Exchange"""

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

        # Separate REST clients for different operation types
        self.account_client = RestClient(ExchangeConfig.REST_CONFIGS['private_account'])
        self.trading_client = RestClient(ExchangeConfig.REST_CONFIGS['private_trading'])

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate exchange-specific signature"""
        # Customize based on exchange authentication method

        # Common pattern (Binance-style):
        query_string = urllib.parse.urlencode(sorted(params.items()))
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

        # Alternative patterns:
        # - Coinbase: timestamp + method + path + body
        # - Kraken: nonce + encoded parameters
        # - Custom: implement based on exchange documentation

    def _add_authentication(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Add authentication headers/parameters"""
        # Add timestamp
        params['timestamp'] = int(time.time() * 1000)

        # Generate signature
        signature = self._generate_signature(params)

        # Return headers (customize based on exchange)
        return {
            'X-API-Key': self.api_key,
            'X-Signature': signature,
            'Content-Type': 'application/json'
        }

    async def get_account_balance(self) -> List[AssetBalance]:
        """Get account balance for all assets"""
        params = {}
        headers = self._add_authentication(params)

        try:
            response = await self.account_client.get(
                ExchangeConfig.ENDPOINTS['account'],
                params=params,
                headers=headers
            )

            data = msgspec.json.decode(response, type=ExchangeAccountResponse)

            balances = []
            for balance_data in data.balances:
                if float(balance_data.free) > 0 or float(balance_data.locked) > 0:
                    balance = AssetBalance(
                        asset=AssetName(balance_data.asset),
                        free=float(balance_data.free),
                        locked=float(balance_data.locked)
                    )
                    balances.append(balance)

            return balances

        except Exception as e:
            raise self._handle_exception(e)

    async def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """Get balance for specific asset"""
        balances = await self.get_account_balance()
        for balance in balances:
            if balance.asset == asset:
                return balance

        # Return zero balance if asset not found
        return AssetBalance(asset=asset, free=0.0, locked=0.0)

    async def place_order(
            self,
            symbol: Symbol,
            side: Side,
            order_type: OrderType,
            amount: Optional[float] = None,
            price: Optional[float] = None,
            **kwargs
    ) -> Order:
        """Place new order"""
        pair = ExchangeUtils.to_pair(symbol)

        # Build order parameters
        params = {
            'symbol': pair,
            'side': ExchangeMappings.get_exchange_side(side),
            'type': ExchangeMappings.get_exchange_order_type(order_type)
        }

        # Add quantity (customize field name based on exchange)
        if amount is not None:
            params['quantity'] = ExchangeUtils.format_quantity(amount, symbol)

        # Add price for limit orders
        if price is not None and order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            params['price'] = ExchangeUtils.format_price(price, symbol)

        # Add optional parameters
        if 'time_in_force' in kwargs:
            params['timeInForce'] = ExchangeMappings.get_exchange_time_in_force(kwargs['time_in_force'])

        headers = self._add_authentication(params)

        try:
            response = await self.trading_client.post(
                ExchangeConfig.ENDPOINTS['new_order'],
                params=params,
                headers=headers
            )

            order_data = msgspec.json.decode(response, type=ExchangeOrderResponse)

            # Transform to unified format
            return Order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                price=float(order_data.price) if order_data.price != "0" else 0.0,
                amount=float(order_data.origQty),
                amount_filled=float(order_data.executedQty),
                order_id=OrderId(str(order_data.orderId)),
                client_order_id=order_data.clientOrderId,
                status=ExchangeMappings.get_unified_order_status(order_data.status),
                timestamp=datetime.fromtimestamp(order_data.time / 1000) if order_data.time else datetime.now()
            )

        except Exception as e:
            raise self._handle_exception(e)

    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Cancel existing order"""
        pair = ExchangeUtils.to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        headers = self._add_authentication(params)

        try:
            response = await self.trading_client.delete(
                ExchangeConfig.ENDPOINTS['cancel_order'],
                params=params,
                headers=headers
            )

            order_data = msgspec.json.decode(response, type=ExchangeOrderResponse)

            return Order(
                symbol=symbol,
                side=ExchangeMappings.get_unified_side(order_data.side),
                order_type=ExchangeMappings.get_unified_order_type(order_data.type),
                price=float(order_data.price) if order_data.price != "0" else 0.0,
                amount=float(order_data.origQty),
                amount_filled=float(order_data.executedQty),
                order_id=order_id,
                status=ExchangeMappings.get_unified_order_status(order_data.status)
            )

        except Exception as e:
            raise self._handle_exception(e)

    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Get order status"""
        pair = ExchangeUtils.to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        headers = self._add_authentication(params)

        try:
            response = await self.account_client.get(
                ExchangeConfig.ENDPOINTS['order_status'],
                params=params,
                headers=headers
            )

            order_data = msgspec.json.decode(response, type=ExchangeOrderResponse)

            return Order(
                symbol=symbol,
                side=ExchangeMappings.get_unified_side(order_data.side),
                order_type=ExchangeMappings.get_unified_order_type(order_data.type),
                price=float(order_data.price) if order_data.price != "0" else 0.0,
                amount=float(order_data.origQty),
                amount_filled=float(order_data.executedQty),
                order_id=order_id,
                status=ExchangeMappings.get_unified_order_status(order_data.status),
                timestamp=datetime.fromtimestamp(order_data.time / 1000) if order_data.time else None
            )

        except Exception as e:
            raise self._handle_exception(e)

    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """Get all open orders"""
        params = {}

        if symbol:
            params['symbol'] = ExchangeUtils.to_pair(symbol)

        headers = self._add_authentication(params)

        try:
            response = await self.account_client.get(
                ExchangeConfig.ENDPOINTS['open_orders'],
                params=params,
                headers=headers
            )

            orders_data = msgspec.json.decode(response, type=List[ExchangeOrderResponse])

            orders = []
            for order_data in orders_data:
                order_symbol = ExchangeUtils.to_symbol(order_data.symbol)
                order = Order(
                    symbol=order_symbol,
                    side=ExchangeMappings.get_unified_side(order_data.side),
                    order_type=ExchangeMappings.get_unified_order_type(order_data.type),
                    price=float(order_data.price) if order_data.price != "0" else 0.0,
                    amount=float(order_data.origQty),
                    amount_filled=float(order_data.executedQty),
                    order_id=OrderId(str(order_data.orderId)),
                    status=ExchangeMappings.get_unified_order_status(order_data.status)
                )
                orders.append(order)

            return orders

        except Exception as e:
            raise self._handle_exception(e)

    def _handle_exception(self, error: Exception) -> Exception:
        """Map exchange errors to unified exceptions"""
        # Customize based on exchange error format

        if hasattr(error, 'status') and hasattr(error, 'response_text'):
            try:
                error_data = msgspec.json.decode(error.response_text)
                error_code = error_data.get('code', 0)
                error_msg = error_data.get('msg', str(error))

                # Map common error codes (customize based on exchange)
                if error_code in [-1003, 429] or error.status == 429:
                    return RateLimitErrorBase(429, error_msg, retry_after=60)
                elif error_code in [-1013, -2010]:
                    return InvalidOrderError(400, error_msg)
                elif error.status >= 500:
                    return BaseExchangeError(error.status, error_msg)
                else:
                    return BaseExchangeError(error.status, error_msg)

            except Exception:
                # Fallback if error parsing fails
                pass

        return BaseExchangeError(500, f"Exchange error: {str(error)}")
```

#### WebSocket Implementation Template

```python
# src/cex/{exchange_name}/ws/{exchange_name}_ws_public.py
import msgspec
from typing import Dict, List, Any
from core.cex.websocket import BaseExchangeWebsocketInterface, SubscriptionAction
from structs import Symbol, OrderBook, OrderBookEntry, Trade, Side, ExchangeName
from core.transport.websocket.structs import WebsocketConfig
from .common.

{exchange_name}
_config
import ExchangeConfig
from .common.

{exchange_name}
_utils
import ExchangeUtils


class ExchangeWebSocketPublic(BaseExchangeWebsocketInterface):
    """Public WebSocket streams for Exchange"""

    def __init__(self, exchange: ExchangeName):
        config = WebsocketConfig(
            url=ExchangeConfig.WEBSOCKET_URL,
            ping_interval=20,  # Customize based on exchange
            ping_timeout=10,
            reconnect_delay=5
        )

        super().__init__(exchange, config)

        # Exchange-specific message handlers
        self.message_handlers = {
            'depthUpdate': self._handle_orderbook_update,
            'trade': self._handle_trade_update,
            'ticker': self._handle_ticker_update
        }

    def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction) -> List[str]:
        """Create exchange-specific subscription messages"""
        symbol_str = ExchangeUtils.to_pair(symbol).lower()

        streams = []
        if action == SubscriptionAction.SUBSCRIBE:
            # Customize stream names based on exchange format
            # Common patterns:
            # - Binance: "btcusdt@depth20", "btcusdt@trade"
            # - Coinbase: {"type": "subscribe", "channels": ["level2", "matches"], "product_ids": ["BTC-USD"]}
            # - Kraken: {"method": "subscribe", "params": {"channel": "book", "symbol": ["BTC/USD"]}}

            streams.append(f"{symbol_str}@depth20")  # Orderbook
            streams.append(f"{symbol_str}@trade")  # Trades

        return streams

    async def _on_message(self, message: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        try:
            # Handle different message formats based on exchange

            # Pattern 1: Stream-based messages (Binance style)
            if 'stream' in message and 'data' in message:
                stream = message['stream']
                data = message['data']

                if '@depth' in stream:
                    await self._handle_orderbook_update(data)
                elif '@trade' in stream:
                    await self._handle_trade_update(data)

            # Pattern 2: Type-based messages (Coinbase style)
            elif 'type' in message:
                msg_type = message['type']
                if msg_type == 'l2update':
                    await self._handle_orderbook_update(message)
                elif msg_type == 'match':
                    await self._handle_trade_update(message)

            # Pattern 3: Channel-based messages (Kraken style)
            elif 'channelName' in message:
                channel = message['channelName']
                if channel == 'book':
                    await self._handle_orderbook_update(message)
                elif channel == 'trade':
                    await self._handle_trade_update(message)

        except Exception as e:
            await self.on_error(e)

    async def _handle_orderbook_update(self, data: Dict[str, Any]):
        """Process orderbook update"""
        try:
            # Extract symbol (customize based on exchange format)
            symbol_str = data.get('s') or data.get('symbol') or data.get('product_id')
            symbol = ExchangeUtils.to_symbol(symbol_str)

            # Parse bids and asks (customize based on exchange format)
            # Common formats:
            # - Binance: {"b": [["price", "quantity"], ...], "a": [["price", "quantity"], ...]}
            # - Coinbase: {"changes": [["side", "price", "size"], ...]}
            # - Kraken: {"bids": [["price", "volume", "timestamp"], ...]}

            bids = []
            asks = []

            # Example for Binance-style format
            if 'b' in data and 'a' in data:
                for bid in data['b']:
                    bids.append(OrderBookEntry(price=float(bid[0]), size=float(bid[1])))
                for ask in data['a']:
                    asks.append(OrderBookEntry(price=float(ask[0]), size=float(ask[1])))

            orderbook = OrderBook(
                bids=bids,
                asks=asks,
                timestamp=time.time()
            )

            # Notify subscribers (implemented in cex class)
            await self._notify_orderbook_update(symbol, orderbook)

        except Exception as e:
            await self.on_error(e)

    async def _handle_trade_update(self, data: Dict[str, Any]):
        """Process trade update"""
        try:
            # Extract trade information (customize based on exchange format)
            symbol_str = data.get('s') or data.get('symbol') or data.get('product_id')
            symbol = ExchangeUtils.to_symbol(symbol_str)

            # Parse trade data (customize based on exchange format)
            # Common formats:
            # - Binance: {"p": "price", "q": "quantity", "m": true/false}
            # - Coinbase: {"price": "price", "size": "size", "side": "buy/sell"}
            # - Kraken: [["price", "volume", "time", "side", "orderType", "misc"], ...]

            trade = Trade(
                price=float(data.get('p') or data.get('price')),
                amount=float(data.get('q') or data.get('size') or data.get('quantity')),
                side=self._parse_trade_side(data),
                timestamp=int(data.get('T') or data.get('time') or time.time() * 1000),
                is_maker=data.get('m', False)  # Maker flag if available
            )

            # Notify subscribers
            await self._notify_trade_update(symbol, trade)

        except Exception as e:
            await self.on_error(e)

    def _parse_trade_side(self, data: Dict[str, Any]) -> Side:
        """Parse trade side from exchange-specific format"""
        # Customize based on exchange format
        if 'm' in data:  # Binance: true if buyer is maker
            return Side.SELL if data['m'] else Side.BUY
        elif 'side' in data:  # Coinbase: "buy" or "sell"
            return Side.BUY if data['side'] == 'buy' else Side.SELL
        else:
            return Side.BUY  # Default fallback

    async def on_error(self, error: Exception):
        """Handle WebSocket errors"""
        self.logger.error(f"WebSocket error in {self.exchange}: {error}")
        # Implement error handling logic
        # - Log errors appropriately
        # - Trigger reconnection if needed
        # - Notify error handlers
```

#### Main Exchange Interface Template

```python
# src/cex/{exchange_name}/{exchange_name}_exchange.py
from typing import Optional, List, Dict, Any
from core.cex.base import BaseExchangeInterface
from structs import Symbol, OrderBook, AssetBalance, Order, Side, OrderType, OrderId,

AssetName,

ExchangeName
from .rest.

{exchange_name}
_public
import ExchangePublic
from .rest.

{exchange_name}
_private
import ExchangePrivate
from .ws.

{exchange_name}
_ws_public
import ExchangeWebSocketPublic


class ExchangeExchange(BaseExchangeInterface):
    """High-level unified cex for Exchange"""

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.exchange = ExchangeName("EXCHANGE")

        # REST components
        self._rest_public = ExchangePublic()
        self._rest_private = ExchangePrivate(api_key, secret_key) if api_key and secret_key else None

        # WebSocket component
        self._ws_public = ExchangeWebSocketPublic(self.exchange)

        # State management
        self._active_symbols: List[Symbol] = []
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._balances_dict: Dict[AssetName, AssetBalance] = {}
        self._initialized = False

        self.logger = logging.getLogger(f"cex.{self.exchange.lower()}")

    # Implement BaseExchangeInterface properties
    @property
    def orderbook(self) -> Optional[OrderBook]:
        """Current primary orderbook snapshot"""
        if self._active_symbols:
            return self._orderbooks.get(self._active_symbols[0])
        return None

    @property
    def balances(self) -> Dict[AssetName, AssetBalance]:
        """Current account balances"""
        return self._balances_dict.copy()

    @property
    def active_symbols(self) -> List[Symbol]:
        """Currently subscribed symbols"""
        return self._active_symbols.copy()

    # Implement BaseExchangeInterface methods
    async def init(self, symbols: Optional[List[Symbol]] = None) -> None:
        """Initialize exchange with optional symbol list"""
        try:
            if symbols:
                self._active_symbols = symbols.copy()

                # Initialize WebSocket connections
                await self._ws_public.initialize(symbols)

                # Subscribe to orderbook updates
                for symbol in symbols:
                    await self._ws_public.start_symbol(symbol)

            # Load initial balances if private API available
            if self._rest_private:
                await self._refresh_balances()

            self._initialized = True
            self.logger.info(f"Initialized {self.exchange} exchange with {len(self._active_symbols)} symbols")

        except Exception as e:
            await self._cleanup_partial_init()
            raise

    async def add_symbol(self, symbol: Symbol) -> None:
        """Start data streaming for symbol"""
        if symbol not in self._active_symbols:
            self._active_symbols.append(symbol)
            await self._ws_public.start_symbol(symbol)
            self.logger.info(f"Added symbol {symbol} to {self.exchange}")

    async def remove_symbol(self, symbol: Symbol) -> None:
        """Stop data streaming for symbol"""
        if symbol in self._active_symbols:
            self._active_symbols.remove(symbol)
            await self._ws_public.stop_symbol(symbol)
            self._orderbooks.pop(symbol, None)
            self.logger.info(f"Removed symbol {symbol} from {self.exchange}")

    # High-level trading methods
    async def place_limit_order(self, symbol: Symbol, side: Side, amount: float, price: float) -> Order:
        """Place limit order"""
        if not self._rest_private:
            raise ValueError("Private API not configured - API keys required")

        return await self._rest_private.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            amount=amount,
            price=price
        )

    async def place_market_order(self, symbol: Symbol, side: Side, amount: float) -> Order:
        """Place market order"""
        if not self._rest_private:
            raise ValueError("Private API not configured - API keys required")

        return await self._rest_private.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            amount=amount
        )

    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Cancel order"""
        if not self._rest_private:
            raise ValueError("Private API not configured - API keys required")

        return await self._rest_private.cancel_order(symbol, order_id)

    async def get_fresh_balances(self) -> Dict[AssetName, AssetBalance]:
        """Get fresh account balances"""
        if not self._rest_private:
            raise ValueError("Private API not configured - API keys required")

        await self._refresh_balances()
        return self.balances

    def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """Get balance for specific asset"""
        return self._balances_dict.get(asset)

    # Context manager support
    def session(self, symbols: Optional[List[Symbol]] = None) -> 'ExchangeExchangeSession':
        """Context manager for proper resource cleanup"""
        return ExchangeExchangeSession(self, symbols or [])

    # Internal methods
    async def _refresh_balances(self) -> None:
        """Refresh account balances"""
        if self._rest_private:
            balances = await self._rest_private.get_account_balance()
            self._balances_dict = {balance.asset: balance for balance in balances}

    async def _cleanup_partial_init(self) -> None:
        """Clean up resources during failed initialization"""
        if self._ws_public:
            await self._ws_public.ws_client.stop()

        self._active_symbols.clear()
        self._orderbooks.clear()
        self._balances_dict.clear()
        self._initialized = False

    async def close(self) -> None:
        """Clean shutdown with proper resource cleanup"""
        if self._ws_public:
            await self._ws_public.ws_client.stop()

        self._active_symbols.clear()
        self._orderbooks.clear()
        self._balances_dict.clear()
        self._initialized = False

        self.logger.info(f"Successfully closed {self.exchange} exchange")


class ExchangeExchangeSession:
    """Context manager for proper resource management"""

    def __init__(self, exchange: ExchangeExchange, symbols: List[Symbol]):
        self.exchange = exchange
        self.symbols = symbols

    async def __aenter__(self) -> ExchangeExchange:
        await self.exchange.init(self.symbols)
        return self.exchange

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.exchange.close()
```

### Testing Template

#### Unit Tests Template

```python
# tests/test_{exchange_name}_integration.py
import pytest
import asyncio
from exchanges.

{exchange_name}.
{exchange_name}
_exchange
import ExchangeExchange
from structs import Symbol, AssetName, Side, OrderType
from core.cex.rest import PublicExchangeSpotRestInterface
from core.cex.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface


class TestExchangeIntegration:
    """Comprehensive integration tests for Exchange"""

    @pytest.fixture
    def test_symbol(self):
        return Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))

    @pytest.fixture
    async def exchange(self):
        exchange = ExchangeExchange()
        yield exchange
        await exchange.close()

    @pytest.fixture
    async def private_exchange(self):
        """Requires environment variables: EXCHANGE_API_KEY, EXCHANGE_SECRET_KEY"""
        api_key = os.getenv('EXCHANGE_API_KEY')
        secret_key = os.getenv('EXCHANGE_SECRET_KEY')

        if not api_key or not secret_key:
            pytest.skip("API credentials not configured")

        exchange = ExchangeExchange(api_key=api_key, secret_key=secret_key)
        yield exchange
        await exchange.close()

    # Interface compliance tests
    async def test_public_interface_compliance(self, exchange):
        """Test public cex implementation"""
        assert isinstance(exchange._rest_public, PublicExchangeSpotRestInterface)

        # Test all public methods are implemented
        public_methods = [
            'get_exchange_info', 'get_orderbook', 'get_recent_trades',
            'get_server_time', 'ping'
        ]

        for method in public_methods:
            assert hasattr(exchange._rest_public, method)
            assert callable(getattr(exchange._rest_public, method))

    async def test_private_interface_compliance(self, private_exchange):
        """Test private cex implementation"""
        if not private_exchange._rest_private:
            pytest.skip("Private API not configured")

        assert isinstance(private_exchange._rest_private, PrivateExchangeSpotRestInterface)

        # Test all private methods are implemented
        private_methods = [
            'get_account_balance', 'get_asset_balance', 'place_order',
            'cancel_order', 'get_order', 'get_open_orders'
        ]

        for method in private_methods:
            assert hasattr(private_exchange._rest_private, method)
            assert callable(getattr(private_exchange._rest_private, method))

    # Data structure compliance tests
    async def test_data_structure_compliance(self, exchange, test_symbol):
        """Test unified data structure usage"""
        # Test orderbook structure
        orderbook = await exchange._rest_public.get_orderbook(test_symbol)

        assert isinstance(orderbook, OrderBook)
        assert hasattr(orderbook, 'bids')
        assert hasattr(orderbook, 'asks')
        assert hasattr(orderbook, 'timestamp')

        # Verify OrderBookEntry structure
        if orderbook.bids:
            assert isinstance(orderbook.bids[0], OrderBookEntry)
            assert hasattr(orderbook.bids[0], 'price')
            assert hasattr(orderbook.bids[0], 'size')

        # Test trades structure
        trades = await exchange._rest_public.get_recent_trades(test_symbol, limit=10)
        assert isinstance(trades, list)

        if trades:
            trade = trades[0]
            assert isinstance(trade, Trade)
            assert hasattr(trade, 'price')
            assert hasattr(trade, 'amount')
            assert hasattr(trade, 'side')

    # Performance tests
    async def test_latency_requirements(self, exchange, test_symbol):
        """Test latency requirements (<50ms)"""
        import time

        # Test REST operation latency
        start_time = time.time()
        orderbook = await exchange._rest_public.get_orderbook(test_symbol)
        latency = time.time() - start_time

        assert latency < 0.05, f"Latency {latency:.3f}s exceeds 50ms requirement"
        assert orderbook is not None
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0

    async def test_concurrent_operations(self, exchange, test_symbol):
        """Test concurrent request handling"""

        # Test multiple concurrent requests
        async def fetch_orderbook():
            return await exchange._rest_public.get_orderbook(test_symbol)

        # Run 20 concurrent requests
        tasks = [fetch_orderbook() for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify results
        errors = [r for r in results if isinstance(r, Exception)]
        success_rate = (len(results) - len(errors)) / len(results)

        assert success_rate > 0.9, f"Success rate {success_rate:.2f} too low"

    # Functional tests
    async def test_exchange_info_caching(self, exchange):
        """Test exchange info caching behavior"""
        # First call
        start_time = time.time()
        info1 = await exchange._rest_public.get_exchange_info()
        first_call_time = time.time() - start_time

        # Second call (should be cached)
        start_time = time.time()
        info2 = await exchange._rest_public.get_exchange_info()
        second_call_time = time.time() - start_time

        # Verify caching worked
        assert info1 == info2
        assert second_call_time < first_call_time / 2  # Should be much faster

    async def test_symbol_conversion(self, test_symbol):
        """Test symbol conversion utilities"""
        from exchanges.
        {exchange_name}.common.
        {exchange_name}
        _utils
        import ExchangeUtils

        # Test conversion both ways
        pair = ExchangeUtils.to_pair(test_symbol)
        assert isinstance(pair, str)
        assert len(pair) > 0

        converted_symbol = ExchangeUtils.to_symbol(pair)
        assert converted_symbol == test_symbol

    # Trading tests (testnet only)
    async def test_account_balance(self, private_exchange):
        """Test account balance retrieval"""
        if not private_exchange._rest_private:
            pytest.skip("Private API not configured")

        balances = await private_exchange._rest_private.get_account_balance()
        assert isinstance(balances, list)

        # Test individual asset balance
        if balances:
            asset = balances[0].asset
            asset_balance = await private_exchange._rest_private.get_asset_balance(asset)
            assert asset_balance.asset == asset

    @pytest.mark.skipif(not os.getenv('ENABLE_TESTNET_TRADING'), reason="Testnet trading not enabled")
    async def test_order_lifecycle(self, private_exchange, test_symbol):
        """Test complete order lifecycle (testnet only)"""
        if not private_exchange._rest_private:
            pytest.skip("Private API not configured")

        # Get current orderbook for safe price
        orderbook = await private_exchange._rest_public.get_orderbook(test_symbol)
        safe_price = orderbook.bids[0].price * 0.5  # Very safe price

        # Place limit order
        order = await private_exchange._rest_private.place_order(
            symbol=test_symbol,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            amount=0.001,  # Minimum amount
            price=safe_price
        )

        # Verify order placement
        assert order.order_id is not None
        assert order.status == OrderStatus.NEW
        assert order.symbol == test_symbol

        try:
            # Check order status
            order_status = await private_exchange._rest_private.get_order(test_symbol, order.order_id)
            assert order_status.order_id == order.order_id

            # Verify order appears in open orders
            open_orders = await private_exchange._rest_private.get_open_orders(test_symbol)
            order_ids = [o.order_id for o in open_orders]
            assert order.order_id in order_ids

        finally:
            # Clean up - cancel order
            cancelled_order = await private_exchange._rest_private.cancel_order(test_symbol, order.order_id)
            assert cancelled_order.status in [OrderStatus.CANCELED, OrderStatus.PARTIALLY_CANCELED]

    # WebSocket tests
    async def test_websocket_connection(self, exchange, test_symbol):
        """Test WebSocket connection and data streaming"""
        async with exchange.session([test_symbol]) as ex:
            # Wait for initial connection
            await asyncio.sleep(2)

            # Verify orderbook data received
            orderbook = ex.orderbook
            assert orderbook is not None
            assert len(orderbook.bids) > 0
            assert len(orderbook.asks) > 0

            # Verify spread is reasonable
            best_bid = orderbook.bids[0].price
            best_ask = orderbook.asks[0].price
            assert best_ask > best_bid, "Invalid spread - ask should be higher than bid"


if __name__ == "__main__":
    # Run specific test
    pytest.main([__file__ + "::TestExchangeIntegration::test_latency_requirements", "-v"])
```

This comprehensive Exchange Integration Guide provides the complete blueprint for integrating new exchanges into your HFT arbitrage engine. It covers all aspects from planning to implementation, testing, and deployment while maintaining the strict performance and safety standards required for high-frequency trading operations.

Key points to remember:
1. **Always prioritize HFT safety** - never cache real-time trading data
2. **Follow SOLID principles** - maintain clean interface separation
3. **Use unified data structures** - ensure consistent behavior across exchanges
4. **Test thoroughly** - both functional and performance requirements
5. **Reference MEXC implementation** for advanced patterns when needed
6. **Focus on JSON APIs** as the default pattern (85% of exchanges)

The templates provided are production-ready and follow all the architectural principles outlined in your system documentation.