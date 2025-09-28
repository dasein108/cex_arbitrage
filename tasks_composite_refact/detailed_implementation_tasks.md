# Pure Dependency Injection Implementation Tasks

## Overview

This document outlines the complete refactoring to implement **pure dependency injection** in composite exchanges. This is a **breaking change** that removes all abstract factory methods and requires all clients to be passed through constructors.

## Core Principles

1. **NO Factory Methods**: Remove all `_create_rest_client()` and `_create_websocket_client()` abstract methods
2. **Constructor Injection Only**: All clients passed through constructor parameters
3. **No Backwards Compatibility**: Clean breaking change for simplified architecture
4. **Minimal Code Changes**: Focus on essential changes only
5. **Type Safety**: Maintain strong typing with constructor injection

## Task Breakdown

### Phase 1: Base Class Simplification

#### Task 1.1: Update BaseCompositeExchange
**File**: `src/exchanges/interfaces/composite/base_composite.py`
**Priority**: Critical
**Estimated Time**: 1 hour

**Changes Required**:

1. **Update Constructor for Dependency Injection**
   ```python
   from typing import TypeVar, Generic, Optional
   
   RestClientType = TypeVar('RestClientType')
   WebSocketClientType = TypeVar('WebSocketClientType')
   
   class BaseCompositeExchange(Generic[RestClientType, WebSocketClientType], ABC):
       def __init__(
           self, 
           config: ExchangeConfig, 
           is_private: bool,
           rest_client: RestClientType,
           websocket_client: Optional[WebSocketClientType] = None,
           logger: Optional[HFTLoggerInterface] = None
       ):
           # ... existing config setup ...
           
           # Direct client assignment (no factory methods)
           self._rest: RestClientType = rest_client
           self._ws: Optional[WebSocketClientType] = websocket_client
           
           # Connection status tracking
           self._rest_connected = rest_client is not None
           self._ws_connected = websocket_client is not None and websocket_client.is_connected
   ```

2. **Remove ALL Factory Method Definitions**
   ```python
   # REMOVE COMPLETELY - No abstract factory methods
   # @abstractmethod
   # async def _create_rest_client(self) -> RestClientType:
   # @abstractmethod  
   # async def _create_websocket_client(self) -> Optional[WebSocketClientType]:
   ```

3. **Simplified Initialization Methods**
   ```python
   async def initialize(self) -> None:
       """Initialize the exchange with injected clients."""
       try:
           # Initialize REST client if needed
           if self._rest and hasattr(self._rest, 'initialize'):
               await self._rest.initialize()
               self._rest_connected = True
           
           # Initialize WebSocket client if provided
           if self._ws and hasattr(self._ws, 'initialize'):
               await self._ws.initialize()
               self._ws_connected = self._ws.is_connected
               
           self.logger.info(f"{self._tag} Exchange initialized with injected clients")
           
       except Exception as e:
           self.logger.error("Exchange initialization failed", error=str(e))
           raise InitializationError(f"Exchange initialization failed: {e}")
   ```

#### Task 1.2: Remove Factory Type Constraints
**File**: `src/exchanges/interfaces/composite/types.py`
**Action**: DELETE FILE
**Priority**: Medium
**Estimated Time**: 5 minutes

**Rationale**: No longer needed since we're not using factory methods or complex generic constraints.

### Phase 2: Private Composite Simplification

#### Task 2.1: Update BasePrivateComposite
**File**: `src/exchanges/interfaces/composite/base_private_composite.py`
**Priority**: High
**Estimated Time**: 1 hour

**Changes Required**:

1. **Update Constructor for Dependency Injection**
   ```python
   from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
   from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
   
   class BasePrivateComposite(BaseCompositeExchange[PrivateSpotRest, PrivateSpotWebsocket]):
       def __init__(
           self,
           config: ExchangeConfig,
           rest_client: PrivateSpotRest,
           websocket_client: Optional[PrivateSpotWebsocket] = None,
           logger: Optional[HFTLoggerInterface] = None
       ):
           super().__init__(
               config=config,
               is_private=True,
               rest_client=rest_client,
               websocket_client=websocket_client,
               logger=logger
           )
   ```

