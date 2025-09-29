# Dependency Injection Implementation Guide

## Step-by-Step Implementation

This guide provides detailed implementation steps for eliminating abstract factory methods and implementing constructor dependency injection.

## Phase 1: Base Class Dependency Injection

### Step 1.1: Update BaseCompositeExchange

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/interfaces/composite/base_composite.py`

#### Changes Required:

1. **Add Generic Type Parameters**:
```python
from typing import TypeVar, Optional, Generic

# Add these type variables at top of file
RestClientType = TypeVar('RestClientType')
WebSocketClientType = TypeVar('WebSocketClientType')

# Update class declaration
class BaseCompositeExchange(Generic[RestClientType, WebSocketClientType], ABC):
```

2. **Update Constructor for Dependency Injection**:
```python
def __init__(self, 
             config: ExchangeConfig, 
             is_private: bool,
             rest_client: RestClientType,
             websocket_client: Optional[WebSocketClientType] = None,
             logger: Optional[HFTLoggerInterface] = None):
    """
    Initialize composite exchange with injected clients.
    
    Args:
        config: Exchange configuration
        is_private: Whether this is a private exchange
        rest_client: Injected REST client instance
        websocket_client: Optional injected WebSocket client instance  
        logger: Optional injected HFT logger
    """
    # Existing initialization code...
    self._is_private = is_private
    self._exchange_name = config.name
    self._tag = f"{config.name}_{'private' if is_private else 'public'}"
    self._config = config
    self._initialized = False
    self._connection_state = ConnectionState.DISCONNECTED
    
    # Use injected logger or create exchange-specific logger
    self.logger = logger or get_exchange_logger(config.name, self._tag)
    
    # Connection and state management
    self._symbols_info: Optional[SymbolsInfo] = None
    self._last_update_time = 0.0
    
    # DEPENDENCY INJECTION: Store injected clients
    self._rest: RestClientType = rest_client
    self._ws: Optional[WebSocketClientType] = websocket_client
    
    # Connection status tracking
    self._rest_connected = rest_client is not None
    self._ws_connected = websocket_client is not None
    
    # Log interface initialization
    self.logger.info("BaseExchangeInterface initialized with injected clients", 
                     exchange=config.name,
                     has_rest=self._rest_connected,
                     has_ws=self._ws_connected)
```

3. **Add Client Access Properties**:
```python
@property
def rest_client(self) -> RestClientType:
    """Get the injected REST client."""
    return self._rest

@property
def websocket_client(self) -> Optional[WebSocketClientType]:
    """Get the injected WebSocket client."""
    return self._ws
```

### Step 1.2: Create Type Constraints File

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/interfaces/composite/types.py` (NEW)

```python
"""Type definitions for composite exchange dependency injection."""

from typing import TypeVar, Union
from exchanges.interfaces import PrivateSpotRest, PublicSpotRest, PublicFuturesRest, PrivateFuturesRest
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
from exchanges.interfaces.ws.futures.ws_futures_public import PublicFuturesWebsocket
from exchanges.interfaces.ws.futures.ws_futures_private import PrivateFuturesWebsocket

# Generic type variables for dependency injection
RestClientType = TypeVar('RestClientType')
WebSocketClientType = TypeVar('WebSocketClientType')

# Specific type unions for spot and futures
SpotRestClient = Union[PublicSpotRest, PrivateSpotRest]
SpotWebSocketClient = Union[PublicSpotWebsocket, PrivateSpotWebsocket]
FuturesRestClient = Union[PublicFuturesRest, PrivateFuturesRest]
FuturesWebSocketClient = Union[PublicFuturesWebsocket, PrivateFuturesWebsocket]

# Type aliases for common combinations
PublicSpotClients = tuple[PublicSpotRest, PublicSpotWebsocket]
PrivateSpotClients = tuple[PrivateSpotRest, PrivateSpotWebsocket]
PublicFuturesClients = tuple[PublicFuturesRest, PublicFuturesWebsocket]
PrivateFuturesClients = tuple[PrivateFuturesRest, PrivateFuturesWebsocket]
```

## Phase 2: Private Composite Refactoring

