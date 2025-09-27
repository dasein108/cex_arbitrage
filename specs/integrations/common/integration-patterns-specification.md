# Common Integration Patterns Specification

## Overview

This specification documents the common patterns, strategies, and architectural components shared across all exchange integrations in the CEX arbitrage engine. These patterns ensure consistency, maintainability, and HFT performance across MEXC, Gate.io, and future exchange integrations.

## Separated Domain Architecture Pattern

### **Universal Domain Separation**

All exchange integrations follow the **separated domain architecture** where public (market data) and private (trading) operations are completely isolated:

```
Exchange Integration Architecture:
┌─────────────────────────┐    ┌──────────────────────────┐
│ CompositePublicExchange │    │ CompositePrivateExchange │
├─────────────────────────┤    ├──────────────────────────┤
│ • Market Data Only      │    │ • Trading Operations     │
│ • No Authentication     │    │ • Authentication Required│
│ • Public WebSocket      │    │ • Private WebSocket      │
│ • Orderbooks, Trades    │    │ • Orders, Balances       │
│ • Tickers, Symbols      │    │ • Positions, Executions  │
└─────────────────────────┘    └──────────────────────────┘
```

### **Domain Separation Benefits**

1. **Clear Boundaries**: Authentication vs non-authentication operations
2. **Independent Scaling**: Each domain optimized for its specific workload
3. **Security Isolation**: Trading operations isolated from market data
4. **HFT Compliance**: No real-time data caching violations
5. **Maintainability**: Separate concerns reduce complexity

### **Implementation Pattern**

```python
# Base pattern for all exchange integrations
class ExchangeCompositePublicExchange(CompositePublicExchange):
    """Public domain - Market data operations only."""
    
    async def _create_public_rest(self) -> PublicSpotRest:
        """Create exchange-specific public REST client."""
        raise NotImplementedError
    
    async def _create_public_ws_with_handlers(self, handlers: PublicWebsocketHandlers) -> PublicSpotWebsocket:
        """Create exchange-specific public WebSocket client."""
        raise NotImplementedError
    
    async def _get_websocket_handlers(self) -> PublicWebsocketHandlers:
        """Get exchange-specific WebSocket handlers."""
        return PublicWebsocketHandlers(
            orderbook_handler=self._handle_orderbook,
            ticker_handler=self._handle_ticker,
            trades_handler=self._handle_trade,
            book_ticker_handler=self._handle_book_ticker,
        )

class ExchangeCompositePrivateExchange(CompositePrivateExchange):
    """Private domain - Trading operations only."""
    
    async def _create_private_rest(self) -> PrivateSpotRest:
        """Create exchange-specific private REST client."""
        raise NotImplementedError
    
    async def _create_private_ws_with_handlers(self, handlers: PrivateWebsocketHandlers) -> PrivateSpotWebsocket:
        """Create exchange-specific private WebSocket client."""
        raise NotImplementedError
    
    async def _get_websocket_handlers(self) -> PrivateWebsocketHandlers:
        """Get exchange-specific WebSocket handlers."""
        return PrivateWebsocketHandlers(
            order_handler=self._order_handler,
            balance_handler=self._balance_handler,
            execution_handler=self._execution_handler,
        )
```

## Strategy Pattern Implementation

### **Connection Strategy Pattern**

Each exchange implements custom connection strategies for optimal performance and reliability:

#### **Base Connection Strategy**

```python
class ConnectionStrategy(ABC):
    """Base connection strategy for exchange WebSocket connections."""
    
    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None):
        self.config = config
        self.logger = logger or get_strategy_logger('connection', ['exchange'])
        self._websocket: Optional[WebSocketClientProtocol] = None
    
    @abstractmethod
    async def connect(self) -> WebSocketClientProtocol:
        """Establish WebSocket connection with exchange-specific optimizations."""
        pass
    
    @abstractmethod
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get exchange-specific reconnection policy."""
        pass
    
    @abstractmethod
    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted."""
        pass
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate connection (if required)."""
        pass
    
    def classify_error(self, error: Exception) -> str:
        """Classify error type for appropriate handling."""
        if hasattr(error, 'code'):
            if error.code == 1005:
                return "abnormal_closure"
            elif error.code in [1006, 1011]:
                return "connection_closed"
        
        if "timeout" in str(error).lower():
            return "timeout"
        elif "connection refused" in str(error).lower():
            return "connection_refused"
        elif "auth" in str(error).lower():
            return "authentication_failure"
        
        return "unknown"
```

#### **Exchange-Specific Implementations**

**MEXC Connection Strategy**:
```python
class MexcPublicConnectionStrategy(ConnectionStrategy):
    """MEXC-specific connection with minimal headers to avoid blocking."""
    
    async def connect(self) -> WebSocketClientProtocol:
        # NO extra headers - MEXC blocks browser-like headers
        self._websocket = await connect(
            self.websocket_url,
            ping_interval=30,      # MEXC uses 30s ping
            compression=None,      # Disabled for HFT
            max_queue=512
        )
        return self._websocket
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        return ReconnectionPolicy(
            max_attempts=10,
            initial_delay=1.0,
            reset_on_1005=True  # MEXC often has 1005 errors
        )
```

**Gate.io Connection Strategy**:
```python
class GateioPublicConnectionStrategy(ConnectionStrategy):
    """Gate.io-specific connection with custom ping/pong."""
    
    async def connect(self) -> WebSocketClientProtocol:
        self._websocket = await connect(
            self.websocket_url,
            ping_interval=None,    # Disable built-in ping
            compression="deflate", # Gate.io supports compression
            max_size=2048 * 1024   # 2MB for compressed messages
        )
        return self._websocket
    
    def get_ping_message(self) -> str:
        """Custom ping message for Gate.io."""
        return msgspec.json.encode({
            "time": int(time.time()),
            "channel": "spot.ping",
            "event": "ping"
        }).decode()
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        return ReconnectionPolicy(
            max_attempts=15,       # Gate.io is more stable
            initial_delay=2.0,
            reset_on_1005=False    # Less common with Gate.io
        )
```

### **Retry Strategy Pattern**

Standardized retry logic with exchange-specific optimizations:

#### **Base Retry Strategy**

```python
class RetryStrategy(ABC):
    """Base retry strategy for REST requests."""
    
    def __init__(self, exchange_config: ExchangeConfig):
        self.max_attempts = exchange_config.network.max_retries
        self.base_delay = exchange_config.network.retry_delay
        self.max_delay = self.base_delay * 10
    
    @abstractmethod
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if request should be retried."""
        pass
    
    @abstractmethod
    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        """Calculate retry delay."""
        pass
    
    def handle_rate_limit(self, response_headers: Dict[str, str]) -> float:
        """Extract rate limit information from response headers."""
        retry_after = response_headers.get('Retry-After')
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return 30.0  # Default delay
```

#### **Exchange-Specific Retry Implementations**

**MEXC Retry Strategy**:
```python
class MexcRetryStrategy(RetryStrategy):
    """MEXC-specific retry with aggressive rate limit handling."""
    
    def should_retry(self, attempt: int, error: Exception) -> bool:
        if attempt >= self.max_attempts:
            return False
        
        # Retry on connection errors and rate limits
        return isinstance(error, (RateLimitErrorRest, ExchangeConnectionRestError))
    
    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        if isinstance(error, RateLimitErrorRest):
            # Longer delay for rate limits (MEXC is strict)
            return min(self.base_delay * (3 ** attempt), self.max_delay)
        else:
            # Standard exponential backoff
            return min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
```

**Gate.io Retry Strategy**:
```python
class GateioRetryStrategy(RetryStrategy):
    """Gate.io-specific retry with gentler backoff."""
    
    def should_retry(self, attempt: int, error: Exception) -> bool:
        if attempt >= self.max_attempts:
            return False
        
        # Gate.io is more forgiving with retries
        return isinstance(error, (RateLimitErrorRest, ExchangeConnectionRestError, asyncio.TimeoutError))
    
    async def calculate_delay(self, attempt: int, error: Exception) -> float:
        if isinstance(error, RateLimitErrorRest):
            # Moderate delay for Gate.io rate limits
            return min(self.base_delay * (2 ** attempt), self.max_delay)
        else:
            # Linear backoff for other errors
            return min(self.base_delay * attempt, self.max_delay)
```

### **Message Parsing Strategy Pattern**

Unified message parsing with format-specific optimizations:

#### **Base Message Parser**

```python
class MessageParsingStrategy(ABC):
    """Base message parsing strategy."""
    
    def __init__(self, symbol_mapper: SymbolMapperInterface):
        self.symbol_mapper = symbol_mapper
    
    @abstractmethod
    async def parse_message(self, message: Union[str, bytes, Dict]) -> Optional[Any]:
        """Parse exchange-specific message format."""
        pass
    
    async def parse_orderbook_message(self, data: Any) -> OrderBook:
        """Parse orderbook update message."""
        raise NotImplementedError
    
    async def parse_trade_message(self, data: Any) -> List[Trade]:
        """Parse trade update message."""
        raise NotImplementedError
    
    async def parse_ticker_message(self, data: Any) -> Ticker:
        """Parse ticker update message."""
        raise NotImplementedError
```

#### **Format-Specific Parsers**

