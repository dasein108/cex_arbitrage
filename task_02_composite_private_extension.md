# Task 02: Extend CompositePrivateExchange with Factory Pattern and Orchestration Logic

## Objective

Transform `CompositePrivateExchange` from an abstract interface into a concrete base class that eliminates code duplication across exchange implementations by adding patterns from UnifiedCompositeExchange.

**Reference Implementation**: UnifiedCompositeExchange (1190 lines) is the PERFECT TEMPLATE containing exactly what needs to be added.

## Critical Discovery from Task 01

UnifiedCompositeExchange already demonstrates the complete implementation pattern needed:
- ✅ Abstract factory methods for client creation (lines 200-220)
- ✅ Template method pattern for initialization orchestration (lines 45-200)
- ✅ Constructor injection for WebSocket handlers (lines 600-650)
- ✅ Centralized connection and resource management (lines 700-850)
- ✅ HFT-compliant with proper performance tracking (throughout)

## Current State Analysis

**File**: `src/exchanges/interfaces/composite/base_private_exchange.py` (996 lines)

**Current Architecture** (Updated September 2025):
- ✅ Complete abstract interface for private trading operations
- ✅ Executed orders state management ALREADY IMPLEMENTED (lines 68-71)
- ✅ Abstract factory methods ALREADY IMPLEMENTED (lines 349-372)
- ✅ Concrete orchestration methods ALREADY IMPLEMENTED (lines 375+)
- ✅ WebSocket handler injection patterns ALREADY IMPLEMENTED
- ✅ HFT-compliant approach with executed orders caching
- ✅ Comprehensive trading and withdrawal operations

**Current Implementation Status**:
- ✅ `_executed_orders` state management exists (line 69)
- ✅ Factory methods `_create_private_rest` and `_create_private_ws_with_handlers` implemented
- ✅ Concrete `_load_balances()` method implemented (line 379)
- ✅ Enhanced `_update_order()` with lifecycle management implemented
- ✅ `get_active_order()` method with 3-tier lookup ALREADY IMPLEMENTED

**CRITICAL ARCHITECTURAL ISSUE - Futures-Specific Code in Spot Base Class**:
- ❌ **Position state and handling** incorrectly placed in base_private_exchange.py (should be futures-only)
- ❌ `self._positions: Dict[Symbol, Position] = {}` at line 66 - belongs in futures subclass
- ❌ `async def _load_positions()` at line 433 - futures-specific logic with spot NotImplementedError
- ❌ `async def _handle_position_event()` at line 683 - position WebSocket handling for futures only
- ❌ `def _update_position()` at line 916 - position state management for futures only
- ❌ Position metrics in `get_trading_stats()` at line 943 - futures-specific monitoring

**Remaining Gaps** (Architectural Cleanup Required):
- ⚠️ May need optimization for HFT performance requirements
- ⚠️ Cache size management could be enhanced  
- ⚠️ Error handling patterns could be standardized
- ⚠️ Race condition protection needed for order state transitions
- 🚨 **CRITICAL**: Position-related code must be moved to base_private_futures_exchange.py

## Critical Race Condition Fix Required

**Issue**: The current `_update_order()` implementation may have race conditions when WebSocket updates and REST fallbacks modify order state simultaneously.

**Solution**: Add per-symbol async locking for atomic order state operations:

```python
# Add to constructor:
self._order_state_locks: Dict[Symbol, asyncio.Lock] = {}

async def _get_symbol_lock(self, symbol: Symbol) -> asyncio.Lock:
    """Get or create atomic lock for symbol-specific operations."""
    if symbol not in self._order_state_locks:
        self._order_state_locks[symbol] = asyncio.Lock()
    return self._order_state_locks[symbol]

# Enhanced get_active_order with atomic operations:
async def get_active_order(self, symbol: Symbol, order_id: OrderId) -> Optional[Order]:
    """Get order with atomic state management."""
    async with await self._get_symbol_lock(symbol):
        # All existing logic here - now protected from race conditions
        # ... existing implementation
        pass

# Enhanced _update_order with atomic operations:
async def _update_order(self, order: Order) -> None:
    """Update order state atomically."""
    async with await self._get_symbol_lock(order.symbol):
        # All existing logic here - now race condition safe
        # ... existing implementation  
        pass

# Enhanced cache management with LRU eviction:
async def _cleanup_executed_orders_cache(self, symbol: Symbol) -> None:
    """Clean up executed orders cache when it exceeds limits."""
    if symbol not in self._executed_orders:
        return
        
    cache = self._executed_orders[symbol]
    if len(cache) > self._max_executed_orders_per_symbol:
        # Simple LRU: remove oldest 20% when limit exceeded
        removal_count = int(len(cache) * 0.2)
        oldest_orders = sorted(cache.values(), key=lambda o: o.timestamp)[:removal_count]
        
        for order in oldest_orders:
            del cache[order.order_id]
            
        self.logger.info("Executed orders cache cleaned",
                        symbol=symbol,
                        removed=removal_count, 
                        remaining=len(cache))

## Partial Failure Recovery Enhancement

**Issue**: Connection recovery doesn't handle partial failures (e.g., REST success but WebSocket failure).

**Solution**: Add state validation and rollback mechanisms:

```python
async def _validate_connection_state(self) -> Dict[str, bool]:
    """Validate connection state and detect partial failures."""
    return {
        "private_rest": self._private_rest_connected and self._private_rest is not None,
        "private_ws": self._private_ws_connected and self._private_ws is not None,
        "public_rest": self._public_rest_connected and self._public_rest is not None,
        "public_ws": self._public_ws_connected and self._public_ws is not None,
    }

