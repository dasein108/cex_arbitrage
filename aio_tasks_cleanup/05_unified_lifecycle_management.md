# Unified Lifecycle Management Plan

## Overview

This document outlines a comprehensive plan for unified lifecycle management across all AsyncIO components to ensure clean shutdown and prevent hanging tasks. The plan establishes consistent patterns for resource management, task tracking, and graceful cleanup.

## Core Principles

### 1. **Unified AsyncResource Interface**

All components that create background tasks or manage resources must implement a common interface:

```python
from abc import ABC, abstractmethod
from typing import Optional

class AsyncResource(ABC):
    """Base interface for all async resources with lifecycle management."""
    
    @abstractmethod
    async def start(self) -> None:
        """Start the resource and any background tasks."""
        pass
    
    @abstractmethod
    async def stop(self, timeout: float = 5.0) -> None:
        """Stop the resource and cleanup all tasks within timeout."""
        pass
    
    @abstractmethod
    def is_running(self) -> bool:
        """Check if the resource is currently active."""
        pass
    
    @property
    @abstractmethod
    def resource_name(self) -> str:
        """Name for logging and identification."""
        pass
```

### 2. **Centralized Task Management**

All background tasks must be tracked and managed centrally:

```python
import asyncio
import weakref
from typing import Set, Dict, Optional

class TaskManager:
    """Centralized task tracking and lifecycle management."""
    
    def __init__(self, name: str):
        self.name = name
        self._tasks: Dict[str, asyncio.Task] = {}
        self._shutdown_event = asyncio.Event()
        self._is_shutting_down = False
    
    def create_task(self, coro, name: str, critical: bool = False) -> asyncio.Task:
        """Create and track a background task."""
        if self._is_shutting_down:
            raise RuntimeError(f"Cannot create task '{name}' during shutdown")
        
        task = asyncio.create_task(coro, name=f"{self.name}.{name}")
        self._tasks[name] = task
        
        # Auto-remove completed tasks
        def cleanup_task(task_ref):
            self._tasks.pop(name, None)
        
        task.add_done_callback(lambda t: cleanup_task(weakref.ref(t)))
        
        return task
    
    async def shutdown(self, timeout: float = 5.0) -> None:
        """Shutdown all managed tasks within timeout."""
        self._is_shutting_down = True
        self._shutdown_event.set()
        
        if not self._tasks:
            return
        
        # Cancel all tasks
        for name, task in self._tasks.items():
            if not task.done():
                task.cancel()
        
        # Wait for completion with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks.values(), return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # Force log remaining tasks
            remaining = [name for name, task in self._tasks.items() if not task.done()]
            if remaining:
                # Log warning but don't raise - allow cleanup to continue
                pass
        
        self._tasks.clear()
    
    def get_running_tasks(self) -> Dict[str, asyncio.Task]:
        """Get currently running tasks."""
        return {name: task for name, task in self._tasks.items() if not task.done()}
    
    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self._is_shutting_down
    
    @property
    def shutdown_event(self) -> asyncio.Event:
        """Event that signals shutdown initiation."""
        return self._shutdown_event
```

### 3. **Dependency-Aware Shutdown**

Components must be shut down in the correct order based on dependencies:

```python
from enum import IntEnum
from typing import List, Dict

class ShutdownPriority(IntEnum):
    """Shutdown priority levels - lower numbers shut down first."""
    CRITICAL_FIRST = 0      # Trading operations, order cancellation
    HIGH = 1                # Private WebSockets, account streams  
    MEDIUM = 2              # Public WebSockets, market data
    LOW = 3                 # Observable streams, UI updates
    CLEANUP = 4             # Rate limiters, caches, logging

class DependencyAwareShutdown:
    """Manages shutdown order based on component dependencies."""
    
    def __init__(self):
        self._resources: Dict[ShutdownPriority, List[AsyncResource]] = {
            priority: [] for priority in ShutdownPriority
        }
    
    def register(self, resource: AsyncResource, priority: ShutdownPriority):
        """Register a resource with shutdown priority."""
        self._resources[priority].append(resource)
    
    async def shutdown_all(self, timeout_per_priority: float = 5.0) -> None:
        """Shutdown all resources in priority order."""
        for priority in sorted(ShutdownPriority):
            resources = self._resources[priority]
            if not resources:
                continue
            
            # Shutdown all resources at this priority level concurrently
            shutdown_tasks = [
                asyncio.create_task(resource.stop(timeout_per_priority))
                for resource in resources
            ]
            
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=timeout_per_priority
                )
            except asyncio.TimeoutError:
                # Log but continue with next priority level
                pass
```

## Component Implementation Plans

### 1. WebSocket Manager Lifecycle