**JSON Message Parser** (Gate.io, general use):
```python
class JsonMessageParsingStrategy(MessageParsingStrategy):
    """JSON-based message parsing for most exchanges."""
    
    async def parse_message(self, message: Union[str, Dict]) -> Optional[Any]:
        if isinstance(message, str):
            try:
                message = msgspec.json.decode(message)
            except Exception:
                return None
        
        channel = message.get('channel', '')
        
        if 'order_book' in channel:
            return await self.parse_orderbook_message(message)
        elif 'trades' in channel:
            return await self.parse_trade_message(message)
        elif 'ticker' in channel:
            return await self.parse_ticker_message(message)
        
        return None
```

**Protocol Buffer Parser** (MEXC):
```python
class ProtobufMessageParsingStrategy(MessageParsingStrategy):
    """Protocol Buffer message parsing for high-performance exchanges."""
    
    # Fast binary pattern detection
    _JSON_INDICATORS = frozenset({ord('{'), ord('[')})
    _PROTOBUF_MAGIC_BYTES = {0x0a: 'deals', 0x12: 'stream', 0x1a: 'symbol'}
    
    async def parse_message(self, message: bytes) -> Optional[Any]:
        if not isinstance(message, bytes):
            return None
        
        # Detect message format
        if message and message[0] in self._JSON_INDICATORS:
            # Fall back to JSON parsing
            json_msg = msgspec.json.decode(message)
            return await self._parse_json_fallback(json_msg)
        
        # Protocol buffer parsing
        first_byte = message[0] if message else 0
        msg_type = self._PROTOBUF_MAGIC_BYTES.get(first_byte, 'unknown')
        
        return await self._parse_protobuf_message(message, msg_type)
    
    async def _parse_protobuf_message(self, data: bytes, msg_type: str) -> Optional[Any]:
        """Parse protobuf with type hints for performance."""
        try:
            wrapper = PushDataV3ApiWrapper()
            wrapper.ParseFromString(data)
            
            if wrapper.HasField('publicLimitDepths'):
                return await self._parse_protobuf_orderbook(wrapper.publicLimitDepths, data)
            elif wrapper.HasField('publicAggreDeals'):
                return await self._parse_protobuf_trades(wrapper.publicAggreDeals, data)
            
        except Exception as e:
            self.logger.warning(f"Protobuf parsing failed: {e}")
        
        return None
```

## Service Architecture Patterns

### **Symbol Mapping Pattern**

Standardized symbol conversion with exchange-specific formats:

#### **Base Symbol Mapper**

```python
class SymbolMapperInterface(ABC):
    """Base interface for symbol mapping services."""
    
    def __init__(self, quote_assets: Tuple[str, ...]):
        self._quote_assets = quote_assets
        self._symbol_cache: Dict[Symbol, str] = {}
        self._string_cache: Dict[str, Symbol] = {}
    
    def symbol_to_string(self, symbol: Symbol) -> str:
        """Convert Symbol to exchange-specific string format."""
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]
        
        result = self._symbol_to_string(symbol)
        self._symbol_cache[symbol] = result
        return result
    
    def string_to_symbol(self, pair: str) -> Symbol:
        """Parse exchange-specific string to Symbol."""
        if pair in self._string_cache:
            return self._string_cache[pair]
        
        result = self._string_to_symbol(pair)
        self._string_cache[pair] = result
        return result
    
    @abstractmethod
    def _symbol_to_string(self, symbol: Symbol) -> str:
        """Exchange-specific implementation."""
        pass
    
    @abstractmethod
    def _string_to_symbol(self, pair: str) -> Symbol:
        """Exchange-specific implementation."""
        pass
```

#### **Exchange-Specific Mappers**

**MEXC Mapper** (Concatenated format):
```python
class MexcSymbolMapper(SymbolMapperInterface):
    """MEXC format: BTCUSDT (no separator)"""
    
    def _symbol_to_string(self, symbol: Symbol) -> str:
        return f"{symbol.base}{symbol.quote}"
    
    def _string_to_symbol(self, pair: str) -> Symbol:
        pair = pair.upper()
        for quote in self._quote_assets:
            if pair.endswith(quote):
                base = pair[:-len(quote)]
                if base:
                    return Symbol(base=AssetName(base), quote=AssetName(quote))
        raise ValueError(f"Unrecognized MEXC pair: {pair}")
```

**Gate.io Mapper** (Underscore format):
```python
class GateioSymbolMapper(SymbolMapperInterface):
    """Gate.io format: BTC_USDT (underscore separator)"""
    
    def _symbol_to_string(self, symbol: Symbol) -> str:
        return f"{symbol.base}_{symbol.quote}"
    
    def _string_to_symbol(self, pair: str) -> Symbol:
        if '_' not in pair:
            raise ValueError(f"Invalid Gate.io pair format: {pair}")
        
        base, quote = pair.upper().split('_', 1)
        return Symbol(base=AssetName(base), quote=AssetName(quote))
```

