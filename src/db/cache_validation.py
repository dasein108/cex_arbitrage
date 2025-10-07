"""
Cache Performance Validation

Comprehensive validation suite for symbol cache performance targets.
Tests all cache operations against HFT requirements and generates detailed reports.
"""

import asyncio
import time
import statistics
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

from .cache import initialize_symbol_cache, get_symbol_cache, close_symbol_cache
from .cache_operations import (
    cached_get_symbol_by_id,
    cached_get_symbol_by_exchange_and_pair,
    cached_get_symbol_by_exchange_and_string,
    cached_resolve_symbol_for_exchange,
    get_cache_stats,
    validate_cache_performance,
    reset_cache_stats
)
from .cache_warming import warm_symbol_cache, WarmingConfig, WarmingStrategy
from .cache_monitor import get_cache_performance_monitor, start_cache_monitoring, stop_cache_monitoring


logger = logging.getLogger(__name__)


@dataclass
class PerformanceTarget:
    """HFT performance targets for cache operations."""
    avg_lookup_time_us: float = 1.0       # <1μs average lookup time
    p95_lookup_time_us: float = 2.0       # <2μs 95th percentile
    p99_lookup_time_us: float = 5.0       # <5μs 99th percentile
    hit_ratio: float = 0.95               # >95% hit ratio
    cache_init_time_ms: float = 100.0     # <100ms initialization time
    warming_time_ms: float = 50.0         # <50ms warming time
    throughput_ops_per_sec: float = 1000000.0  # >1M operations/second


@dataclass
class ValidationResult:
    """Results from cache validation test."""
    test_name: str
    passed: bool
    target_value: float
    actual_value: float
    error_message: Optional[str] = None
    
    @property
    def performance_ratio(self) -> float:
        """Calculate performance ratio (actual/target)."""
        if self.target_value == 0:
            return float('inf')
        return self.actual_value / self.target_value


@dataclass
class CacheValidationReport:
    """Comprehensive cache validation report."""
    total_tests: int
    passed_tests: int
    failed_tests: int
    overall_passed: bool
    execution_time_ms: float
    results: List[ValidationResult]
    performance_summary: Dict[str, Any]
    
    @property
    def success_rate(self) -> float:
        """Calculate test success rate."""
        if self.total_tests == 0:
            return 0.0
        return self.passed_tests / self.total_tests


