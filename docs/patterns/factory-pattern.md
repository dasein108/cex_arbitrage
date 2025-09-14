# Factory Pattern Implementation

## Overview

The CEX Arbitrage Engine implements the **Abstract Factory Pattern** to eliminate code duplication in exchange creation, enable dynamic exchange scaling, and maintain clean architecture principles.

## Factory Pattern Architecture

### Problem Solved

**Before Factory Pattern (Legacy Issues)**:
- Code duplication in exchange creation
- Hard-coded exchange instantiation
- Scattered credential management
- God Class antipattern in main components
- Difficult to add new exchanges

**After Factory Pattern (Current Solution)**:
- Centralized exchange creation logic
- Dynamic credential lookup
- Unified error handling and retry logic
- Clean separation of concerns
- Zero-code-change exchange addition

## Core Factory Implementation

### ExchangeFactory Class

```python
# src/arbitrage/exchange_factory.py

class ExchangeFactory:
    """
    Factory for creating and managing exchange instances.
    
    Implements Abstract Factory pattern with:
    - Centralized creation logic
    - Dynamic credential management  
    - Concurrent initialization
    - Error resilience and recovery
    """
    
    # EXCHANGE CLASS REGISTRY - Add new exchanges here only
    EXCHANGE_CLASSES: Dict[str, Type[BaseExchangeInterface]] = {
        'MEXC': MexcExchange,
        'GATEIO': GateioExchange,
        # Future exchanges added here with zero other code changes
    }
    
    def __init__(self):
        self.exchanges: Dict[str, BaseExchangeInterface] = {}
        self._initialization_timeout = 10.0
        self._retry_attempts = 3
        self._retry_delay = 2.0
        self._initialization_results: List[ExchangeInitResult] = []
    
    async def create_exchange(
        self, 
        exchange_name: str,
        symbols: Optional[List[Symbol]] = None,
        max_attempts: Optional[int] = None
    ) -> BaseExchangeInterface:
        """Create and initialize exchange with comprehensive error handling"""
        
        # Factory pattern implementation with retry logic
        for attempt in range(1, (max_attempts or self._retry_attempts) + 1):
            try:
                # 1. Get and validate credentials via unified config
                credentials = self._get_credentials(exchange_name)
                
                # 2. Get exchange class from registry
                exchange_class = self._get_exchange_class(exchange_name)
                
                # 3. Create instance with credential injection
                exchange = await self._create_exchange_instance(
                    exchange_class, credentials, exchange_name
                )
                
                # 4. Initialize with validation
                await self._initialize_exchange_with_validation(
                    exchange, exchange_name, symbols or self.DEFAULT_SYMBOLS
                )
                
                # 5. Store and return
                self.exchanges[exchange_name] = exchange
                return exchange
                
            except Exception as e:
                if attempt < (max_attempts or self._retry_attempts):
                    await asyncio.sleep(self._retry_delay * attempt)
                else:
                    raise ExchangeAPIError(500, f"Factory failed: {e}")
```

### Unified Credential Management

**Dynamic Credential Lookup**:
```python
def _get_credentials(self, exchange_name: str) -> ExchangeCredentials:
    """Retrieve credentials for any exchange via unified config system"""
    
    # Uses unified configuration architecture - no exchange-specific code
    credentials = config.get_exchange_credentials(exchange_name.lower())
    
    return ExchangeCredentials(
        api_key=credentials.get('api_key', ''),
        secret_key=credentials.get('secret_key', '')
    )

def _get_exchange_class(self, exchange_name: str) -> Type[BaseExchangeInterface]:
    """Get exchange class from registry"""
    
    if exchange_name not in self.EXCHANGE_CLASSES:
        available = list(self.EXCHANGE_CLASSES.keys())
        raise ValueError(f"Unsupported exchange: {exchange_name}. Available: {available}")
    
    return self.EXCHANGE_CLASSES[exchange_name]

async def _create_exchange_instance(
    self,
    exchange_class: Type[BaseExchangeInterface],
    credentials: ExchangeCredentials, 
    exchange_name: str
) -> BaseExchangeInterface:
    """Create exchange instance with proper dependency injection"""
    
    # Secure credential logging without exposing sensitive data
    if credentials.has_private_access:
        key_preview = self._get_key_preview(credentials.api_key)
        logger.info(f"{exchange_name} private credentials: {key_preview}")
    else:
        logger.info(f"{exchange_name} public mode only")
    
    # Dependency injection based on credential availability
    if credentials.has_private_access:
        return exchange_class(
            api_key=credentials.api_key,
            secret_key=credentials.secret_key
        )
    else:
        return exchange_class()  # Public-only mode
```