async def _recover_from_partial_failure(self) -> None:
    """Recover from partial connection failures with state validation."""
    connection_state = await self._validate_connection_state()
    
    # If any private connections failed but others succeeded, reset all private state
    if connection_state["private_rest"] != connection_state["private_ws"]:
        self.logger.warning("Partial private connection failure detected - resetting private state")
        
        # Clear potentially inconsistent state
        self._balances.clear()
        self._open_orders.clear() 
        
        # Attempt full private reconnection
        try:
            if not connection_state["private_rest"]:
                await self._initialize_private_rest()
            if not connection_state["private_ws"]: 
                await self._initialize_private_websocket()
                
            # Reload private data if both connections restored
            if self._private_rest_connected and self._private_ws_connected:
                await self._load_private_data()
                
        except Exception as e:
            self.logger.error("Failed to recover from partial failure", error=str(e))
            raise BaseExchangeError(f"Partial failure recovery failed: {e}") from e
```

## New Requirements Integration

### Executed Orders State Management Requirements

**Added Requirements** (September 2025):
1. **Executed Orders State Management**: Track completed orders alongside open orders
2. **Enhanced Order Retrieval**: Smart lookup with fallback to REST API calls  
3. **Order Lifecycle Management**: Proper transitions between open → executed states
4. **HFT-Safe Implementation**: No dangerous caching violations per HFT Caching Policy

**New Data Structures Required**:
```python
# Add to CompositePrivateExchange state management
self._executed_orders: Dict[Symbol, Dict[OrderId, Order]] = {}  # New executed orders cache
self._open_orders: Dict[Symbol, List[Order]] = {}              # Existing open orders (unchanged)
```

**New Core Method Required**:
```python
async def get_active_order(self, symbol: Symbol, order_id: OrderId) -> Optional[Order]:
    """
    Retrieve order with smart lookup priority:
    1. Check _open_orders[symbol] first (fastest lookup)
    2. Check _executed_orders[symbol][order_id] if not found
    3. Fallback to REST API call if still not found
    4. Cache REST result in _executed_orders (HFT-safe for completed orders)
    
    HFT COMPLIANCE: Only executed orders are cached (static data).
    Open orders remain real-time without caching.
    """
    pass
```

## Implementation Plan (Updated - Most Work Already Complete)

Since the base class already contains 80%+ of the required functionality, the implementation plan is now focused on **architectural cleanup (positions migration)** and refinements rather than new development.

## PRIORITY PHASE 0: Futures-Specific Code Migration (CRITICAL)

**Issue**: Position-related functionality is incorrectly implemented in the general spot base class. This violates architectural separation and causes confusion.

### Step 1: Remove Position Code from base_private_exchange.py

**Code to Remove** (7 locations):
```python
# Constructor (line 66)
self._positions: Dict[Symbol, Position] = {}

# Abstract Property (lines 110-117)  
@property
@abstractmethod
def positions(self) -> Dict[Symbol, Position]:
    """Get current positions (for margin/futures trading)."""
    pass

# Loading Method (lines 433-458)
async def _load_positions(self) -> None:
    """Load positions from REST API (for margin/futures)."""
    # ... complete method implementation

# Event Handler (lines 683-693)
async def _handle_position_event(self, event: PositionUpdateEvent) -> None:
    """Handle position update events from private WebSocket."""
    # ... complete implementation

# Update Method (lines 916-924)  
def _update_position(self, position: Position) -> None:
    """Update internal position state."""
    # ... complete implementation

# Initialization Reference (line 551)
self._load_positions(),

# WebSocket Handler Registration (line 596)
position_handler=self._handle_position_event,

# Data Refresh Reference (line 748)
await self._load_positions()