### **Error Classification Pattern**

Unified error handling with exchange-specific mappings:

#### **Base Error Classifier**

```python
class ErrorClassifier(ABC):
    """Base error classification for exchange integrations."""
    
    @abstractmethod
    def classify_error(self, error_code: int, message: str) -> Type[Exception]:
        """Map exchange error codes to unified exceptions."""
        pass
    
    def create_exception(self, error_code: int, message: str, original_error: Exception) -> Exception:
        """Create appropriate exception instance."""
        exception_class = self.classify_error(error_code, message)
        return exception_class(error_code, message, original_error)
```

#### **Exchange-Specific Classifiers**

**MEXC Error Classifier**:
```python
class MexcErrorClassifier(ErrorClassifier):
    """MEXC-specific error code mappings."""
    
    MEXC_RATE_LIMIT_CODES = {1100, 1101, 1102}
    MEXC_TRADING_DISABLED_CODES = {2010, 2011, 2013}
    MEXC_INSUFFICIENT_BALANCE_CODES = {2019, 2020}
    
    def classify_error(self, error_code: int, message: str) -> Type[Exception]:
        if error_code in self.MEXC_RATE_LIMIT_CODES:
            return RateLimitError
        elif error_code in self.MEXC_TRADING_DISABLED_CODES:
            return TradingDisabled
        elif error_code in self.MEXC_INSUFFICIENT_BALANCE_CODES:
            return InsufficientBalance
        else:
            return ExchangeAPIError
```

**Gate.io Error Classifier**:
```python
class GateioErrorClassifier(ErrorClassifier):
    """Gate.io-specific error code mappings."""
    
    GATEIO_RATE_LIMIT_CODES = {40001, 40002, 40003}
    GATEIO_TRADING_DISABLED_CODES = {40004, 40005, 40006}
    GATEIO_POSITION_ERRORS = {40009, 40010, 40011}
    
    def classify_error(self, error_code: int, message: str) -> Type[Exception]:
        if error_code in self.GATEIO_RATE_LIMIT_CODES:
            return RateLimitError
        elif error_code in self.GATEIO_TRADING_DISABLED_CODES:
            return TradingDisabled
        elif error_code in self.GATEIO_POSITION_ERRORS:
            return PositionError
        else:
            return ExchangeAPIError
```

## Performance Optimization Patterns

### **Object Pooling Pattern**

Reduce allocation overhead for high-frequency operations:

#### **Generic Object Pool**

```python
class ObjectPool(Generic[T]):
    """Generic object pool for HFT optimization."""
    
    def __init__(self, factory: Callable[[], T], initial_size: int = 100, max_size: int = 500):
        self._factory = factory
        self._pool = deque()
        self._max_size = max_size
        self._created_count = 0
        self._reused_count = 0
        
        # Pre-allocate initial objects
        for _ in range(initial_size):
            self._pool.append(factory())
            self._created_count += 1
    
    def get(self) -> T:
        """Get object from pool or create new one."""
        if self._pool:
            self._reused_count += 1
            return self._pool.popleft()
        
        self._created_count += 1
        return self._factory()
    
    def return_object(self, obj: T) -> None:
        """Return object to pool for reuse."""
        if len(self._pool) < self._max_size:
            self._pool.append(obj)
    
    def get_stats(self) -> Dict[str, int]:
        """Get pool utilization statistics."""
        total_requests = self._created_count + self._reused_count
        return {
            'pool_size': len(self._pool),
            'created_count': self._created_count,
            'reused_count': self._reused_count,
            'reuse_rate': (self._reused_count / total_requests * 100) if total_requests > 0 else 0
        }
```

#### **Specialized Pools**

**OrderBookEntry Pool** (MEXC):
```python
class OrderBookEntryPool:
    """Specialized pool for OrderBookEntry objects."""
    
    def __init__(self, initial_size: int = 200):
        self._pool = deque()
        
        # Pre-allocate entries
        for _ in range(initial_size):
            self._pool.append(OrderBookEntry(price=0.0, size=0.0))
    
    def get_entry(self, price: float, size: float) -> OrderBookEntry:
        """Get pooled entry with new values."""
        if self._pool:
            entry = self._pool.popleft()
            return OrderBookEntry(price=price, size=size)
        return OrderBookEntry(price=price, size=size)
    
    def return_entry(self, entry: OrderBookEntry) -> None:
        """Return entry to pool."""
        if len(self._pool) < 500:  # Max pool size
            self._pool.append(entry)
```

### **Caching Strategy Pattern**

Intelligent caching for static data with HFT safety:

#### **HFT-Safe Cache**

