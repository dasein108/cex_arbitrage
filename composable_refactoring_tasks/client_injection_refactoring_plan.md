# Client Injection Refactoring Plan

**Objective**: Replace factory function pattern with direct client injection to eliminate redundancy and improve code clarity.

## Current State Analysis

### **Problem Statement**
The current factory function approach adds unnecessary abstraction:
```python
# Current (overly complex)
rest_client_factory=lambda cfg, log: MexcPrivateSpotRest(cfg, log)

# Proposed (direct and clear)
rest_client=MexcPrivateSpotRest(config, logger)
```

### **Architecture Overview**
```
BaseCompositeExchange
└── BasePrivateComposite[RestT, WebsocketT] 
    ├── CompositePrivateSpotExchange
    │   ├── MexcCompositePrivateSpotExchange
    │   └── GateioCompositePrivateSpotExchange  
    └── CompositePrivateFuturesExchange
        └── GateioFuturesCompositePrivateExchange
```

## Detailed Implementation Plan

### **Phase 1: Update Base Class Architecture**

#### **Task 1.1: Modify BasePrivateComposite Constructor**
**File**: `src/exchanges/interfaces/composite/base_private_composite.py`

**Current Signature**:
```python
def __init__(self, config: ExchangeConfig, exchange_type: ExchangeType,
             logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None,
             rest_client_factory=None, websocket_client_factory=None) -> None:
```

**Target Signature**:
```python
def __init__(self, config: ExchangeConfig, exchange_type: ExchangeType,
             logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None,
             rest_client: Optional[RestT] = None,
             websocket_client: Optional[WebsocketT] = None) -> None:
```

**Changes Required**:
1. Replace factory parameter names with direct client parameters
2. Update parameter types to use generic types `RestT` and `WebsocketT`
3. Store clients directly instead of factory functions:
   ```python
   self._private_rest = rest_client
   self._private_ws = websocket_client
   ```

#### **Task 1.2: Remove Factory Methods**
**File**: `src/exchanges/interfaces/composite/base_private_composite.py`

**Remove These Methods**:
```python
async def _create_private_rest(self) -> RestT:
    # Remove entire method

async def _create_private_websocket(self) -> Optional[WebsocketT]:
    # Remove entire method
```

**Update Initialization Logic**:
```python
async def initialize(self, symbols_info: SymbolsInfo) -> None:
    # Instead of: self._private_rest = await self._create_private_rest()
    # Use: Client already available as self._private_rest
    
    if self._private_rest is None:
        raise InitializationError("No REST client provided during construction")
```

### **Phase 2: Update Intermediate Classes**

#### **Task 2.1: Update CompositePrivateSpotExchange**
**File**: `src/exchanges/interfaces/composite/spot/base_private_spot_composite.py`

**Current Constructor**:
```python
def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None,
             rest_client_factory=None, websocket_client_factory=None) -> None:
    super().__init__(config, ExchangeType.SPOT, logger, handlers,
                     rest_client_factory, websocket_client_factory)
```

**Target Constructor**:
```python
def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None,
             rest_client: Optional[PrivateSpotRest] = None,
             websocket_client: Optional[PrivateSpotWebsocket] = None) -> None:
    super().__init__(config, ExchangeType.SPOT, logger, handlers,
                     rest_client, websocket_client)
```

**Type Specification**:
- Specify concrete types instead of generic `RestT`/`WebsocketT`
- Use `PrivateSpotRest` and `PrivateSpotWebsocket`

#### **Task 2.2: Update CompositePrivateFuturesExchange**
**File**: `src/exchanges/interfaces/composite/futures/base_private_futures_composite.py`

**Similar Changes**:
- Replace factory parameters with direct client parameters
- Use `PrivateFuturesRest` and `PrivateFuturesWebsocket` types
- Maintain futures-specific state initialization

### **Phase 3: Update Exchange Implementations**

#### **Task 3.1: Update MexcCompositePrivateSpotExchange**
**File**: `src/exchanges/integrations/mexc/mexc_composite_private.py`

**Current Constructor**:
```python
def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None):
    super().__init__(config, logger, handlers,
                     rest_client_factory=lambda cfg, log: MexcPrivateSpotRest(cfg, log),
                     websocket_client_factory=lambda cfg, handlers, log: MexcPrivateSpotWebsocket(
                         config=cfg, handlers=handlers, logger=log))
```

