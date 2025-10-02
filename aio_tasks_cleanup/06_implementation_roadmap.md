# AsyncIO Tasks Cleanup - Implementation Roadmap

## Executive Summary

This roadmap provides a detailed, step-by-step plan to implement AsyncIO task cleanup across the HFT arbitrage system. The plan is designed to eliminate hanging tasks and ensure clean program shutdown while maintaining HFT performance requirements.

## Priority Matrix

| Component | Priority | Risk Level | Implementation Effort | Dependencies |
|-----------|----------|------------|----------------------|--------------|
| **WebSocket Auto-Reconnection** | CRITICAL | HIGH | Medium | None |
| **Message Queue Processing** | HIGH | HIGH | Medium | WebSocket Manager |
| **Observable Streams Disposal** | HIGH | MEDIUM | Low | WebSocket Handlers |
| **Rate Limiter Timers** | MEDIUM | LOW | Low | REST Clients |
| **Unified Lifecycle Management** | HIGH | MEDIUM | High | All Components |

## Phase-by-Phase Implementation Plan

### **PHASE 1: CRITICAL FOUNDATION (Week 1)**

**Objective**: Fix the most critical hanging issues and establish core infrastructure.

#### **Day 1-2: WebSocket Connection Loop Fix**

**Files to Modify:**
- `/src/infrastructure/networking/websocket/ws_manager.py`
- `/src/infrastructure/networking/websocket/ws_client.py`

**Tasks:**
1. **Add Shutdown Flags to WebSocket Manager**
   ```python
   # Add to WebSocketManager.__init__()
   self._is_shutting_down = False
   self._shutdown_event = asyncio.Event()
   ```

2. **Fix Connection Loop with Shutdown Check**
   ```python
   # Modify _connection_loop() method
   async def _connection_loop(self):
       while self._should_reconnect and not self._is_shutting_down:
           # ... existing logic
   ```

3. **Add Timeout-Protected Close Method**
   ```python
   async def close(self):
       self._should_reconnect = False
       self._is_shutting_down = True
       self._shutdown_event.set()
       
       # Cancel tasks with timeout
       tasks = [self._connection_task, self._processing_task, self._reader_task]
       # ... implementation from analysis
   ```

**Success Criteria:**
- WebSocket connection loops stop within 2 seconds of close()
- No hanging connection tasks after shutdown
- All WebSocket tests pass

#### **Day 3-4: Message Queue Processing Fix**

**Files to Modify:**
- `/src/infrastructure/networking/websocket/ws_manager.py` (message processing)

**Tasks:**
1. **Add Shutdown-Aware Message Processing**
   ```python
   async def _process_messages(self):
       while not self._is_shutting_down:
           try:
               # Use timeout instead of blocking forever
               raw_message, queue_time = await asyncio.wait_for(
                   self._message_queue.get(),
                   timeout=1.0
               )
               # ... process message
           except asyncio.TimeoutError:
               continue  # Check shutdown flag
   ```

2. **Implement Queue Draining**
   ```python
   async def _drain_message_queue(self):
       while not self._message_queue.empty():
           try:
               self._message_queue.get_nowait()
               self._message_queue.task_done()
           except asyncio.QueueEmpty:
               break
   ```

**Success Criteria:**
- Message processing stops within 1 second of shutdown
- No messages left in queue after cleanup
- Message processing tests pass

#### **Day 5: Core Infrastructure Setup**

**Files to Create:**
- `/src/infrastructure/lifecycle/async_resource.py`
- `/src/infrastructure/lifecycle/task_manager.py`

**Tasks:**
1. **Create AsyncResource Interface**
   - Implement base interface from unified lifecycle plan
   - Add documentation and examples

2. **Create TaskManager Class**
   - Implement centralized task tracking
   - Add timeout-protected shutdown
   - Include task lifecycle logging

**Success Criteria:**
- AsyncResource interface defined and documented
- TaskManager tested with basic task creation/cleanup
- Integration points identified

---

### **PHASE 2: OBSERVABLE STREAMS (Week 2)**