```python
class HFTSafeCache:
    """Cache that only stores static data safe for HFT systems."""
    
    # Allowed cache categories (NEVER real-time trading data)
    SAFE_CACHE_CATEGORIES = {
        'symbol_info',      # Trading rules and precision
        'exchange_config',  # Static exchange configuration
        'trading_rules',    # Symbol-specific trading rules
        'fee_schedules',    # Trading fee structures
        'market_hours'      # Exchange operating hours
    }
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float, str]] = {}
        self._access_count: Dict[str, int] = {}
    
    def set(self, key: str, value: Any, ttl: float, category: str) -> None:
        """Set cache value with category validation."""
        if category not in self.SAFE_CACHE_CATEGORIES:
            raise ValueError(f"Unsafe cache category: {category}. HFT systems must not cache real-time data.")
        
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry, category)
        self._access_count[key] = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        if key not in self._cache:
            return None
        
        value, expiry, category = self._cache[key]
        
        if time.time() > expiry:
            del self._cache[key]
            return None
        
        self._access_count[key] += 1
        return value
```

#### **Symbol Information Cache**

```python
class SymbolInfoCache:
    """Specialized cache for symbol information (safe for HFT)."""
    
    def __init__(self, ttl: float = 300):  # 5 minute TTL
        self._cache = HFTSafeCache()
        self._ttl = ttl
    
    async def get_symbol_info(self, symbol: Symbol, fetcher: Callable) -> SymbolInfo:
        """Get symbol info with caching."""
        cache_key = f"symbol_info_{symbol.base}_{symbol.quote}"
        
        # Try cache first
        cached_info = self._cache.get(cache_key)
        if cached_info:
            return cached_info
        
        # Fetch fresh data
        symbol_info = await fetcher(symbol)
        self._cache.set(cache_key, symbol_info, self._ttl, 'symbol_info')
        
        return symbol_info
```

### **Connection Pooling Pattern**

Efficient connection management for REST requests:

#### **REST Connection Pool**

```python
class RestConnectionPool:
    """Managed connection pool for REST clients."""
    
    def __init__(self, base_url: str, pool_size: int = 10):
        self.base_url = base_url
        self.pool_size = pool_size
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._connection_count = 0
        self._request_count = 0
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with connection pooling."""
        if self._session is None or self._session.closed:
            # Create connector with connection pooling
            self._connector = aiohttp.TCPConnector(
                limit=self.pool_size,
                limit_per_host=self.pool_size,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            
            # Create session with timeout configuration
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                base_url=self.base_url
            )
            
            self._connection_count += 1
        
        return self._session
    
    async def request(self, method: str, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make HTTP request with connection pooling."""
        session = await self.get_session()
        self._request_count += 1
        return await session.request(method, endpoint, **kwargs)
    
    async def close(self) -> None:
        """Close connection pool."""
        if self._session:
            await self._session.close()
        if self._connector:
            await self._connector.close()
    
    def get_stats(self) -> Dict[str, int]:
        """Get connection pool statistics."""
        return {
            'connections_created': self._connection_count,
            'requests_made': self._request_count,
            'reuse_rate': (self._request_count / max(self._connection_count, 1))
        }
```

## Authentication Pattern

### **Unified Authentication Interface**

Standardized authentication across different exchanges:

#### **Base Authentication Strategy**

```python
class AuthenticationStrategy(ABC):
    """Base authentication strategy for exchange APIs."""
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
    
    @abstractmethod
    def generate_signature(self, **kwargs) -> str:
        """Generate authentication signature."""
        pass
    
    @abstractmethod
    def get_auth_headers(self, **kwargs) -> Dict[str, str]:
        """Get authentication headers for requests."""
        pass
    
    def mask_credentials(self) -> Dict[str, str]:
        """Get masked credentials for logging."""
        return {
            'api_key': f"{self.api_key[:8]}...{self.api_key[-4:]}",
            'secret_key': "***masked***"
        }
```

#### **Exchange-Specific Authentication**

**MEXC Authentication**:
```python
class MexcAuthenticationStrategy(AuthenticationStrategy):
    """MEXC HMAC-SHA256 authentication."""
    
    def generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate MEXC signature from query parameters."""
        query_string = urllib.parse.urlencode(params)
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def get_auth_headers(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Get MEXC authentication headers."""
        signature = self.generate_signature(params)
        return {
            'X-MEXC-APIKEY': self.api_key,
            'signature': signature
        }
```

**Gate.io Authentication**:
```python
class GateioAuthenticationStrategy(AuthenticationStrategy):
    """Gate.io HMAC-SHA512 authentication."""
    
    def generate_signature(self, method: str, path: str, query: str, payload: str, timestamp: str) -> str:
        """Generate Gate.io signature from request components."""
        message = f"{method}\n{path}\n{query}\n{payload}\n{timestamp}"
        return hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
    
    def get_auth_headers(self, method: str, path: str, query: str, payload: str) -> Dict[str, str]:
        """Get Gate.io authentication headers."""
        timestamp = str(int(time.time()))
        signature = self.generate_signature(method, path, query, payload, timestamp)
        
        return {
            'KEY': self.api_key,
            'Timestamp': timestamp,
            'SIGN': signature
        }
```

## Configuration Management Pattern

### **Unified Configuration Structure**

Standardized configuration with exchange-specific extensions:

#### **Base Exchange Configuration**

```python
@msgspec.struct
class ExchangeConfig:
    """Base configuration for all exchange integrations."""
    name: str
    rest_url: str
    websocket_url: str
    network: NetworkConfig
    rate_limiting: RateLimitConfig
    performance: PerformanceConfig
    
    # Exchange-specific extensions
    custom_config: Optional[Dict[str, Any]] = None

@msgspec.struct
class NetworkConfig:
    """Network-related configuration."""
    timeout: float = 10.0
    max_retries: int = 3
    retry_delay: float = 1.0
    connection_pool_size: int = 10

@msgspec.struct
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_second: int = 10
    burst_allowance: int = 5
    orders_per_second: int = 5

@msgspec.struct
class PerformanceConfig:
    """Performance optimization settings."""
    enable_caching: bool = True
    enable_compression: bool = False
    enable_object_pooling: bool = True
    cache_ttl: float = 300.0
```

#### **Exchange-Specific Configuration Extensions**

**MEXC Configuration**:
```python
@msgspec.struct
class MexcCustomConfig:
    """MEXC-specific configuration extensions."""
    enable_protobuf: bool = True
    protobuf_message_size: int = 1024 * 1024  # 1MB
    object_pool_size: int = 500
    symbol_cache_size: int = 1000

def create_mexc_config() -> ExchangeConfig:
    """Create MEXC-specific configuration."""
    return ExchangeConfig(
        name="mexc_spot",
        rest_url="https://api.mexc.com",
        websocket_url="wss://wbs.mexc.com/ws",
        network=NetworkConfig(timeout=8.0, max_retries=2),
        rate_limiting=RateLimitConfig(requests_per_second=20),
        performance=PerformanceConfig(enable_compression=False),
        custom_config=msgspec.to_builtins(MexcCustomConfig())
    )
```

**Gate.io Configuration**:
```python
@msgspec.struct
class GateioCustomConfig:
    """Gate.io-specific configuration extensions."""
    enable_compression: bool = True
    custom_ping_interval: int = 20
    max_message_size: int = 2 * 1024 * 1024  # 2MB
    futures_enabled: bool = True

def create_gateio_config() -> ExchangeConfig:
    """Create Gate.io-specific configuration."""
    return ExchangeConfig(
        name="gateio_spot",
        rest_url="https://api.gateio.ws",
        websocket_url="wss://api.gateio.ws/ws/v4/",
        network=NetworkConfig(timeout=10.0, max_retries=3),
        rate_limiting=RateLimitConfig(requests_per_second=30),
        performance=PerformanceConfig(enable_compression=True),
        custom_config=msgspec.to_builtins(GateioCustomConfig())
    )
```

## Testing Patterns

### **Integration Testing Pattern**

Standardized testing approach for all exchange integrations:

#### **Base Integration Test**

```python
class BaseExchangeIntegrationTest(ABC):
    """Base test class for exchange integrations."""

    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name
        self.factory = FullExchangeFactory()
        self.test_symbols = [Symbol('BTC', 'USDT'), Symbol('ETH', 'USDT')]

    async def test_public_domain(self):
        """Test public domain functionality."""
        public_exchange = await self.factory.create_public_exchange(
            self.exchange_name, self.test_symbols
        )

        # Test market data endpoints
        symbols_info = await public_exchange.get_symbols_info()
        assert len(symbols_info) > 0

        orderbook = await public_exchange.get_orderbook(self.test_symbols[0])
        assert len(orderbook.bids) > 0 and len(orderbook.asks) > 0

        trades = await public_exchange.get_recent_trades(self.test_symbols[0])
        assert len(trades) > 0

    async def test_private_domain(self):
        """Test private domain functionality (requires credentials)."""
        if not self._has_credentials():
            pytest.skip("No credentials provided for private testing")

        private_exchange = await self.factory.create_private_exchange(self.exchange_name)

        # Test account endpoints
        balances = await private_exchange.get_balances()
        assert isinstance(balances, dict)

        # Test order placement (paper trading)
        order = await private_exchange.place_limit_order(
            self.test_symbols[0], Side.BUY, 0.001, 30000.0
        )
        assert order.order_id is not None

        # Clean up
        await private_exchange.cancel_order(self.test_symbols[0], order.order_id)

    @abstractmethod
    def _has_credentials(self) -> bool:
        """Check if test credentials are available."""
        pass

    @abstractmethod
    async def test_exchange_specific_features(self):
        """Test exchange-specific features."""
        pass
```

#### **Exchange-Specific Test Implementations**

**MEXC Integration Test**:
```python
class MexcIntegrationTest(BaseExchangeIntegrationTest):
    """MEXC-specific integration tests."""
    
    def __init__(self):
        super().__init__('mexc_spot')
    
    def _has_credentials(self) -> bool:
        return bool(os.getenv('MEXC_API_KEY') and os.getenv('MEXC_SECRET_KEY'))
    
    async def test_exchange_specific_features(self):
        """Test MEXC-specific features."""
        public_exchange = await self.factory.create_public_exchange(
            self.exchange_name, self.test_symbols
        )
        
        # Test Protocol Buffer support
        assert hasattr(public_exchange, '_protobuf_parser')
        
        # Test object pooling
        assert hasattr(public_exchange, '_entry_pool')
        pool_stats = public_exchange._entry_pool.get_stats()
        assert 'reuse_rate' in pool_stats
    
    async def test_protobuf_performance(self):
        """Test Protocol Buffer message processing performance."""
        # Create test protobuf message
        test_message = create_test_protobuf_orderbook()
        
        start_time = time.time()
        for _ in range(1000):
            parsed = await self._parse_protobuf_message(test_message)
        duration = time.time() - start_time
        
        # Should process 1000 messages in under 1 second
        assert duration < 1.0
        assert parsed is not None
```

### **Performance Benchmarking Pattern**

Standardized performance testing across exchanges:

#### **Performance Benchmark Suite**

```python
class ExchangePerformanceBenchmark:
    """Performance benchmark suite for exchange integrations."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name
        self.factory = FullExchangeFactory()
        self.test_symbols = [Symbol('BTC', 'USDT')]
    
    async def benchmark_rest_latency(self) -> Dict[str, float]:
        """Benchmark REST API latency."""
        public_exchange = await self.factory.create_public_exchange(
            self.exchange_name, self.test_symbols
        )
        
        # Warm up
        await public_exchange.get_orderbook(self.test_symbols[0])
        
        latencies = []
        for _ in range(10):
            start = time.time()
            await public_exchange.get_orderbook(self.test_symbols[0])
            latencies.append((time.time() - start) * 1000)  # Convert to ms
        
        return {
            'avg_latency_ms': sum(latencies) / len(latencies),
            'min_latency_ms': min(latencies),
            'max_latency_ms': max(latencies)
        }
    
    async def benchmark_symbol_conversion(self) -> Dict[str, float]:
        """Benchmark symbol conversion performance."""
        symbol_mapper = get_symbol_mapper(self.exchange_name)
        test_symbol = self.test_symbols[0]
        
        # Test symbol to string conversion
        start = time.time()
        for _ in range(10000):
            symbol_mapper.symbol_to_string(test_symbol)
        symbol_to_string_time = time.time() - start
        
        # Test string to symbol conversion
        test_string = symbol_mapper.symbol_to_string(test_symbol)
        start = time.time()
        for _ in range(10000):
            symbol_mapper.string_to_symbol(test_string)
        string_to_symbol_time = time.time() - start
        
        return {
            'symbol_to_string_us': (symbol_to_string_time / 10000) * 1000000,
            'string_to_symbol_us': (string_to_symbol_time / 10000) * 1000000
        }
    
    async def benchmark_websocket_throughput(self) -> Dict[str, int]:
        """Benchmark WebSocket message processing throughput."""
        # This would require setting up a mock WebSocket server
        # and measuring message processing rates
        pass
```

## Monitoring and Observability Patterns

### **Unified Metrics Collection**

Standardized metrics across all integrations:

#### **Exchange Metrics Collector**