# Monitoring Integration (line 943)
'active_positions': len(self._positions),
```

### Step 2: Add Position Code to base_private_futures_exchange.py

**Code to Add** (ensure futures subclass contains all position functionality):
- Move all 7 code sections from Step 1 into the futures subclass
- Override `initialize()` to include position loading
- Override `_refresh_exchange_data()` to include position refresh  
- Extend `get_futures_trading_stats()` with position metrics
- Ensure WebSocket handlers include position_handler

### Step 3: Update Architecture

**After Migration**:
- **Spot exchanges** (base_private_exchange): balances + orders only
- **Futures exchanges** (base_private_futures_exchange): balances + orders + positions  
- **Clear separation**: Position functionality only available where needed

This migration fixes the architectural violation and provides proper separation of concerns.

### Phase 1: Validate Executed Orders State Management ✅ COMPLETED

**ALREADY IMPLEMENTED**: Executed orders state management exists in constructor and properties:

```python
def __init__(self, config: ExchangeConfig):
    super().__init__(config=config, is_private=True)
    
    # Existing private data state
    self._balances: Dict[Symbol, AssetBalance] = {}
    self._open_orders: Dict[Symbol, List[Order]] = {}
    self._positions: Dict[Symbol, Position] = {}
    
    # NEW: Executed orders state management
    self._executed_orders: Dict[Symbol, Dict[OrderId, Order]] = {}
    
    # Client instances (managed by factory methods)
    self._private_rest: Optional[PrivateSpotRest] = None
    self._private_ws: Optional[PrivateSpotWebsocket] = None
```

**Add Properties for Executed Orders**:
```python
@property
def executed_orders(self) -> Dict[Symbol, Dict[OrderId, Order]]:
    """
    Get cached executed orders (filled/canceled/expired).
    
    HFT COMPLIANCE: These are static completed orders - safe to cache.
    Real-time trading data (open orders, balances) remain uncached.
    """
    return self._executed_orders.copy()
```

### Phase 2: Validate Abstract Factory Methods ✅ COMPLETED

**ALREADY IMPLEMENTED**: These factory methods exist in base_private_exchange.py (lines 349-372):

```python
@abstractmethod
async def _create_private_rest(self) -> BasePrivateRest:
    """
    Create exchange-specific private REST client.
    PATTERN: Copied from UnifiedCompositeExchange line 200
    """
    pass

@abstractmethod  
async def _create_private_ws_with_handlers(self, handlers: PrivateWebsocketHandlers) -> Optional[BasePrivateWebsocket]:
    """
    Create exchange-specific private WebSocket client with handler objects.
    PATTERN: Copied from UnifiedCompositeExchange line 210
    """
    pass

# These should be inherited from CompositePublicExchange parent
# But need to ensure they exist:
@abstractmethod
async def _create_public_rest(self) -> BasePublicRest:
    """Create exchange-specific public REST client."""
    pass

@abstractmethod
async def _create_public_ws_with_handlers(self, handlers: PublicWebsocketHandlers) -> Optional[BasePublicWebsocket]:
    """Create exchange-specific public WebSocket client."""
    pass
```

### Phase 3: Validate Concrete Orchestration Logic ✅ COMPLETED  

**ALREADY IMPLEMENTED**: Concrete orchestration methods exist (lines 375+):

The template methods are already implemented including:

```python
async def _load_balances(self) -> None:
    """
    Load account balances from REST API with error handling and metrics.
    PATTERN: Copied from UnifiedCompositeExchange line 350
    """
    if not self._private_rest:
        self.logger.warning("No private REST client available for balance loading")
        return
        
    try:
        with LoggingTimer(self.logger, "load_balances") as timer:
            balances_data = await self._private_rest.get_balances()
            
            # Update internal state (pattern from line 360)
            for asset, balance in balances_data.items():
                self._balances[asset] = balance
                
        self.logger.info("Balances loaded successfully",
                        balance_count=len(balances_data),
                        load_time_ms=timer.elapsed_ms)
                        
    except Exception as e:
        self.logger.error("Failed to load balances", error=str(e))
        raise BaseExchangeError(f"Balance loading failed: {e}")

async def _load_open_orders(self) -> None:
    """
    Load open orders from REST API with error handling.
    PATTERN: Copied from UnifiedCompositeExchange line 380
    ENHANCED: Initialize executed orders cache per symbol
    """
    if not self._private_rest:
        return
        
    try:
        with LoggingTimer(self.logger, "load_open_orders") as timer:
            # Load orders for each active symbol
            for symbol in self.active_symbols:
                orders = await self._private_rest.get_open_orders(symbol=symbol)
                self._open_orders[symbol] = orders
                
                # NEW: Initialize executed orders cache for symbol
                if symbol not in self._executed_orders:
                    self._executed_orders[symbol] = {}
                
        self.logger.info("Open orders loaded",
                        symbol_count=len(self.active_symbols),
                        open_orders_count=sum(len(orders) for orders in self._open_orders.values()),
                        load_time_ms=timer.elapsed_ms)
                        
    except Exception as e:
        self.logger.error("Failed to load open orders", error=str(e))
        raise

