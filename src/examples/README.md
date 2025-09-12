# Usage Examples and Testing Patterns

Comprehensive examples demonstrating usage patterns, testing approaches, and best practices for the HFT arbitrage engine.

## Overview

The `src/examples/` directory contains practical examples showing how to:

- **Public API Integration** - Market data retrieval and validation
- **Private API Integration** - Account management and trading operations  
- **WebSocket Streaming** - Real-time data processing patterns
- **Testing Patterns** - Integration testing and API validation
- **Production Usage** - Complete trading workflows

## Examples Structure

```
src/examples/
└── mexc/
    ├── public_rest_checks.py      # Public API validation
    ├── private_rest_checks.py     # Private API and trading validation
    ├── ws_public_simple_check.py  # WebSocket market data streaming
    └── ws_private_simple_check.py # WebSocket account data streaming
```

## Public API Examples

### Market Data Retrieval (`mexc/public_rest_checks.py`)

Complete validation of MEXC public API endpoints.

#### Key Features
- **Connectivity testing** - Ping and server time verification
- **Exchange information** - Trading rules and symbol discovery
- **Market data access** - Order books, recent trades, tickers
- **Error handling patterns** - Comprehensive exception management

#### Usage Example
```python
"""MEXC Public API Integration Check"""
import asyncio
from exchanges.interface.structs import Symbol, AssetName
from exchanges.mexc.rest.mexc_public import MexcPublicExchange

async def main():
    exchange = MexcPublicExchange()
    
    # Test connectivity
    is_connected = await exchange.ping()
    print(f"Exchange connected: {is_connected}")
    
    # Get server time
    server_time = await exchange.get_server_time()
    print(f"Server time: {server_time}")
    
    # Get exchange information
    exchange_info = await exchange.get_exchange_info()
    print(f"Available symbols: {len(exchange_info)}")
    
    # Get orderbook for BTC/USDT
    btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    orderbook = await exchange.get_orderbook(btc_usdt, limit=10)
    
    print(f"Best bid: {orderbook.bids[0].price}")
    print(f"Best ask: {orderbook.asks[0].price}")
    print(f"Spread: {orderbook.asks[0].price - orderbook.bids[0].price}")
    
    # Get recent trades
    trades = await exchange.get_recent_trades(btc_usdt, limit=5)
    print(f"Recent trades: {len(trades)}")
    for trade in trades[:3]:
        print(f"  {trade.side.name}: {trade.amount} @ {trade.price}")

if __name__ == "__main__":
    asyncio.run(main())
```

#### API Validation Pattern
```python
async def check_ping(exchange: MexcPublicExchange):
    """Validate connectivity with error handling"""
    print("=== PING CHECK ===")
    try:
        result = await exchange.ping()
        print(f"✓ Connection successful: {result}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False
    return True

async def check_exchange_info(exchange: MexcPublicExchange):
    """Validate exchange information retrieval"""
    print("=== EXCHANGE INFO CHECK ===")
    try:
        info = await exchange.get_exchange_info()
        print(f"✓ Retrieved info for {len(info)} symbols")
        
        # Validate specific symbol
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        if btc_usdt in info:
            symbol_info = info[btc_usdt]
            print(f"  BTC/USDT precision: {symbol_info.base_precision}/{symbol_info.quote_precision}")
            print(f"  Min amounts: {symbol_info.min_base_amount}/{symbol_info.min_quote_amount}")
        
    except Exception as e:
        print(f"✗ Exchange info failed: {e}")
        return False
    return True
```

## Private API Examples

### Trading Operations (`mexc/private_rest_checks.py`)

Complete validation of MEXC private API and trading functionality.

#### Key Features
- **Authentication verification** - API key and signature validation
- **Account management** - Balance queries and asset management
- **Order operations** - Placement, cancellation, status queries
- **Error handling** - Trading-specific exception management

