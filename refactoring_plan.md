# CEX Arbitrage Engine - RxPY Refactoring Plan

## Executive Summary

This document outlines a comprehensive plan to refactor the CEX arbitrage engine using RxPY (ReactiveX for Python) patterns. The refactoring aims to simplify complex asynchronous flows, improve code clarity, and maintain HFT performance requirements (<50ms latency).

## Current Architecture Analysis

### Pain Points Identified

1. **Callback Hell in WebSocket Handlers**
   - Deeply nested callbacks in message processing
   - Difficult error propagation through callback chains
   - Complex state management across callbacks

2. **Complex Multi-Exchange Coordination**
   - Manual synchronization of data from multiple exchanges
   - Race conditions in arbitrage opportunity detection
   - Inefficient polling patterns for cross-exchange data

3. **Error Handling Complexity**
   - Scattered try-catch blocks throughout async code
   - Inconsistent retry strategies across components
   - Difficult to implement circuit breakers and fallbacks

4. **Backpressure Issues**
   - WebSocket buffers can overflow during high volatility
   - No elegant throttling mechanism for rate-limited APIs
   - Memory issues from unbounded queues

## Refactoring Strategy

### Core Principles

1. **Rational Application** - Only use RxPY where it genuinely simplifies code
2. **Performance First** - Maintain sub-50ms latency requirements
3. **Incremental Migration** - Refactor component by component
4. **Backward Compatibility** - Maintain existing interfaces during transition

### Priority Classification

- **P0 (Critical)**: Components causing production issues or blocking features
- **P1 (High)**: Significant complexity reduction opportunities
- **P2 (Medium)**: Quality of life improvements
- **P3 (Low)**: Nice-to-have enhancements

## Detailed Refactoring Tasks

### Phase 1: Foundation (Week 1-2)

#### Task 1.1: RxPY Integration Setup [P0]
**File**: `pyproject.toml`, `requirements.txt`
**Effort**: 2 hours

- [ ] Add RxPY dependency (version 4.0+)
- [ ] Create `src/infrastructure/reactive/` module structure
- [ ] Setup base Observable factories and utilities
- [ ] Create performance benchmarking utilities for before/after comparison

```python
# src/infrastructure/reactive/__init__.py
from .factories import create_websocket_stream, create_rest_stream
from .operators import with_retry, with_backpressure, with_timeout
from .schedulers import HFTScheduler
```

#### Task 1.2: Reactive WebSocket Base [P0]
**File**: `src/infrastructure/reactive/websocket_stream.py`
**Effort**: 1 day

- [ ] Create Observable-based WebSocket wrapper
- [ ] Implement automatic reconnection with exponential backoff
- [ ] Add message type filtering and routing
- [ ] Include performance metrics collection

```python
# Example implementation
class ReactiveWebSocketClient:
    def create_message_stream(self) -> Observable:
        return rx.create(self._subscribe_to_messages).pipe(
            ops.retry_with_backoff(max_attempts=5),
            ops.share()  # Multicast to multiple subscribers
        )
```

#### Task 1.3: Reactive REST Client [P1]
**File**: `src/infrastructure/reactive/rest_stream.py`
**Effort**: 4 hours

- [ ] Create Observable-based REST request wrapper
- [ ] Implement rate limiting with `throttle` operator
- [ ] Add retry logic with circuit breaker pattern
- [ ] Cache responses using `share_replay` where appropriate

### Phase 2: WebSocket Refactoring (Week 2-3)

#### Task 2.1: Refactor ws_manager.py [P0]
**File**: `src/infrastructure/networking/websocket/ws_manager.py`
**Effort**: 2 days
**Current Issues**: Complex callback chains, difficult error handling

- [ ] Replace callback-based message handling with Observable streams
- [ ] Implement backpressure using `buffer_with_time_or_count`
- [ ] Add `catch` operators for graceful error recovery
- [ ] Use `merge` for combining multiple WebSocket connections

**Before**:
```python
async def _handle_message(self, message: str):
    try:
        data = self._parse_message(message)
        await self._route_message(data)
        await self._update_metrics(data)
    except Exception as e:
        await self._handle_error(e)
        await self._maybe_reconnect()
```

**After**:
```python
def create_message_stream(self) -> Observable:
    return self._raw_messages.pipe(
        ops.map(self._parse_message),
        ops.catch(self._handle_parse_error),
        ops.flat_map(self._route_message),
        ops.tap(self._update_metrics),
        ops.retry_when(self._should_retry),
        ops.share()
    )
```