async def get_active_order(self, symbol: Symbol, order_id: OrderId) -> Optional[Order]:
    """
    NEW METHOD: Get order with smart lookup priority and HFT-safe caching.
    
    Lookup Priority:
    1. Check _open_orders[symbol] first (real-time, no caching)  
    2. Check _executed_orders[symbol][order_id] (cached executed orders)
    3. Fallback to REST API and cache result in _executed_orders
    
    HFT COMPLIANCE: Only executed orders cached (static completed data).
    Open orders remain real-time to avoid stale price execution.
    
    Args:
        symbol: Trading symbol
        order_id: Order identifier
        
    Returns:
        Order object if found, None otherwise
    """
    # Step 1: Check open orders first (real-time lookup)
    if symbol in self._open_orders:
        for order in self._open_orders[symbol]:
            if order.order_id == order_id:
                self.logger.debug("Order found in open orders cache", 
                                order_id=order_id, status=order.status)
                return order
    
    # Step 2: Check executed orders cache
    if symbol in self._executed_orders and order_id in self._executed_orders[symbol]:
        cached_order = self._executed_orders[symbol][order_id]
        self.logger.debug("Order found in executed orders cache", 
                        order_id=order_id, status=cached_order.status)
        return cached_order
    
    # Step 3: Fallback to REST API call
    if not self._private_rest:
        self.logger.warning("No private REST client available for order lookup", 
                          order_id=order_id)
        return None
    
    try:
        with LoggingTimer(self.logger, f"get_order_fallback_{symbol}") as timer:
            order = await self._private_rest.get_order(symbol, order_id)
            
            if order and order.status in ['filled', 'canceled', 'expired']:
                # Cache executed orders (HFT-safe - completed orders are static)
                if symbol not in self._executed_orders:
                    self._executed_orders[symbol] = {}
                self._executed_orders[symbol][order_id] = order
                
                self.logger.info("Order cached in executed orders",
                               order_id=order_id, status=order.status, 
                               lookup_time_ms=timer.elapsed_ms)
            
            return order
            
    except Exception as e:
        self.logger.error("Failed to get order via REST fallback", 
                        order_id=order_id, error=str(e))
        return None
```

### Phase 4: Add Enhanced Order Lifecycle Management

**CRITICAL**: Update the existing `_update_order` method to properly manage order transitions between open and executed states:

```python
def _update_order(self, order: Order) -> None:
    """
    Update internal order state with enhanced lifecycle management.
    ENHANCED: Proper transitions between open → executed order states.
    
    Args:
        order: Updated order information
    """
    symbol = order.symbol
    if symbol not in self._open_orders:
        self._open_orders[symbol] = []
    
    # Ensure executed orders dict exists for symbol
    if symbol not in self._executed_orders:
        self._executed_orders[symbol] = {}

    # Update existing order or add new one
    existing_orders = self._open_orders[symbol]
    for i, existing_order in enumerate(existing_orders):
        if existing_order.order_id == order.order_id:
            if order.status in ['filled', 'canceled', 'expired']:
                # ENHANCED: Move to executed orders instead of just removing
                existing_orders.pop(i)
                self._executed_orders[symbol][order.order_id] = order
                
                self.logger.info("Order moved to executed orders",
                               order_id=order.order_id,
                               symbol=symbol,
                               status=order.status,
                               executed_quantity=getattr(order, 'filled_quantity', 0))
            else:
                # Update existing open order
                existing_orders[i] = order
                self.logger.debug("Open order updated",
                                order_id=order.order_id, 
                                status=order.status)
            return

    # Add new order if it's still open
    if order.status not in ['filled', 'canceled', 'expired']:
        existing_orders.append(order)
        self.logger.debug("New open order added",
                        order_id=order.order_id, 
                        symbol=symbol)
    else:
        # Add directly to executed orders if already completed
        self._executed_orders[symbol][order.order_id] = order
        self.logger.info("New executed order cached",
                       order_id=order.order_id,
                       symbol=symbol, 
                       status=order.status)
```

### Phase 5: Add Connection Management

Add client lifecycle management properties and methods:

```python
def __init__(self, config: ExchangeConfig):
    super().__init__(config=config, is_private=True)
    
    # Existing private data state
    self._balances: Dict[Symbol, AssetBalance] = {}
    self._open_orders: Dict[Symbol, List[Order]] = {}
    self._positions: Dict[Symbol, Position] = {}
    
    # NEW: Executed orders state management
    self._executed_orders: Dict[Symbol, Dict[OrderId, Order]] = {}
    
    # Client instances (managed by factory methods)
    self._private_rest: Optional[PrivateSpotRest] = None
    self._private_ws: Optional[PrivateSpotWebsocket] = None
    
    # Connection status tracking
    self._private_rest_connected = False
    self._private_ws_connected = False
