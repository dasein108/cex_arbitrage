# Exchange Integration Workflow

## Overview

The CEX Arbitrage Engine's **unified configuration architecture** enables seamless addition of new exchanges through a **standardized integration workflow** that requires **minimal code changes** and **maximum reusability**.

## Integration Architecture

### Unified Integration Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                  EXCHANGE INTEGRATION FLOW                      │
└─────────────────────────────────────────────────────────────────┘

1. Configuration Entry (config.yaml - exchanges: dictionary)
                    ↓
2. Environment Variables (.env file with credentials)
                    ↓
3. Exchange Implementation (BaseExchangeInterface)
                    ↓
4. Factory Registration (ExchangeFactory.EXCHANGE_CLASSES)
                    ↓
5. Testing & Validation (automated integration tests)
                    ↓
6. Production Deployment (zero downtime integration)
```

## Step-by-Step Integration Process

### Step 1: Configuration Entry

**Add to config.yaml under exchanges: dictionary**:
```yaml
exchanges:
  # Existing cex
  mexc:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
    base_url: "https://api.mexc.com"
    
  gateio:
    api_key: "${GATEIO_API_KEY}" 
    secret_key: "${GATEIO_SECRET_KEY}"
    base_url: "https://api.gateio.ws/api/v4"
  
  # NEW EXCHANGE - Standard pattern
  binance:
    api_key: "${BINANCE_API_KEY}"
    secret_key: "${BINANCE_SECRET_KEY}"
    base_url: "https://api.binance.com"
    websocket_url: "wss://stream.binance.com:9443/ws"
    testnet_base_url: "https://testnet.binance.vision"  # Optional
    rate_limit_per_second: 20  # Optional override
    
  kraken:
    api_key: "${KRAKEN_API_KEY}" 
    secret_key: "${KRAKEN_SECRET_KEY}"
    base_url: "https://api.kraken.com"
    websocket_url: "wss://ws.kraken.com"
    # Exchange-specific settings
    api_version: "0"
    private_endpoint_base: "/0/private"
```

**Benefits of Unified Structure**:
- **Consistent pattern** across all exchanges
- **Environment variable integration** automatically handled
- **Exchange-specific settings** supported within unified structure
- **No code changes required** for basic configuration

### Step 2: Environment Variables

**Add to .env file**:
```bash
# Existing exchange credentials
MEXC_API_KEY=your_mexc_api_key
MEXC_SECRET_KEY=your_mexc_secret_key
GATEIO_API_KEY=your_gateio_api_key  
GATEIO_SECRET_KEY=your_gateio_secret_key

# NEW EXCHANGE CREDENTIALS - Standard pattern
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key

KRAKEN_API_KEY=your_kraken_api_key
KRAKEN_SECRET_KEY=your_kraken_secret_key
```

**Automatic Integration**:
- **Dynamic credential resolution** via `config.get_exchange_credentials('binance')`
- **Unified validation** through existing validation methods
- **Secure logging** with credential preview (e.g., "abc1...xyz9")
- **Public-only mode** if credentials not provided

### Step 3: Exchange Implementation

**CRITICAL: All exchange implementations must inherit from `BaseExchangeInterface`**

**Create exchange implementation following composition pattern**:

```python
# src/cex/binance/binance_exchange.py
from core.cex.base import BaseExchangeInterface
from structs import (
    Symbol, SymbolInfo, OrderBook, AssetBalance, ExchangeStatus, Order
)