```python
class ExchangeMetricsCollector:
    """Unified metrics collection for exchange integrations."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name
        self.metrics = {
            # Connection metrics
            'ws_connections_established': 0,
            'ws_connections_failed': 0,
            'ws_reconnections': 0,
            'rest_connections_created': 0,
            'rest_connection_reuse_rate': 0.0,
            
            # Performance metrics
            'rest_request_latency_ms': [],
            'ws_message_processing_latency_ms': [],
            'symbol_conversion_latency_us': [],
            
            # Error metrics
            'api_errors': 0,
            'rate_limit_errors': 0,
            'authentication_errors': 0,
            'connection_errors': 0,
            
            # Cache metrics
            'cache_hits': 0,
            'cache_misses': 0,
            'cache_hit_rate': 0.0,
            
            # Trading metrics
            'orders_placed': 0,
            'orders_cancelled': 0,
            'orders_filled': 0,
            'trade_executions': 0
        }
    
    def record_metric(self, metric_name: str, value: Union[int, float]):
        """Record a metric value."""
        if metric_name in self.metrics:
            if isinstance(self.metrics[metric_name], list):
                self.metrics[metric_name].append(value)
            else:
                self.metrics[metric_name] = value
    
    def increment_counter(self, metric_name: str, amount: int = 1):
        """Increment a counter metric."""
        if metric_name in self.metrics:
            self.metrics[metric_name] += amount
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for the exchange."""
        summary = {}
        
        # Calculate averages for latency metrics
        for metric_name, values in self.metrics.items():
            if isinstance(values, list) and values:
                if 'latency' in metric_name:
                    summary[f"{metric_name}_avg"] = sum(values) / len(values)
                    summary[f"{metric_name}_p95"] = self._calculate_percentile(values, 95)
                    summary[f"{metric_name}_p99"] = self._calculate_percentile(values, 99)
            else:
                summary[metric_name] = values
        
        # Calculate rates
        total_cache_requests = self.metrics['cache_hits'] + self.metrics['cache_misses']
        if total_cache_requests > 0:
            summary['cache_hit_rate'] = self.metrics['cache_hits'] / total_cache_requests
        
        return summary
    
    def _calculate_percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile value."""
        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * percentile / 100
        f = int(k)
        c = k - f
        
        if f + 1 < len(sorted_values):
            return sorted_values[f] + c * (sorted_values[f + 1] - sorted_values[f])
        else:
            return sorted_values[f]
```

## Integration Workflow Pattern

### **Standardized Integration Process**

Common workflow for adding new exchange integrations:

#### **Integration Checklist**

```python
class ExchangeIntegrationWorkflow:
    """Standardized workflow for new exchange integrations."""
    
    REQUIRED_COMPONENTS = [
        'composite_public_exchange',      # Public domain implementation
        'composite_private_exchange',     # Private domain implementation
        'public_rest_client',            # REST client for market data
        'private_rest_client',           # REST client for trading
        'public_websocket_client',       # WebSocket for market data
        'private_websocket_client',      # WebSocket for account data
        'symbol_mapper',                 # Symbol conversion service
        'error_classifier',              # Error handling service
        'connection_strategy',           # WebSocket connection strategy
        'retry_strategy',                # REST retry strategy
        'message_parser',                # Message parsing strategy
        'authentication_strategy',       # API authentication
        'configuration',                 # Exchange configuration
        'integration_tests',             # Test suite
        'performance_benchmarks'         # Performance tests
    ]
    
    def validate_integration(self, exchange_name: str) -> Dict[str, bool]:
        """Validate that all required components are implemented."""
        results = {}
        
        for component in self.REQUIRED_COMPONENTS:
            try:
                implementation = self._get_component_implementation(exchange_name, component)
                results[component] = implementation is not None
            except Exception as e:
                results[component] = False
                logger.warning(f"Component {component} validation failed: {e}")
        
        return results
    
    def _get_component_implementation(self, exchange_name: str, component: str) -> Optional[Any]:
        """Get component implementation for validation."""
        # Implementation would dynamically import and validate components
        pass
```

## Best Practices Summary

### **Architectural Guidelines**

1. **Separated Domain Architecture**: Always implement public and private domains separately
2. **Strategy Pattern Usage**: Use strategy patterns for connection, retry, parsing, and authentication
3. **HFT Safety**: Never cache real-time trading data (balances, orders, positions, orderbooks)
4. **Performance Optimization**: Implement object pooling, connection pooling, and intelligent caching
5. **Error Handling**: Use unified exception types with exchange-specific error mapping
6. **Configuration Management**: Use structured configuration with exchange-specific extensions
7. **Testing Coverage**: Implement comprehensive integration tests and performance benchmarks
8. **Monitoring**: Collect standardized metrics for observability and debugging

### **Implementation Guidelines**

1. **Symbol Mapping**: Use cached symbol conversion for performance
2. **WebSocket Handling**: Implement exchange-specific connection strategies
3. **Authentication**: Use appropriate signature generation for each exchange
4. **Message Parsing**: Support both JSON and binary formats where applicable
5. **Retry Logic**: Implement exchange-specific retry strategies
6. **Resource Management**: Use connection pooling and proper cleanup
7. **Documentation**: Maintain comprehensive specifications for each integration

### **Performance Targets**

- **REST API Latency**: <15ms for market data requests
- **WebSocket Processing**: <2ms per message
- **Symbol Conversion**: <1μs with caching
- **Connection Reuse**: >95% for REST connections
- **Cache Hit Rate**: >90% for static data
- **Object Pool Efficiency**: >75% allocation reduction

This common patterns specification provides the foundation for consistent, high-performance exchange integrations across the CEX arbitrage engine.