**Target Constructor**:
```python
def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None):
    # Create clients directly
    rest_client = MexcPrivateSpotRest(config, logger)
    websocket_client = MexcPrivateSpotWebsocket(config, handlers, logger)
    
    super().__init__(config, logger, handlers, rest_client, websocket_client)
```

**Benefits**:
- Eliminates lambda functions
- Makes client creation explicit and readable
- Enables better error handling at construction time

#### **Task 3.2: Update GateioCompositePrivateSpotExchange**
**File**: `src/exchanges/integrations/gateio/gateio_composite_private.py`

**Similar Changes**:
```python
def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None):
    rest_client = GateioPrivateSpotRest(config, logger)
    websocket_client = GateioPrivateSpotWebsocket(config, handlers, logger)
    
    super().__init__(config, logger, handlers, rest_client, websocket_client)
```

#### **Task 3.3: Update GateioFuturesCompositePrivateExchange**
**File**: `src/exchanges/integrations/gateio/gateio_futures_composite_private.py`

**Target Changes**:
```python
def __init__(self, config, logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None):
    rest_client = GateioPrivateFuturesRest(config, logger)
    websocket_client = GateioPrivateFuturesWebsocket(config, handlers)
    
    super().__init__(config, logger, handlers, rest_client, websocket_client)
```

### **Phase 4: Update Initialization Logic**

#### **Task 4.1: Modify BasePrivateComposite.initialize()**
**File**: `src/exchanges/interfaces/composite/base_private_composite.py`

**Current Logic**:
```python
async def initialize(self, symbols_info: SymbolsInfo) -> None:
    # Step 1: Create REST clients using abstract factory
    self._private_rest = await self._create_private_rest()
    
    # Step 3: Create WebSocket clients with handler injection
    await self._initialize_private_websocket()
```

**Target Logic**:
```python
async def initialize(self, symbols_info: SymbolsInfo) -> None:
    # Validate clients were provided during construction
    if self._private_rest is None:
        raise InitializationError("No REST client provided during construction")
        
    # Initialize WebSocket if provided
    if self._private_ws:
        await self._private_ws.initialize()
    else:
        self.logger.info("No WebSocket client provided - continuing without real-time data")
```

**Simplified Flow**:
1. Validate required clients exist
2. Initialize WebSocket if available
3. No client creation during initialize (already done in constructor)

#### **Task 4.2: Remove Factory-Related Methods**
**Files**: All composite classes

**Methods to Remove**:
- `_create_private_rest()` 
- `_create_private_websocket()`
- `_initialize_private_websocket()` (if only used for factory creation)

**Methods to Simplify**:
- Initialization methods that call factory methods

### **Phase 5: Error Handling Updates**

#### **Task 5.1: Constructor Error Handling**
**Pattern for All Exchange Implementations**:
```python
def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None):
    try:
        # Create clients with proper error context
        rest_client = MexcPrivateSpotRest(config, logger)
        websocket_client = MexcPrivateSpotWebsocket(config, handlers, logger)
        
        super().__init__(config, logger, handlers, rest_client, websocket_client)
        
    except Exception as e:
        # Use logger if available, otherwise fall back to basic logging
        if logger:
            logger.error(f"Failed to create {self.__class__.__name__}", error=str(e))
        raise InitializationError(f"Exchange construction failed: {e}") from e
```

#### **Task 5.2: Runtime Validation**
**In BasePrivateComposite.initialize()**:
```python
async def initialize(self, symbols_info: SymbolsInfo) -> None:
    # Validate required components
    if self._private_rest is None:
        raise InitializationError("REST client is required but was not provided")
    
    # Test client connectivity (optional)
    try:
        # Could add a simple health check here
        # await self._private_rest.health_check()
        pass
    except Exception as e:
        self.logger.warning("REST client health check failed", error=str(e))
```

### **Phase 6: Type Safety and Documentation**

#### **Task 6.1: Update Type Hints**
**Ensure Consistent Types**:
```python
# BasePrivateComposite
rest_client: Optional[RestT] = None
websocket_client: Optional[WebsocketT] = None

# CompositePrivateSpotExchange  
rest_client: Optional[PrivateSpotRest] = None
websocket_client: Optional[PrivateSpotWebsocket] = None

# CompositePrivateFuturesExchange
rest_client: Optional[PrivateFuturesRest] = None
websocket_client: Optional[PrivateFuturesWebsocket] = None
```