```python
class WebSocketManager(AsyncResource):
    """Enhanced WebSocket manager with lifecycle management."""
    
    def __init__(self, config, **kwargs):
        super().__init__()
        self.config = config
        self._task_manager = TaskManager("websocket_manager")
        
        # Connection state
        self._websocket: Optional[WebSocketClientProtocol] = None
        self.connection_state = ConnectionState.DISCONNECTED
        
        # Message processing
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._message_handlers: List[Callable] = []
    
    async def start(self) -> None:
        """Start WebSocket connection and background tasks."""
        # Start connection management
        self._task_manager.create_task(
            self._connection_loop(), 
            "connection_loop", 
            critical=True
        )
        
        # Start message processing
        self._task_manager.create_task(
            self._process_messages(), 
            "message_processing", 
            critical=False
        )
    
    async def stop(self, timeout: float = 5.0) -> None:
        """Stop WebSocket manager and cleanup resources."""
        # Close WebSocket connection first
        if self._websocket and not self._websocket.closed:
            await self._websocket.close()
        
        # Drain message queue
        await self._drain_message_queue()
        
        # Shutdown task manager
        await self._task_manager.shutdown(timeout)
        
        # Clear handlers
        self._message_handlers.clear()
    
    def is_running(self) -> bool:
        """Check if WebSocket manager is active."""
        return (self.connection_state == ConnectionState.CONNECTED and 
                not self._task_manager.is_shutting_down)
    
    @property
    def resource_name(self) -> str:
        return f"websocket_manager.{self.config.exchange_name}"
    
    async def _process_messages(self) -> None:
        """Process messages with shutdown awareness."""
        while not self._task_manager.is_shutting_down:
            try:
                # Wait for either message or shutdown
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(self._message_queue.get()),
                        asyncio.create_task(self._task_manager.shutdown_event.wait())
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending operations
                for task in pending:
                    task.cancel()
                
                # Check if shutdown was signaled
                if self._task_manager.is_shutting_down:
                    break
                
                # Process message if available
                for task in done:
                    if not task.cancelled() and not self._task_manager.is_shutting_down:
                        try:
                            raw_message = task.result()
                            await self._handle_message(raw_message)
                        finally:
                            self._message_queue.task_done()
                            
            except Exception as e:
                # Log error but continue if not shutting down
                if not self._task_manager.is_shutting_down:
                    await asyncio.sleep(0.1)
    
    async def _drain_message_queue(self) -> None:
        """Drain remaining messages from queue."""
        drained_count = 0
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
                self._message_queue.task_done()
                drained_count += 1
            except asyncio.QueueEmpty:
                break
```

### 2. Observable Streams Lifecycle

```python
class ObservableStreamsInterface(AsyncResource):
    """Enhanced observable streams with lifecycle management."""
    
    def __init__(self):
        super().__init__()
        self._streams: Dict[str, BehaviorSubject] = {}
        self._subscriptions: Set[Disposable] = set()
        self._task_manager = TaskManager("observable_streams")
        self._is_disposed = False
    
    async def start(self) -> None:
        """Initialize observable streams."""
        # Create subjects
        self._initialize_subjects()
    
    async def stop(self, timeout: float = 5.0) -> None:
        """Dispose all streams and subscriptions."""
        if self._is_disposed:
            return
        
        self._is_disposed = True
        
        # Dispose all tracked subscriptions
        for subscription in list(self._subscriptions):
            try:
                subscription.dispose()
            except Exception:
                pass  # Continue cleanup even if disposal fails
        self._subscriptions.clear()
        
        # Complete and dispose all subjects
        for subject in self._streams.values():
            try:
                subject.on_completed()
                subject.dispose()
            except Exception:
                pass  # Continue cleanup even if disposal fails
        
        self._streams.clear()
        
        # Shutdown any background tasks
        await self._task_manager.shutdown(timeout)
    
    def subscribe_tracked(self, stream_name: str, observer) -> Disposable:
        """Subscribe with automatic tracking for cleanup."""
        if self._is_disposed:
            raise RuntimeError("Cannot subscribe to disposed streams")
        
        subject = self._streams.get(stream_name)
        if not subject:
            raise ValueError(f"Unknown stream: {stream_name}")
        
        subscription = subject.subscribe(observer)
        self._subscriptions.add(subscription)
        
        # Auto-remove when disposed
        original_dispose = subscription.dispose
        def tracked_dispose():
            self._subscriptions.discard(subscription)
            return original_dispose()
        subscription.dispose = tracked_dispose
        
        return subscription
    
    def is_running(self) -> bool:
        """Check if streams are active."""
        return not self._is_disposed
    
    @property
    def resource_name(self) -> str:
        return "observable_streams"
```

### 3. Rate Limiter Lifecycle

