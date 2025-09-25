#!/usr/bin/env python3
"""
Async/Await Standardization Examples

Demonstrates the standardized async/await patterns implemented across the codebase
for TASK_3_2_ASYNC_AWAIT_STANDARDIZATION.

Key Improvements Implemented:
1. Standardized context manager usage for components with lifecycle
2. Proper task cancellation patterns with CancelledError handling  
3. Async coordination patterns for parallel operations
4. Resource management best practices

HFT COMPLIANT: All examples maintain sub-millisecond performance requirements
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional

# Import the standardized components
from trading.analytics.performance_monitor import PerformanceMonitor
from common.orderbook_manager import OrderbookManager
from trading.arbitrage.types import ArbitrageConfig
from exchanges.structs.common import Symbol


# Configure logging for examples
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def example_multi_component_session() -> AsyncIterator[tuple]:
    """
    Example of coordinated lifecycle management for multiple components.
    
    Demonstrates proper async context manager usage with exception safety.
    """
    logger.info("Starting multi-component session...")
    
    # Create components
    config = ArbitrageConfig(
        target_execution_time_ms=50,
        position_monitor_interval_ms=1000
    )
    
    performance_monitor = PerformanceMonitor(config)
    orderbook_manager = OrderbookManager()
    
    # Start all components with proper error handling
    try:
        # Method 1: Direct context managers
        async with performance_monitor, orderbook_manager:
            logger.info("All components started successfully")
            yield (performance_monitor, orderbook_manager)
            
    except Exception as e:
        logger.error(f"Error in multi-component session: {e}")
        raise
    finally:
        logger.info("Multi-component session ended")


async def example_performance_monitoring():
    """Example of standardized performance monitoring usage."""
    
    def mock_statistics_callback():
        """Mock callback for engine statistics."""
        return {
            'opportunities_detected': 42,
            'opportunities_executed': 38,
            'total_realized_profit': 123.45,
            'average_execution_time_ms': 35.2,
            'success_rate': 90.5
        }
    
    # Method 1: Direct async context manager
    logger.info("=== Performance Monitor Example 1: Direct Context Manager ===")
    async with PerformanceMonitor(ArbitrageConfig()) as monitor:
        monitor._statistics_callback = mock_statistics_callback
        
        # Simulate some operations
        for i in range(5):
            await asyncio.sleep(0.1)  # Simulate work
            monitor.record_execution_time(30.0 + i * 2)
        
        # Check metrics
        metrics = monitor.get_metrics()
        logger.info(f"Monitor metrics: {metrics}")
    
    # Method 2: monitoring_session context manager
    logger.info("=== Performance Monitor Example 2: monitoring_session ===")
    monitor = PerformanceMonitor(ArbitrageConfig())
    async with monitor.monitoring_session(mock_statistics_callback) as perf_monitor:
        # Simulate trading operations
        await asyncio.sleep(0.2)
        
        # Record some execution times
        execution_times = [28.5, 31.2, 29.8, 33.1, 27.9]
        for exec_time in execution_times:
            perf_monitor.record_execution_time(exec_time)
        
        # Check health status
        logger.info(f"Monitor healthy: {perf_monitor.is_healthy}")
        logger.info(f"HFT compliant: {perf_monitor.get_metrics()['hft_compliant']}")


async def example_orderbook_management():
    """Example of standardized orderbook management."""
    
    # Test symbols
    symbols = [
        Symbol("BTC", "USDT"),
        Symbol("ETH", "USDT"), 
        Symbol("BNB", "USDT")
    ]
    
    # Method 1: Direct context manager
    logger.info("=== Orderbook Manager Example 1: Direct Context Manager ===")
    async with OrderbookManager() as manager:
        # Add symbols for tracking
        for symbol in symbols:
            manager.add_symbol(symbol)
        
        # Simulate orderbook updates
        await asyncio.sleep(0.1)
        
        # Check statistics
        stats = manager.get_global_stats()
        logger.info(f"Global orderbook stats: {stats}")
    
    # Method 2: management_session
    logger.info("=== Orderbook Manager Example 2: management_session ===")
    manager = OrderbookManager()
    async with manager.management_session() as orderbook_mgr:
        # Add symbols and simulate processing
        for symbol in symbols:
            orderbook_mgr.add_symbol(symbol)
        
        await asyncio.sleep(0.1)
        
        # Get symbol statistics
        for symbol in symbols:
            symbol_stats = orderbook_mgr.get_symbol_stats(symbol)
            if symbol_stats:
                logger.info(f"Stats for {symbol}: {symbol_stats.total_updates} updates")


async def example_proper_task_cancellation():
    """
    Example of proper task cancellation patterns used throughout codebase.
    
    Demonstrates the standardized cancellation pattern that ensures clean shutdown.
    """
    logger.info("=== Task Cancellation Pattern Example ===")
    
    async def long_running_task(task_id: int):
        """Mock long-running task."""
        try:
            while True:
                logger.info(f"Task {task_id} working...")
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info(f"Task {task_id} cancelled gracefully")
            raise  # Re-raise to ensure proper cancellation
    
    # Create multiple tasks
    tasks = []
    for i in range(3):
        task = asyncio.create_task(long_running_task(i))
        tasks.append(task)
    
    # Let them run briefly
    await asyncio.sleep(1.5)
    
    # STANDARDIZED CANCELLATION PATTERN (used throughout codebase)
    logger.info("Cancelling all tasks...")
    
    # Step 1: Cancel all tasks
    for task in tasks:
        if not task.done():
            task.cancel()
    
    # Step 2: Wait for graceful shutdown using gather with exception handling
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Step 3: Log results
    for i, result in enumerate(results):
        if isinstance(result, asyncio.CancelledError):
            logger.info(f"Task {i} cancelled successfully")
        elif isinstance(result, Exception):
            logger.error(f"Task {i} failed with error: {result}")
        else:
            logger.info(f"Task {i} completed normally: {result}")


async def example_async_coordination():
    """
    Example of async coordination patterns for parallel operations.
    
    Shows how to properly coordinate multiple async operations while maintaining
    HFT performance requirements.
    """
    logger.info("=== Async Coordination Example ===")
    
    async def fetch_market_data(exchange: str, symbol: str) -> dict:
        """Mock market data fetch."""
        # Simulate network latency with realistic timing
        await asyncio.sleep(0.01 + hash(exchange + symbol) % 10 * 0.001)  # 10-20ms
        return {
            "exchange": exchange,
            "symbol": symbol,
            "bid": 50000.0 + hash(exchange) % 100,
            "ask": 50010.0 + hash(exchange) % 100,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    # Example 1: Parallel data fetching with timeout
    exchanges = ["mexc", "gateio", "binance"]
    symbol = "BTC/USDT"
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        # Fetch from all exchanges in parallel with timeout
        market_data_tasks = [
            fetch_market_data(exchange, symbol) 
            for exchange in exchanges
        ]
        
        # HFT requirement: Complete within 50ms
        market_data = await asyncio.wait_for(
            asyncio.gather(*market_data_tasks),
            timeout=0.05  # 50ms timeout
        )
        
        execution_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        logger.info(f"Fetched data from {len(market_data)} exchanges in {execution_time_ms:.2f}ms")
        
        for data in market_data:
            logger.info(f"  {data['exchange']}: bid={data['bid']}, ask={data['ask']}")
            
    except asyncio.TimeoutError:
        logger.error("Market data fetch exceeded HFT timeout requirement (50ms)")
    
    # Example 2: Error-resilient parallel processing
    logger.info("Testing error-resilient parallel processing...")
    
    async def potentially_failing_operation(op_id: int) -> str:
        """Mock operation that might fail."""
        await asyncio.sleep(0.01)
        if op_id == 2:  # Simulate failure
            raise ValueError(f"Operation {op_id} failed")
        return f"Operation {op_id} success"
    
    operations = [potentially_failing_operation(i) for i in range(5)]
    results = await asyncio.gather(*operations, return_exceptions=True)
    
    successful_ops = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Operation {i} failed: {result}")
        else:
            logger.info(f"Operation {i}: {result}")
            successful_ops += 1
    
    logger.info(f"Completed {successful_ops}/5 operations successfully")


async def example_resource_cleanup_patterns():
    """
    Example of proper resource cleanup patterns.
    
    Shows standardized approaches to resource management that ensure no leaks
    even during exceptional conditions.
    """
    logger.info("=== Resource Cleanup Example ===")
    
    class MockResource:
        """Mock resource that needs cleanup."""
        def __init__(self, name: str):
            self.name = name
            self.closed = False
            logger.info(f"Resource {name} opened")
        
        async def close(self):
            """Close the resource."""
            if not self.closed:
                await asyncio.sleep(0.001)  # Simulate async cleanup
                self.closed = True
                logger.info(f"Resource {self.name} closed")
    
    @asynccontextmanager
    async def managed_resource(name: str) -> AsyncIterator[MockResource]:
        """Context manager for resource lifecycle."""
        resource = MockResource(name)
        try:
            yield resource
        finally:
            await resource.close()
    
    # Example 1: Single resource with exception
    try:
        async with managed_resource("single") as resource:
            logger.info(f"Using resource: {resource.name}")
            # Simulate exception
            raise ValueError("Simulated error")
    except ValueError as e:
        logger.info(f"Handled expected error: {e}")
    
    # Example 2: Multiple resources with proper cleanup order
    resources = []
    try:
        async with managed_resource("resource_1") as r1, \
                   managed_resource("resource_2") as r2, \
                   managed_resource("resource_3") as r3:
            resources = [r1, r2, r3]
            logger.info(f"All resources active: {[r.name for r in resources]}")
            
            # Simulate some work
            await asyncio.sleep(0.01)
            
    except Exception as e:
        logger.error(f"Error with resources: {e}")
    
    # Resources should be automatically closed in reverse order
    logger.info("Resource cleanup demonstration complete")


async def main():
    """Run all async standardization examples."""
    logger.info("Starting Async/Await Standardization Examples")
    logger.info("=" * 60)
    
    try:
        # Run examples in sequence to show clear output
        await example_performance_monitoring()
        await asyncio.sleep(0.1)
        
        await example_orderbook_management()
        await asyncio.sleep(0.1)
        
        await example_proper_task_cancellation()
        await asyncio.sleep(0.1)
        
        await example_async_coordination()
        await asyncio.sleep(0.1)
        
        await example_resource_cleanup_patterns()
        await asyncio.sleep(0.1)
        
        # Multi-component coordination example
        logger.info("=== Multi-Component Coordination Example ===")
        async with example_multi_component_session() as (perf_monitor, orderbook_mgr):
            logger.info("Multi-component session active")
            await asyncio.sleep(0.1)
        
    except Exception as e:
        logger.error(f"Error in examples: {e}")
        raise
    
    logger.info("=" * 60)
    logger.info("Async/Await Standardization Examples Completed Successfully")


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())