```

### Phase 6: Add Template Method Initialization (CRITICAL PATTERN)

**Copy EXACT initialization pattern from UnifiedCompositeExchange (lines 45-200)**:

```python
async def initialize(self, symbols_info: SymbolsInfo) -> None:
    """
    Initialize private exchange with template method orchestration.
    PATTERN: Copied from UnifiedCompositeExchange line 45-100
    
    ELIMINATES DUPLICATION: This orchestration logic was previously 
    duplicated across ALL exchange implementations (80%+ code reduction).
    """
    # Initialize public functionality first (parent class)
    await super().initialize(symbols_info)
    
    try:
        # Step 1: Create REST clients using abstract factory
        self.logger.info(f"{self._tag} Creating REST clients...")
        self._private_rest = await self._create_private_rest()
        
        # Step 2: Load private data via REST (parallel loading)
        self.logger.info(f"{self._tag} Loading private data...")
        await asyncio.gather(
            self._load_balances(),
            self._load_open_orders(),
            self._load_positions() if hasattr(self, '_load_positions') else asyncio.sleep(0),
            return_exceptions=True
        )
        
        # Step 3: Create WebSocket clients with handler injection
        if self.config.enable_websocket:
            self.logger.info(f"{self._tag} Creating WebSocket clients...")
            await self._initialize_private_websocket()
        
        # Step 4: Start private streaming if WebSocket enabled
        if self._private_ws:
            self.logger.info(f"{self._tag} Starting private streaming...")
            await self._start_private_streaming()
        
        self.logger.info(f"{self._tag} private initialization completed",
                        has_rest=self._private_rest is not None,
                        has_ws=self._private_ws is not None,
                        balance_count=len(self._balances),
                        order_count=sum(len(orders) for orders in self._open_orders.values()))
        
    except Exception as e:
        self.logger.error(f"Private exchange initialization failed: {e}")
        await self.close()  # Cleanup on failure
        raise
```

### Phase 7: Add Constructor Injection for WebSocket Handlers (KEY PATTERN)

**Copy EXACT handler injection pattern from UnifiedCompositeExchange (lines 600-650)**:

```python
async def _initialize_private_websocket(self) -> None:
    """
    Initialize private WebSocket with constructor injection.
    PATTERN: Copied from UnifiedCompositeExchange line 600-650
    
    KEY INSIGHT: This pattern eliminates manual handler setup in each exchange.
    """
    if not self.config.has_credentials():
        self.logger.info("No credentials - skipping private WebSocket")
        return
        
    try:
        # Create handler objects for constructor injection (line 610)
        private_handlers = PrivateWebsocketHandlers(
            order_handler=self._handle_order_event,
            balance_handler=self._handle_balance_event,
            position_handler=self._handle_position_event,
            execution_handler=self._handle_execution_event,
            connection_handler=self._handle_private_connection_event,
            error_handler=self._handle_error_event
        )
        
        # Use abstract factory method to create client with handlers (line 620)
        self._private_ws = await self._create_private_ws_with_handlers(private_handlers)
        
        if self._private_ws:
            # Connect and start event processing (line 630)
            await self._private_ws.connect()
            self._private_ws_connected = self._private_ws.is_connected
            
            self.logger.info("Private WebSocket initialized",
                            connected=self._private_ws_connected,
                            has_order_handler=private_handlers.order_handler is not None,
                            has_balance_handler=private_handlers.balance_handler is not None)
            
    except Exception as e:
        self.logger.error("Private WebSocket initialization failed", error=str(e))
        raise
```

## Detailed Implementation Requirements

### Required Imports

```python
from infrastructure.networking.websocket.handlers import (
    PrivateWebsocketHandlers, PublicWebsocketHandlers
)
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.rest.spot.rest_spot_public import PublicSpotRest
from exchanges.interfaces.ws.spot.base_ws_private import PrivateSpotWebsocket
from exchanges.interfaces.ws.spot.base_ws_public import PublicSpotWebsocket
from exchanges.interfaces.base_events import (
    OrderUpdateEvent, BalanceUpdateEvent, PositionUpdateEvent,
    ExecutionReportEvent, ConnectionStatusEvent, ErrorEvent
)
```

### Event Handler Methods to Add

```python
async def _handle_order_event(self, event: OrderUpdateEvent) -> None:
    """
    Handle order update events from private WebSocket.
    ENHANCED: Proper executed orders management with lifecycle tracking.
    """
    try:
        # Update internal order state (includes executed orders management)
        self._update_order(event.order)
        
        # Track operation with enhanced metrics
        self._track_operation("order_update")
        
        # Enhanced logging with executed orders context
        is_executed = event.order.status in ['filled', 'canceled', 'expired']
        self.logger.debug("Order update processed",
                         order_id=event.order.order_id,
                         symbol=event.order.symbol,
                         status=event.order.status.name if hasattr(event.order.status, 'name') else event.order.status,
                         is_executed=is_executed,
                         filled_quantity=getattr(event.order, 'filled_quantity', 0))
                         
    except Exception as e:
        self.logger.error("Error handling order event", 
                         order_id=getattr(event.order, 'order_id', 'unknown'),
                         symbol=getattr(event.order, 'symbol', 'unknown'),
                         error=str(e))

