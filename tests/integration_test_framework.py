"""
Comprehensive Integration Test Framework for HFT Arbitrage Engine

Enhanced testing infrastructure for exchange integrations with:
- Standardized test structure and reporting
- Performance metrics collection
- HFT compliance validation  
- AI-agent compatible JSON output
- Support for new exchange integrations (Binance, etc.)
"""

import json
import time
import asyncio
import traceback
from typing import Dict, Any, List, Optional, Union, Callable
from enum import Enum
from dataclasses import dataclass, asdict
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.WARNING)


class TestStatus(Enum):
    """Standardized test status."""
    PASSED = "PASSED"
    FAILED = "FAILED" 
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class TestCategory(Enum):
    """Test categories for organization."""
    REST_PUBLIC = "REST_PUBLIC"
    REST_PRIVATE = "REST_PRIVATE"
    WEBSOCKET_PUBLIC = "WEBSOCKET_PUBLIC"
    WEBSOCKET_PRIVATE = "WEBSOCKET_PRIVATE"
    PERFORMANCE = "PERFORMANCE"
    CONFIGURATION = "CONFIGURATION"
    INTEGRATION = "INTEGRATION"
    COMPLIANCE = "COMPLIANCE"


@dataclass
class TestMetrics:
    """Performance and execution metrics."""
    execution_time_ms: float
    memory_usage_mb: Optional[float] = None
    network_requests: int = 0
    data_points_received: int = 0
    error_count: int = 0
    latency_percentiles: Optional[Dict[str, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    """Structured test result."""
    test_name: str
    test_category: TestCategory
    status: TestStatus
    exchange: str
    start_time: float
    end_time: float
    metrics: TestMetrics
    details: Dict[str, Any]
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    expected_behavior: str = ""
    actual_behavior: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['status'] = self.status.value
        result['test_category'] = self.test_category.value
        result['duration_ms'] = (self.end_time - self.start_time) * 1000
        return result


@dataclass
class IntegrationTestReport:
    """Complete integration test report."""
    exchange: str
    test_suite: str
    start_time: float
    end_time: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int
    skipped_tests: int
    overall_status: TestStatus
    test_results: List[TestResult]
    summary_metrics: Dict[str, Any]
    system_info: Dict[str, str]
    compliance_status: Dict[str, bool]
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['overall_status'] = self.overall_status.value
        result['duration_ms'] = (self.end_time - self.start_time) * 1000
        result['test_results'] = [test.to_dict() for test in self.test_results]
        return result
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


class HFTComplianceValidator:
    """Validates HFT performance requirements."""
    
    HFT_THRESHOLDS = {
        "rest_request_max_ms": 5000,
        "websocket_message_max_ms": 100, 
        "json_parsing_max_ms": 50,
        "orderbook_processing_max_ms": 10,
        "connection_setup_max_ms": 10000,
        "memory_usage_max_mb": 100,
        "success_rate_min": 0.95,
    }
    
    @classmethod
    def validate_performance(cls, metrics: TestMetrics, test_category: TestCategory) -> Dict[str, bool]:
        """Validate performance metrics against HFT thresholds."""
        validation = {}
        
        # General performance checks
        if test_category == TestCategory.REST_PUBLIC or test_category == TestCategory.REST_PRIVATE:
            validation["execution_time_compliant"] = metrics.execution_time_ms <= cls.HFT_THRESHOLDS["rest_request_max_ms"]
        elif test_category == TestCategory.WEBSOCKET_PUBLIC or test_category == TestCategory.WEBSOCKET_PRIVATE:
            validation["execution_time_compliant"] = metrics.execution_time_ms <= cls.HFT_THRESHOLDS["websocket_message_max_ms"]
        
        # Memory usage check
        if metrics.memory_usage_mb:
            validation["memory_usage_compliant"] = metrics.memory_usage_mb <= cls.HFT_THRESHOLDS["memory_usage_max_mb"]
        
        # Error rate check
        if metrics.network_requests > 0:
            error_rate = metrics.error_count / metrics.network_requests
            validation["error_rate_compliant"] = error_rate <= (1 - cls.HFT_THRESHOLDS["success_rate_min"])
        
        return validation


class IntegrationTestRunner:
    """Enhanced integration test runner for exchange testing."""
    
    def __init__(self, exchange: str, test_suite: str, output_dir: Optional[str] = None):
        self.exchange = exchange.upper()
        self.test_suite = test_suite
        self.test_results: List[TestResult] = []
        self.start_time = time.time()
        self.current_test_start: Optional[float] = None
        self.output_dir = Path(output_dir) if output_dir else Path("test_results")
        self.output_dir.mkdir(exist_ok=True)
        
        # Compliance validator
        self.compliance_validator = HFTComplianceValidator()
        
    def start_test(self, test_name: str) -> None:
        """Start timing a test."""
        self.current_test_start = time.time()
        
    def record_test_result(
        self,
        test_name: str,
        test_category: TestCategory,
        status: TestStatus,
        details: Dict[str, Any],
        metrics: Optional[TestMetrics] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        expected_behavior: str = "",
        actual_behavior: str = ""
    ) -> None:
        """Record a test result with compliance validation."""
        end_time = time.time()
        start_time = self.current_test_start or end_time
        
        if metrics is None:
            metrics = TestMetrics(
                execution_time_ms=(end_time - start_time) * 1000
            )
        
        # Add compliance validation to details
        compliance_check = self.compliance_validator.validate_performance(metrics, test_category)
        details["compliance_validation"] = compliance_check
        
        result = TestResult(
            test_name=test_name,
            test_category=test_category,
            status=status,
            exchange=self.exchange,
            start_time=start_time,
            end_time=end_time,
            metrics=metrics,
            details=details,
            error_message=error_message,
            error_code=error_code,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior
        )
        
        self.test_results.append(result)
        
    def generate_report(self) -> IntegrationTestReport:
        """Generate comprehensive test report with compliance status."""
        end_time = time.time()
        
        # Calculate test statistics
        passed_tests = sum(1 for r in self.test_results if r.status == TestStatus.PASSED)
        failed_tests = sum(1 for r in self.test_results if r.status == TestStatus.FAILED)
        error_tests = sum(1 for r in self.test_results if r.status == TestStatus.ERROR)
        skipped_tests = sum(1 for r in self.test_results if r.status == TestStatus.SKIPPED)
        
        # Determine overall status
        if error_tests > 0:
            overall_status = TestStatus.ERROR
        elif failed_tests > 0:
            overall_status = TestStatus.FAILED
        elif passed_tests == 0:
            overall_status = TestStatus.SKIPPED
        else:
            overall_status = TestStatus.PASSED
            
        # Calculate summary metrics
        total_execution_time = sum(r.metrics.execution_time_ms for r in self.test_results)
        total_network_requests = sum(r.metrics.network_requests for r in self.test_results)
        total_data_points = sum(r.metrics.data_points_received for r in self.test_results)
        total_errors = sum(r.metrics.error_count for r in self.test_results)
        
        summary_metrics = {
            "total_execution_time_ms": total_execution_time,
            "total_network_requests": total_network_requests,
            "total_data_points_received": total_data_points,
            "total_error_count": total_errors,
            "average_test_time_ms": total_execution_time / len(self.test_results) if self.test_results else 0,
            "success_rate": passed_tests / len(self.test_results) if self.test_results else 0,
            "hft_performance_score": self._calculate_hft_score()
        }
        
        # Compliance status summary
        compliance_status = {
            "overall_compliant": overall_status == TestStatus.PASSED and summary_metrics["success_rate"] >= 0.95,
            "performance_compliant": summary_metrics["hft_performance_score"] >= 0.8,
            "error_rate_compliant": (total_errors / max(total_network_requests, 1)) <= 0.05,
            "all_tests_executed": len(self.test_results) > 0
        }
        
        # System information
        system_info = {
            "python_version": "3.9+",
            "test_framework": "HFT Integration Test Framework v2.0",
            "architecture": "HFT Clean Architecture",
            "test_runner": "IntegrationTestRunner",
            "exchange": self.exchange,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }
        
        return IntegrationTestReport(
            exchange=self.exchange,
            test_suite=self.test_suite,
            start_time=self.start_time,
            end_time=end_time,
            total_tests=len(self.test_results),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            error_tests=error_tests,
            skipped_tests=skipped_tests,
            overall_status=overall_status,
            test_results=self.test_results,
            summary_metrics=summary_metrics,
            system_info=system_info,
            compliance_status=compliance_status
        )
    
    def _calculate_hft_score(self) -> float:
        """Calculate HFT performance compliance score."""
        if not self.test_results:
            return 0.0
            
        compliant_tests = 0
        total_validations = 0
        
        for result in self.test_results:
            compliance = result.details.get("compliance_validation", {})
            for key, value in compliance.items():
                total_validations += 1
                if value:
                    compliant_tests += 1
        
        return compliant_tests / max(total_validations, 1)
    
    async def run_test_with_timeout(
        self,
        test_func: Callable,
        test_name: str,
        test_category: TestCategory,
        timeout_seconds: int = 30,
        expected_behavior: str = "",
        **kwargs
    ) -> None:
        """Run a test function with timeout and structured error handling."""
        self.start_test(test_name)
        
        try:
            result = await asyncio.wait_for(
                test_func(**kwargs),
                timeout=timeout_seconds
            )
            
            # Extract metrics from result
            network_requests = 1
            data_points = 0
            
            if isinstance(result, dict):
                network_requests = result.get('network_requests', 1)
                data_points = result.get('data_points_received', 0)
            
            metrics = TestMetrics(
                execution_time_ms=(time.time() - self.current_test_start) * 1000,
                network_requests=network_requests,
                data_points_received=data_points,
                error_count=0
            )
            
            self.record_test_result(
                test_name=test_name,
                test_category=test_category,
                status=TestStatus.PASSED,
                details=result if isinstance(result, dict) else {"result": str(result)},
                metrics=metrics,
                expected_behavior=expected_behavior,
                actual_behavior="Test completed successfully"
            )
            
        except asyncio.TimeoutError:
            self.record_test_result(
                test_name=test_name,
                test_category=test_category,
                status=TestStatus.TIMEOUT,
                details={"timeout_seconds": timeout_seconds},
                error_message=f"Test timed out after {timeout_seconds} seconds",
                error_code="TIMEOUT_ERROR",
                expected_behavior=expected_behavior,
                actual_behavior=f"Test did not complete within {timeout_seconds} seconds"
            )
            
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "exception_message": str(e),
                "traceback": traceback.format_exc()
            }
            
            error_code = self._get_error_code(e)
            
            self.record_test_result(
                test_name=test_name,
                test_category=test_category,
                status=TestStatus.ERROR,
                details=error_details,
                error_message=str(e),
                error_code=error_code,
                expected_behavior=expected_behavior,
                actual_behavior=f"Exception raised: {type(e).__name__}: {str(e)}"
            )
    
    def _get_error_code(self, exception: Exception) -> str:
        """Map exception types to standardized error codes."""
        error_mapping = {
            ConnectionError: "CONNECTION_ERROR",
            TimeoutError: "TIMEOUT_ERROR", 
            ValueError: "VALIDATION_ERROR",
            KeyError: "MISSING_DATA_ERROR",
            AttributeError: "ATTRIBUTE_ERROR",
            TypeError: "TYPE_ERROR",
            ImportError: "IMPORT_ERROR",
            FileNotFoundError: "FILE_NOT_FOUND",
            PermissionError: "PERMISSION_ERROR"
        }
        
        return error_mapping.get(type(exception), "UNKNOWN_ERROR")
    
    def save_report(self, filename: Optional[str] = None) -> Path:
        """Save test report to file."""
        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{self.exchange}_{self.test_suite}_{timestamp}.json"
        
        filepath = self.output_dir / filename
        report = self.generate_report()
        
        with open(filepath, 'w') as f:
            f.write(report.to_json())
        
        return filepath
    
    def print_summary_for_agent(self) -> None:
        """Print brief summary for AI agent parsing."""
        report = self.generate_report()
        
        summary = {
            "exchange": report.exchange,
            "test_suite": report.test_suite,
            "status": report.overall_status.value,
            "total_tests": report.total_tests,
            "passed": report.passed_tests,
            "failed": report.failed_tests,
            "errors": report.error_tests,
            "duration_ms": (report.end_time - report.start_time) * 1000,
            "success_rate": report.summary_metrics["success_rate"],
            "hft_compliant": report.compliance_status["overall_compliant"]
        }
        
        print("=== AI-AGENT-RESULT-START ===")
        print(json.dumps(summary, indent=2))
        print("=== AI-AGENT-RESULT-END ===")


# Standard exit codes
EXIT_CODE_SUCCESS = 0
EXIT_CODE_FAILED_TESTS = 1
EXIT_CODE_ERROR = 2
EXIT_CODE_TIMEOUT = 3
EXIT_CODE_CONFIG_ERROR = 4