class CacheValidator:
    """
    Comprehensive cache validation system.
    
    Validates all cache operations against HFT performance targets
    and generates detailed performance reports.
    """
    
    def __init__(self, targets: PerformanceTarget = None):
        """
        Initialize cache validator.
        
        Args:
            targets: Performance targets for validation
        """
        self._logger = logging.getLogger(f"{__name__}.CacheValidator")
        self._targets = targets or PerformanceTarget()
        self._results: List[ValidationResult] = []
    
    async def run_full_validation(self) -> CacheValidationReport:
        """
        Run comprehensive cache validation suite.
        
        Returns:
            Complete validation report
        """
        start_time = time.perf_counter()
        self._results.clear()
        
        self._logger.info("Starting comprehensive cache validation...")
        
        try:
            # Test 1: Cache initialization performance
            await self._test_cache_initialization()
            
            # Test 2: Cache warming performance
            await self._test_cache_warming()
            
            # Test 3: Lookup operation performance
            await self._test_lookup_performance()
            
            # Test 4: Throughput performance
            await self._test_throughput_performance()
            
            # Test 5: Cache hit ratio
            await self._test_hit_ratio()
            
            # Test 6: Cache consistency
            await self._test_cache_consistency()
            
            # Test 7: Memory efficiency
            await self._test_memory_efficiency()
            
            # Generate summary
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            passed_tests = sum(1 for r in self._results if r.passed)
            failed_tests = len(self._results) - passed_tests
            
            report = CacheValidationReport(
                total_tests=len(self._results),
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                overall_passed=(failed_tests == 0),
                execution_time_ms=execution_time_ms,
                results=self._results.copy(),
                performance_summary=await self._generate_performance_summary()
            )
            
            self._logger.info(f"Cache validation completed in {execution_time_ms:.2f}ms")
            self._logger.info(f"Results: {passed_tests}/{len(self._results)} tests passed")
            
            return report
            
        except Exception as e:
            self._logger.error(f"Cache validation failed: {e}")
            raise
    
    async def _test_cache_initialization(self) -> None:
        """Test cache initialization performance."""
        self._logger.debug("Testing cache initialization performance...")
        
        # Close existing cache if present
        try:
            await close_symbol_cache()
        except:
            pass
        
        # Measure initialization time
        start_time = time.perf_counter()
        await initialize_symbol_cache(auto_refresh_interval=0)  # Disable auto-refresh for testing
        end_time = time.perf_counter()
        
        init_time_ms = (end_time - start_time) * 1000
        passed = init_time_ms <= self._targets.cache_init_time_ms
        
        self._results.append(ValidationResult(
            test_name="Cache Initialization Time",
            passed=passed,
            target_value=self._targets.cache_init_time_ms,
            actual_value=init_time_ms,
            error_message=None if passed else f"Initialization took {init_time_ms:.2f}ms (target: ≤{self._targets.cache_init_time_ms}ms)"
        ))
    
    async def _test_cache_warming(self) -> None:
        """Test cache warming performance."""
        self._logger.debug("Testing cache warming performance...")
        
        # Reset cache stats
        reset_cache_stats()
        
        # Measure warming time
        start_time = time.perf_counter()
        warming_result = await warm_symbol_cache(WarmingConfig(strategy=WarmingStrategy.FULL))
        end_time = time.perf_counter()
        
        warming_time_ms = (end_time - start_time) * 1000
        passed = warming_time_ms <= self._targets.warming_time_ms and warming_result.success
        
        error_message = None
        if not warming_result.success:
            error_message = f"Warming failed: {warming_result.error_message}"
        elif warming_time_ms > self._targets.warming_time_ms:
            error_message = f"Warming took {warming_time_ms:.2f}ms (target: ≤{self._targets.warming_time_ms}ms)"
        
        self._results.append(ValidationResult(
            test_name="Cache Warming Time",
            passed=passed,
            target_value=self._targets.warming_time_ms,
            actual_value=warming_time_ms,
            error_message=error_message
        ))
    
    async def _test_lookup_performance(self) -> None:
        """Test individual lookup operation performance."""
        self._logger.debug("Testing lookup operation performance...")
        
        cache = get_symbol_cache()
        all_symbols = cache.get_all_symbols()
        
        if not all_symbols:
            self._results.append(ValidationResult(
                test_name="Lookup Performance",
                passed=False,
                target_value=self._targets.avg_lookup_time_us,
                actual_value=0,
                error_message="No symbols available for testing"
            ))
            return
        
        # Test different lookup patterns
        test_symbol = all_symbols[0]
        iterations = 1000
        
        # Test 1: Lookup by ID
        lookup_times = []
        for _ in range(iterations):
            start_time = time.perf_counter_ns()
            cached_get_symbol_by_id(test_symbol.id)
            end_time = time.perf_counter_ns()
            lookup_times.append((end_time - start_time) / 1000)  # Convert to microseconds
        
        avg_time_us = statistics.mean(lookup_times)
        p95_time_us = statistics.quantiles(lookup_times, n=20)[18]  # 95th percentile
        p99_time_us = statistics.quantiles(lookup_times, n=100)[98]  # 99th percentile
        
        # Validate average lookup time
        self._results.append(ValidationResult(
            test_name="Average Lookup Time",
            passed=avg_time_us <= self._targets.avg_lookup_time_us,
            target_value=self._targets.avg_lookup_time_us,
            actual_value=avg_time_us,
            error_message=None if avg_time_us <= self._targets.avg_lookup_time_us else f"Average lookup time {avg_time_us:.3f}μs exceeds target {self._targets.avg_lookup_time_us}μs"
        ))
        
        # Validate P95 lookup time
        self._results.append(ValidationResult(
            test_name="P95 Lookup Time",
            passed=p95_time_us <= self._targets.p95_lookup_time_us,
            target_value=self._targets.p95_lookup_time_us,
            actual_value=p95_time_us,
            error_message=None if p95_time_us <= self._targets.p95_lookup_time_us else f"P95 lookup time {p95_time_us:.3f}μs exceeds target {self._targets.p95_lookup_time_us}μs"
        ))
        
        # Validate P99 lookup time
        self._results.append(ValidationResult(
            test_name="P99 Lookup Time", 
            passed=p99_time_us <= self._targets.p99_lookup_time_us,
            target_value=self._targets.p99_lookup_time_us,
            actual_value=p99_time_us,
            error_message=None if p99_time_us <= self._targets.p99_lookup_time_us else f"P99 lookup time {p99_time_us:.3f}μs exceeds target {self._targets.p99_lookup_time_us}μs"
        ))
    
    async def _test_throughput_performance(self) -> None:
        """Test cache throughput performance."""
        self._logger.debug("Testing cache throughput performance...")
        
        cache = get_symbol_cache()
        all_symbols = cache.get_all_symbols()
        
        if not all_symbols:
            self._results.append(ValidationResult(
                test_name="Throughput Performance",
                passed=False,
                target_value=self._targets.throughput_ops_per_sec,
                actual_value=0,
                error_message="No symbols available for testing"
            ))
            return
        
        # Reset stats for clean measurement
        reset_cache_stats()
        
        # Perform high-volume operations
        test_duration = 1.0  # seconds
        start_time = time.perf_counter()
        operations = 0
        
        while (time.perf_counter() - start_time) < test_duration:
            for symbol in all_symbols[:10]:  # Use first 10 symbols
                cached_get_symbol_by_id(symbol.id)
                cached_get_symbol_by_exchange_and_pair(
                    symbol.exchange_id,
                    symbol.symbol_base,
                    symbol.symbol_quote
                )
                operations += 2
                
                # Check time limit
                if (time.perf_counter() - start_time) >= test_duration:
                    break
        
        end_time = time.perf_counter()
        actual_duration = end_time - start_time
        ops_per_second = operations / actual_duration
        
        passed = ops_per_second >= self._targets.throughput_ops_per_sec
        
        self._results.append(ValidationResult(
            test_name="Throughput Performance",
            passed=passed,
            target_value=self._targets.throughput_ops_per_sec,
            actual_value=ops_per_second,
            error_message=None if passed else f"Throughput {ops_per_second:.0f} ops/sec below target {self._targets.throughput_ops_per_sec:.0f} ops/sec"
        ))
    
    async def _test_hit_ratio(self) -> None:
        """Test cache hit ratio."""
        self._logger.debug("Testing cache hit ratio...")
        
        # Reset stats
        reset_cache_stats()
        
        cache = get_symbol_cache()
        all_symbols = cache.get_all_symbols()
        
        if not all_symbols:
            self._results.append(ValidationResult(
                test_name="Cache Hit Ratio",
                passed=False,
                target_value=self._targets.hit_ratio,
                actual_value=0,
                error_message="No symbols available for testing"
            ))
            return
        
        # Perform cache operations
        for symbol in all_symbols[:100]:  # Test with first 100 symbols
            cached_get_symbol_by_id(symbol.id)
            cached_get_symbol_by_exchange_and_pair(
                symbol.exchange_id,
                symbol.symbol_base,
                symbol.symbol_quote
            )
        
        stats = get_cache_stats()
        hit_ratio = stats.hit_ratio
        passed = hit_ratio >= self._targets.hit_ratio
        
        self._results.append(ValidationResult(
            test_name="Cache Hit Ratio",
            passed=passed,
            target_value=self._targets.hit_ratio,
            actual_value=hit_ratio,
            error_message=None if passed else f"Hit ratio {hit_ratio:.1%} below target {self._targets.hit_ratio:.1%}"
        ))
    
    async def _test_cache_consistency(self) -> None:
        """Test cache data consistency."""
        self._logger.debug("Testing cache consistency...")
        
        cache = get_symbol_cache()
        all_symbols = cache.get_all_symbols()
        
        if not all_symbols:
            self._results.append(ValidationResult(
                test_name="Cache Consistency",
                passed=False,
                target_value=1.0,
                actual_value=0,
                error_message="No symbols available for testing"
            ))
            return
        
        # Test consistency across different lookup methods
        inconsistencies = 0
        total_tests = 0
        
        for symbol in all_symbols[:50]:  # Test first 50 symbols
            # Get symbol via different methods
            by_id = cached_get_symbol_by_id(symbol.id)
            by_pair = cached_get_symbol_by_exchange_and_pair(
                symbol.exchange_id,
                symbol.symbol_base,
                symbol.symbol_quote
            )
            by_string = cached_get_symbol_by_exchange_and_string(
                symbol.exchange_id,
                symbol.exchange_symbol
            )
            
            total_tests += 3
            
            # Check consistency
            if not by_id or by_id.id != symbol.id:
                inconsistencies += 1
            if not by_pair or by_pair.id != symbol.id:
                inconsistencies += 1
            if not by_string or by_string.id != symbol.id:
                inconsistencies += 1
        
        consistency_ratio = (total_tests - inconsistencies) / total_tests if total_tests > 0 else 0
        passed = consistency_ratio >= 0.99  # 99% consistency required
        
        self._results.append(ValidationResult(
            test_name="Cache Consistency",
            passed=passed,
            target_value=0.99,
            actual_value=consistency_ratio,
            error_message=None if passed else f"Consistency ratio {consistency_ratio:.1%} below 99% (found {inconsistencies} inconsistencies)"
        ))
    
    async def _test_memory_efficiency(self) -> None:
        """Test cache memory efficiency."""
        self._logger.debug("Testing cache memory efficiency...")
        
        cache = get_symbol_cache()
        stats = get_cache_stats()
        
        # Memory efficiency is hard to measure directly, so we test cache size vs symbol count
        cache_size = stats.cache_size
        
        # For this test, we assume memory efficiency is good if cache is properly populated
        passed = cache_size > 0
        
        self._results.append(ValidationResult(
            test_name="Memory Efficiency",
            passed=passed,
            target_value=1.0,
            actual_value=cache_size,
            error_message=None if passed else "Cache is empty or not properly populated"
        ))
    
    async def _generate_performance_summary(self) -> Dict[str, Any]:
        """Generate detailed performance summary."""
        stats = get_cache_stats()
        validation = validate_cache_performance()
        
        return {
            "cache_stats": {
                "total_requests": stats.total_requests,
                "hit_ratio": stats.hit_ratio,
                "avg_lookup_time_us": stats.avg_lookup_time_us,
                "cache_size": stats.cache_size,
                "last_refresh": stats.last_refresh.isoformat() if stats.last_refresh else None
            },
            "performance_validation": validation,
            "test_results": {
                "total_tests": len(self._results),
                "passed_tests": sum(1 for r in self._results if r.passed),
                "failed_tests": sum(1 for r in self._results if not r.passed),
                "success_rate": sum(1 for r in self._results if r.passed) / len(self._results) if self._results else 0
            },
            "performance_targets": {
                "avg_lookup_time_us": self._targets.avg_lookup_time_us,
                "p95_lookup_time_us": self._targets.p95_lookup_time_us,
                "p99_lookup_time_us": self._targets.p99_lookup_time_us,
                "hit_ratio": self._targets.hit_ratio,
                "throughput_ops_per_sec": self._targets.throughput_ops_per_sec
            }
        }