async def _handle_balance_event(self, event: BalanceUpdateEvent) -> None:
    """Handle balance update events from private WebSocket."""
    try:
        # Update internal balance state
        self._update_balance(event.asset, event.balance)
        
        self._track_operation("balance_update")
        
        self.logger.debug("Balance update processed",
                         asset=event.asset,
                         available=event.balance.available)
                         
    except Exception as e:
        self.logger.error("Error handling balance event", 
                         asset=event.asset, error=str(e))

async def _handle_position_event(self, event: PositionUpdateEvent) -> None:
    """Handle position update events from private WebSocket."""
    try:
        # Update internal position state
        self._update_position(event.position)
        
        self._track_operation("position_update")
        
    except Exception as e:
        self.logger.error("Error handling position event", 
                         symbol=event.symbol, error=str(e))

async def _handle_execution_event(self, event: ExecutionReportEvent) -> None:
    """Handle execution report events from private WebSocket."""
    try:
        self._track_operation("execution_report")
        
        self.logger.info("Execution report processed",
                        symbol=event.symbol,
                        execution_id=event.execution_id,
                        price=event.execution.price,
                        quantity=event.execution.quantity)
                        
    except Exception as e:
        self.logger.error("Error handling execution event", error=str(e))

async def _handle_private_connection_event(self, event: ConnectionStatusEvent) -> None:
    """Handle private WebSocket connection status changes."""
    try:
        self._private_ws_connected = event.is_connected
        
        self.logger.info("Private WebSocket connection status changed",
                        connected=event.is_connected,
                        error=event.error_message)
                        
    except Exception as e:
        self.logger.error("Error handling private connection event", error=str(e))

async def _handle_error_event(self, event: ErrorEvent) -> None:
    """Handle error events from private WebSocket."""
    self.logger.error("Private WebSocket error event",
                     error_type=event.error_type,
                     error_code=event.error_code,
                     error_message=event.error_message)
```

### Connection Recovery Methods

```python
async def _reconnect_private_ws(self) -> None:
    """Reconnect private WebSocket with exponential backoff."""
    if self._private_ws:
        try:
            await self._private_ws.reconnect()
            self._private_ws_connected = self._private_ws.is_connected
            
            # Re-subscribe to private streams if connection restored
            if self._private_ws_connected:
                await self._private_ws.subscribe_orders()
                await self._private_ws.subscribe_balances()
                await self._private_ws.subscribe_executions()
                
        except Exception as e:
            self.logger.error("Private WebSocket reconnect failed", error=str(e))
            self._private_ws_connected = False

async def close(self) -> None:
    """Close private exchange connections."""
    try:
        close_tasks = []
        
        if self._private_ws:
            close_tasks.append(self._private_ws.close())
        if self._private_rest:
            close_tasks.append(self._private_rest.close())
            
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
            
        # Call parent cleanup
        await super().close()
        
        # Reset connection status
        self._private_rest_connected = False
        self._private_ws_connected = False
        
    except Exception as e:
        self.logger.error("Error closing private exchange", error=str(e))
        raise

def get_trading_stats(self) -> Dict[str, Any]:
    """
    Get enhanced trading statistics for monitoring.
    ENHANCED: Include executed orders metrics.
    
    Returns:
        Dictionary with trading and account statistics including executed orders
    """
    # Count executed orders across all symbols
    executed_orders_count = sum(len(orders_dict) for orders_dict in self._executed_orders.values())
    
    trading_stats = {
        'total_balances': len(self._balances),
        'open_orders_count': sum(len(orders) for orders in self._open_orders.values()),
        'executed_orders_count': executed_orders_count,  # NEW: executed orders tracking
        'active_positions': len(self._positions),
        'has_credentials': self._config.has_credentials(),
        'symbols_with_executed_orders': len([s for s, orders in self._executed_orders.items() if orders]),  # NEW
        'connection_status': {  # Enhanced connection tracking
            'private_rest_connected': self._private_rest_connected,
            'private_ws_connected': self._private_ws_connected,
        }
    }
    
    return {**trading_stats}