**Objective**: Fix RxPY subscription leaks and handler unbinding issues.

#### **Day 1-2: Observable Streams Lifecycle**

**Files to Modify:**
- `/src/exchanges/interfaces/ractive/observable_streams.py`
- `/src/exchanges/interfaces/composite/base_public_composite.py`
- `/src/exchanges/interfaces/composite/base_private_composite.py`

**Tasks:**
1. **Implement AsyncResource in Observable Streams**
   ```python
   class ObservableStreamsInterface(AsyncResource):
       def __init__(self):
           self._subscriptions: Set[Disposable] = set()
           self._is_disposed = False
   ```

2. **Add Subscription Tracking**
   ```python
   def subscribe_tracked(self, stream_name: str, observer) -> Disposable:
       subscription = self._streams[stream_name].subscribe(observer)
       self._subscriptions.add(subscription)
       return subscription
   ```

3. **Fix Double Observable Creation**
   - Remove duplicate `self.streams = PublicObservableStreams()` in base_public_composite.py
   - Ensure single initialization in constructor

**Success Criteria:**
- All subscriptions properly tracked and disposed
- No memory leaks in observable streams
- Observable disposal tests pass

#### **Day 3-4: Handler Unbinding**

**Files to Modify:**
- `/src/exchanges/interfaces/composite/base_public_composite.py`
- `/src/exchanges/interfaces/composite/base_private_composite.py`
- WebSocket client implementations

**Tasks:**
1. **Track Bound Handlers**
   ```python
   def __init__(self, ...):
       self._bound_handlers: List[Tuple[ChannelType, Callable]] = []
       
       # Track all bindings
       for channel, handler in handlers:
           websocket_client.bind(channel, handler)
           self._bound_handlers.append((channel, handler))
   ```

2. **Implement Handler Unbinding**
   ```python
   async def close(self):
       # Unbind handlers first
       for channel, handler in self._bound_handlers:
           self.websocket_client.unbind(channel, handler)
       
       # Then dispose streams
       self.streams.dispose()
   ```

**Success Criteria:**
- All WebSocket handlers properly unbound
- No handler reference leaks
- Handler unbinding tests pass

---

### **PHASE 3: EXCHANGE INTEGRATION (Week 3)**

**Objective**: Integrate lifecycle management into exchange implementations.

#### **Day 1-2: WebSocket Manager Integration**

**Files to Modify:**
- `/src/infrastructure/networking/websocket/ws_manager.py`
- Exchange-specific WebSocket implementations

**Tasks:**
1. **Implement AsyncResource in WebSocketManager**
   ```python
   class WebSocketManager(AsyncResource):
       async def start(self):
           self._task_manager.create_task(self._connection_loop(), "connection")
           self._task_manager.create_task(self._process_messages(), "processing")
       
       async def stop(self, timeout=5.0):
           await self._drain_message_queue()
           await self._task_manager.shutdown(timeout)
   ```

2. **Update Exchange WebSocket Implementations**
   - MEXC: `/src/exchanges/integrations/mexc/ws/`
   - Gate.io: `/src/exchanges/integrations/gateio/ws/`
   - Implement AsyncResource interface in each

**Success Criteria:**
- WebSocket managers start/stop cleanly
- Exchange-specific WebSocket implementations integrated
- WebSocket integration tests pass

#### **Day 3-4: Composite Exchange Lifecycle**

**Files to Modify:**
- `/src/exchanges/interfaces/composite/base_public_composite.py`
- `/src/exchanges/interfaces/composite/base_private_composite.py`

**Tasks:**
1. **Implement AsyncResource in Composite Exchanges**
   ```python
   class BasePublicComposite(AsyncResource):
       async def start(self):
           # Start all sub-components
           await self.websocket_client.start()
           await self.streams.start()
       
       async def stop(self, timeout=5.0):
           # Stop in dependency order
           await self.streams.stop()
           await self.websocket_client.stop()
   ```

2. **Add Dependency-Aware Shutdown**
   - Implement shutdown priority system
   - Ensure proper cleanup order