#### Usage Example
```python
"""MEXC Private API Integration Check"""
import asyncio
from exchanges.interface.structs import Symbol, AssetName, Side, OrderType, TimeInForce
from exchanges.mexc.rest.mexc_private import MexcPrivateExchange

async def main():
    # Initialize with credentials
    exchange = MexcPrivateExchange(
        api_key="your_mexc_api_key",
        secret_key="your_mexc_secret_key"
    )
    
    try:
        # Get account balances
        balances = await exchange.get_account_balance()
        print(f"Account has {len(balances)} assets with non-zero balance")
        
        # Check specific asset balance
        usdt_balance = await exchange.get_asset_balance(AssetName("USDT"))
        if usdt_balance:
            print(f"USDT balance: {usdt_balance.free} free, {usdt_balance.locked} locked")
        
        # Get open orders
        open_orders = await exchange.get_open_orders()
        print(f"Open orders: {len(open_orders)}")
        
        # Example: Place a limit order (use testnet for real testing)
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        # WARNING: This places a real order - use testnet!
        order = await exchange.place_order(
            symbol=btc_usdt,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            amount=0.001,  # 0.001 BTC
            price=30000.0,  # Well below market for safety
            time_in_force=TimeInForce.GTC
        )
        
        print(f"Order placed: {order.order_id}")
        print(f"Status: {order.status.name}")
        
        # Query order status
        order_status = await exchange.get_order(btc_usdt, order.order_id)
        print(f"Order status: {order_status.status.name}")
        
        # Cancel the order
        cancelled_order = await exchange.cancel_order(btc_usdt, order.order_id)
        print(f"Order cancelled: {cancelled_order.status.name}")
        
    finally:
        # Clean up connections
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
```

#### Trading Safety Patterns
```python
async def safe_order_placement(exchange, symbol, side, amount, price):
    """Safe order placement with validation and cleanup"""
    
    # Pre-flight checks
    balance = await exchange.get_asset_balance(
        symbol.quote if side == Side.BUY else symbol.base
    )
    
    required_amount = amount * price if side == Side.BUY else amount
    if balance.free < required_amount:
        raise ValueError(f"Insufficient balance: need {required_amount}, have {balance.free}")
    
    # Place order with error handling
    try:
        order = await exchange.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            amount=amount,
            price=price,
            time_in_force=TimeInForce.GTC
        )
        
        print(f"Order placed successfully: {order.order_id}")
        return order
        
    except RateLimitError as e:
        print(f"Rate limited, retry after {e.retry_after} seconds")
        raise
    except TradingDisabled as e:
        print(f"Trading disabled: {e.message}")
        raise
    except ExchangeAPIError as e:
        print(f"API error: {e.code} - {e.message}")
        raise
```

## WebSocket Examples

### Real-Time Market Data (`mexc/ws_public_simple_check.py`)

Complete WebSocket integration for real-time market data streaming.

#### Key Features
- **Connection management** - Automatic connection and reconnection
- **Subscription handling** - Dynamic symbol subscription/unsubscription
- **Data processing** - Order book and trade data handling
- **Performance monitoring** - Message processing statistics

#### Usage Example
```python
"""MEXC Public WebSocket Integration"""
import asyncio
import logging
from typing import Dict, List
from exchanges.interface.structs import Symbol, AssetName, OrderBook, Trade
from exchanges.mexc.ws.mexc_ws_public import MexcWebsocketPublic
from common.ws_client import WebSocketConfig

class MarketDataManager:
    """Manage real-time market data from WebSocket"""
    
    def __init__(self):
        self.orderbooks: Dict[Symbol, OrderBook] = {}
        self.trade_history: Dict[Symbol, List[Trade]] = {}
        self.message_count = 0
    
    async def handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Process order book updates"""
        self.orderbooks[symbol] = orderbook
        self.message_count += 1
        
        # Display top of book
        if orderbook.bids and orderbook.asks:
            spread = orderbook.asks[0].price - orderbook.bids[0].price
            print(f"{symbol.base}/{symbol.quote}: "
                  f"Bid {orderbook.bids[0].price}, "
                  f"Ask {orderbook.asks[0].price}, "
                  f"Spread {spread:.2f}")
    
    async def handle_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """Process trade updates"""
        if symbol not in self.trade_history:
            self.trade_history[symbol] = []
        
        self.trade_history[symbol].extend(trades)
        # Keep only recent trades (memory management)
        self.trade_history[symbol] = self.trade_history[symbol][-1000:]
        
        # Display recent trades
        for trade in trades[-3:]:
            print(f"{symbol.base}/{symbol.quote} Trade: "
                  f"{trade.side.name} {trade.amount} @ {trade.price}")

async def main():
    # Set up market data manager
    manager = MarketDataManager()
    
    # Configure WebSocket
    config = WebSocketConfig(
        name="mexc_market_data",
        url="wss://wbs.mexc.com/ws",
        timeout=30.0,
        ping_interval=20.0,
        max_reconnect_attempts=10
    )
    
    # Initialize WebSocket client
    ws_client = MexcWebsocketPublic(
        config=config,
        orderbook_handler=manager.handle_orderbook_update,
        trades_handler=manager.handle_trades_update
    )
    
    # Define symbols to track
    symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
    ]
    
    try:
        # Start WebSocket connection
        await ws_client.init(symbols)
        print("WebSocket connected, streaming market data...")
        print("Press Ctrl+C to stop")
        
        # Monitor for 30 seconds
        await asyncio.sleep(30)
        
        # Display statistics
        print(f"\nStatistics:")
        print(f"Messages received: {manager.message_count}")
        print(f"Symbols tracked: {len(manager.orderbooks)}")
        for symbol, orderbook in manager.orderbooks.items():
            trade_count = len(manager.trade_history.get(symbol, []))
            print(f"  {symbol.base}/{symbol.quote}: "
                  f"{len(orderbook.bids)} bids, {len(orderbook.asks)} asks, "
                  f"{trade_count} trades")
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up
        await ws_client.ws_client.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

#### WebSocket Error Handling
```python
class RobustWebSocketManager:
    """WebSocket manager with comprehensive error handling"""
    
    def __init__(self):
        self.reconnect_count = 0
        self.last_message_time = time.time()
    
    async def handle_error(self, error: Exception):
        """Handle WebSocket errors with recovery logic"""
        self.reconnect_count += 1
        
        if isinstance(error, ConnectionError):
            print(f"Connection error #{self.reconnect_count}: {error}")
            if self.reconnect_count < 5:
                print("Will attempt reconnection...")
            else:
                print("Max reconnections exceeded, stopping...")
                return False
                
        elif isinstance(error, TimeoutError):
            print(f"Timeout error: {error}")
            # Check if we're receiving messages
            if time.time() - self.last_message_time > 60:
                print("No messages for 60 seconds, forcing reconnection")
                return False
        
        return True
    
    async def handle_message(self, message):
        """Process messages with heartbeat tracking"""
        self.last_message_time = time.time()
        self.reconnect_count = 0  # Reset on successful message
        
        # Process message...
        await self.process_message(message)