```python
class BaseExchangeRateLimit(AsyncResource):
    """Enhanced rate limiter with lifecycle management."""
    
    def __init__(self, exchange_config: ExchangeConfig, logger=None):
        super().__init__()
        self.exchange_config = exchange_config
        self.logger = logger
        self._task_manager = TaskManager("rate_limiter")
        
        # Rate limiting state
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._pending_sleeps: Set[asyncio.Task] = set()
        self._is_shutdown = False
    
    async def start(self) -> None:
        """Initialize rate limiter."""
        self._initialize_semaphores()
    
    async def stop(self, timeout: float = 5.0) -> None:
        """Shutdown rate limiter and cleanup resources."""
        self._is_shutdown = True
        
        # Cancel all pending sleep operations
        for sleep_task in list(self._pending_sleeps):
            if not sleep_task.done():
                sleep_task.cancel()
        
        # Wait for sleep cancellation
        if self._pending_sleeps:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._pending_sleeps, return_exceptions=True),
                    timeout=min(timeout, 2.0)
                )
            except asyncio.TimeoutError:
                pass  # Continue cleanup
        
        # Force release all semaphores
        await self._release_all_semaphores()
        
        # Shutdown task manager
        await self._task_manager.shutdown(timeout)
    
    async def _tracked_sleep(self, delay: float) -> None:
        """Sleep with task tracking for cleanup."""
        if self._is_shutdown or delay <= 0:
            return
        
        sleep_task = asyncio.create_task(asyncio.sleep(delay))
        self._pending_sleeps.add(sleep_task)
        
        try:
            await sleep_task
        except asyncio.CancelledError:
            pass  # Expected during shutdown
        finally:
            self._pending_sleeps.discard(sleep_task)
    
    def is_running(self) -> bool:
        """Check if rate limiter is active."""
        return not self._is_shutdown
    
    @property
    def resource_name(self) -> str:
        return f"rate_limiter.{self.exchange_name}"
```

### 4. Exchange Composite Lifecycle

```python
class BaseCompositeExchange(AsyncResource):
    """Enhanced composite exchange with lifecycle management."""
    
    def __init__(self, config, rest_client, websocket_client, logger=None):
        super().__init__()
        self.config = config
        self.rest_client = rest_client
        self.websocket_client = websocket_client
        self.logger = logger
        
        # Lifecycle management
        self._shutdown_manager = DependencyAwareShutdown()
        self._is_initialized = False
    
    async def start(self) -> None:
        """Start exchange and all sub-components."""
        if self._is_initialized:
            return
        
        # Register components with shutdown priorities
        if hasattr(self.websocket_client, 'streams'):
            self._shutdown_manager.register(
                self.websocket_client.streams, 
                ShutdownPriority.LOW
            )
        
        if hasattr(self.websocket_client, 'manager'):
            self._shutdown_manager.register(
                self.websocket_client.manager, 
                ShutdownPriority.MEDIUM
            )
        
        if hasattr(self.rest_client, 'rate_limiter'):
            self._shutdown_manager.register(
                self.rest_client.rate_limiter, 
                ShutdownPriority.CLEANUP
            )
        
        # Start all components
        components = [self.rest_client, self.websocket_client]
        for component in components:
            if hasattr(component, 'start'):
                await component.start()
        
        self._is_initialized = True
    
    async def stop(self, timeout: float = 5.0) -> None:
        """Stop exchange with dependency-aware shutdown."""
        if not self._is_initialized:
            return
        
        # Shutdown in dependency order
        await self._shutdown_manager.shutdown_all(timeout_per_priority=timeout)
        
        self._is_initialized = False
    
    def is_running(self) -> bool:
        """Check if exchange is active."""
        return self._is_initialized
    
    @property
    def resource_name(self) -> str:
        return f"composite_exchange.{self.config.exchange_name}"
```

## Integration Points

### 1. Exchange Factory Integration

```python
class ExchangeFactory:
    """Enhanced factory with lifecycle management."""
    
    @staticmethod
    async def create_exchange_with_lifecycle(
        config: ExchangeConfig, 
        is_private: bool = False
    ) -> AsyncResource:
        """Create exchange with full lifecycle management."""
        
        # Create components
        rest_client = ExchangeFactory._create_rest_client(config, is_private)
        websocket_client = ExchangeFactory._create_websocket_client(config, is_private)
        
        # Create composite exchange
        if is_private:
            exchange = PrivateCompositeExchange(config, rest_client, websocket_client)
        else:
            exchange = PublicCompositeExchange(config, rest_client, websocket_client)
        
        # Initialize (start all components)
        await exchange.start()
        
        return exchange
```

### 2. Context Manager Integration

