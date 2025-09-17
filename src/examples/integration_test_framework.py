"""
AI-Agent Integration Test Framework

Provides structured testing infrastructure for AI agents to run exchange integration tests.
Outputs machine-readable JSON results with standardized test outcomes, performance metrics,
and error reporting.

This framework adheres to the HFT system architecture with proper SOLID principles
and clean separation of concerns.
"""

import json
import time
import asyncio
import traceback
from typing import Dict, Any, List, Optional, Union
from enum import Enum
from dataclasses import dataclass, asdict
import logging

# Configure logging to be less verbose for agent consumption
logging.basicConfig(level=logging.WARNING)


class TestStatus(Enum):
    """Standardized test status for AI agent consumption."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class TestCategory(Enum):
    """Test categories for organization and filtering."""
    REST_PUBLIC = "REST_PUBLIC"
    REST_PRIVATE = "REST_PRIVATE"
    WEBSOCKET_PUBLIC = "WEBSOCKET_PUBLIC"
    WEBSOCKET_PRIVATE = "WEBSOCKET_PRIVATE"
    PERFORMANCE = "PERFORMANCE"
    CONFIGURATION = "CONFIGURATION"


@dataclass
class TestMetrics:
    """Performance and execution metrics for HFT compliance."""
    execution_time_ms: float
    memory_usage_mb: Optional[float] = None
    network_requests: int = 0
    data_points_received: int = 0
    error_count: int = 0
    latency_percentiles: Optional[Dict[str, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class TestResult:
    """Structured test result for AI agent consumption."""
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
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['status'] = self.status.value
        result['test_category'] = self.test_category.value
        result['duration_ms'] = (self.end_time - self.start_time) * 1000
        return result


@dataclass
class IntegrationTestReport:
    """Complete integration test report for AI agent consumption."""
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['overall_status'] = self.overall_status.value
        result['duration_ms'] = (self.end_time - self.start_time) * 1000
        result['test_results'] = [test.to_dict() for test in self.test_results]
        return result
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string for AI agent consumption."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class IntegrationTestRunner:
    """
    Base integration test runner for AI agent compatibility.
    
    Provides structured testing framework with machine-readable output,
    standardized error codes, and HFT performance metrics collection.
    """
    
    def __init__(self, exchange: str, test_suite: str):
        self.exchange = exchange.upper()
        self.test_suite = test_suite
        self.test_results: List[TestResult] = []
        self.start_time = time.time()
        self.current_test_start: Optional[float] = None
        
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
        """Record a test result with structured data."""
        end_time = time.time()
        start_time = self.current_test_start or end_time
        
        if metrics is None:
            metrics = TestMetrics(
                execution_time_ms=(end_time - start_time) * 1000
            )
        
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
        """Generate comprehensive test report for AI agent consumption."""
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
            "success_rate": passed_tests / len(self.test_results) if self.test_results else 0
        }
        
        # System information
        system_info = {
            "python_version": "3.9+",
            "test_framework": "AI-Agent Integration Test Framework v1.0",
            "architecture": "HFT Clean src-only Architecture",
            "test_runner": "IntegrationTestRunner"
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
            system_info=system_info
        )
    
    async def run_test_with_timeout(
        self,
        test_func,
        test_name: str,
        test_category: TestCategory,
        timeout_seconds: int = 30,
        expected_behavior: str = "",
        **kwargs
    ) -> None:
        """
        Run a test function with timeout and structured error handling.
        
        Args:
            test_func: Async function to test
            test_name: Name of the test for reporting
            test_category: Category of the test
            timeout_seconds: Timeout in seconds
            expected_behavior: Description of expected behavior
            **kwargs: Arguments to pass to test function
        """
        self.start_test(test_name)
        
        try:
            # Run test with timeout
            result = await asyncio.wait_for(
                test_func(**kwargs),
                timeout=timeout_seconds
            )
            
            # Test passed - record success
            metrics = TestMetrics(
                execution_time_ms=(time.time() - self.current_test_start) * 1000,
                network_requests=getattr(result, 'network_requests', 1),
                data_points_received=getattr(result, 'data_points', 0),
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
            
            # Determine error code based on exception type
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
        """Map exception types to standardized error codes for AI agents."""
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
    
    def output_json_result(self, file_path: Optional[str] = None) -> str:
        """
        Output test results in JSON format for AI agent consumption.
        
        Args:
            file_path: Optional file path to save results
            
        Returns:
            JSON string of test results
        """
        report = self.generate_report()
        json_output = report.to_json()
        
        if file_path:
            with open(file_path, 'w') as f:
                f.write(json_output)
        
        return json_output
    
    def print_summary_for_agent(self) -> None:
        """Print a brief summary suitable for AI agent parsing."""
        report = self.generate_report()
        
        # Create condensed summary for agent
        summary = {
            "exchange": report.exchange,
            "test_suite": report.test_suite,
            "status": report.overall_status.value,
            "total_tests": report.total_tests,
            "passed": report.passed_tests,
            "failed": report.failed_tests,
            "errors": report.error_tests,
            "duration_ms": (report.end_time - report.start_time) * 1000,
            "success_rate": report.summary_metrics["success_rate"]
        }
        
        print("=== AI-AGENT-RESULT-START ===")
        print(json.dumps(summary, indent=2))
        print("=== AI-AGENT-RESULT-END ===")


def create_test_metrics(
    execution_time_ms: float,
    network_requests: int = 0,
    data_points_received: int = 0,
    error_count: int = 0,
    **kwargs
) -> TestMetrics:
    """Helper function to create test metrics."""
    return TestMetrics(
        execution_time_ms=execution_time_ms,
        network_requests=network_requests,
        data_points_received=data_points_received,
        error_count=error_count,
        **kwargs
    )


# Exit codes for AI agent consumption
EXIT_CODE_SUCCESS = 0
EXIT_CODE_FAILED_TESTS = 1
EXIT_CODE_ERROR = 2
EXIT_CODE_TIMEOUT = 3
EXIT_CODE_CONFIG_ERROR = 4