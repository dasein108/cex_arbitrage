# WebSocket Auto-Reconnection Analysis

## Problem Summary

WebSocket connections create persistent background tasks that run forever by design, preventing clean AsyncIO shutdown. These tasks continue running even after the main trading logic completes, causing the program to hang.

## Affected Components

### 1. WebSocketManager (`/src/infrastructure/networking/websocket/ws_manager.py`)

**Background Tasks Created:**
- **Line 96**: `_connection_task = asyncio.create_task(self._connection_loop())`
- **Line 99**: `_processing_task = asyncio.create_task(self._process_messages())`
- **Line 173**: `_reader_task = asyncio.create_task(self._message_reader())`

**Root Cause - Connection Loop (Lines 137-187):**
```python
async def _connection_loop(self):
    while self._should_reconnect:  # ← Runs forever until explicitly set to False
        try:
            await self._establish_connection()
            await self._connection.wait_closed()
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            await asyncio.sleep(self._reconnect_delay)
```

**Issue**: The `_should_reconnect` flag defaults to `True` and the loop continues indefinitely.

### 2. WebSocketClient (`/src/infrastructure/networking/websocket/ws_client.py`)

**Background Tasks Created:**
- **Line 235**: Reader loop task in `_reader_loop()` method

**Root Cause - Reader Loop (Lines 200-235):**
```python
async def _reader_loop(self):
    while True:  # ← Infinite loop with no proper exit condition
        try:
            message = await self._websocket.recv()
            # Process message
        except websockets.exceptions.ConnectionClosed:
            break
        except Exception as e:
            self.logger.error(f"Reader error: {e}")
```

**Issue**: Reader loop only exits on connection close, but may not handle all shutdown scenarios.

### 3. Exchange WebSocket Implementations

**MEXC WebSocket Strategies:**
- `/src/exchanges/integrations/mexc/ws/strategies/public/connection.py`
- `/src/exchanges/integrations/mexc/ws/strategies/private/connection.py`

**Gate.io WebSocket Strategies:**
- `/src/exchanges/integrations/gateio/ws/strategies/spot/public/connection.py`
- `/src/exchanges/integrations/gateio/ws/strategies/spot/private/connection.py`
- `/src/exchanges/integrations/gateio/ws/strategies/futures/public/connection.py`
- `/src/exchanges/integrations/gateio/ws/strategies/futures/private/connection.py`

**Issue**: Each implementation may create additional connection management tasks.

## Current Cleanup Mechanisms

### WebSocketManager.close() (Lines 110-135)
```python
async def close(self):
    self._should_reconnect = False
    
    # Cancel tasks
    if self._connection_task:
        self._connection_task.cancel()
    if self._processing_task:
        self._processing_task.cancel()
    if self._reader_task:
        self._reader_task.cancel()
    
    # Wait for cancellation
    tasks = [t for t in [self._connection_task, self._processing_task, self._reader_task] if t]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
```

**Potential Issues:**
1. **Race Conditions**: Tasks may not cancel immediately
2. **No Timeout**: `gather()` could wait indefinitely
3. **Exception Handling**: Cancellation exceptions might not be properly handled

## Impact Analysis

### Symptoms
- Program hangs after successful completion
- AsyncIO event loop remains active
- Background tasks prevent `asyncio.run()` from exiting

### Resource Leaks
- **Network Connections**: WebSocket connections remain open
- **Memory Usage**: Message buffers and connection state maintained
- **CPU Usage**: Connection loops continue consuming cycles

## Proposed Solutions

### 1. Immediate Fixes

**Add Cancellation Timeouts:**
```python
async def close(self):
    self._should_reconnect = False
    
    # Cancel all tasks
    tasks_to_cancel = [
        self._connection_task,
        self._processing_task, 
        self._reader_task
    ]
    
    for task in tasks_to_cancel:
        if task and not task.done():
            task.cancel()
    
    # Wait with timeout
    if tasks_to_cancel:
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                timeout=2.0
            )
        except asyncio.TimeoutError:
            self.logger.warning("WebSocket task cancellation timed out")
```

### 2. Structural Improvements

**Task Tracking:**
```python
class WebSocketManager:
    def __init__(self):
        self._background_tasks: Set[asyncio.Task] = set()
        
    def _create_task(self, coro, name: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task
        
    async def close(self):
        # Cancel all tracked tasks
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
```

### 3. Context Manager Support

**Automatic Resource Management:**
```python
class WebSocketManager:
    async def __aenter__(self):
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
```

## Testing Strategy

### 1. Task Counting Test
```python
async def test_websocket_cleanup():
    initial_tasks = len(asyncio.all_tasks())
    
    async with WebSocketManager(config) as ws:
        # Use WebSocket
        await ws.connect()
        
    # Verify cleanup
    final_tasks = len(asyncio.all_tasks())
    assert final_tasks == initial_tasks
```

### 2. Shutdown Timeout Test
```python
async def test_shutdown_timeout():
    ws = WebSocketManager(config)
    await ws.start()
    
    # Force unresponsive connection
    ws._connection._websocket = mock_unresponsive_websocket()
    
    # Should complete within timeout
    start_time = time.time()
    await ws.close()
    duration = time.time() - start_time
    assert duration < 3.0  # Should timeout and force close
```

## Priority Level: **CRITICAL**

WebSocket auto-reconnection is the **primary cause** of AsyncIO hanging. This component must be fixed first as it creates the most persistent background tasks that prevent clean shutdown.

## Dependencies

- **Observable Streams**: Depend on WebSocket data feeds
- **Exchange Implementations**: Use WebSocket managers
- **Message Processing**: Relies on WebSocket message flow

## Implementation Order

1. **Fix WebSocketManager task lifecycle** (highest priority)
2. **Update WebSocketClient with proper shutdown**
3. **Test exchange WebSocket implementations**
4. **Add context manager support**
5. **Integrate with exchange factory pattern**