## Initialization Strategies

### Strategy Pattern Integration

```python
class InitializationStrategy(Enum):
    """Exchange initialization strategies"""
    FAIL_FAST = "fail_fast"          # Fail immediately on any error
    CONTINUE_ON_ERROR = "continue"   # Continue with available exchanges
    RETRY_WITH_BACKOFF = "retry"     # Retry failed initializations

async def create_exchanges(
    self,
    exchange_names: List[str],
    strategy: InitializationStrategy = InitializationStrategy.CONTINUE_ON_ERROR,
    symbols: Optional[List[Symbol]] = None
) -> Dict[str, BaseExchangeInterface]:
    """Create multiple exchanges with intelligent error handling"""
    
    logger.info(f"Creating {len(exchange_names)} exchanges with {strategy.value} strategy")
    
    if strategy == InitializationStrategy.FAIL_FAST:
        return await self._create_exchanges_fail_fast(exchange_names, symbols)
    elif strategy == InitializationStrategy.CONTINUE_ON_ERROR:
        return await self._create_exchanges_continue(exchange_names, symbols)  
    elif strategy == InitializationStrategy.RETRY_WITH_BACKOFF:
        return await self._create_exchanges_with_retry(exchange_names, symbols)
```

### Concurrent Initialization

**CONTINUE_ON_ERROR Strategy (Recommended)**:
```python
async def _create_exchanges_continue(
    self, 
    exchange_names: List[str],
    symbols: Optional[List[Symbol]]
) -> Dict[str, BaseExchangeInterface]:
    """Create exchanges concurrently with error resilience"""
    
    # Create initialization tasks
    tasks = []
    for name in exchange_names:
        tasks.append(self._create_exchange_safe(name, symbols))
    
    # Execute concurrently - maximum performance
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results with error resilience
    successful_exchanges = {}
    for name, result in zip(exchange_names, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to create {name}: {result}")
            # Continue with other exchanges
        elif result:
            successful_exchanges[name] = result
            logger.info(f"✅ {name} created successfully")
    
    if not successful_exchanges:
        raise ExchangeAPIError(500, "No exchanges could be initialized")
    
    return successful_exchanges
```

**RETRY_WITH_BACKOFF Strategy (High Reliability)**:
```python
async def _create_exchanges_with_retry(
    self, 
    exchange_names: List[str],
    symbols: Optional[List[Symbol]]
) -> Dict[str, BaseExchangeInterface]:
    """Create exchanges with intelligent retry logic"""
    
    # First attempt - concurrent
    successful = await self._create_exchanges_continue(exchange_names, symbols)
    
    # Identify failures
    failed_exchanges = [name for name in exchange_names if name not in successful]
    
    # Retry failed exchanges with exponential backoff
    for attempt in range(2, self._retry_attempts + 1):
        if not failed_exchanges:
            break
            
        # Wait with exponential backoff
        wait_time = self._retry_delay * (2 ** (attempt - 2))
        logger.info(f"Retrying {len(failed_exchanges)} failed exchanges in {wait_time:.1f}s...")
        await asyncio.sleep(wait_time)
        
        # Retry failed exchanges
        retry_tasks = []
        for name in failed_exchanges:
            retry_tasks.append(self._create_exchange_safe(name, symbols))
        
        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
        
        # Update failed list
        new_failed = []
        for name, result in zip(failed_exchanges, retry_results):
            if isinstance(result, Exception) or not result:
                new_failed.append(name)
            else:
                successful[name] = result
                logger.info(f"✅ {name} recovered on attempt {attempt}")
        
        failed_exchanges = new_failed
    
    return successful
```