```

## Testing Patterns

### Integration Testing Framework

#### API Validation Testing
```python
import pytest
from exchanges.mexc.rest.mexc_public import MexcPublicExchange
from exchanges.interface.structs import Symbol, AssetName

class TestMexcPublicAPI:
    """Comprehensive API integration tests"""
    
    @pytest.fixture
    async def exchange(self):
        """Create exchange instance for testing"""
        exchange = MexcPublicExchange()
        yield exchange
        # Cleanup after test
        await exchange.client.close()
    
    @pytest.mark.asyncio
    async def test_connectivity(self, exchange):
        """Test basic connectivity"""
        result = await exchange.ping()
        assert result is True
        
        server_time = await exchange.get_server_time()
        assert isinstance(server_time, int)
        assert server_time > 0
    
    @pytest.mark.asyncio
    async def test_exchange_info(self, exchange):
        """Test exchange information retrieval"""
        info = await exchange.get_exchange_info()
        assert len(info) > 0
        
        # Check for common trading pairs
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        assert btc_usdt in info
        
        symbol_info = info[btc_usdt]
        assert symbol_info.base_precision > 0
        assert symbol_info.quote_precision > 0
    
    @pytest.mark.asyncio
    async def test_orderbook_retrieval(self, exchange):
        """Test order book data retrieval"""
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        orderbook = await exchange.get_orderbook(btc_usdt, limit=10)
        
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0
        assert orderbook.bids[0].price < orderbook.asks[0].price
        assert orderbook.timestamp > 0
    
    @pytest.mark.asyncio 
    async def test_performance_requirements(self, exchange):
        """Verify performance meets HFT requirements"""
        import time
        
        # Test latency requirement (<50ms)
        start_time = time.time()
        await exchange.ping()
        latency = (time.time() - start_time) * 1000
        assert latency < 50, f"Latency {latency}ms exceeds 50ms requirement"
        
        # Test orderbook retrieval speed
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        start_time = time.time()
        orderbook = await exchange.get_orderbook(btc_usdt)
        latency = (time.time() - start_time) * 1000
        assert latency < 100, f"Orderbook latency {latency}ms too high"
```

#### WebSocket Testing
```python
class TestMexcWebSocket:
    """WebSocket integration testing"""
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """Test WebSocket connection and basic functionality"""
        
        message_received = asyncio.Event()
        received_messages = []
        
        async def message_handler(message):
            received_messages.append(message)
            message_received.set()
        
        config = WebSocketConfig(name="test", url="wss://wbs.mexc.com/ws")
        ws_client = MexcWebsocketPublic(
            config=config,
            orderbook_handler=message_handler
        )
        
        try:
            # Start connection
            symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
            await ws_client.init(symbols)
            
            # Wait for first message (max 30 seconds)
            await asyncio.wait_for(message_received.wait(), timeout=30.0)
            
            assert len(received_messages) > 0
            print(f"Received {len(received_messages)} messages")
            
        finally:
            await ws_client.ws_client.stop()
