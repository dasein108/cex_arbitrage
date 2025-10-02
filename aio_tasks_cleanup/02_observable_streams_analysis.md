# Observable Streams (RxPY) Disposal Analysis

## Problem Summary

RxPY observable streams and subscriptions may not be properly disposed, creating memory leaks and preventing clean AsyncIO shutdown. Observable subscriptions can maintain references to callback functions and other resources that keep background tasks alive.

## Affected Components

### 1. Observable Streams Interface (`/src/exchanges/interfaces/ractive/observable_streams.py`)

**RxPY Components Created:**
- **Lines 29-33**: `BehaviorSubject` instances for public streams (trades, book_tickers, tickers)
- **Lines 45-49**: `BehaviorSubject` instances for private streams (balances, orders, positions)

**Current Disposal Mechanism (Lines 22-25):**
```python
def dispose(self) -> None:
    for subject in self._streams.values():
        subject.on_completed()  # Signal completion
        subject.dispose()       # Release resources
```

**Potential Issues:**
1. **Subscription Tracking**: External subscriptions to these subjects are not tracked
2. **Observer References**: Subscriptions may hold references to callback functions
3. **No Subscription Registry**: No way to ensure all subscriptions are cleaned up

### 2. Public Composite Exchange (`/src/exchanges/interfaces/composite/base_public_composite.py`)

**Observable Integration:**
- **Line 85**: `PublicObservableStreams.__init__(self)`
- **Line 94**: `self.streams = PublicObservableStreams()` (redundant creation)
- **Line 471**: `self.streams.dispose()` called in close method

**Issue**: Double initialization of observable streams on lines 85 and 94.

### 3. Private Composite Exchange (`/src/exchanges/interfaces/composite/base_private_composite.py`)

**Observable Integration:**
- **Line 527**: `self.dispose()` called in close method
- **Issue**: Private exchange inherits disposal but may have additional subscriptions

### 4. WebSocket Handler Bindings

**Handler Binding Pattern:**
```python
# Lines 98-100 in base_public_composite.py
websocket_client.bind(PublicWebsocketChannelType.BOOK_TICKER, self._handle_book_ticker)
websocket_client.bind(PublicWebsocketChannelType.ORDERBOOK, self._handle_orderbook)
websocket_client.bind(PublicWebsocketChannelType.TICKER, self._handle_ticker)
```

**Potential Issues:**
1. **Handler References**: Bound handlers may maintain references to exchange instances
2. **No Unbinding**: No corresponding unbind calls during cleanup
3. **Circular References**: Handlers might reference observables that reference handlers

## Current Cleanup Mechanisms

### Observable Streams Disposal
```python
def dispose(self) -> None:
    for subject in self._streams.values():
        subject.on_completed()  # Signals to all subscribers
        subject.dispose()       # Releases internal resources
```

**Limitations:**
- Only disposes the subjects themselves
- External subscriptions are not tracked or disposed
- No handling of subscription leaks

### Exchange Close Methods
```python
# In base_public_composite.py (line 471)
async def close(self) -> None:
    # ... other cleanup
    self.streams.dispose()

# In base_private_composite.py (line 527)  
async def close(self) -> None:
    # ... other cleanup
    self.dispose()
```

**Issues:**
- Disposal happens at the end of cleanup
- No validation that all subscriptions are cleaned up
- No timeout for disposal operations

## Impact Analysis

### Memory Leaks
- **Observer Functions**: Subscription callbacks maintain references
- **Subject State**: BehaviorSubjects retain last emitted values
- **Circular References**: Observers referencing the source subjects

### Background Task Issues
- **Observer Callbacks**: May be scheduled as async tasks
- **Scheduler References**: RxPY schedulers might maintain background tasks
- **Unhandled Exceptions**: Disposed subjects with active subscriptions may cause errors

### Resource Consumption
- **Memory Growth**: Accumulating observer references over time
- **CPU Usage**: Unused observers still consuming callback cycles
- **GC Pressure**: Unreleased objects preventing garbage collection

## Root Cause Analysis

### 1. Untracked External Subscriptions

**Problem**: When external code subscribes to observable streams, those subscriptions are not tracked:

```python
# External code subscribing
subscription = exchange.streams.book_tickers_stream.subscribe(my_callback)
# This subscription is never tracked for cleanup
```

### 2. Handler Binding Without Unbinding

**Problem**: WebSocket handlers are bound but never unbound:

```python
websocket_client.bind(channel, handler)  # Binding creates reference
# No corresponding websocket_client.unbind(channel, handler)
```

### 3. Double Observable Creation

**Problem**: Base public composite creates observables twice:

```python
PublicObservableStreams.__init__(self)  # Creates _streams dict
self.streams = PublicObservableStreams()  # Creates another _streams dict
```

## Proposed Solutions

### 1. Subscription Tracking Registry