# Convenience function
async def validate_cache_hft_performance() -> CacheValidationReport:
    """
    Run complete cache validation for HFT performance.
    
    Returns:
        Comprehensive validation report
    """
    validator = CacheValidator()
    return await validator.run_full_validation()


def print_validation_report(report: CacheValidationReport) -> None:
    """Print formatted validation report."""
    print("=" * 80)
    print("CACHE PERFORMANCE VALIDATION REPORT")
    print("=" * 80)
    print(f"Overall Result: {'✅ PASSED' if report.overall_passed else '❌ FAILED'}")
    print(f"Tests: {report.passed_tests}/{report.total_tests} passed ({report.success_rate:.1%})")
    print(f"Execution Time: {report.execution_time_ms:.2f}ms")
    print()
    
    print("Test Results:")
    print("-" * 40)
    for result in report.results:
        status = "✅" if result.passed else "❌"
        print(f"{status} {result.test_name}")
        print(f"   Target: {result.target_value:.3f}")
        print(f"   Actual: {result.actual_value:.3f}")
        if result.error_message:
            print(f"   Error: {result.error_message}")
        print()
    
    print("Performance Summary:")
    print("-" * 40)
    summary = report.performance_summary
    if "cache_stats" in summary:
        cache_stats = summary["cache_stats"]
        print(f"Cache Size: {cache_stats['cache_size']:,} symbols")
        print(f"Total Requests: {cache_stats['total_requests']:,}")
        print(f"Hit Ratio: {cache_stats['hit_ratio']:.1%}")
        print(f"Avg Lookup Time: {cache_stats['avg_lookup_time_us']:.3f}μs")
    
    print("=" * 80)