### Step 2.1: Update BasePrivateComposite

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/interfaces/composite/base_private_composite.py`

#### Critical Changes:

1. **ELIMINATE Factory Methods** (Lines 178-196):
```python
# REMOVE THESE METHODS COMPLETELY:
# @abstractmethod
# async def _create_private_rest(self) -> PrivateSpotRest:
# @abstractmethod
# async def _create_private_websocket(self) -> Optional[PrivateSpotWebsocket]:
```

2. **Update Class Declaration with Generic Types**:
```python
from .types import RestClientType, WebSocketClientType
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket

class BasePrivateComposite(BaseCompositeExchange[PrivateSpotRest, PrivateSpotWebsocket]):
```

3. **Update Constructor for Dependency Injection**:
```python
def __init__(self, 
             config: ExchangeConfig,
             rest_client: PrivateSpotRest,
             websocket_client: Optional[PrivateSpotWebsocket] = None,
             logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None) -> None:
    """
    Initialize base private exchange with injected clients.
    
    Args:
        config: Exchange configuration with API credentials
        rest_client: Injected private REST client
        websocket_client: Optional injected private WebSocket client
        logger: Optional injected HFT logger
        handlers: Optional private WebSocket handlers
    """
    super().__init__(
        config=config, 
        is_private=True, 
        rest_client=rest_client,
        websocket_client=websocket_client,
        logger=logger
    )

    if not handlers:
        self.handlers = PrivateWebsocketHandlers()
    else:
        self.handlers = handlers

    self._tag = f'{config.name}_private'

    # Private data state (HFT COMPLIANT - no caching of real-time data)
    self._balances: Dict[AssetName, AssetBalance] = {}
    self._open_orders: Dict[Symbol, Dict[OrderId, Order]] = {}

    # Executed orders state management (HFT-safe caching of completed orders only)
    self._executed_orders: Dict[Symbol, Dict[OrderId, Order]] = {}
    self._max_executed_orders_per_symbol = 1000  # Memory management limit

    # Authentication validation
    if not config.has_credentials():
        self.logger.error("No API credentials provided - trading operations will fail")
```

4. **REMOVE Duplicate Client Attributes** (Lines 73-76):
```python
# REMOVE THESE LINES:
# self._private_rest: Optional[PrivateSpotRest] = None
# self._private_ws: Optional[PrivateSpotWebsocket] = None
# self._private_rest_connected = False
# self._private_ws_connected = False
```

5. **Update Client Usage Throughout File**:
```python
# Replace all instances of self._private_rest with self._rest
# Replace all instances of self._private_ws with self._ws

# Example: Line 204 in _load_balances method:
async def _load_balances(self) -> None:
    """Load account balances from REST API with error handling and metrics."""
    if not self._rest:  # Changed from self._private_rest
        self.logger.warning("No private REST client available for balance loading")
        return

    try:
        with LoggingTimer(self.logger, "load_balances") as timer:
            balances_data = await self._rest.get_balances()  # Changed from self._private_rest
            self._balances = {b.asset: b for b in balances_data}
        # ... rest of method unchanged
```

6. **Update Initialize Method** (Lines 358-388):
```python
async def initialize(self, symbols_info: SymbolsInfo) -> None:
    """Initialize base private exchange functionality."""
    # Initialize public functionality first (parent class)
    await super().initialize()

    self._symbols_info = symbols_info

    try:
        # REMOVED: Client creation via factory methods
        # self._private_rest = await self._create_private_rest()
        # self._private_rest_connected = self._private_rest is not None
        
        # Clients are already injected via constructor
        self.logger.info(f"{self._tag} Using injected clients...")

        # Step 1: Load private data via REST (parallel loading)
        self.logger.info(f"{self._tag} Loading private data...")
        await self._refresh_exchange_data()

        # Step 2: Initialize WebSocket client if provided
        self.logger.info(f"{self._tag} Initializing WebSocket client...")
        await self._initialize_private_websocket()

        self.logger.info(f"{self._tag} private initialization completed",
                        has_rest=self._rest is not None,
                        has_ws=self._ws is not None,
                        balance_count=len(self._balances),
                        order_count=sum(len(orders) for orders in self._open_orders.values()))

    except Exception as e:
        self.logger.error(f"Private exchange initialization failed: {e}")
        await self.close()  # Cleanup on failure
        raise
```

7. **Update WebSocket Initialization**:
```python
async def _initialize_private_websocket(self) -> None:
    """Initialize private WebSocket with injected client."""
    if not self.config.has_credentials():
        self.logger.info("No credentials - skipping private WebSocket")
        return

    if not self._ws:
        self.logger.info("No WebSocket client injected - skipping WebSocket initialization")
        return

    try:
        await self._ws.initialize()  # Use injected client directly

    except Exception as e:
        self.logger.error("Private WebSocket initialization failed", error=str(e))
        raise InitializationError(f"Private WebSocket initialization failed: {e}")
```

### Step 2.2: Update BasePrivateSpotComposite

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/interfaces/composite/spot/base_private_spot_composite.py`

```python
# Update imports and class declaration
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket

class CompositePrivateSpotExchange(BasePrivateComposite):
    """
    Private spot exchange implementation with withdrawal functionality.
    Uses dependency injection for REST and WebSocket clients.
    """
    
    def __init__(self,
                 config: ExchangeConfig,
                 rest_client: PrivateSpotRest,
                 websocket_client: Optional[PrivateSpotWebsocket] = None,
                 logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None):
        """Initialize private spot exchange with injected clients."""
        super().__init__(config, rest_client, websocket_client, logger, handlers)
```

## Phase 3: Public Composite Refactoring

### Step 3.1: Update CompositePublicSpotExchange

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/interfaces/composite/spot/base_public_spot_composite.py`

#### Similar changes to private composite:

1. **ELIMINATE Factory Methods**
2. **Update Class Declaration** with Generic Types
3. **Update Constructor** for Dependency Injection
4. **REMOVE Duplicate Client Attributes**
5. **Update Client Usage** Throughout File

## Phase 4: Exchange Implementation Updates

### Step 4.1: Update MEXC Private Composite

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/integrations/mexc/mexc_composite_private.py`

```python
"""MEXC private exchange implementation using dependency injection."""

from typing import Optional
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig


class MexcCompositePrivateSpotExchange(CompositePrivateSpotExchange):
    """
    MEXC private exchange implementation using dependency injection.
    
    No factory methods - clients are injected via constructor.
    """

    def __init__(self, 
                 config: ExchangeConfig,
                 rest_client: PrivateSpotRest,
                 websocket_client: Optional[PrivateSpotWebsocket] = None,
                 logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None):
        """Initialize MEXC private exchange with injected clients."""
        super().__init__(config, rest_client, websocket_client, logger, handlers)

    # REMOVED: All factory methods eliminated
    # async def _create_private_rest(self) -> PrivateSpotRest:
    # async def _create_private_websocket(self) -> Optional[PrivateSpotWebsocket]:

    # WebSocket Handler Implementation remains the same
    def _create_inner_websocket_handlers(self) -> PrivateWebsocketHandlers:
        """Get private WebSocket handlers for MEXC."""
        return PrivateWebsocketHandlers(
            order_handler=self._order_handler,
            balance_handler=self._balance_handler,
            execution_handler=self._execution_handler,
        )
```

## Phase 5: Factory and Creation Pattern Updates

### Step 5.1: Create Client Factory Utilities

**File**: `/Users/dasein/dev/cex_arbitrage/src/exchanges/utils/client_factory.py` (NEW)