```

### Performance Testing

#### Latency Benchmarks
```python
async def benchmark_api_latency():
    """Benchmark API call latencies"""
    exchange = MexcPublicExchange()
    symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    # Warm up connection
    await exchange.ping()
    
    # Benchmark different endpoints
    endpoints = {
        'ping': lambda: exchange.ping(),
        'server_time': lambda: exchange.get_server_time(),
        'orderbook': lambda: exchange.get_orderbook(symbol, limit=10),
        'trades': lambda: exchange.get_recent_trades(symbol, limit=10)
    }
    
    results = {}
    for name, endpoint in endpoints.items():
        latencies = []
        
        for _ in range(10):  # 10 samples
            start = time.time()
            await endpoint()
            latency = (time.time() - start) * 1000  # Convert to ms
            latencies.append(latency)
            await asyncio.sleep(0.1)  # Rate limiting
        
        results[name] = {
            'avg': sum(latencies) / len(latencies),
            'min': min(latencies),
            'max': max(latencies),
            'p95': sorted(latencies)[int(0.95 * len(latencies))]
        }
    
    # Display results
    print("API Latency Benchmarks:")
    for endpoint, stats in results.items():
        print(f"{endpoint:12}: avg={stats['avg']:5.1f}ms, "
              f"min={stats['min']:5.1f}ms, max={stats['max']:5.1f}ms, "
              f"p95={stats['p95']:5.1f}ms")
    
    await exchange.client.close()
```

#### Memory Usage Monitoring
```python
import psutil
import tracemalloc

async def monitor_memory_usage():
    """Monitor memory usage during operation"""
    
    # Start memory tracing
    tracemalloc.start()
    process = psutil.Process()
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    exchange = MexcExchange()
    
    try:
        # Initialize with multiple symbols
        symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
            Symbol(base=AssetName("BNB"), quote=AssetName("USDT")),
        ]
        
        async with exchange.session(symbols) as mexc:
            # Simulate heavy usage
            for i in range(100):
                orderbook = mexc.orderbook
                balances = await mexc.get_fresh_balances()
                
                if i % 10 == 0:
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_growth = current_memory - initial_memory
                    print(f"Iteration {i}: Memory usage: {current_memory:.1f}MB "
                          f"(+{memory_growth:.1f}MB)")
                
                await asyncio.sleep(0.1)
        
        # Final memory check
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory
        
        print(f"\nMemory Usage Summary:")
        print(f"Initial: {initial_memory:.1f}MB")
        print(f"Final: {final_memory:.1f}MB") 
        print(f"Growth: {memory_growth:.1f}MB")
        
        # Get top memory allocations
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')[:10]
        
        print("\nTop 10 memory allocations:")
        for stat in top_stats:
            print(f"{stat.size / 1024:.1f}KB: {stat}")
    
    finally:
        tracemalloc.stop()
```

## Best Practices

### Configuration Management
```python
# Use environment-based configuration
import os
from dataclasses import dataclass

@dataclass
class TradingConfig:
    """Trading configuration with environment fallbacks"""
    mexc_api_key: str = os.getenv('MEXC_API_KEY', '')
    mexc_secret_key: str = os.getenv('MEXC_SECRET_KEY', '')
    max_order_size: float = float(os.getenv('MAX_ORDER_SIZE', '0.01'))
    max_spread_pct: float = float(os.getenv('MAX_SPREAD_PCT', '0.5'))
    trading_enabled: bool = os.getenv('TRADING_ENABLED', 'false').lower() == 'true'

# Validate configuration
config = TradingConfig()
if not config.mexc_api_key or not config.mexc_secret_key:
    raise ValueError("MEXC API credentials not configured")
```

### Error Handling Patterns
```python
async def robust_trading_operation(exchange, operation_func, *args, **kwargs):
    """Execute trading operation with comprehensive error handling"""
    
    max_retries = 3
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            return await operation_func(*args, **kwargs)
            
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            delay = e.retry_after or (base_delay * (2 ** attempt))
            print(f"Rate limited, waiting {delay} seconds...")
            await asyncio.sleep(delay)
            
        except TradingDisabled as e:
            print(f"Trading disabled: {e.message}")
            raise  # Don't retry trading disabled errors
            
        except ExchangeAPIError as e:
            if e.code >= 500 and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Server error, retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                raise
                
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise
```

### Resource Management
```python
import contextlib

@contextlib.asynccontextmanager
async def trading_session(api_key, secret_key, symbols):
    """Managed trading session with proper cleanup"""
    
    exchange = MexcExchange(api_key=api_key, secret_key=secret_key)
    
    try:
        # Initialize exchange
        await exchange.init(symbols)
        print(f"Trading session started with {len(symbols)} symbols")
        
        # Yield exchange for use
        yield exchange
        
    except Exception as e:
        print(f"Error in trading session: {e}")
        raise
    finally:
        # Ensure cleanup
        try:
            await exchange.close()
            print("Trading session closed")
        except Exception as e:
            print(f"Error closing session: {e}")

# Usage
async def main():
    symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
    
    async with trading_session(api_key, secret_key, symbols) as exchange:
        # Trading operations
        orderbook = exchange.orderbook
        # ... other operations
```

## Production Deployment Examples

### High-Availability Configuration
```python
async def create_resilient_exchange(config):
    """Create exchange with high-availability configuration"""
    
    # Configure with production settings
    exchange = MexcExchange(
        api_key=config.api_key,
        secret_key=config.secret_key
    )
    
    # Set up health monitoring
    async def health_check():
        try:
            return await exchange._rest_public.ping()
        except Exception:
            return False
    
    # Set up automatic reconnection
    async def ensure_connection():
        while True:
            if not await health_check():
                print("Connection lost, attempting reconnection...")
                try:
                    await exchange._ws_client.ws_client.restart()
                except Exception as e:
                    print(f"Reconnection failed: {e}")
            
            await asyncio.sleep(30)  # Check every 30 seconds
    
    # Start health monitoring
    asyncio.create_task(ensure_connection())
    
    return exchange
```

### Monitoring and Alerting
```python
async def monitor_trading_session(exchange):
    """Monitor trading session with alerting"""
    
    last_orderbook_update = time.time()
    last_balance_check = time.time()
    
    while True:
        try:
            # Check orderbook freshness
            if exchange.orderbook and exchange.orderbook.timestamp:
                last_update = time.time() - exchange.orderbook.timestamp
                if last_update > 10:  # Alert if no updates for 10 seconds
                    print(f"WARNING: Orderbook stale for {last_update:.1f} seconds")
            
            # Check connection status
            if hasattr(exchange, '_ws_client') and exchange._ws_client:
                if not exchange._ws_client.ws_client.is_connected:
                    print("WARNING: WebSocket disconnected")
            
            # Periodic balance verification
            if time.time() - last_balance_check > 300:  # Every 5 minutes
                try:
                    balances = await exchange.get_fresh_balances()
                    print(f"Balance check: {len(balances)} assets")
                    last_balance_check = time.time()
                except Exception as e:
                    print(f"Balance check failed: {e}")
            
            # Get performance metrics
            metrics = exchange.get_performance_metrics()
            if metrics['cache_hit_rate_percent'] < 70:
                print(f"WARNING: Low cache hit rate: {metrics['cache_hit_rate_percent']}%")
            
            await asyncio.sleep(10)  # Check every 10 seconds
            
        except Exception as e:
            print(f"Monitoring error: {e}")
            await asyncio.sleep(30)  # Back off on errors
```

## Running Examples

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MEXC_API_KEY="your_api_key"
export MEXC_SECRET_KEY="your_secret_key"
```

### Public API Examples
```bash
# Run public API validation
python src/examples/mexc/public_rest_checks.py

# Run WebSocket market data streaming
python src/examples/mexc/ws_public_simple_check.py
```

### Private API Examples (Testnet Recommended)
```bash
# Run private API validation
python src/examples/mexc/private_rest_checks.py

# Run WebSocket account data streaming
python src/examples/mexc/ws_private_simple_check.py
```

### Integration Testing
```bash
# Run comprehensive integration tests
pytest src/examples/ -v

# Run performance benchmarks
python -c "
import asyncio
from src.examples.performance_benchmarks import benchmark_api_latency
asyncio.run(benchmark_api_latency())
"
```

## Safety Considerations

### Testnet Usage
- **Always test with testnet first** before production deployment
- **Use small order sizes** when testing with real funds
- **Implement circuit breakers** to prevent runaway trading

### Risk Management
- **Set maximum order sizes** to limit exposure
- **Implement position limits** across all symbols
- **Monitor account balances** continuously
- **Use stop-loss mechanisms** for automated trading

### Production Checklist
- [ ] API credentials secured and encrypted
- [ ] Rate limiting properly configured
- [ ] Error handling and recovery implemented
- [ ] Monitoring and alerting configured
- [ ] Trading limits and safeguards in place
- [ ] Backup and disaster recovery procedures tested