```python
class ObservableStreamsInterface:
    def __init__(self):
        self._streams: Dict[str, BehaviorSubject] = {}
        self._subscriptions: Set[Disposable] = set()
        
    def subscribe_tracked(self, stream_name: str, observer) -> Disposable:
        """Subscribe with automatic tracking for cleanup"""
        subscription = self._streams[stream_name].subscribe(observer)
        self._subscriptions.add(subscription)
        
        # Remove from tracking when disposed
        def on_dispose():
            self._subscriptions.discard(subscription)
        subscription.add_dispose_callback(on_dispose)
        
        return subscription
        
    def dispose(self) -> None:
        # Dispose all tracked subscriptions first
        for subscription in list(self._subscriptions):
            try:
                subscription.dispose()
            except Exception as e:
                # Log but continue cleanup
                pass
        self._subscriptions.clear()
        
        # Then dispose subjects
        for subject in self._streams.values():
            try:
                subject.on_completed()
                subject.dispose()
            except Exception as e:
                # Log but continue cleanup
                pass
```

### 2. Handler Unbinding Support

```python
class BasePublicComposite:
    def __init__(self, ...):
        # Track bound handlers for cleanup
        self._bound_handlers: List[Tuple[ChannelType, Callable]] = []
        
        # Bind and track handlers
        handlers = [
            (PublicWebsocketChannelType.BOOK_TICKER, self._handle_book_ticker),
            (PublicWebsocketChannelType.ORDERBOOK, self._handle_orderbook),
            (PublicWebsocketChannelType.TICKER, self._handle_ticker),
        ]
        
        for channel, handler in handlers:
            websocket_client.bind(channel, handler)
            self._bound_handlers.append((channel, handler))
    
    async def close(self) -> None:
        # Unbind handlers first
        for channel, handler in self._bound_handlers:
            try:
                self.websocket_client.unbind(channel, handler)
            except Exception as e:
                self.logger.warning(f"Failed to unbind handler: {e}")
        
        # Then dispose streams
        self.streams.dispose()
```

### 3. Context Manager Support

```python
class ObservableStreamsInterface:
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.dispose()

# Usage:
async with PublicObservableStreams() as streams:
    subscription = streams.subscribe_tracked('book_tickers', my_callback)
    # Automatic disposal on exit
```

### 4. Timeout-Protected Disposal

```python
async def dispose_with_timeout(self, timeout: float = 2.0) -> None:
    """Dispose with timeout protection"""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(self.dispose),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        self.logger.warning(f"Observable disposal timed out after {timeout}s")
        # Force cleanup anyway
        self._subscriptions.clear()
        self._streams.clear()
```

## Testing Strategy

### 1. Subscription Leak Detection

```python
async def test_subscription_cleanup():
    streams = PublicObservableStreams()
    
    # Create subscriptions
    callback_called = False
    def test_callback(value):
        nonlocal callback_called
        callback_called = True
        
    subscription = streams.subscribe_tracked('book_tickers', test_callback)
    
    # Dispose and verify cleanup
    streams.dispose()
    
    # Verify subscription is inactive
    streams.publish('book_tickers', mock_ticker)
    assert not callback_called  # Should not be called after disposal
```

### 2. Memory Leak Detection

```python
import gc
import weakref

async def test_memory_cleanup():
    streams = PublicObservableStreams()
    weak_ref = weakref.ref(streams)
    
    # Use streams
    subscription = streams.subscribe_tracked('trades', lambda x: None)
    
    # Cleanup
    streams.dispose()
    del streams
    del subscription
    gc.collect()
    
    # Verify garbage collection
    assert weak_ref() is None  # Should be garbage collected
```

### 3. Handler Unbinding Test

```python
async def test_handler_unbinding():
    exchange = MexcPublicExchange(config)
    
    # Track handler calls
    handler_calls = 0
    original_handler = exchange._handle_book_ticker
    
    def counting_handler(*args, **kwargs):
        nonlocal handler_calls
        handler_calls += 1
        return original_handler(*args, **kwargs)
    
    exchange._handle_book_ticker = counting_handler
    
    # Close exchange
    await exchange.close()
    
    # Simulate WebSocket message (should not call handler)
    # ... send mock message
    assert handler_calls == 0  # Handler should be unbound
```

## Priority Level: **HIGH**

Observable stream disposal is the **second highest priority** after WebSocket issues. RxPY subscriptions can create subtle memory leaks and maintain references that prevent garbage collection.

## Dependencies

- **WebSocket Handlers**: Observable streams receive data from WebSocket handlers
- **Exchange Implementations**: All exchanges use observable streams
- **External Subscribers**: Trading logic and arbitrage components subscribe to streams

## Implementation Order

1. **Fix subscription tracking in observable streams** (critical)
2. **Add handler unbinding support** (high priority)
3. **Fix double observable creation** (medium priority)  
4. **Add context manager support** (enhancement)
5. **Implement timeout-protected disposal** (robustness)

## Related Components

- **WebSocket Managers**: Feed data to observable streams
- **Exchange Factory**: Creates exchanges with observable streams
- **Trading Logic**: Subscribes to observable streams for market data
- **Arbitrage Engine**: May maintain long-lived subscriptions to price streams