class BinanceExchange(BaseExchangeInterface):
    """
    Binance Exchange Implementation using Composition Pattern.
    
    MUST inherit from BaseExchangeInterface - NOT WebSocketExchange or other classes.
    
    Architecture:
    - Delegates public market data operations to BinancePublicExchange
    - Delegates private trading operations to BinancePrivateExchange  
    - Manages WebSocket streaming for real-time data
    - Coordinates between public and private operations
    
    HFT Compliance:
    - No caching of real-time trading data (balances, orders, trades)
    - Real-time streaming orderbook data only
    - Fresh API calls for all trading operations
    """

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        # REQUIRED: Call parent constructor with exchange name
        super().__init__('BINANCE', api_key, secret_key)

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Composition pattern - delegate to specialized components
        self._public_api: Optional[BinancePublicExchange] = None
        self._private_api: Optional[BinancePrivateExchange] = None
        self._ws_client: Optional[BinanceWebsocketPublic] = None

    @property
    def status(self) -> ExchangeStatus:
        """REQUIRED: Implement status property"""
        # Implementation logic here
        pass

    @property
    def orderbook(self) -> OrderBook:
        """REQUIRED: Implement orderbook property"""
        # Return current streaming orderbook data
        pass

    @property
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """REQUIRED: Implement balances property"""
        # HFT COMPLIANT: Fresh API call, no caching
        pass

    @property
    def symbol_info(self) -> Dict[Symbol, SymbolInfo]:
        """REQUIRED: Implement symbol_info property"""
        # Static data - safe to cache
        pass

    @property
    def active_symbols(self) -> List[Symbol]:
        """REQUIRED: Implement active_symbols property"""
        pass

    @property
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """REQUIRED: Implement open_orders property"""
        # HFT COMPLIANT: Fresh API call, no caching
        pass

    async def init(self, symbols: List[Symbol] = None) -> None:
        """REQUIRED: Implement initialization"""
        pass

    async def add_symbol(self, symbol: Symbol) -> None:
        """REQUIRED: Implement symbol addition"""
        pass

    async def remove_symbol(self, symbol: Symbol) -> None:
        """REQUIRED: Implement symbol removal"""
        pass
```

**Key Implementation Rules**:
1. **MUST inherit from BaseExchangeInterface** - Not WebSocketExchange or other classes
2. **MUST implement ALL abstract methods** - No partial implementations allowed
3. **Use composition pattern** - Delegate to specialized REST/WebSocket components  
4. **HFT compliance mandatory** - No caching of real-time trading data
5. **Use unified data structures** - Only `Symbol`, `SymbolInfo`, etc. from `exchanges.interface.structs`

### Step 4: Factory Registration

**Add to ExchangeFactory.EXCHANGE_CLASSES**:
```python
# src/arbitrage/exchange_factory.py

class ExchangeFactory:
    """Factory for creating and managing exchange instances"""
    
    # EXCHANGE CLASS REGISTRY - Add new cex here
    EXCHANGE_CLASSES: Dict[str, Type[BaseExchangeInterface]] = {
        'MEXC': MexcExchange,
        'GATEIO': GateioExchange,
        'BINANCE': BinanceExchange,      # <- NEW EXCHANGE
        'KRAKEN': KrakenExchange,        # <- ANOTHER NEW EXCHANGE
    }
```

**That's it!** The unified configuration system handles:
- **Dynamic credential loading** via `config.get_exchange_credentials('binance')`
- **Configuration validation** through existing validation methods  
- **Initialization orchestration** via existing factory methods
- **Error handling and retry logic** through established patterns

### Step 5: Testing & Validation

**Integration Test Template**:

```python
# tests/test_binance_integration.py

import pytest
from exchanges.binance.binance_exchange import BinanceExchange
from structs import Symbol, AssetName
from core.config.config import config


@pytest.mark.asyncio
async def test_binance_initialization():
    """Test Binance exchange initialization"""

    # Test symbols
    symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
    ]

    # Initialize exchange
    exchange = BinanceExchange()
    await exchange.initialize(symbols)

    # Validate initialization
    assert exchange.status == ExchangeStatus.ACTIVE
    assert len(exchange.active_symbols) > 0

    # Test configuration integration
    binance_config = config.get_exchange_config('binance')
    assert 'base_url' in binance_config

    await exchange.close()


@pytest.mark.asyncio
async def test_binance_with_credentials():
    """Test Binance with private credentials"""

    credentials = config.get_exchange_credentials('binance')
    if credentials['api_key'] and credentials['secret_key']:
        exchange = BinanceExchange(
            api_key=credentials['api_key'],
            secret_key=credentials['secret_key']
        )

        assert exchange.has_private == True
        await exchange.close()
    else:
        pytest.skip("Binance credentials not configured")


@pytest.mark.asyncio
async def test_binance_factory_integration():
    """Test integration with ExchangeFactory"""

    from arbitrage.exchange_factory import ExchangeFactory

    factory = ExchangeFactory()

    # Test exchange creation through factory
    exchange = await factory.create_exchange('BINANCE')
    assert isinstance(exchange, BinanceExchange)
    assert exchange.status == ExchangeStatus.ACTIVE

    await factory.close_all()