```

## Implementation Strategy

### Step 1: Backup Current Implementation
```bash
cp src/exchanges/interfaces/composite/base_private_exchange.py src/exchanges/interfaces/composite/base_private_exchange.py.backup
```

### Step 2: Architectural Cleanup Implementation
1. **PRIORITY**: Remove position code from base_private_exchange.py (7 locations)
2. **PRIORITY**: Move position code to base_private_futures_exchange.py  
3. Update any existing futures exchange implementations to use the new architecture
4. Test spot exchanges work without position functionality
5. Test futures exchanges have complete position functionality

### Step 3: Exchange Implementation Updates
After completing architectural cleanup:
1. Verify spot exchange implementations work without position references
2. Verify futures exchange implementations inherit proper position functionality
3. Update any direct position references in concrete exchange classes
4. Test the clear separation between spot and futures functionality

## Acceptance Criteria

### PRIORITY: Architectural Cleanup Requirements (CRITICAL)
- [ ] **Position State Removal**: `self._positions` removed from base_private_exchange.py constructor
- [ ] **Position Property Removal**: Abstract `positions` property removed from base class
- [ ] **Position Loading Removal**: `_load_positions()` method removed from base class  
- [ ] **Position Event Handler Removal**: `_handle_position_event()` removed from base class
- [ ] **Position Update Removal**: `_update_position()` method removed from base class
- [ ] **Position Initialization Removal**: Position loading removed from initialization flow
- [ ] **Position WebSocket Handler Removal**: Position handler removed from WebSocket setup
- [ ] **Position Monitoring Removal**: Position metrics removed from get_trading_stats()
- [ ] **Futures Migration**: All position functionality properly implemented in base_private_futures_exchange.py
- [ ] **Clean Separation**: Spot exchanges have no position references, futures exchanges have complete position functionality

### Functional Requirements (BASED ON UNIFIED PATTERNS + EXECUTED ORDERS)
- [ ] All existing abstract methods remain functional (no breaking changes)
- [ ] Abstract factory methods added exactly like UnifiedCompositeExchange lines 200-220
- [ ] Concrete orchestration logic matches UnifiedCompositeExchange lines 45-200
- [ ] Constructor injection pattern identical to UnifiedCompositeExchange lines 600-650
- [ ] Connection management copied from UnifiedCompositeExchange lines 700-850
- [ ] Event handling patterns match UnifiedCompositeExchange implementation

### Executed Orders Management Requirements (NEW)
- [ ] **State Management**: `_executed_orders: Dict[Symbol, Dict[OrderId, Order]]` properly initialized
- [ ] **get_active_order Method**: Implements 3-tier lookup priority (open → executed → REST fallback)
- [ ] **Order Lifecycle**: `_update_order` properly transitions orders from open → executed states
- [ ] **HFT Compliance**: Only executed orders cached, open orders remain real-time
- [ ] **Cache Management**: REST fallback results cached in `_executed_orders` when completed
- [ ] **Enhanced Statistics**: `get_trading_stats()` includes executed orders metrics
- [ ] **Event Handler Enhancement**: Order events properly manage executed orders transitions

### Performance Requirements (HFT COMPLIANCE + EXECUTED ORDERS)
- [ ] Initialization completes in <50ms (same as UnifiedCompositeExchange)
- [ ] Memory usage optimized (no caching of real-time trading data per HFT Caching Policy)
- [ ] Event processing <1ms per event (UnifiedCompositeExchange benchmark)
- [ ] Parallel data loading reduces init time by 60% (UnifiedCompositeExchange result)
- [ ] **get_active_order Performance**: <5ms lookup including REST fallback
- [ ] **Order Transition Performance**: <1ms for open → executed order state changes
- [ ] **Executed Orders Cache**: Memory-efficient storage without impacting HFT performance

### Code Quality Requirements (SPECIFIC METRICS + EXECUTED ORDERS)
- [ ] No breaking changes to existing 442-line interface
- [ ] Add ~400 lines of concrete orchestration + executed orders (target: ~842 lines total)
- [ ] Logging patterns identical to UnifiedCompositeExchange (LoggingTimer, structured metrics)
- [ ] Error handling follows UnifiedCompositeExchange exception patterns
- [ ] Resource cleanup identical to UnifiedCompositeExchange close() method
- [ ] **Executed Orders Code Quality**: Type-safe msgspec.Struct usage, proper error handling
- [ ] **Method Documentation**: Complete docstrings for all executed orders functionality

### Integration Requirements (COMPATIBILITY)
- [ ] Exchange implementations can extend without modification
- [ ] Factory pattern works with existing MexcPrivateExchange and GateioPrivateExchange
- [ ] HFT logging system integration identical to UnifiedCompositeExchange
- [ ] WebSocket infrastructure compatible (same handler interface)

## Testing Strategy

1. **Unit Tests**: Test each new concrete method in isolation
2. **Integration Tests**: Test with mock exchange implementations
3. **Regression Tests**: Ensure existing functionality unchanged
4. **Performance Tests**: Verify HFT compliance maintained
5. **Error Handling Tests**: Test recovery and cleanup logic

### Executed Orders Specific Testing (NEW)
6. **Order Lifecycle Tests**: Verify open → executed transitions work correctly
7. **Lookup Priority Tests**: Verify get_active_order follows proper lookup order
8. **Cache Management Tests**: Ensure HFT-safe caching (only executed orders)
9. **Fallback Mechanism Tests**: Test REST fallback and result caching
10. **Performance Benchmarks**: Verify <5ms lookup times and <1ms transitions

## Success Metrics

### Code Metrics (MEASURABLE TARGETS + EXECUTED ORDERS)
- **Code Reduction**: 80%+ reduction in exchange implementation duplication (UnifiedCompositeExchange proved this)
- **Line Count**: CompositePrivateExchange grows from 442 → ~842 lines (400 lines added including executed orders)
- **Exchange Implementations**: Reduce each from ~800 lines → ~200 lines (factory methods only)
- **New Functionality Lines**: ~100 lines for executed orders management (get_active_order, enhanced _update_order, properties)

### Performance Metrics (HFT BENCHMARKS + EXECUTED ORDERS)  
- **Initialization**: <50ms total init time (UnifiedCompositeExchange target)
- **Event Processing**: <1ms per WebSocket event (UnifiedCompositeExchange benchmark)
- **Memory Usage**: No degradation from current levels
- **Connection Stability**: No degradation in reconnection success rates
- **Order Lookup Performance**: get_active_order <5ms including REST fallback
- **State Transition Performance**: <1ms for order lifecycle transitions (open → executed)
- **Cache Efficiency**: Executed orders cache hit rate >80% for repeat lookups

### Architecture Metrics (QUALITY MEASURES)
- **Maintainability**: New exchange implementations require only factory methods
- **Consistency**: All exchanges use identical orchestration logic
- **Testing**: Shared orchestration reduces test surface area by 80%
- **Documentation**: Single reference implementation instead of N duplicates

## Expected Outcome

This extension will transform CompositePrivateExchange from a 442-line abstract interface into a ~842-line concrete base class that:

1. **ELIMINATES 80%+ code duplication** across exchange implementations
2. **Maintains HFT performance** with identical patterns from UnifiedCompositeExchange  
3. **Provides perfect template** for new exchange integrations
4. **Reduces maintenance burden** by centralizing orchestration logic
5. **Enables fast development** - new exchanges need only implement factory methods

### New Executed Orders Capabilities (September 2025)
6. **Smart Order Retrieval** with 3-tier lookup priority (open → executed → REST fallback)
7. **Proper Order Lifecycle Management** with automated transitions between states
8. **HFT-Safe Executed Orders Caching** that doesn't violate real-time trading data policies
9. **Enhanced Monitoring** with executed orders metrics in trading statistics
10. **Performance-Optimized Implementation** maintaining sub-millisecond event processing

**Key Achievements**: 
- **Architectural**: Move from "every exchange implements orchestration" to "every exchange just provides clients" (UnifiedCompositeExchange pattern)
- **Functional**: Add comprehensive executed orders management without compromising HFT performance
- **Compliance**: Full adherence to HFT Caching Policy - only static completed orders are cached
- **Developer Experience**: Simplified exchange implementations with powerful executed orders functionality built-in

**HFT Safety Guarantee**: All real-time trading data (balances, open orders, positions) remains uncached per HFT Caching Policy. Only completed, static order data (executed orders) is cached for performance optimization.

---

## Implementation Summary (Updated September 2025)

### Phase Overview with Executed Orders Integration

| Phase | Component | Lines Added | Key Features |
|-------|-----------|-------------|--------------|
| 1 | Executed Orders State | ~30 | `_executed_orders` dict, properties |
| 2 | Abstract Factory Methods | ~50 | UnifiedCompositeExchange patterns |
| 3 | Orchestration Logic | ~150 | Template methods, data loading |
| 4 | Order Lifecycle Management | ~80 | Enhanced `_update_order`, `get_active_order` |
| 5 | Connection Management | ~40 | Client lifecycle, status tracking |
| 6 | Template Initialization | ~60 | UnifiedCompositeExchange orchestration |
| 7 | WebSocket Handlers | ~80 | Constructor injection, event processing |

**Total Addition**: ~490 lines (442 → ~932 lines total)

### Critical Implementation Requirements

1. **HFT Caching Policy Compliance**: 
   - ✅ Real-time data (balances, open orders, positions) - NO CACHING
   - ✅ Static data (executed orders, symbol configs) - CACHING ALLOWED

2. **UnifiedCompositeExchange Pattern Fidelity**:
   - ✅ Exact factory method signatures
   - ✅ Identical orchestration logic structure  
   - ✅ Same handler injection patterns
   - ✅ Matching performance benchmarks

3. **Executed Orders Architecture**:
   - ✅ Smart 3-tier lookup (open → executed → REST)
   - ✅ Automated lifecycle transitions
   - ✅ Performance-optimized caching
   - ✅ Enhanced monitoring and statistics

**Next Steps**: Begin Phase 1 implementation with executed orders state management, then proceed through phases systematically while maintaining all existing functionality.