#### Task 2.2: Refactor MEXC WebSocket Handler [P0]
**File**: `src/exchanges/integrations/mexc/ws/strategies/public/connection.py`
**Effort**: 1 day

- [ ] Convert protobuf message parsing to Observable pipeline
- [ ] Implement `buffer` operator for batch processing
- [ ] Add `timeout` operator for stale connection detection
- [ ] Use `distinct_until_changed` for deduplication

#### Task 2.3: Refactor Gate.io WebSocket Handler [P0]
**File**: `src/exchanges/integrations/gateio/ws/strategies/spot/public/connection.py`
**Effort**: 1 day

- [ ] Similar refactoring as MEXC
- [ ] Handle dual market (spot/futures) streams with `merge`
- [ ] Implement proper stream disposal on market switch

### Phase 3: Market Data Aggregation (Week 3-4)

#### Task 3.1: Refactor Arbitrage Aggregator [P0]
**File**: `src/trading/arbitrage/aggregator.py`
**Effort**: 2 days
**Current Issues**: Complex synchronization logic, race conditions

- [ ] Use `combine_latest` for cross-exchange price monitoring
- [ ] Implement `window` operator for time-based opportunity detection
- [ ] Add `debounce` for trade execution triggers
- [ ] Use `scan` for maintaining arbitrage state

**Before**:
```python
async def detect_arbitrage(self):
    mexc_price = await self.get_mexc_price()
    gate_price = await self.get_gate_price()
    if self.is_opportunity(mexc_price, gate_price):
        await self.execute_arbitrage()
```

**After**:
```python
def create_arbitrage_stream(self) -> Observable:
    return rx.combine_latest(
        self.mexc_price_stream,
        self.gate_price_stream
    ).pipe(
        ops.map(lambda prices: self.calculate_spread(*prices)),
        ops.filter(lambda spread: spread > self.threshold),
        ops.debounce(0.1),  # Avoid rapid-fire executions
        ops.flat_map(self.execute_arbitrage)
    )
```

#### Task 3.2: Orderbook Stream Processing [P1]
**File**: `src/exchanges/interfaces/composite/base_public_exchange.py`
**Effort**: 1 day

- [ ] Create Observable streams for orderbook updates
- [ ] Use `scan` for incremental orderbook building
- [ ] Implement `sample` for rate-limited consumers
- [ ] Add `timestamp` operator for latency tracking

#### Task 3.3: Trade Stream Aggregation [P1]
**File**: New file `src/infrastructure/reactive/market_data.py`
**Effort**: 1 day

- [ ] Aggregate trade streams from multiple exchanges
- [ ] Use `group_by` for per-symbol processing
- [ ] Implement `buffer_with_time` for volume calculations
- [ ] Add `sliding_window` for moving averages

### Phase 4: Error Handling & Resilience (Week 4-5)

#### Task 4.1: Reactive Retry Strategies [P1]
**File**: `src/infrastructure/reactive/retry_strategies.py`
**Effort**: 4 hours

- [ ] Implement exponential backoff with `retry_when`
- [ ] Add circuit breaker pattern using `scan` and `filter`
- [ ] Create fallback strategies with `catch` and `on_error_resume_next`
- [ ] Add timeout handling with `timeout` operator

```python
def with_advanced_retry(source: Observable) -> Observable:
    return source.pipe(
        ops.timeout(30),
        ops.retry_when(exponential_backoff(max_attempts=5)),
        ops.catch(lambda err: fallback_stream if is_recoverable(err) else rx.throw(err))
    )
```

#### Task 4.2: Connection Lifecycle Management [P2]
**File**: `src/infrastructure/reactive/connection_manager.py`
**Effort**: 1 day

- [ ] Manage connection states with `scan` operator
- [ ] Implement health checks using `interval` and `switch_map`
- [ ] Add automatic reconnection with `repeat_when`
- [ ] Create connection pooling with `share` and reference counting

### Phase 5: Performance Optimization (Week 5-6)

#### Task 5.1: HFT Scheduler Implementation [P1]
**File**: `src/infrastructure/reactive/schedulers.py`
**Effort**: 1 day

- [ ] Create custom scheduler optimized for HFT
- [ ] Implement priority queue for critical operations
- [ ] Add CPU affinity for performance-critical streams
- [ ] Minimize context switching overhead