```

**Automated Validation**:
- **Interface compliance testing** ensures proper implementation
- **Configuration integration testing** validates unified config system
- **Factory pattern testing** confirms seamless integration
- **Credential handling testing** verifies security patterns

### Step 6: Arbitrage Configuration

**Add to arbitrage pairs configuration**:
```yaml
arbitrage:
  enabled_exchanges:
    - "MEXC"
    - "GATEIO" 
    - "BINANCE"      # <- Enable new exchange
    
  arbitrage_pairs:
    - id: "btc_usdt_tri_arb"
      base_asset: "BTC"
      quote_asset: "USDT"
      opportunity_type: "SPOT_SPOT"
      min_profit_bps: 25
      exchanges:        # Optional: specify which cex
        - "MEXC"
        - "GATEIO"
        - "BINANCE"    # <- Include new exchange
      is_enabled: true
```

**Automatic Integration**:
- **Symbol auto-discovery** from new exchange
- **Precision data fetching** for accurate trading
- **Arbitrage opportunity detection** across all exchanges including new one
- **Risk management** applied consistently

## Advanced Integration Patterns

### Custom Exchange Configuration

**Exchange-Specific Settings**:
```yaml
exchanges:
  advanced_exchange:
    api_key: "${ADVANCED_API_KEY}"
    secret_key: "${ADVANCED_SECRET_KEY}"
    base_url: "https://api.advanced-exchange.com"
    
    # Custom settings specific to this exchange
    api_version: "v2"
    rate_limit_per_second: 10
    request_timeout: 15.0
    max_retries: 5
    
    # Trading-specific settings
    order_types: ["limit", "market", "stop_loss"]
    supports_websocket: true
    supports_margin: false
    
    # HFT optimization settings
    connection_pool_size: 20
    enable_http2: true
    custom_headers:
      "X-Custom-Header": "arbitrage-engine"
```

**Access in Implementation**:
```python
class AdvancedExchange(BaseExchangeInterface):
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        super().__init__()
        
        # Get exchange-specific configuration
        config = config.get_exchange_config('advanced_exchange')
        
        self.api_version = config.get('api_version', 'v1')
        self.order_types = config.get('order_types', ['limit', 'market'])
        self.supports_margin = config.get('supports_margin', False)
        
        # Custom REST client with exchange-specific settings
        self.rest_client = RestClient(
            base_url=config['base_url'],
            rate_limit=config.get('rate_limit_per_second', 10),
            timeout=config.get('request_timeout', 10.0),
            max_retries=config.get('max_retries', 3),
            custom_headers=config.get('custom_headers', {})
        )
```

### WebSocket Integration Pattern

**WebSocket Configuration**:
```yaml
exchanges:
  websocket_exchange:
    api_key: "${WS_EXCHANGE_API_KEY}"
    secret_key: "${WS_EXCHANGE_SECRET_KEY}"
    base_url: "https://api.ws-exchange.com"
    websocket_url: "wss://stream.ws-exchange.com/ws"
    
    # WebSocket-specific settings
    websocket_config:
      heartbeat_interval: 30
      reconnect_attempts: 10
      compression: true
      buffer_size: 8192
```

**WebSocket Implementation**:
```python
from common.websocket_client import WebSocketClient

class WebSocketExchange(BaseExchangeInterface):
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        super().__init__()
        
        config = config.get_exchange_config('websocket_exchange')
        ws_config = config.get('websocket_config', {})
        
        # Initialize WebSocket client with exchange-specific settings
        self.ws_client = WebSocketClient(
            url=config['websocket_url'],
            heartbeat_interval=ws_config.get('heartbeat_interval', 30),
            max_reconnect_attempts=ws_config.get('reconnect_attempts', 10)
        )
    
    async def subscribe_to_orderbook(self, symbol: Symbol) -> None:
        """Subscribe to real-time orderbook updates"""
        message = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol.base}{symbol.quote}@depth"],
            "id": 1
        }
        await self.ws_client.send_message(message)