## Exchange Integration via Factory

### Adding New Exchanges (Zero Code Changes)

**Step 1: Register in Factory**:
```python
# Only change needed in existing codebase
EXCHANGE_CLASSES: Dict[str, Type[BaseExchangeInterface]] = {
    'MEXC': MexcExchange,
    'GATEIO': GateioExchange,
    'BINANCE': BinanceExchange,      # <- Add new exchange
    'KRAKEN': KrakenExchange,        # <- Add another exchange
}
```

**Step 2: Configure in config.yaml**:
```yaml
exchanges:
  # Existing exchanges...
  mexc:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
  
  # New exchanges automatically supported
  binance:
    api_key: "${BINANCE_API_KEY}"
    secret_key: "${BINANCE_SECRET_KEY}"
    base_url: "https://api.binance.com"
    
  kraken:
    api_key: "${KRAKEN_API_KEY}"
    secret_key: "${KRAKEN_SECRET_KEY}"
    base_url: "https://api.kraken.com"
```

**Automatic Integration Benefits**:
- **ConfigurationManager**: Automatically recognizes new exchanges
- **SymbolResolver**: Integrates new exchange symbols automatically  
- **PerformanceMonitor**: Tracks new exchange performance
- **ArbitrageController**: Orchestrates new exchanges seamlessly

## Error Handling & Recovery

### Comprehensive Error Tracking

```python
@dataclass
class ExchangeInitResult:
    """Result of exchange initialization attempt"""
    exchange_name: str
    success: bool
    exchange: Optional[BaseExchangeInterface] = None
    error: Optional[Exception] = None
    attempts: int = 1
    initialization_time: float = 0.0

class ExchangeFactory:
    def get_initialization_summary(self) -> Dict[str, Any]:
        """Get comprehensive initialization summary"""
        
        total_requested = len(self._initialization_results)
        successful = len([r for r in self._initialization_results if r.success])
        failed = total_requested - successful
        
        avg_init_time = 0.0
        if successful > 0:
            successful_results = [r for r in self._initialization_results if r.success]
            avg_init_time = sum(r.initialization_time for r in successful_results) / len(successful_results)
        
        return {
            'total_requested': total_requested,
            'successful': successful,
            'failed': failed,
            'success_rate': (successful / total_requested * 100) if total_requested > 0 else 0.0,
            'average_init_time': avg_init_time,
            'active_exchanges': list(self.exchanges.keys()),
            'failed_exchanges': [r.exchange_name for r in self._initialization_results if not r.success],
            'retry_attempts': {r.exchange_name: r.attempts for r in self._initialization_results if r.attempts > 1}
        }
```

### Graceful Error Recovery

