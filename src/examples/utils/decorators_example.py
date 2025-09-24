"""
Example Usage of Testing Decorators

Demonstrates how to use the decorators in examples/utils/decorators.py
to eliminate repetitive try-catch patterns and standardize testing.

This file shows both the old way (with manual try-catch) and the new way (with decorators).
"""

import asyncio
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from examples.utils.decorators import test_method, rest_api_test, integration_test, safe_execution


# =============================================================================
# OLD WAY: Manual try-catch pattern (repetitive, error-prone)
# =============================================================================

async def old_check_ping(exchange, exchange_name: str):
    """Old way: Manual try-catch pattern."""
    print(f"=== {exchange_name.upper()} PING CHECK ===")
    try:
        result = await exchange.ping()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")


async def old_check_server_time(exchange, exchange_name: str):
    """Old way: Manual try-catch pattern."""
    print(f"\n=== {exchange_name.upper()} GET SERVER TIME CHECK ===")
    try:
        result = await exchange.get_server_time()
        print(f"Server time: {result}")
    except Exception as e:
        print(f"Error: {e}")


# =============================================================================
# NEW WAY: Using decorators (clean, consistent, DRY)
# =============================================================================

@rest_api_test("ping")
async def new_check_ping(exchange, exchange_name: str):
    """New way: Using decorator - clean and simple."""
    return await exchange.ping()


@rest_api_test("server_time")
async def new_check_server_time(exchange, exchange_name: str):
    """New way: Using decorator - returns structured data."""
    result = await exchange.get_server_time()
    return {"server_time": result}


@test_method("Custom API Test", print_result=True, capture_timing=True)
async def custom_api_test(exchange, exchange_name: str):
    """Example of custom test method decorator."""
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    orderbook = await exchange.get_orderbook(symbol, limit=5)
    
    return {
        "symbol": f"{symbol.base}/{symbol.quote}",
        "best_bid": orderbook.bids[0].price if orderbook.bids else None,
        "best_ask": orderbook.asks[0].price if orderbook.asks else None,
        "spread": (orderbook.asks[0].price - orderbook.bids[0].price) if orderbook.bids and orderbook.asks else None
    }


# =============================================================================
# INTEGRATION TEST EXAMPLE
# =============================================================================

class IntegrationTestExample:
    """Example of using integration_test decorator in test classes."""
    
    def __init__(self, exchange):
        self.exchange = exchange
    
    @integration_test("ping_connectivity", "Exchange responds to ping request", timeout_seconds=10)
    async def test_ping(self):
        """Test ping connectivity using decorator."""
        result = await self.exchange.ping()
        return {"ping_successful": result is True or result == "pong"}
    
    @integration_test("server_time_sync", "Server time within reasonable range", timeout_seconds=5)
    async def test_server_time(self):
        """Test server time synchronization."""
        import time
        server_time = await self.exchange.get_server_time()
        local_time = int(time.time() * 1000)
        time_diff = abs(server_time - local_time)
        
        return {
            "server_time": server_time,
            "local_time": local_time,
            "time_diff_ms": time_diff,
            "sync_acceptable": time_diff < 5000  # Within 5 seconds
        }


# =============================================================================
# SAFE EXECUTION EXAMPLE
# =============================================================================

@safe_execution("Database connection", log_errors=True)
async def connect_to_database():
    """Example of safe execution decorator for operations that might fail."""
    # Simulate database connection that might fail
    import random
    if random.random() < 0.3:  # 30% chance of failure
        raise ConnectionError("Database unreachable")
    return {"connection": "successful", "db_version": "1.0"}


def sync_function_example():
    """Example showing decorators work with sync functions too."""
    
    @test_method("Synchronous calculation", print_result=True)
    def calculate_something(value: int, exchange_name: str = "TEST"):
        """Sync function with decorator."""
        return {"input": value, "result": value * 2, "calculation": "double"}
    
    return calculate_something


# =============================================================================
# DEMONSTRATION FUNCTION
# =============================================================================

async def demonstrate_decorators():
    """Demonstrate the difference between old and new approaches."""
    
    # Mock exchange object for demonstration
    class MockExchange:
        async def ping(self):
            return True
        
        async def get_server_time(self):
            import time
            return int(time.time() * 1000)
        
        async def get_orderbook(self, symbol, limit=5):
            from exchanges.structs.common import OrderBook, OrderBookEntry
            return OrderBook(
                bids=[OrderBookEntry(price=50000.0, size=1.0)],
                asks=[OrderBookEntry(price=50001.0, size=1.0)],
                timestamp=time.time()
            )
    
    exchange = MockExchange()
    exchange_name = "DEMO"
    
    print("=== DECORATOR DEMONSTRATION ===\n")
    
    # Test old way (verbose)
    print("1. OLD WAY (manual try-catch):")
    await old_check_ping(exchange, exchange_name)
    await old_check_server_time(exchange, exchange_name)
    
    print("\n" + "="*50 + "\n")
    
    # Test new way (clean)
    print("2. NEW WAY (using decorators):")
    ping_result = await new_check_ping(exchange, exchange_name)
    print(f"Ping result: {ping_result}")
    
    time_result = await new_check_server_time(exchange, exchange_name)
    print(f"Time result: {time_result}")
    
    custom_result = await custom_api_test(exchange, exchange_name)
    print(f"Custom test result: {custom_result}")
    
    print("\n" + "="*50 + "\n")
    
    # Test integration test example
    print("3. INTEGRATION TEST EXAMPLE:")
    test_suite = IntegrationTestExample(exchange)
    
    ping_test_result = await test_suite.test_ping()
    print(f"Integration ping test: {ping_test_result}")
    
    time_test_result = await test_suite.test_server_time()
    print(f"Integration time test: {time_test_result}")
    
    print("\n" + "="*50 + "\n")
    
    # Test safe execution
    print("4. SAFE EXECUTION EXAMPLE:")
    for i in range(3):
        db_result = await connect_to_database()
        print(f"Database connection attempt {i+1}: {db_result}")
    
    print("\n=== DEMONSTRATION COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(demonstrate_decorators())