```

## Integration Best Practices

### 1. Configuration Standards

**Mandatory Fields**:
```yaml
exchanges:
  new_exchange:
    api_key: "${NEW_EXCHANGE_API_KEY}"           # Required
    secret_key: "${NEW_EXCHANGE_SECRET_KEY}"     # Required  
    base_url: "https://api.new-exchange.com"     # Required
```

**Recommended Fields**:
```yaml
exchanges:
  new_exchange:
    # ... mandatory fields ...
    websocket_url: "wss://ws.new-exchange.com"   # For real-time data
    testnet_base_url: "https://testnet.new-exchange.com"  # For testing
    rate_limit_per_second: 20                    # Exchange-specific limit
    request_timeout: 10.0                        # Custom timeout
```

### 2. Error Handling Patterns

**Standardized Error Handling**:

```python
from core.exceptions.exchange import BaseExchangeError, ConfigurationError


class NewExchange(BaseExchangeInterface):
    async def init(self, symbols: List[Symbol]) -> None:
        try:
            # Exchange initialization logic
            await self._initialize_exchange()
            self._status = ExchangeStatus.ACTIVE

        except ConnectionError as e:
            self._status = ExchangeStatus.ERROR
            raise BaseExchangeError(503, f"Connection failed: {e}")

        except ValueError as e:
            self._status = ExchangeStatus.ERROR
            raise ConfigurationError(f"Configuration error: {e}")

        except Exception as e:
            self._status = ExchangeStatus.ERROR
            raise BaseExchangeError(500, f"Initialization failed: {e}")
```

### 3. Performance Optimization

**HFT-Compliant Implementation**:
```python
class OptimizedExchange(BaseExchangeInterface):
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        super().__init__()
        
        # Pre-compute frequently used values
        self._symbol_cache = {}
        self._precision_cache = {}
        
        # Optimize connection settings for HFT
        config = config.get_exchange_config('optimized_exchange')
        self.rest_client = RestClient(
            base_url=config['base_url'],
            connection_pool_size=20,    # More concurrent connections
            tcp_keepalive=True,         # Maintain connections
            request_timeout=5.0         # Aggressive timeout for HFT
        )
    
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> Dict[str, Any]:
        """HFT-optimized orderbook retrieval"""
        
        # Use pre-computed symbol format
        exchange_symbol = self._get_cached_symbol_format(symbol)
        
        # Single API call with minimal processing
        response = await self.rest_client.get(
            '/orderbook',
            {'symbol': exchange_symbol, 'limit': limit}
        )
        
        return response  # Return raw data for zero-copy processing
    
    def _get_cached_symbol_format(self, symbol: Symbol) -> str:
        """O(1) symbol format conversion"""
        if symbol not in self._symbol_cache:
            self._symbol_cache[symbol] = f"{symbol.base}{symbol.quote}"
        return self._symbol_cache[symbol]
```

## Testing New Integrations

### Integration Test Checklist

**Functionality Tests**:
- [ ] Exchange initialization with and without credentials
- [ ] Symbol information retrieval and parsing
- [ ] Orderbook data fetching
- [ ] Configuration integration via unified config system
- [ ] Factory pattern integration
- [ ] Error handling for various failure scenarios

**Performance Tests**:
- [ ] Initialization time under 10 seconds
- [ ] Symbol resolution under 100ms
- [ ] Orderbook retrieval under 500ms  
- [ ] Memory usage within acceptable limits
- [ ] Connection cleanup on shutdown

**Integration Tests**:
- [ ] Multi-exchange arbitrage opportunity detection
- [ ] Symbol resolution across exchanges
- [ ] Configuration validation with new exchange
- [ ] Graceful handling when exchange unavailable

### Automated Testing Command

```bash
# Run integration tests for new exchange
PYTHONPATH=src pytest tests/cex/test_new_exchange_integration.py -v

# Run full system test with new exchange
PYTHONPATH=src python src/main.py --log-level DEBUG --dry-run

# Test with live credentials (if available)
NEW_EXCHANGE_API_KEY=test_key NEW_EXCHANGE_SECRET_KEY=test_secret \
PYTHONPATH=src python src/main.py --live --log-level INFO
```

---

*This integration workflow enables rapid addition of new exchanges while maintaining system integrity, performance, and the unified configuration architecture.*