#### **Task 6.2: Update Documentation**
**Constructor Docstrings**:
```python
def __init__(self, config: ExchangeConfig, exchange_type: ExchangeType,
             logger: Optional[HFTLoggerInterface] = None,
             handlers: Optional[PrivateWebsocketHandlers] = None,
             rest_client: Optional[RestT] = None,
             websocket_client: Optional[WebsocketT] = None) -> None:
    """
    Initialize base private exchange interface with direct client injection.
    
    Args:
        config: Exchange configuration with API credentials
        exchange_type: Exchange type (SPOT, FUTURES) for behavior customization
        logger: Optional injected HFT logger (auto-created if not provided)
        handlers: Optional private WebSocket handlers
        rest_client: Pre-constructed REST client for API operations
        websocket_client: Pre-constructed WebSocket client for real-time data
        
    Raises:
        InitializationError: If required clients are not provided
    """
```

## Testing Strategy

### **Phase 7: Validation and Testing**

#### **Task 7.1: Compilation Tests**
```bash
# Test all files compile without errors
python -m py_compile src/exchanges/interfaces/composite/base_private_composite.py
python -m py_compile src/exchanges/interfaces/composite/spot/base_private_spot_composite.py
python -m py_compile src/exchanges/interfaces/composite/futures/base_private_futures_composite.py
python -m py_compile src/exchanges/integrations/mexc/mexc_composite_private.py
python -m py_compile src/exchanges/integrations/gateio/gateio_composite_private.py
python -m py_compile src/exchanges/integrations/gateio/gateio_futures_composite_private.py
```

#### **Task 7.2: Import Tests**
```python
# Test basic instantiation works
from exchanges.integrations.mexc.mexc_composite_private import MexcCompositePrivateSpotExchange
from config.structs import ExchangeConfig

config = MockConfig()
exchange = MexcCompositePrivateSpotExchange(config)
assert exchange._private_rest is not None
assert exchange._private_ws is not None
```

#### **Task 7.3: Functional Tests**
- Test that initialization works without factory methods
- Test error handling when clients are not provided
- Test backward compatibility with existing usage patterns

## Benefits of This Refactoring

### **1. Code Simplification**
- **Eliminates**: Lambda functions and factory method abstractions
- **Reduces**: Lines of code across all exchange implementations
- **Improves**: Readability and maintainability

### **2. Performance Improvements**
- **Removes**: Function call overhead from factory pattern
- **Eliminates**: Lambda function object storage
- **Simplifies**: Initialization flow

### **3. Better Error Handling**
- **Constructor-time**: Client creation errors happen immediately with full context
- **Clear Messages**: Direct client instantiation provides clearer error messages
- **Early Validation**: Problems detected at construction rather than during usage

### **4. Enhanced Type Safety**
- **Explicit Types**: Direct client parameters have clear, specific types
- **IDE Support**: Better autocompletion and type checking
- **Compile-time Validation**: Type errors caught earlier

### **5. Improved Testability**
- **Direct Injection**: Easier to inject mock clients for testing
- **No Factory Mocking**: Simpler test setup without factory function mocking
- **Clear Dependencies**: Explicit client dependencies are easier to understand and test

## Implementation Timeline

### **Week 1**: Foundation
- Tasks 1.1-1.2: Update BasePrivateComposite
- Task 4.1: Update initialization logic
- Task 7.1: Compilation validation

### **Week 2**: Intermediate Classes  
- Tasks 2.1-2.2: Update composite classes
- Task 6.1: Type safety updates
- Task 7.2: Import validation

### **Week 3**: Exchange Implementations
- Tasks 3.1-3.3: Update all exchange implementations
- Task 5.1: Error handling improvements
- Task 7.3: Functional validation

### **Week 4**: Documentation and Cleanup
- Task 6.2: Documentation updates
- Task 5.2: Runtime validation
- Final testing and validation

## Risk Mitigation

### **Backward Compatibility**
- Constructor signatures remain the same for end users
- Internal changes are transparent to external consumers
- Existing usage patterns continue to work

### **Error Handling**
- Comprehensive error handling at construction time
- Clear error messages for debugging
- Graceful degradation when optional components (WebSocket) are not available

### **Type Safety**
- Maintain generic constraints throughout the hierarchy
- Ensure type checking works at all levels
- Validate that IDEs provide proper autocompletion

This refactoring will significantly simplify the codebase while maintaining all existing functionality and improving performance, readability, and maintainability.