2. **Remove ALL Factory Method Implementations**
   ```python
   # REMOVE COMPLETELY:
   # async def _create_rest_client(self) -> PrivateSpotRest:
   # async def _create_websocket_client(self) -> Optional[PrivateSpotWebsocket]:
   ```

3. **Update Initialization Logic**
   ```python
   async def initialize(self) -> None:
       """Initialize private composite with pre-injected clients."""
       try:
           # Call parent initialization for clients
           await super().initialize()
           
           # Load private data via REST
           self.logger.info(f"{self._tag} Loading private data...")
           await self._refresh_exchange_data()
           
           self.logger.info(f"{self._tag} Private composite initialized successfully")
           
       except Exception as e:
           self.logger.error("Private composite initialization failed", error=str(e))
           raise
   ```

4. **Update All Client References** (No Changes Needed)
   - All existing `self._rest` and `self._ws` usage remains the same
   - No changes needed to trading methods since they already use the correct references

#### Task 2.2: Update BasePrivateSpotComposite
**File**: `src/exchanges/interfaces/composite/spot/base_private_spot_composite.py`
**Priority**: Low
**Estimated Time**: 15 minutes

**Changes Required**:

1. **Update Constructor**
   ```python
   class BasePrivateSpotComposite(BasePrivateComposite, WithdrawalMixin):
       def __init__(
           self,
           config: ExchangeConfig,
           rest_client: PrivateSpotRest,
           websocket_client: Optional[PrivateSpotWebsocket] = None,
           logger: Optional[HFTLoggerInterface] = None
       ):
           super().__init__(config, rest_client, websocket_client, logger)
   ```

### Phase 3: Public Composite Simplification

#### Task 3.1: Update CompositePublicSpotExchange
**File**: `src/exchanges/interfaces/composite/spot/base_public_spot_composite.py`
**Priority**: High
**Estimated Time**: 1 hour

**Changes Required**:

1. **Update Constructor for Dependency Injection**
   ```python
   from exchanges.interfaces.rest.spot.rest_spot_public import PublicSpotRest
   from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
   
   class CompositePublicSpotExchange(BaseCompositeExchange[PublicSpotRest, PublicSpotWebsocket]):
       def __init__(
           self,
           config: ExchangeConfig,
           rest_client: PublicSpotRest,
           websocket_client: Optional[PublicSpotWebsocket] = None,
           logger: Optional[HFTLoggerInterface] = None
       ):
           super().__init__(
               config=config,
               is_private=False,
               rest_client=rest_client,
               websocket_client=websocket_client,
               logger=logger
           )
   ```

2. **Remove ALL Factory Method Implementations**
   ```python
   # REMOVE COMPLETELY:
   # async def _create_rest_client(self) -> PublicSpotRest:
   # async def _create_websocket_client(self) -> Optional[PublicSpotWebsocket]:
   ```

3. **Update Initialization Logic**
   ```python
   async def initialize(self) -> None:
       """Initialize public composite with pre-injected clients."""
       try:
           init_start = time.perf_counter()
           
           # Call parent initialization for clients
           await super().initialize()
           
           # Load initial market data via REST
           self.logger.info(f"{self._tag} Loading initial market data...")
           await asyncio.gather(
               self._load_symbols_info(),
               self._refresh_exchange_data(),
               return_exceptions=True
           )
           
           init_duration = time.perf_counter() - init_start
           self.logger.info(f"{self._tag} Public composite initialized in {init_duration:.3f}s")
           
       except Exception as e:
           self.logger.error("Public composite initialization failed", error=str(e))
           raise
   ```

4. **Update All Client References** (No Changes Needed)
   - All existing `self._rest` and `self._ws` usage remains the same
   - No changes needed to market data methods

### Phase 4: Integration Updates

#### Task 4.1: Update MEXC Public Exchange
**File**: `src/exchanges/integrations/mexc/mexc_composite_public.py`
**Priority**: Medium
**Estimated Time**: 30 minutes

**Changes Required**:

1. **Update Constructor to Remove Factory Methods**
   ```python
   class MexcCompositePublic(CompositePublicSpotExchange):
       def __init__(
           self,
           config: ExchangeConfig,
           rest_client: MexcPublicRest,
           websocket_client: Optional[MexcPublicWebsocket] = None,
           logger: Optional[HFTLoggerInterface] = None
       ):
           super().__init__(config, rest_client, websocket_client, logger)
   ```

