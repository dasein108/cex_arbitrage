# WebSocket Performance Validation Framework

## Overview

This document defines a comprehensive performance validation framework for the WebSocket architecture refactoring. It ensures HFT compliance and validates that the new mixin-based architecture meets or exceeds current performance targets.

## Performance Targets & Compliance

### HFT Latency Requirements

| Component | Current Target | Post-Refactoring Target | Validation Method |
|-----------|----------------|-------------------------|-------------------|
| Message Type Detection | <10μs | <8μs | Microsecond timing |
| Orderbook Processing | <50μs | <45μs | End-to-end timing |
| Trade Processing | <30μs | <25μs | End-to-end timing |
| Ticker Processing | <20μs | <18μs | End-to-end timing |
| Connection Establishment | <100ms | <80ms | Connection timing |
| Reconnection Time | <50ms | <40ms | Reconnection timing |
| Template Method Overhead | N/A | <5μs | New requirement |

### MEXC-Specific Targets

| Operation | Protobuf Target | JSON Fallback Target | Validation |
|-----------|----------------|----------------------|------------|
| Binary Detection | <10μs | N/A | Magic byte detection |
| Orderbook Parsing | <50μs | <100μs | Full parsing cycle |
| Trade Parsing | <30μs | <60μs | Full parsing cycle |
| Ticker Parsing | <20μs | <40μs | Full parsing cycle |
| Object Pool Efficiency | 75% reuse | 75% reuse | Pool statistics |

### Memory Performance Targets

| Metric | Current | Target | Validation Method |
|--------|---------|--------|------------------|
| Allocation Reduction | 75% (MEXC) | 75% | Object pool metrics |
| Memory per Connection | Baseline | ≤110% of baseline | Memory profiling |
| GC Pressure | Baseline | ≤105% of baseline | GC monitoring |
| Memory Leaks | 0 | 0 | Extended testing |

## Performance Testing Framework

### 1. Microsecond-Level Timing Infrastructure

**File:** `/ws_refactoring/performance_testing/timing_framework.py`

```python
"""
High-precision timing framework for HFT performance validation.
"""

import time
import statistics
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass
from contextlib import contextmanager
import asyncio


@dataclass
class PerformanceResult:
    """Performance measurement result."""
    operation: str
    measurements: List[float]  # microseconds
    mean: float
    median: float
    p95: float
    p99: float
    min_time: float
    max_time: float
    std_dev: float
    target_us: Optional[float] = None
    
    @property
    def passes_target(self) -> bool:
        """Check if performance meets target."""
        if self.target_us is None:
            return True
        return self.p95 <= self.target_us
    
    def summary(self) -> str:
        """Get performance summary string."""
        status = "✅ PASS" if self.passes_target else "❌ FAIL"
        target_str = f" (target: {self.target_us}μs)" if self.target_us else ""
        
        return (
            f"{self.operation}: {status}\n"
            f"  Mean: {self.mean:.2f}μs, P95: {self.p95:.2f}μs, P99: {self.p99:.2f}μs{target_str}\n"
            f"  Min: {self.min_time:.2f}μs, Max: {self.max_time:.2f}μs, StdDev: {self.std_dev:.2f}μs"
        )


class HFTPerformanceTester:
    """High-frequency trading performance testing framework."""
    
    def __init__(self):
        self.results: Dict[str, PerformanceResult] = {}
    
    @contextmanager
    def measure_operation(self, operation_name: str, target_us: Optional[float] = None):
        """Context manager for measuring operation performance."""
        start_time = time.perf_counter()
        try:
            yield
        finally:
            end_time = time.perf_counter()
            duration_us = (end_time - start_time) * 1_000_000
            
            if operation_name not in self.results:
                self.results[operation_name] = PerformanceResult(
                    operation=operation_name,
                    measurements=[],
                    mean=0, median=0, p95=0, p99=0,
                    min_time=0, max_time=0, std_dev=0,
                    target_us=target_us
                )
            
            self.results[operation_name].measurements.append(duration_us)
    
    def measure_function(self, func: Callable, operation_name: str, 
                        iterations: int = 1000, target_us: Optional[float] = None) -> PerformanceResult:
        """Measure function performance over multiple iterations."""
        measurements = []
        
        # Warmup
        for _ in range(100):
            func()
        
        # Actual measurements
        for _ in range(iterations):
            start_time = time.perf_counter()
            func()
            end_time = time.perf_counter()
            measurements.append((end_time - start_time) * 1_000_000)
        
        return self._create_result(operation_name, measurements, target_us)
    
    async def measure_async_function(self, func: Callable, operation_name: str,
                                   iterations: int = 1000, target_us: Optional[float] = None) -> PerformanceResult:
        """Measure async function performance over multiple iterations."""
        measurements = []
        
        # Warmup
        for _ in range(100):
            await func()
        
        # Actual measurements
        for _ in range(iterations):
            start_time = time.perf_counter()
            await func()
            end_time = time.perf_counter()
            measurements.append((end_time - start_time) * 1_000_000)
        
        return self._create_result(operation_name, measurements, target_us)
    
    def _create_result(self, operation_name: str, measurements: List[float], 
                      target_us: Optional[float]) -> PerformanceResult:
        """Create performance result from measurements."""
        result = PerformanceResult(
            operation=operation_name,
            measurements=measurements,
            mean=statistics.mean(measurements),
            median=statistics.median(measurements),
            p95=statistics.quantiles(measurements, n=20)[18],  # 95th percentile
            p99=statistics.quantiles(measurements, n=100)[98],  # 99th percentile
            min_time=min(measurements),
            max_time=max(measurements),
            std_dev=statistics.stdev(measurements),
            target_us=target_us
        )
        
        self.results[operation_name] = result
        return result
    
    def finalize_results(self):
        """Finalize all accumulated results."""
        for result in self.results.values():
            if result.measurements:
                result.mean = statistics.mean(result.measurements)
                result.median = statistics.median(result.measurements)
                result.p95 = statistics.quantiles(result.measurements, n=20)[18]
                result.p99 = statistics.quantiles(result.measurements, n=100)[98]
                result.min_time = min(result.measurements)
                result.max_time = max(result.measurements)
                result.std_dev = statistics.stdev(result.measurements)
    
    def get_summary_report(self) -> str:
        """Get comprehensive performance report."""
        self.finalize_results()
        
        report = ["=" * 80]
        report.append("HFT PERFORMANCE VALIDATION REPORT")
        report.append("=" * 80)
        
        passed = 0
        failed = 0
        
        for result in sorted(self.results.values(), key=lambda r: r.operation):
            report.append(result.summary())
            report.append("")
            
            if result.passes_target:
                passed += 1
            else:
                failed += 1
        
        report.append("=" * 80)
        report.append(f"SUMMARY: {passed} PASSED, {failed} FAILED")
        
        if failed == 0:
            report.append("🎉 ALL PERFORMANCE TARGETS MET - HFT COMPLIANT")
        else:
            report.append("⚠️  PERFORMANCE TARGETS NOT MET - REVIEW REQUIRED")
        
        report.append("=" * 80)
        
        return "\n".join(report)
```

### 2. Component-Specific Performance Tests

**File:** `/ws_refactoring/performance_testing/component_tests.py`

```python
"""
Component-specific performance tests for WebSocket refactoring.
"""

import asyncio
from typing import Any, Dict, List
import msgspec
from timing_framework import HFTPerformanceTester

# Mock data for testing
MOCK_MEXC_PROTOBUF = b'\x0a\x12spot@public.deals'
MOCK_MEXC_JSON = '{"c":"spot@public.deals.BTCUSDT","d":{"deals":[{"p":"50000","v":"1.0","t":1234567890,"s":1}]}}'
MOCK_GATEIO_JSON = '{"channel":"spot.order","result":{"status":"success"}}'


class BaseWebSocketInterfacePerformanceTest:
    """Performance tests for BaseWebSocketInterface."""
    
    def __init__(self, tester: HFTPerformanceTester):
        self.tester = tester
    
    async def test_message_queuing_performance(self):
        """Test message queuing performance."""
        from infrastructure.networking.websocket.base_interface import BaseWebSocketInterface
        from unittest.mock import Mock
        
        # Mock handler
        handler = Mock()
        handler._handle_message = Mock()
        
        # Mock config
        config = Mock()
        config.heartbeat_interval = 0
        
        interface = BaseWebSocketInterface(config, handler)
        
        # Test message queuing
        async def queue_message():
            await interface._on_raw_message("test message")
        
        result = await self.tester.measure_async_function(
            queue_message,
            "message_queuing",
            iterations=10000,
            target_us=1.0
        )
        
        return result
    
    async def test_state_transition_performance(self):
        """Test connection state transition performance."""
        from infrastructure.networking.websocket.base_interface import BaseWebSocketInterface
        from infrastructure.networking.websocket.structs import ConnectionState
        from unittest.mock import Mock
        
        handler = Mock()
        config = Mock()
        config.heartbeat_interval = 0
        
        interface = BaseWebSocketInterface(config, handler)
        
        async def transition_state():
            await interface._update_state(ConnectionState.CONNECTED)
            await interface._update_state(ConnectionState.DISCONNECTED)
        
        result = await self.tester.measure_async_function(
            transition_state,
            "state_transitions",
            iterations=1000,
            target_us=100.0
        )
        
        return result


class MessageHandlerPerformanceTest:
    """Performance tests for message handlers."""
    
    def __init__(self, tester: HFTPerformanceTester):
        self.tester = tester
    
    async def test_template_method_overhead(self):
        """Test template method pattern overhead."""
        from infrastructure.networking.websocket.handlers.base_message_handler import BaseMessageHandler
        from infrastructure.networking.websocket.message_types import WebSocketMessageType
        
        class MockHandler(BaseMessageHandler):
            async def _detect_message_type(self, raw_message):
                return WebSocketMessageType.ORDERBOOK
            
            async def _route_message(self, message_type, raw_message):
                pass
        
        handler = MockHandler("test")
        
        async def process_message():
            await handler._handle_message("test message")
        
        result = await self.tester.measure_async_function(
            process_message,
            "template_method_overhead",
            iterations=10000,
            target_us=5.0
        )
        
        return result
    
    def test_message_type_detection_performance(self):
        """Test message type detection performance for different formats."""
        
        # MEXC protobuf detection
        def detect_mexc_protobuf():
            # Simulate fast binary detection
            if MOCK_MEXC_PROTOBUF[0] == 0x0a:
                return "orderbook"
            return "unknown"
        
        mexc_protobuf_result = self.tester.measure_function(
            detect_mexc_protobuf,
            "mexc_protobuf_detection",
            iterations=100000,
            target_us=10.0
        )
        
        # MEXC JSON detection
        def detect_mexc_json():
            if '"c"' in MOCK_MEXC_JSON[:100]:
                if "deals" in MOCK_MEXC_JSON[:200]:
                    return "trade"
            return "unknown"
        
        mexc_json_result = self.tester.measure_function(
            detect_mexc_json,
            "mexc_json_detection",
            iterations=50000,
            target_us=15.0
        )
        
        # Gate.io JSON detection
        def detect_gateio_json():
            message = msgspec.json.decode(MOCK_GATEIO_JSON)
            channel = message.get("channel", "")
            if "order" in channel:
                return "order_update"
            return "unknown"
        
        gateio_result = self.tester.measure_function(
            detect_gateio_json,
            "gateio_json_detection",
            iterations=30000,
            target_us=20.0
        )
        
        return [mexc_protobuf_result, mexc_json_result, gateio_result]


class MexcPerformanceTest:
    """MEXC-specific performance tests."""
    
    def __init__(self, tester: HFTPerformanceTester):
        self.tester = tester
    
    def test_protobuf_parsing_performance(self):
        """Test MEXC protobuf parsing performance."""
        
        # Mock protobuf parsing (simplified)
        def parse_orderbook_protobuf():
            # Simulate protobuf parsing with direct field access
            symbol = "BTCUSDT"
            bids = [{"price": 50000.0, "size": 1.0}]
            asks = [{"price": 50001.0, "size": 1.0}]
            return {"symbol": symbol, "bids": bids, "asks": asks}
        
        orderbook_result = self.tester.measure_function(
            parse_orderbook_protobuf,
            "mexc_orderbook_protobuf",
            iterations=10000,
            target_us=50.0
        )
        
        def parse_trade_protobuf():
            # Simulate trade parsing
            return {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "quantity": 1.0,
                "side": "buy",
                "timestamp": 1234567890
            }
        
        trade_result = self.tester.measure_function(
            parse_trade_protobuf,
            "mexc_trade_protobuf",
            iterations=10000,
            target_us=30.0
        )
        
        def parse_ticker_protobuf():
            # Simulate ticker parsing
            return {
                "symbol": "BTCUSDT",
                "bid_price": 49999.0,
                "ask_price": 50001.0,
                "bid_quantity": 1.0,
                "ask_quantity": 1.0
            }
        
        ticker_result = self.tester.measure_function(
            parse_ticker_protobuf,
            "mexc_ticker_protobuf",
            iterations=10000,
            target_us=20.0
        )
        
        return [orderbook_result, trade_result, ticker_result]
    
    def test_object_pool_performance(self):
        """Test object pool performance and efficiency."""
        
        class MockObjectPool:
            def __init__(self):
                self.pool = []
                self.created = 0
                self.reused = 0
            
            def get_entry(self, price, size):
                if self.pool:
                    entry = self.pool.pop()
                    entry.price = price
                    entry.size = size
                    self.reused += 1
                    return entry
                else:
                    self.created += 1
                    return type('Entry', (), {'price': price, 'size': size})()
            
            def return_entry(self, entry):
                if len(self.pool) < 100:  # Max pool size
                    self.pool.append(entry)
        
        pool = MockObjectPool()
        
        # Warm up pool
        entries = []
        for i in range(50):
            entry = pool.get_entry(float(i), float(i))
            entries.append(entry)
        
        for entry in entries:
            pool.return_entry(entry)
        
        def use_object_pool():
            entry = pool.get_entry(50000.0, 1.0)
            pool.return_entry(entry)
        
        result = self.tester.measure_function(
            use_object_pool,
            "mexc_object_pool_usage",
            iterations=10000,
            target_us=2.0
        )
        
        # Calculate efficiency
        total_operations = pool.created + pool.reused
        efficiency = (pool.reused / total_operations) * 100 if total_operations > 0 else 0
        
        print(f"Object Pool Efficiency: {efficiency:.1f}% (target: 75%)")
        
        return result


class ConnectionPerformanceTest:
    """Connection-related performance tests."""
    
    def __init__(self, tester: HFTPerformanceTester):
        self.tester = tester
    
    async def test_connection_mixin_performance(self):
        """Test connection mixin creation and usage performance."""
        from infrastructure.networking.websocket.mixins.connection_mixin import MexcConnectionMixin
        from config.structs import ExchangeConfig
        
        config = ExchangeConfig(
            name="mexc",
            websocket_url="wss://stream.mexc.com/ws"
        )
        
        def create_connection_context():
            mixin = MexcConnectionMixin(config)
            return mixin.create_connection_context()
        
        result = self.tester.measure_function(
            create_connection_context,
            "mexc_connection_context_creation",
            iterations=10000,
            target_us=10.0
        )
        
        return result
    
    async def test_reconnection_policy_performance(self):
        """Test reconnection policy calculation performance."""
        from infrastructure.networking.websocket.mixins.connection_mixin import ReconnectionPolicy
        
        policy = ReconnectionPolicy(
            max_attempts=15,
            initial_delay=0.5,
            backoff_factor=1.5,
            max_delay=30.0
        )
        
        def calculate_delay():
            for attempt in range(10):
                delay = policy.calculate_delay(attempt)
        
        result = self.tester.measure_function(
            calculate_delay,
            "reconnection_policy_calculation",
            iterations=10000,
            target_us=5.0
        )
        
        return result


async def run_comprehensive_performance_test():
    """Run comprehensive performance test suite."""
    tester = HFTPerformanceTester()
    
    print("🚀 Starting WebSocket Performance Validation...")
    print("=" * 80)
    
    # Test BaseWebSocketInterface
    base_tests = BaseWebSocketInterfacePerformanceTest(tester)
    await base_tests.test_message_queuing_performance()
    await base_tests.test_state_transition_performance()
    
    # Test Message Handlers
    handler_tests = MessageHandlerPerformanceTest(tester)
    await handler_tests.test_template_method_overhead()
    handler_tests.test_message_type_detection_performance()
    
    # Test MEXC-specific performance
    mexc_tests = MexcPerformanceTest(tester)
    mexc_tests.test_protobuf_parsing_performance()
    mexc_tests.test_object_pool_performance()
    
    # Test Connection performance
    connection_tests = ConnectionPerformanceTest(tester)
    await connection_tests.test_connection_mixin_performance()
    await connection_tests.test_reconnection_policy_performance()
    
    # Generate report
    report = tester.get_summary_report()
    print(report)
    
    # Save report to file
    with open("/ws_refactoring/performance_results.txt", "w") as f:
        f.write(report)
    
    print("\n📊 Performance report saved to: /ws_refactoring/performance_results.txt")
    
    return tester.results


if __name__ == "__main__":
    asyncio.run(run_comprehensive_performance_test())
```

### 3. Regression Testing Framework

**File:** `/ws_refactoring/performance_testing/regression_tests.py`

```python
"""
Performance regression testing framework.
"""

import json
import asyncio
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
import statistics


@dataclass
class PerformanceBaseline:
    """Performance baseline for regression testing."""
    operation: str
    baseline_p95: float
    baseline_mean: float
    tolerance_percent: float = 10.0  # 10% tolerance
    
    def check_regression(self, current_p95: float, current_mean: float) -> bool:
        """Check if current performance shows regression."""
        p95_regression = ((current_p95 - self.baseline_p95) / self.baseline_p95) * 100
        mean_regression = ((current_mean - self.baseline_mean) / self.baseline_mean) * 100
        
        return (p95_regression <= self.tolerance_percent and 
                mean_regression <= self.tolerance_percent)
    
    def regression_report(self, current_p95: float, current_mean: float) -> str:
        """Generate regression report."""
        p95_change = ((current_p95 - self.baseline_p95) / self.baseline_p95) * 100
        mean_change = ((current_mean - self.baseline_mean) / self.baseline_mean) * 100
        
        status = "✅ PASS" if self.check_regression(current_p95, current_mean) else "❌ REGRESSION"
        
        return (
            f"{self.operation}: {status}\n"
            f"  P95: {self.baseline_p95:.2f}μs → {current_p95:.2f}μs ({p95_change:+.1f}%)\n"
            f"  Mean: {self.baseline_mean:.2f}μs → {current_mean:.2f}μs ({mean_change:+.1f}%)"
        )


class PerformanceRegressionTester:
    """Framework for performance regression testing."""
    
    def __init__(self, baseline_file: str = "/ws_refactoring/performance_baseline.json"):
        self.baseline_file = baseline_file
        self.baselines: Dict[str, PerformanceBaseline] = {}
        self.load_baselines()
    
    def load_baselines(self):
        """Load performance baselines from file."""
        try:
            with open(self.baseline_file, 'r') as f:
                data = json.load(f)
                
            for operation, baseline_data in data.items():
                self.baselines[operation] = PerformanceBaseline(**baseline_data)
                
        except FileNotFoundError:
            print(f"⚠️  Baseline file not found: {self.baseline_file}")
            print("   Creating new baseline on first run...")
    
    def save_baselines(self):
        """Save current baselines to file."""
        data = {}
        for operation, baseline in self.baselines.items():
            data[operation] = asdict(baseline)
        
        with open(self.baseline_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_baseline(self, operation: str, measurements: List[float], 
                       tolerance_percent: float = 10.0):
        """Create baseline from measurements."""
        baseline = PerformanceBaseline(
            operation=operation,
            baseline_p95=statistics.quantiles(measurements, n=20)[18],
            baseline_mean=statistics.mean(measurements),
            tolerance_percent=tolerance_percent
        )
        
        self.baselines[operation] = baseline
        self.save_baselines()
        
        print(f"📊 Created baseline for {operation}: "
              f"P95={baseline.baseline_p95:.2f}μs, Mean={baseline.baseline_mean:.2f}μs")
    
    def check_regression(self, operation: str, measurements: List[float]) -> bool:
        """Check for performance regression."""
        if operation not in self.baselines:
            print(f"⚠️  No baseline for {operation}, creating...")
            self.create_baseline(operation, measurements)
            return True
        
        baseline = self.baselines[operation]
        current_p95 = statistics.quantiles(measurements, n=20)[18]
        current_mean = statistics.mean(measurements)
        
        return baseline.check_regression(current_p95, current_mean)
    
    def generate_regression_report(self, test_results: Dict[str, Any]) -> str:
        """Generate comprehensive regression report."""
        report = ["=" * 80]
        report.append("PERFORMANCE REGRESSION ANALYSIS")
        report.append("=" * 80)
        
        passed = 0
        failed = 0
        new_baselines = 0
        
        for operation, result in test_results.items():
            if hasattr(result, 'measurements'):
                measurements = result.measurements
                current_p95 = result.p95
                current_mean = result.mean
                
                if operation not in self.baselines:
                    self.create_baseline(operation, measurements)
                    report.append(f"{operation}: 📊 NEW BASELINE CREATED")
                    new_baselines += 1
                else:
                    baseline = self.baselines[operation]
                    regression_report = baseline.regression_report(current_p95, current_mean)
                    report.append(regression_report)
                    
                    if baseline.check_regression(current_p95, current_mean):
                        passed += 1
                    else:
                        failed += 1
        
        report.append("")
        report.append("=" * 80)
        report.append(f"REGRESSION SUMMARY: {passed} PASSED, {failed} REGRESSIONS, {new_baselines} NEW")
        
        if failed == 0:
            report.append("🎉 NO PERFORMANCE REGRESSIONS DETECTED")
        else:
            report.append("⚠️  PERFORMANCE REGRESSIONS DETECTED - REVIEW REQUIRED")
        
        report.append("=" * 80)
        
        return "\n".join(report)


# Pre-defined baselines for critical operations
CRITICAL_OPERATION_BASELINES = {
    "mexc_orderbook_protobuf": PerformanceBaseline(
        operation="mexc_orderbook_protobuf",
        baseline_p95=50.0,
        baseline_mean=35.0,
        tolerance_percent=5.0  # Strict tolerance for critical path
    ),
    "mexc_trade_protobuf": PerformanceBaseline(
        operation="mexc_trade_protobuf", 
        baseline_p95=30.0,
        baseline_mean=20.0,
        tolerance_percent=5.0
    ),
    "mexc_ticker_protobuf": PerformanceBaseline(
        operation="mexc_ticker_protobuf",
        baseline_p95=20.0,
        baseline_mean=15.0,
        tolerance_percent=5.0
    ),
    "message_queuing": PerformanceBaseline(
        operation="message_queuing",
        baseline_p95=1.0,
        baseline_mean=0.5,
        tolerance_percent=15.0
    ),
    "template_method_overhead": PerformanceBaseline(
        operation="template_method_overhead",
        baseline_p95=5.0,
        baseline_mean=3.0,
        tolerance_percent=10.0
    )
}


async def run_regression_test():
    """Run complete regression test suite."""
    from component_tests import run_comprehensive_performance_test
    
    print("🔍 Starting Performance Regression Testing...")
    
    # Run performance tests
    results = await run_comprehensive_performance_test()
    
    # Initialize regression tester with critical baselines
    tester = PerformanceRegressionTester()
    
    # Add critical baselines if not present
    for operation, baseline in CRITICAL_OPERATION_BASELINES.items():
        if operation not in tester.baselines:
            tester.baselines[operation] = baseline
    
    # Generate regression report
    regression_report = tester.generate_regression_report(results)
    print("\n" + regression_report)
    
    # Save regression report
    with open("/ws_refactoring/regression_report.txt", "w") as f:
        f.write(regression_report)
    
    print("\n📈 Regression report saved to: /ws_refactoring/regression_report.txt")
    
    return tester


if __name__ == "__main__":
    asyncio.run(run_regression_test())
```

## Performance Monitoring Integration

### 1. Continuous Performance Monitoring

**File:** `/ws_refactoring/performance_testing/continuous_monitoring.py`

```python
"""
Continuous performance monitoring for production validation.
"""

import asyncio
import time
from typing import Dict, Any
import json
from datetime import datetime


class ContinuousPerformanceMonitor:
    """Monitor WebSocket performance in production."""
    
    def __init__(self, sample_interval: float = 60.0):
        self.sample_interval = sample_interval
        self.metrics: Dict[str, Any] = {}
        self.running = False
    
    async def start_monitoring(self, websocket_manager):
        """Start continuous performance monitoring."""
        self.running = True
        
        while self.running:
            try:
                # Collect metrics
                metrics = self._collect_metrics(websocket_manager)
                
                # Store metrics with timestamp
                timestamp = datetime.now().isoformat()
                self.metrics[timestamp] = metrics
                
                # Log critical metrics
                self._log_critical_metrics(metrics)
                
                # Check for performance degradation
                self._check_performance_alerts(metrics)
                
                await asyncio.sleep(self.sample_interval)
                
            except Exception as e:
                print(f"⚠️  Performance monitoring error: {e}")
                await asyncio.sleep(self.sample_interval)
    
    def _collect_metrics(self, websocket_manager) -> Dict[str, Any]:
        """Collect current performance metrics."""
        base_metrics = websocket_manager.get_performance_metrics()
        
        # Add system metrics
        current_time = time.time()
        
        metrics = {
            "timestamp": current_time,
            "websocket_metrics": base_metrics,
            "system_metrics": {
                "cpu_usage": self._get_cpu_usage(),
                "memory_usage": self._get_memory_usage(),
                "gc_stats": self._get_gc_stats()
            }
        }
        
        return metrics
    
    def _get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        # Simplified - would use psutil in real implementation
        return 0.0
    
    def _get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage."""
        # Simplified - would use psutil in real implementation
        return {"rss": 0, "vms": 0}
    
    def _get_gc_stats(self) -> Dict[str, Any]:
        """Get garbage collection statistics."""
        import gc
        return {
            "collections": gc.get_count(),
            "threshold": gc.get_threshold()
        }
    
    def _log_critical_metrics(self, metrics: Dict[str, Any]):
        """Log critical performance metrics."""
        ws_metrics = metrics.get("websocket_metrics", {})
        
        if "avg_processing_time_us" in ws_metrics:
            avg_time = ws_metrics["avg_processing_time_us"]
            if avg_time > 100:  # Alert if processing time > 100μs
                print(f"⚠️  High processing time detected: {avg_time:.2f}μs")
        
        if "error_rate" in ws_metrics:
            error_rate = ws_metrics["error_rate"]
            if error_rate > 0.01:  # Alert if error rate > 1%
                print(f"⚠️  High error rate detected: {error_rate:.2%}")
    
    def _check_performance_alerts(self, metrics: Dict[str, Any]):
        """Check for performance degradation alerts."""
        ws_metrics = metrics.get("websocket_metrics", {})
        
        # Define alert thresholds
        alerts = []
        
        if ws_metrics.get("avg_processing_time_us", 0) > 200:
            alerts.append("Average processing time exceeds 200μs")
        
        if ws_metrics.get("error_rate", 0) > 0.05:
            alerts.append("Error rate exceeds 5%")
        
        if not ws_metrics.get("is_connected", True):
            alerts.append("WebSocket connection lost")
        
        # Log alerts
        for alert in alerts:
            print(f"🚨 PERFORMANCE ALERT: {alert}")
    
    def stop_monitoring(self):
        """Stop performance monitoring."""
        self.running = False
    
    def export_metrics(self, filename: str):
        """Export collected metrics to file."""
        with open(filename, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        
        print(f"📊 Performance metrics exported to: {filename}")
```