```python
async def _create_exchange_safe(
    self, 
    name: str, 
    symbols: Optional[List[Symbol]] = None
) -> Optional[BaseExchangeInterface]:
    """Create exchange with comprehensive error handling"""
    
    try:
        return await self.create_exchange(name, symbols)
    except ExchangeAPIError as e:
        logger.error(f"Exchange API error for {name}: {e}")
        return None
    except ConfigurationError as e:
        logger.error(f"Configuration error for {name}: {e}")
        return None
    except NetworkError as e:
        logger.error(f"Network error for {name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error for {name}: {e}")
        return None

def _log_exchange_summary(self):
    """Log comprehensive initialization summary"""
    
    summary = self.get_initialization_summary()
    
    logger.info("Exchange Initialization Summary:")
    logger.info(f"  Requested: {summary['total_requested']}")
    logger.info(f"  Successful: {summary['successful']}")  
    logger.info(f"  Failed: {summary['failed']}")
    logger.info(f"  Success Rate: {summary['success_rate']:.1f}%")
    logger.info(f"  Average Init Time: {summary['average_init_time']:.2f}s")
    
    # Log successful exchanges with details
    for name, exchange in self.exchanges.items():
        status = exchange.status.name
        symbols = len(getattr(exchange, 'active_symbols', []))
        private = "Private" if exchange.has_private else "Public Only"
        
        result = next((r for r in self._initialization_results if r.exchange_name == name), None)
        time_info = f" in {result.initialization_time:.2f}s" if result else ""
        attempts_info = f" (attempts: {result.attempts})" if result and result.attempts > 1 else ""
        
        logger.info(f"  ✅ {name}: {status} ({symbols} symbols, {private}){time_info}{attempts_info}")
    
    # Log failed exchanges
    for exchange_name in summary['failed_exchanges']:
        result = next((r for r in self._initialization_results if r.exchange_name == exchange_name), None)
        error_info = f" - {result.error}" if result and result.error else ""
        logger.error(f"  ❌ {exchange_name}: Failed after {result.attempts if result else 1} attempts{error_info}")
```

## Advanced Factory Patterns

### Factory with Dependency Injection

```python
class AdvancedExchangeFactory:
    """Advanced factory with full dependency injection support"""
    
    def __init__(
        self,
        config_manager: ConfigurationManager,
        symbol_resolver: SymbolResolver,
        performance_monitor: PerformanceMonitor
    ):
        # Dependency injection - factory receives dependencies
        self.config_manager = config_manager
        self.symbol_resolver = symbol_resolver  
        self.performance_monitor = performance_monitor
        
        self.exchanges: Dict[str, BaseExchangeInterface] = {}
    
    async def create_exchange_with_dependencies(
        self, 
        exchange_name: str
    ) -> BaseExchangeInterface:
        """Create exchange with full dependency injection"""
        
        # Get configuration through injected dependency
        exchange_config = self.config_manager.get_exchange_config(exchange_name)
        
        # Create exchange with injected dependencies
        exchange_class = self.EXCHANGE_CLASSES[exchange_name]
        exchange = exchange_class()
        
        # Inject dependencies into exchange
        exchange.set_config_manager(self.config_manager)
        exchange.set_symbol_resolver(self.symbol_resolver)
        exchange.set_performance_monitor(self.performance_monitor)
        
        # Initialize with dependencies
        await exchange.init_with_dependencies()
        
        return exchange
```

### Factory with Plugin Architecture

```python
class PluginExchangeFactory:
    """Factory supporting plugin-based exchange loading"""
    
    def __init__(self):
        self.exchange_plugins: Dict[str, Type[BaseExchangeInterface]] = {}
        self._load_builtin_exchanges()
        self._discover_plugin_exchanges()
    
    def _load_builtin_exchanges(self) -> None:
        """Load built-in exchange implementations"""
        self.exchange_plugins.update(self.EXCHANGE_CLASSES)
    
    def _discover_plugin_exchanges(self) -> None:
        """Discover exchange plugins from plugin directory"""
        plugin_dir = Path(__file__).parent / "plugins"
        
        if plugin_dir.exists():
            for plugin_file in plugin_dir.glob("*_exchange.py"):
                try:
                    # Dynamic plugin loading
                    spec = importlib.util.spec_from_file_location(
                        plugin_file.stem, plugin_file
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Find exchange class in plugin
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseExchangeInterface) and 
                            attr != BaseExchangeInterface):
                            
                            exchange_name = attr_name.replace('Exchange', '').upper()
                            self.exchange_plugins[exchange_name] = attr
                            logger.info(f"Loaded exchange plugin: {exchange_name}")
                            
                except Exception as e:
                    logger.warning(f"Failed to load plugin {plugin_file}: {e}")
    
    def list_available_exchanges(self) -> List[str]:
        """List all available exchanges (builtin + plugins)"""
        return list(self.exchange_plugins.keys())
    
    def is_plugin_exchange(self, exchange_name: str) -> bool:
        """Check if exchange is a plugin (not built-in)"""
        return (exchange_name in self.exchange_plugins and 
                exchange_name not in self.EXCHANGE_CLASSES)
```