**Success Criteria:**
- Composite exchanges start/stop properly
- Dependencies shut down in correct order
- Composite exchange tests pass

#### **Day 5: Factory Integration**

**Files to Modify:**
- `/src/exchanges/exchange_factory.py`

**Tasks:**
1. **Update Factory for Lifecycle Management**
   ```python
   async def create_exchange_with_lifecycle(config, is_private=False):
       exchange = create_composite_implementation(config, is_private)
       await exchange.start()
       return exchange
   ```

2. **Add Context Manager Support**
   ```python
   class ExchangeContext:
       async def __aenter__(self):
           # Create and start exchanges
       async def __aexit__(self, exc_type, exc_val, exc_tb):
           # Stop exchanges in proper order
   ```

**Success Criteria:**
- Factory creates exchanges with lifecycle management
- Context manager provides automatic cleanup
- Factory integration tests pass

---

### **PHASE 4: RATE LIMITERS & POLISH (Week 4)**

**Objective**: Complete rate limiter cleanup and polish the implementation.

#### **Day 1-2: Rate Limiter Lifecycle**

**Files to Modify:**
- `/src/exchanges/interfaces/rest/base_rate_limit.py`
- `/src/exchanges/integrations/mexc/rest/rate_limit.py`
- `/src/exchanges/integrations/gateio/rest/rate_limit.py`

**Tasks:**
1. **Implement AsyncResource in Rate Limiters**
   ```python
   class BaseExchangeRateLimit(AsyncResource):
       def __init__(self, ...):
           self._pending_sleeps: Set[asyncio.Task] = set()
           self._is_shutdown = False
       
       async def stop(self, timeout=5.0):
           self._is_shutdown = True
           # Cancel sleep operations
           # Release semaphores
   ```

2. **Add Tracked Sleep Operations**
   ```python
   async def _tracked_sleep(self, delay: float):
       if self._is_shutdown:
           return
       sleep_task = asyncio.create_task(asyncio.sleep(delay))
       self._pending_sleeps.add(sleep_task)
       try:
           await sleep_task
       finally:
           self._pending_sleeps.discard(sleep_task)
   ```

**Success Criteria:**
- Rate limiters implement clean shutdown
- All sleep operations tracked and cancelable
- Rate limiter tests pass

#### **Day 3-4: Demo Script Integration**

**Files to Modify:**
- `/src/examples/demo/rx_mm_demo.py`

**Tasks:**
1. **Fix Context Scope Bug**
   ```python
   async def main():
       async with ExchangeContext(config) as exchanges:
           context = MarketMakerContext(
               public_exchange=exchanges.public_exchange,
               private_exchange=exchanges.private_exchange,
               # ... other params
           )
           # Run trading logic
       # Automatic cleanup
   ```

2. **Add Comprehensive Cleanup**
   - Remove manual cleanup code
   - Rely on context manager for resource management

**Success Criteria:**
- Demo script exits cleanly without hanging
- No manual cleanup required
- All demo tests pass

#### **Day 5: Testing & Validation**

**Files to Create:**
- `/tests/lifecycle/test_asyncio_cleanup.py`
- `/tests/integration/test_full_lifecycle.py`

**Tasks:**
1. **Create Lifecycle Tests**
   ```python
   async def test_no_hanging_tasks():
       initial_tasks = len(asyncio.all_tasks())
       
       async with ExchangeContext(config) as exchanges:
           # Use exchanges
           pass
       
       final_tasks = len(asyncio.all_tasks())
       assert final_tasks <= initial_tasks
   ```

2. **Performance Validation**
   - Ensure no performance regression
   - Validate HFT latency requirements still met
   - Benchmark shutdown times

**Success Criteria:**
- All lifecycle tests pass
- No task leaks detected
- Performance requirements maintained

---

## Implementation Guidelines

### **Code Quality Standards**

1. **Error Handling**
   - All cleanup operations must use try/except
   - Continue cleanup even if individual operations fail
   - Log errors but don't raise exceptions during shutdown

2. **Timeout Management**
   - All shutdown operations must have timeouts
   - Default timeout: 5 seconds for normal shutdown
   - Force cleanup if timeout exceeded

