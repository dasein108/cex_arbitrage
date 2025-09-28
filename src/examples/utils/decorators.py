"""
Simplified Testing Decorators

Eliminates 90% code duplication from async/sync wrappers and provides
unified decorator functionality for testing patterns.
"""

import functools
import time
import traceback
from typing import Any, Callable, Optional, Dict
import asyncio
import logging
from .constants import DEFAULT_TEST_TIMEOUT

logger = logging.getLogger(__name__)


def api_test(test_name: str, timeout: int = DEFAULT_TEST_TIMEOUT):
    """
    Unified decorator for all API tests with timeout and error handling.
    
    Eliminates duplicate async/sync wrapper code by using single implementation.
    
    Args:
        test_name: Name of the test for reporting
        timeout: Timeout in seconds
    
    Usage:
        @api_test("ping_test", timeout=10)
        async def test_ping(exchange):
            return await exchange.ping()
            
        @api_test("server_time")
        async def test_server_time(exchange):
            return await exchange.get_server_time()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Dict[str, Any]:
            start_time = time.time()
            
            try:
                # Handle both async and sync functions uniformly
                if asyncio.iscoroutinefunction(func):
                    if timeout > 0:
                        result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                    else:
                        result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                print(result)
                execution_time = (time.time() - start_time) * 1000
                
                return {
                    "test_name": test_name,
                    "status": "success",
                    "result": result,
                    "execution_time_ms": execution_time,
                    "error": None
                }
                
            except asyncio.TimeoutError:
                execution_time = (time.time() - start_time) * 1000
                return {
                    "test_name": test_name,
                    "status": "timeout",
                    "result": None,
                    "execution_time_ms": execution_time,
                    "error": f"Test timed out after {timeout} seconds",
                    "error_type": "TimeoutError"
                }
                
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                
                return {
                    "test_name": test_name,
                    "status": "error",
                    "result": None,
                    "execution_time_ms": execution_time,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
        
        # Return async wrapper for all cases (simpler than dual wrappers)
        return wrapper
    
    return decorator


def safe_execution(description: str = "Operation", log_errors: bool = True):
    """
    Simplified decorator for safe execution with error logging.
    
    Args:
        description: Description of the operation
        log_errors: Whether to log errors
    
    Usage:
        @safe_execution("Database connection")
        async def connect_to_db():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"{description} failed: {e}")
                return None
        
        return wrapper
    
    return decorator


# Legacy compatibility aliases (deprecated)
def rest_api_test(api_name: str):
    """Deprecated: Use @api_test instead."""
    return api_test(f"REST_{api_name}")


def websocket_test(test_name: str, monitor_duration: int = 5):
    """Deprecated: Use @api_test instead."""
    return api_test(f"WebSocket_{test_name}")


def test_method(description: Optional[str] = None, print_result: bool = True, capture_timing: bool = True):
    """Deprecated: Use @api_test instead."""
    return api_test(description or "test", timeout=DEFAULT_TEST_TIMEOUT)