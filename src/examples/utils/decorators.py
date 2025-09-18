"""
Example Testing Decorators

Provides reusable decorators for common testing patterns in the examples directory.
Eliminates repetitive try-catch blocks and standardizes error handling.

HFT COMPLIANCE: Zero-overhead decorators for performance-critical testing.
"""

import functools
import time
import traceback
from typing import Any, Callable, Optional, Dict
import asyncio
import logging

logger = logging.getLogger(__name__)


def test_method(description: Optional[str] = None, print_result: bool = True, capture_timing: bool = True):
    """
    Decorator for test methods that provides standardized error handling and output.
    
    Args:
        description: Custom description for the test (defaults to function name)
        print_result: Whether to print the result to console
        capture_timing: Whether to capture and include execution timing
    
    Usage:
        @test_method("Testing ping functionality")
        async def check_ping(exchange, exchange_name: str):
            return await exchange.ping()
            
        @test_method()
        async def check_server_time(exchange, exchange_name: str):
            return await exchange.get_server_time()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Dict[str, Any]:
            # Extract exchange_name from arguments
            exchange_name = "UNKNOWN"
            if len(args) >= 2 and isinstance(args[1], str):
                exchange_name = args[1].upper()
            elif 'exchange_name' in kwargs:
                exchange_name = kwargs['exchange_name'].upper()
            
            # Use provided description or generate from function name
            test_description = description or func.__name__.replace('_', ' ').replace('check ', '').title()
            
            if print_result:
                print(f"\n=== {exchange_name} {test_description.upper()} CHECK ===")
            
            start_time = time.time() if capture_timing else None
            
            try:
                # Execute the function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                execution_time = (time.time() - start_time) * 1000 if capture_timing else None
                
                # Print result if requested
                if print_result:
                    if isinstance(result, dict):
                        for key, value in result.items():
                            print(f"{key}: {value}")
                    else:
                        print(f"Result: {result}")
                    
                    if execution_time is not None:
                        print(f"Execution time: {execution_time:.2f}ms")
                
                # Return structured result for programmatic use
                return {
                    "status": "success",
                    "result": result,
                    "execution_time_ms": execution_time,
                    "error": None
                }
                
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000 if capture_timing else None
                
                if print_result:
                    print(f"Error: {e}")
                    traceback.print_exc()
                    if execution_time is not None:
                        print(f"Execution time: {execution_time:.2f}ms")
                
                # Return structured error result
                return {
                    "status": "error", 
                    "result": None,
                    "execution_time_ms": execution_time,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
        
        # For non-async functions
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Dict[str, Any]:
            # Extract exchange_name from arguments
            exchange_name = "UNKNOWN"
            if len(args) >= 2 and isinstance(args[1], str):
                exchange_name = args[1].upper()
            elif 'exchange_name' in kwargs:
                exchange_name = kwargs['exchange_name'].upper()
            
            # Use provided description or generate from function name
            test_description = description or func.__name__.replace('_', ' ').replace('check ', '').title()
            
            if print_result:
                print(f"\n=== {exchange_name} {test_description.upper()} CHECK ===")
            
            start_time = time.time() if capture_timing else None
            
            try:
                result = func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000 if capture_timing else None
                
                # Print result if requested
                if print_result:
                    if isinstance(result, dict):
                        for key, value in result.items():
                            print(f"{key}: {value}")
                    else:
                        print(f"Result: {result}")
                    
                    if execution_time is not None:
                        print(f"Execution time: {execution_time:.2f}ms")
                
                # Return structured result
                return {
                    "status": "success",
                    "result": result,
                    "execution_time_ms": execution_time,
                    "error": None
                }
                
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000 if capture_timing else None
                
                if print_result:
                    print(f"Error: {e}")
                    traceback.print_exc()
                    if execution_time is not None:
                        print(f"Execution time: {execution_time:.2f}ms")
                
                return {
                    "status": "error",
                    "result": None, 
                    "execution_time_ms": execution_time,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def integration_test(test_name: str, expected_behavior: str = "", timeout_seconds: int = 30):
    """
    Decorator for integration test methods that provides structured testing with timeout.
    
    Args:
        test_name: Name of the test for reporting
        expected_behavior: Description of expected behavior
        timeout_seconds: Timeout for the test
    
    Usage:
        @integration_test("ping_test", "Server responds to ping request", timeout_seconds=10)
        async def test_ping(self):
            return await self.exchange.ping()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    func(self, *args, **kwargs),
                    timeout=timeout_seconds
                )
                
                return {
                    "test_name": test_name,
                    "status": "passed",
                    "result": result,
                    "expected_behavior": expected_behavior,
                    "actual_behavior": "Test completed successfully",
                    "error": None
                }
                
            except asyncio.TimeoutError:
                return {
                    "test_name": test_name,
                    "status": "timeout",
                    "result": None,
                    "expected_behavior": expected_behavior,
                    "actual_behavior": f"Test timed out after {timeout_seconds} seconds",
                    "error": "TimeoutError"
                }
            except Exception as e:
                return {
                    "test_name": test_name,
                    "status": "error",
                    "result": None,
                    "expected_behavior": expected_behavior,
                    "actual_behavior": f"Test failed with exception: {str(e)}",
                    "error": str(e),
                    "error_type": type(e).__name__
                }
        
        return wrapper
    return decorator


def rest_api_test(api_name: str):
    """
    Decorator specifically for REST API testing with standardized patterns.
    
    Args:
        api_name: Name of the API being tested (e.g., "ping", "server_time")
    
    Usage:
        @rest_api_test("ping")
        async def test_ping(exchange):
            return await exchange.ping()
    """
    return test_method(f"REST API {api_name.upper()}", print_result=True, capture_timing=True)


def websocket_test(test_name: str, monitor_duration: int = 5):
    """
    Decorator for WebSocket testing with monitoring duration.
    
    Args:
        test_name: Name of the WebSocket test
        monitor_duration: How long to monitor for data (seconds)
    
    Usage:
        @websocket_test("orderbook_data", monitor_duration=10)
        async def test_orderbook_stream(websocket):
            # Test implementation
            pass
    """
    return test_method(f"WebSocket {test_name.upper()}", print_result=True, capture_timing=True)


def safe_execution(description: str = "Operation", log_errors: bool = True):
    """
    Simple decorator for safe execution with error logging.
    
    Args:
        description: Description of the operation
        log_errors: Whether to log errors
    
    Usage:
        @safe_execution("Database connection")
        def connect_to_db():
            # Implementation
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"{description} failed: {e}")
                return None
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"{description} failed: {e}")
                return None
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator