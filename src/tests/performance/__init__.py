"""
Performance Testing Framework

This module provides comprehensive performance testing, baseline management,
and regression detection for WebSocket message processing architectures.

Key Components:
- WebSocketPerformanceTester: Core performance benchmarking
- BaselineMetricsManager: Persistent baseline storage and analysis
- PerformanceRegressionDetector: Automated regression monitoring

Usage:
    ```python
    from tests.performance import (
        establish_performance_baseline,
        check_current_performance,
        start_monitoring
    )
    
    # Establish baseline
    baselines = establish_performance_baseline()
    
    # Check for regressions
    has_regression = await check_current_performance(metrics, "direct")
    
    # Start continuous monitoring
    await start_monitoring()
    ```

Performance Targets:
- Legacy architecture: ~130ns function call overhead
- Direct architecture: ~35ns function call overhead
- Expected improvement: 73% reduction in overhead
- Target latency: <100μs message processing
"""

from .websocket_performance_test import (
    WebSocketPerformanceTester,
    BenchmarkConfig,
    PerformanceMetrics,
    quick_performance_test,
    establish_performance_baseline
)

from .baseline_metrics import (
    BaselineMetricsManager,
    BaselineRecord,
    get_baseline_manager,
    record_performance_baseline,
    check_for_regression
)

from .regression_detection import (
    PerformanceRegressionDetector,
    RegressionAlert,
    RegressionSeverity,
    RegressionConfig,
    get_regression_detector,
    check_current_performance,
    start_monitoring,
    stop_monitoring
)

__all__ = [
    # Core testing
    "WebSocketPerformanceTester",
    "BenchmarkConfig", 
    "PerformanceMetrics",
    "quick_performance_test",
    "establish_performance_baseline",
    
    # Baseline management
    "BaselineMetricsManager",
    "BaselineRecord",
    "get_baseline_manager",
    "record_performance_baseline",
    "check_for_regression",
    
    # Regression detection
    "PerformanceRegressionDetector",
    "RegressionAlert",
    "RegressionSeverity", 
    "RegressionConfig",
    "get_regression_detector",
    "check_current_performance",
    "start_monitoring",
    "stop_monitoring",
]

# Module metadata
__version__ = "1.0.0"
__author__ = "CEX Arbitrage Engine"
__description__ = "Performance testing framework for WebSocket architecture migration"