2. **Remove ALL Factory Method Implementations**
   ```python
   # REMOVE COMPLETELY:
   # async def _create_rest_client(self) -> PublicSpotRest:
   # async def _create_websocket_client(self) -> Optional[PublicSpotWebsocket]:
   ```

#### Task 4.2: Update Gate.io Public Exchange
**File**: `src/exchanges/integrations/gateio/gateio_composite_public.py`
**Priority**: Medium
**Estimated Time**: 30 minutes

**Changes Required**: Same pattern as Task 4.1

#### Task 4.3: Update Gate.io Futures Public Exchange
**File**: `src/exchanges/integrations/gateio/gateio_futures_composite_public.py`
**Priority**: Medium
**Estimated Time**: 30 minutes

**Changes Required**: Same pattern as Task 4.1

### Phase 5: Factory Pattern Updates

#### Task 5.1: Update Exchange Factory for Constructor Injection
**File**: `src/exchanges/factory.py` or relevant factory files
**Priority**: Critical
**Estimated Time**: 1 hour

**Changes Required**:

1. **Update Factory to Create and Inject Clients**
   ```python
   async def create_public_exchange(
       exchange: ExchangeEnum,
       config: ExchangeConfig,
       logger: Optional[HFTLoggerInterface] = None
   ) -> CompositePublicSpotExchange:
       """Create public exchange with dependency injection."""
       
       # Create REST client
       rest_client = await create_rest_client(exchange, config, is_private=False)
       
       # Create WebSocket client (optional)
       websocket_client = None
       if config.enable_websocket:
           websocket_client = await create_websocket_client(exchange, config, is_private=False)
       
       # Create composite with injected dependencies
       if exchange == ExchangeEnum.MEXC:
           return MexcCompositePublic(config, rest_client, websocket_client, logger)
       elif exchange == ExchangeEnum.GATEIO:
           return GateioCompositePublic(config, rest_client, websocket_client, logger)
       # ... other exchanges
       
       raise ValueError(f"Unsupported exchange: {exchange}")
   ```

### Phase 6: Testing and Validation

#### Task 6.1: Update Unit Tests
**Files**: All test files using composite exchanges
**Priority**: High
**Estimated Time**: 1 hour

**Changes Required**:
- Update test mocks to create clients before composite
- Remove factory method mocking
- Test constructor injection directly

#### Task 6.2: Integration Test Validation
**Priority**: Critical
**Estimated Time**: 30 minutes

**Test Cases**:
- Verify factory creates exchanges correctly with injected clients
- Verify all exchange operations work with new pattern
- Verify initialization flow works correctly

## Implementation Order

1. **Phase 1**: Update base classes (breaking change foundation)
2. **Phase 5**: Update factory pattern (critical for creation)
3. **Phase 2-4**: Update implementations (can be done in parallel)
4. **Phase 6**: Testing and validation

## Success Criteria

### Code Simplification
- **Zero Factory Methods**: No abstract factory methods in any composite class
- **Clear Dependencies**: All dependencies injected through constructor
- **Reduced Complexity**: Simpler inheritance hierarchy

### Functional Requirements
- **No Functionality Loss**: All existing features continue to work
- **Performance Maintained**: No degradation in initialization or operation speed
- **Type Safety**: Strong typing maintained with constructor injection

### Breaking Change Acceptance
- **Clean Architecture**: Simplified dependency management
- **Explicit Dependencies**: Clear dependency injection pattern
- **Future Maintainability**: Easier to test and extend

## Risk Mitigation

### Factory Creation Issues
- **Risk**: Factory becomes complex with client creation
- **Mitigation**: Keep factory focused, delegate client creation to specialized functions
- **Fallback**: Implement builder pattern if factory becomes unwieldy

### Constructor Complexity
- **Risk**: Constructors become too complex with many parameters
- **Mitigation**: Use configuration objects and optional parameters
- **Fallback**: Implement builder pattern for complex initialization

This refactoring results in a **clean, simple architecture** where all dependencies are explicit and injected through constructors, eliminating the complexity of abstract factory methods while maintaining type safety and functionality.