#### Task 5.2: Memory Optimization [P1]
**File**: Various
**Effort**: 2 days

- [ ] Implement proper stream disposal patterns
- [ ] Add memory monitoring observables
- [ ] Use `take_until` for automatic cleanup
- [ ] Optimize buffer sizes based on profiling

#### Task 5.3: Latency Monitoring [P2]
**File**: `src/infrastructure/reactive/metrics.py`
**Effort**: 4 hours

- [ ] Create latency tracking observables
- [ ] Use `timestamp` and `time_interval` operators
- [ ] Implement percentile calculations with `scan`
- [ ] Add alerting for latency violations

### Phase 6: Testing & Migration (Week 6-7)

#### Task 6.1: Unit Tests for Reactive Components [P0]
**File**: `tests/test_reactive/`
**Effort**: 3 days

- [ ] Test Observable factories and custom operators
- [ ] Verify backpressure handling under load
- [ ] Test error scenarios and recovery
- [ ] Benchmark performance vs current implementation

#### Task 6.2: Integration Tests [P0]
**File**: `tests/integration/test_reactive_exchanges.py`
**Effort**: 2 days

- [ ] Test end-to-end data flow with real exchanges
- [ ] Verify arbitrage detection accuracy
- [ ] Test failover and recovery scenarios
- [ ] Measure latency under production-like load

#### Task 6.3: Gradual Migration Strategy [P0]
**File**: Documentation and migration scripts
**Effort**: 1 day

- [ ] Create feature flags for reactive components
- [ ] Implement A/B testing infrastructure
- [ ] Document rollback procedures
- [ ] Create performance comparison dashboards

## Success Metrics

### Performance Metrics
- **Latency**: Maintain <50ms end-to-end arbitrage execution
- **Throughput**: Handle 10,000+ messages/second per exchange
- **Memory**: Reduce memory footprint by 30%
- **CPU**: Decrease CPU usage by 20%

### Code Quality Metrics
- **Complexity**: Reduce cyclomatic complexity by 40%
- **Lines of Code**: Decrease by 25% through reactive patterns
- **Test Coverage**: Maintain >90% coverage
- **Bug Rate**: Reduce production incidents by 50%

### Developer Experience Metrics
- **Onboarding Time**: Reduce from 2 weeks to 1 week
- **Debug Time**: Decrease average debug time by 60%
- **Feature Velocity**: Increase by 30%

## Risk Mitigation

### Technical Risks
1. **Performance Regression**
   - Mitigation: Comprehensive benchmarking before/after
   - Fallback: Feature flags for instant rollback

2. **Learning Curve**
   - Mitigation: Team training sessions on RxPY
   - Documentation: Extensive examples and patterns

3. **Integration Issues**
   - Mitigation: Incremental migration approach
   - Testing: Thorough integration test suite

### Business Risks
1. **Trading Disruption**
   - Mitigation: Parallel run of old and new systems
   - Monitoring: Real-time alerts for anomalies

2. **Opportunity Loss**
   - Mitigation: Gradual rollout with careful monitoring
   - Validation: Shadow mode testing before production

## Timeline Summary

- **Week 1-2**: Foundation and infrastructure setup
- **Week 2-3**: WebSocket refactoring
- **Week 3-4**: Market data aggregation improvements
- **Week 4-5**: Error handling and resilience
- **Week 5-6**: Performance optimization
- **Week 6-7**: Testing and migration

**Total Estimated Effort**: 7 weeks with 2 developers

## Next Steps

1. Review and approve refactoring plan
2. Set up RxPY development environment
3. Create proof-of-concept for WebSocket streams
4. Begin Phase 1 implementation
5. Establish performance benchmarking baseline

## Appendix: RxPY Operators Cheat Sheet

### Essential Operators for HFT

- `buffer_with_time_or_count`: Batch processing for efficiency
- `combine_latest`: Synchronize multiple price streams
- `debounce`: Prevent rapid-fire trade executions
- `retry_when`: Sophisticated retry logic
- `scan`: Maintain state across stream
- `share`: Multicast to multiple subscribers
- `throttle`: Rate limiting for APIs
- `timeout`: Detect stale connections
- `window`: Time-based analysis windows
- `with_latest_from`: Enrich events with latest data

---

*This refactoring plan provides a structured approach to modernizing the CEX arbitrage engine with reactive patterns while maintaining critical performance requirements and system stability.*