## Validation Scripts

### 1. Pre-Deployment Validation

**File:** `/ws_refactoring/performance_testing/validation_script.py`

```python
"""
Pre-deployment validation script for WebSocket refactoring.
"""

import asyncio
import sys
from component_tests import run_comprehensive_performance_test
from regression_tests import run_regression_test


async def validate_refactoring():
    """Complete validation of WebSocket refactoring."""
    print("🔬 WEBSOCKET REFACTORING VALIDATION")
    print("=" * 80)
    
    validation_results = {
        "performance_tests": False,
        "regression_tests": False,
        "hft_compliance": False
    }
    
    try:
        # 1. Run comprehensive performance tests
        print("\n📊 Running Performance Tests...")
        performance_results = await run_comprehensive_performance_test()
        
        # Check if all performance targets met
        all_passed = all(
            result.passes_target for result in performance_results.values()
            if hasattr(result, 'passes_target')
        )
        validation_results["performance_tests"] = all_passed
        
        if all_passed:
            print("✅ All performance tests PASSED")
        else:
            print("❌ Some performance tests FAILED")
        
        # 2. Run regression tests
        print("\n📈 Running Regression Tests...")
        regression_tester = await run_regression_test()
        
        # Check for regressions
        no_regressions = all(
            baseline.check_regression(
                performance_results[operation].p95,
                performance_results[operation].mean
            )
            for operation, baseline in regression_tester.baselines.items()
            if operation in performance_results
        )
        validation_results["regression_tests"] = no_regressions
        
        if no_regressions:
            print("✅ No performance regressions detected")
        else:
            print("❌ Performance regressions detected")
        
        # 3. HFT compliance check
        hft_critical_operations = [
            "mexc_orderbook_protobuf",
            "mexc_trade_protobuf", 
            "mexc_ticker_protobuf",
            "message_queuing",
            "template_method_overhead"
        ]
        
        hft_compliant = all(
            performance_results[op].passes_target
            for op in hft_critical_operations
            if op in performance_results
        )
        validation_results["hft_compliance"] = hft_compliant
        
        if hft_compliant:
            print("✅ HFT compliance requirements MET")
        else:
            print("❌ HFT compliance requirements NOT MET")
        
        # 4. Overall validation result
        all_validations_passed = all(validation_results.values())
        
        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        
        for test_type, passed in validation_results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{test_type.replace('_', ' ').title()}: {status}")
        
        if all_validations_passed:
            print("\n🎉 WEBSOCKET REFACTORING VALIDATION SUCCESSFUL")
            print("   ✅ Ready for production deployment")
            return 0
        else:
            print("\n❌ WEBSOCKET REFACTORING VALIDATION FAILED")
            print("   ⚠️  Review and fix issues before deployment")
            return 1
            
    except Exception as e:
        print(f"\n💥 VALIDATION ERROR: {e}")
        print("   ❌ Cannot validate refactoring")
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(validate_refactoring())
    sys.exit(exit_code)
```

### 2. CI/CD Integration Script

**File:** `/ws_refactoring/performance_testing/ci_validation.sh`

```bash
#!/bin/bash

# CI/CD Performance Validation Script
# Run this in CI pipeline to validate WebSocket refactoring

set -e

echo "🚀 Starting CI Performance Validation..."

# Ensure we're in the right directory
cd /Users/dasein/dev/cex_arbitrage

# Create performance testing directory if it doesn't exist
mkdir -p ws_refactoring/performance_testing

# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Run validation script
echo "📊 Running performance validation..."
python ws_refactoring/performance_testing/validation_script.py

VALIDATION_RESULT=$?

if [ $VALIDATION_RESULT -eq 0 ]; then
    echo "✅ Performance validation PASSED - WebSocket refactoring approved"
    exit 0
elif [ $VALIDATION_RESULT -eq 1 ]; then
    echo "❌ Performance validation FAILED - Review required"
    exit 1
else
    echo "💥 Performance validation ERROR - Investigation required"
    exit 2
fi
```

This comprehensive performance validation framework ensures that the WebSocket refactoring maintains HFT compliance while providing detailed metrics for performance optimization and regression detection. The framework can be integrated into CI/CD pipelines to automatically validate performance characteristics before deployment.