## Performance Optimizations

### Factory Performance Features

**Connection Pool Pre-warming**:
```python
async def pre_warm_connections(self) -> None:
    """Pre-warm connection pools for all exchanges"""
    
    tasks = []
    for exchange_name, exchange in self.exchanges.items():
        if hasattr(exchange, 'pre_warm_connections'):
            tasks.append(exchange.pre_warm_connections())
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"Pre-warmed connections for {len(tasks)} exchanges")
```

**Batch Operations**:
```python
async def batch_initialize_symbols(
    self, 
    symbols: List[Symbol]
) -> Dict[str, List[SymbolInfo]]:
    """Batch initialize symbols across all exchanges"""
    
    tasks = {}
    for exchange_name, exchange in self.exchanges.items():
        if hasattr(exchange, 'batch_get_symbol_info'):
            tasks[exchange_name] = exchange.batch_get_symbol_info(symbols)
    
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    return dict(zip(tasks.keys(), results))
```

**Memory Management**:
```python
async def cleanup_unused_exchanges(self, active_exchanges: Set[str]) -> None:
    """Clean up exchanges not in active set"""
    
    to_cleanup = set(self.exchanges.keys()) - active_exchanges
    
    cleanup_tasks = []
    for exchange_name in to_cleanup:
        exchange = self.exchanges.pop(exchange_name)
        cleanup_tasks.append(exchange.close())
    
    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        logger.info(f"Cleaned up {len(cleanup_tasks)} unused exchanges")
```

## Factory Testing Strategies

### Factory Unit Tests

```python
@pytest.mark.asyncio
async def test_exchange_factory_creation():
    """Test basic exchange factory creation"""
    
    factory = ExchangeFactory()
    
    # Test exchange creation
    exchange = await factory.create_exchange('MEXC')
    
    assert isinstance(exchange, MexcExchange)
    assert exchange.status == ExchangeStatus.ACTIVE
    assert exchange in factory.exchanges.values()

@pytest.mark.asyncio
async def test_factory_error_handling():
    """Test factory error handling and recovery"""
    
    factory = ExchangeFactory()
    
    # Test with invalid exchange
    with pytest.raises(ValueError, match="Unsupported exchange"):
        await factory.create_exchange('INVALID_EXCHANGE')

@pytest.mark.asyncio
async def test_concurrent_initialization():
    """Test concurrent exchange initialization"""
    
    factory = ExchangeFactory()
    
    # Test concurrent creation
    exchanges = await factory.create_exchanges(
        ['MEXC', 'GATEIO'],
        strategy=InitializationStrategy.CONTINUE_ON_ERROR
    )
    
    assert len(exchanges) >= 1  # At least one should succeed
    
    summary = factory.get_initialization_summary()
    assert summary['total_requested'] == 2
    assert summary['success_rate'] > 0
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_factory_config_integration():
    """Test factory integration with configuration system"""
    
    # Test that factory uses unified configuration
    factory = ExchangeFactory()
    
    for exchange_name in ['mexc', 'gateio']:
        credentials = factory._get_credentials(exchange_name)
        config_creds = config.get_exchange_credentials(exchange_name)
        
        assert credentials.api_key == config_creds['api_key']
        assert credentials.secret_key == config_creds['secret_key']
```

---

*This Factory Pattern implementation enables clean exchange creation, eliminates code duplication, and supports the unified configuration architecture while maintaining HFT performance requirements.*