3. **Logging**
   - Log all lifecycle events (start/stop)
   - Include timing information
   - Use structured logging with component names

4. **Testing**
   - Each component must have lifecycle tests
   - Integration tests for full shutdown scenarios
   - Performance tests to ensure no regression

### **Risk Mitigation**

1. **Incremental Rollout**
   - Implement one component at a time
   - Test thoroughly before moving to next component
   - Maintain backward compatibility during transition

2. **Rollback Plan**
   - Keep original implementation as fallback
   - Use feature flags to enable/disable new lifecycle
   - Monitor for performance issues

3. **Performance Monitoring**
   - Add metrics for shutdown times
   - Monitor task counts during operation
   - Alert on hanging task detection

### **Testing Strategy**

1. **Unit Tests**
   - Test each AsyncResource implementation
   - Verify proper start/stop behavior
   - Test timeout scenarios

2. **Integration Tests**
   - Test full exchange lifecycle
   - Verify clean shutdown scenarios
   - Test error conditions and recovery

3. **Performance Tests**
   - Benchmark normal operation performance
   - Measure shutdown time performance
   - Validate HFT latency requirements

4. **Load Tests**
   - Test under high message volume
   - Verify cleanup under stress
   - Test concurrent access scenarios

## Success Metrics

### **Primary Objectives**

1. **Zero Hanging Tasks**
   - Target: 0 AsyncIO tasks remaining after program completion
   - Measurement: `len(asyncio.all_tasks())` before/after operation
   - Success: Consistent task count across all test scenarios

2. **Fast Shutdown**
   - Target: < 5 seconds for complete shutdown
   - Measurement: Time from close() call to completion
   - Success: 95% of shutdowns complete within target

3. **Resource Cleanup**
   - Target: All resources properly released
   - Measurement: WebSocket connections, subscriptions, semaphores
   - Success: Zero resource leaks detected in testing

### **Performance Requirements**

1. **HFT Latency Maintained**
   - Target: < 50ms end-to-end arbitrage execution
   - Measurement: Latency benchmarks during operation
   - Success: No measurable performance regression

2. **Memory Usage Stable**
   - Target: No memory leaks during lifecycle operations
   - Measurement: Memory profiling over extended runs
   - Success: Stable memory usage patterns

3. **CPU Overhead Minimal**
   - Target: < 1% CPU overhead for lifecycle management
   - Measurement: CPU profiling during normal operation
   - Success: Negligible impact on trading performance

## Risk Assessment

### **High Risk Items**

1. **WebSocket Connection Loops** - Complex state management
2. **Message Queue Processing** - High message volume scenarios
3. **Observable Stream Dependencies** - Complex subscription chains

### **Medium Risk Items**

1. **Rate Limiter Integration** - Timing-sensitive operations
2. **Exchange Factory Changes** - Central component with many dependencies
3. **Context Manager Integration** - New usage patterns

### **Low Risk Items**

1. **AsyncResource Interface** - Simple abstract interface
2. **Task Manager** - Well-defined scope
3. **Demo Script Updates** - Isolated changes

## Timeline Summary

| Phase | Duration | Deliverables | Risk Level |
|-------|----------|--------------|------------|
| **Phase 1** | Week 1 | WebSocket fixes, Core infrastructure | HIGH |
| **Phase 2** | Week 2 | Observable streams, Handler unbinding | MEDIUM |
| **Phase 3** | Week 3 | Exchange integration, Factory updates | MEDIUM |
| **Phase 4** | Week 4 | Rate limiters, Testing, Polish | LOW |

**Total Implementation Time**: 4 weeks

**Key Milestones**:
- End of Week 1: Critical hanging issues resolved
- End of Week 2: Observable stream leaks fixed
- End of Week 3: Full exchange lifecycle implemented
- End of Week 4: Complete solution tested and validated

This roadmap provides a comprehensive, step-by-step approach to implementing AsyncIO task cleanup while maintaining the high-performance requirements of the HFT arbitrage system.