```python
class ExchangeContext:
    """Context manager for automatic exchange lifecycle management."""
    
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.public_exchange: Optional[AsyncResource] = None
        self.private_exchange: Optional[AsyncResource] = None
    
    async def __aenter__(self):
        # Create exchanges
        self.public_exchange = await ExchangeFactory.create_exchange_with_lifecycle(
            self.config, is_private=False
        )
        self.private_exchange = await ExchangeFactory.create_exchange_with_lifecycle(
            self.config, is_private=True
        )
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Shutdown in correct order
        shutdown_tasks = []
        
        if self.private_exchange:
            shutdown_tasks.append(self.private_exchange.stop())
        
        if self.public_exchange:
            shutdown_tasks.append(self.public_exchange.stop())
        
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
```

### 3. Demo Script Integration

```python
# Enhanced rx_mm_demo.py
async def main():
    config = get_exchange_config("mexc_spot")
    symbol = Symbol(base=AssetName("HIFI"), quote=AssetName("USDT"), is_futures=False)
    quantity_usdt = 2.1
    
    # Use context manager for automatic cleanup
    async with ExchangeContext(config) as exchanges:
        context = MarketMakerContext(
            symbol=symbol,
            quantity_usdt=quantity_usdt,
            public_exchange=exchanges.public_exchange,
            private_exchange=exchanges.private_exchange,
            logger=get_logger("market_maker")
        )
        
        # Run trading logic
        state_machine = MarketMakerStateMachine(context)
        buy_order, sell_order = await state_machine.run_cycle()
        
        print(f"✅ Cycle completed: {buy_order}, {sell_order}")
    
    # Automatic cleanup ensures no hanging tasks
    print("🏁 Program completed cleanly")
```

## Implementation Timeline

### Phase 1: Core Infrastructure (Week 1)
1. **AsyncResource Interface** - Define base interface for all components
2. **TaskManager** - Centralized task tracking and cancellation
3. **DependencyAwareShutdown** - Priority-based shutdown orchestration

### Phase 2: WebSocket Components (Week 2)
1. **WebSocketManager Lifecycle** - Implement AsyncResource interface
2. **Message Queue Cleanup** - Add graceful shutdown and draining
3. **Connection Loop Management** - Proper task cancellation

### Phase 3: Observable Streams (Week 2)
1. **Observable Lifecycle** - Implement AsyncResource interface
2. **Subscription Tracking** - Track and dispose all subscriptions
3. **Handler Unbinding** - Cleanup WebSocket handler bindings

### Phase 4: Rate Limiters (Week 3)
1. **Rate Limiter Lifecycle** - Implement AsyncResource interface
2. **Sleep Task Tracking** - Track and cancel sleep operations
3. **Semaphore Cleanup** - Force release acquired semaphores

### Phase 5: Exchange Integration (Week 3)
1. **Exchange Composite Lifecycle** - Integrate all components
2. **Factory Updates** - Create exchanges with lifecycle management
3. **Context Manager** - Automatic resource management

### Phase 6: Testing and Validation (Week 4)
1. **Lifecycle Tests** - Verify clean shutdown of all components
2. **Integration Tests** - Test complete exchange lifecycle
3. **Performance Validation** - Ensure no performance regression

## Success Criteria

### 1. **No Hanging Tasks**
- All background tasks properly cancelled during shutdown
- No AsyncIO tasks remain after program completion
- Event loop exits cleanly

### 2. **Resource Cleanup**
- All WebSocket connections closed
- All observable subscriptions disposed
- All semaphores released
- All message queues drained

### 3. **Graceful Shutdown**
- Shutdown completes within 10 seconds maximum
- No forced task cancellation timeouts
- All components report clean shutdown

### 4. **Performance Maintained**
- No measurable performance impact during normal operation
- Shutdown overhead < 100ms for most components
- HFT latency requirements still met

## Monitoring and Debugging

### 1. **Lifecycle Logging**
```python
# Each component logs lifecycle events
self.logger.info("Component starting", component=self.resource_name)
self.logger.info("Component stopping", component=self.resource_name)
self.logger.info("Component stopped", component=self.resource_name, duration_ms=duration)
```

### 2. **Task Tracking Metrics**
```python
# Task manager metrics
self.logger.metric("active_background_tasks", len(self._tasks))
self.logger.metric("shutdown_duration_ms", duration)
self.logger.metric("failed_shutdowns", 1 if timeout else 0)
```

### 3. **Resource Leak Detection**
```python
# Pre/post operation task counting
initial_tasks = len(asyncio.all_tasks())
# ... run operation
final_tasks = len(asyncio.all_tasks())
assert final_tasks <= initial_tasks, "Task leak detected"
```

This unified lifecycle management plan provides a comprehensive solution to the AsyncIO hanging issues by establishing consistent patterns for resource management, task tracking, and graceful cleanup across all components in the HFT trading system.