```python
"""Client factory utilities for dependency injection."""

from typing import Optional
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers, PublicWebsocketHandlers

# MEXC imports
from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
from exchanges.integrations.mexc.rest.mexc_rest_spot_public import MexcPublicSpotRest
from exchanges.integrations.mexc.ws.mexc_ws_private import MexcSpotWebsocket
from exchanges.integrations.mexc.ws.mexc_ws_public import MexcSpotWebsocketPublic


# Gate.io imports (add as needed)
# from exchanges.integrations.gateio.rest... import ...


class ClientFactory:
    """Factory for creating REST and WebSocket clients before injection."""

    @staticmethod
    def create_mexc_private_clients(
            config: ExchangeConfig,
            logger: Optional[HFTLoggerInterface] = None,
            handlers: Optional[PrivateWebsocketHandlers] = None
    ) -> tuple[MexcPrivateSpotRest, Optional[MexcSpotWebsocket]]:
        """Create MEXC private REST and WebSocket clients."""
        rest_client = MexcPrivateSpotRest(config, logger)

        ws_client = None
        if config.has_credentials() and handlers:
            ws_client = MexcSpotWebsocket(config, handlers, logger)

        return rest_client, ws_client

    @staticmethod
    def create_mexc_public_clients(
            config: ExchangeConfig,
            logger: Optional[HFTLoggerInterface] = None,
            handlers: Optional[PublicWebsocketHandlers] = None
    ) -> tuple[MexcPublicSpotRest, Optional[MexcSpotWebsocketPublic]]:
        """Create MEXC public REST and WebSocket clients."""
        rest_client = MexcPublicSpotRest(config, logger)

        ws_client = None
        if handlers:
            ws_client = MexcSpotWebsocketPublic(config, handlers, logger)

        return rest_client, ws_client
```

### Step 5.2: Update Usage Patterns

**Example usage with dependency injection:**

```python
from exchanges.utils.client_factory import ClientFactory
from exchanges.integrations.mexc.mexc_composite_private import MexcCompositePrivateSpotExchange

# Create clients first
rest_client, ws_client = ClientFactory.create_mexc_private_clients(
    config=mexc_config,
    logger=logger,
    handlers=private_handlers
)

# Inject clients into composite exchange
exchange = MexcCompositePrivateSpotExchange(
    config=mexc_config,
    rest_client=rest_client,
    websocket_client=ws_client,
    logger=logger,
    handlers=private_handlers
)

# Initialize (no client creation needed)
await exchange.initialize(symbols_info)
```

## Testing Strategy

### Step 6.1: Update Test Patterns

```python
# OLD (factory method mocking - complex)
@patch.object(MexcCompositePrivateSpotExchange, '_create_private_rest')
@patch.object(MexcCompositePrivateSpotExchange, '_create_private_websocket')
async def test_exchange_old_pattern(mock_ws, mock_rest):
    # Complex mocking of factory methods
    pass

# NEW (direct client injection - simple)
async def test_exchange_new_pattern():
    # Create mock clients
    mock_rest = AsyncMock(spec=MexcPrivateSpotRest)
    mock_ws = AsyncMock(spec=MexcPrivateSpotWebsocket)
    
    # Inject directly
    exchange = MexcCompositePrivateSpotExchange(
        config=test_config,
        rest_client=mock_rest,
        websocket_client=mock_ws,
        logger=test_logger
    )
    
    # Test with injected mocks
    await exchange.initialize(symbols_info)
    assert exchange.rest_client is mock_rest
    assert exchange.websocket_client is mock_ws
```

## Validation Checklist

### Before Implementation
- [ ] Review all current factory method usage
- [ ] Identify all files that instantiate composite exchanges
- [ ] Create comprehensive test plan
- [ ] Backup current implementation

### During Implementation
- [ ] Implement phases sequentially
- [ ] Run tests after each major change
- [ ] Validate type checking passes
- [ ] Check for remaining factory method references

### After Implementation
- [ ] Full integration test suite
- [ ] Performance benchmarking
- [ ] Code coverage analysis
- [ ] Documentation updates

## Rollback Procedures

### If Issues Arise
1. **Stop current phase implementation**
2. **Assess scope of problems**
3. **Revert to last known good state**
4. **Analyze root cause**
5. **Plan corrective action**

### Git Strategy
```bash
# Create feature branch
git checkout -b feature/dependency-injection-refactor

# Create savepoints after each phase
git commit -m "Phase 1: Base class dependency injection"
git commit -m "Phase 2: Private composite refactoring"
# etc.

# Rollback to specific phase if needed
git reset --hard <phase-commit-hash>
```

This implementation guide provides the detailed steps needed to eliminate factory methods and implement proper dependency injection throughout the composite exchange architecture.