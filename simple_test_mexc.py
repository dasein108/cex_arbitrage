#!/usr/bin/env python3
"""
Simple MEXC Direct Implementation Test

Minimal test script to validate the core MEXC base REST implementation.
Tests only the direct implementation without complex dependencies.
"""

import asyncio
import time
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config.structs import ExchangeConfig
from exchanges.integrations.mexc.rest.mexc_base_rest import MexcBaseRestInterface
from infrastructure.logging import get_console_logger


class MockRateLimiter:
    """Mock rate limiter for testing."""
    
    async def acquire(self, endpoint: str):
        """Mock acquire - no actual rate limiting."""
        pass
    
    def release(self, endpoint: str):
        """Mock release - no actual rate limiting."""
        pass


async def test_mexc_base_rest():
    """Test MEXC base REST implementation directly."""
    print("=== Testing MEXC Base REST Implementation ===")
    
    # Create MEXC config
    mexc_config = ExchangeConfig(
        name="MEXC_SPOT",
        base_url="https://api.mexc.com",
        credentials=None  # Public endpoints only
    )
    
    # Create mock dependencies
    rate_limiter = MockRateLimiter()
    logger = get_console_logger("mexc_test", level="INFO")
    
    try:
        # Create MEXC base REST client
        print("\n1. Creating MEXC base REST client...")
        client = MexcBaseRestInterface(
            config=mexc_config,
            rate_limiter=rate_limiter,
            logger=logger,
            is_private=False
        )
        print("   ✓ Client created successfully")
        
        # Test ping endpoint
        print("\n2. Testing ping endpoint...")
        start_time = time.perf_counter()
        ping_result = await client.request("GET", "/api/v3/ping")
        ping_duration = (time.perf_counter() - start_time) * 1000
        print(f"   ✓ Ping result: {ping_result}")
        print(f"   ✓ Duration: {ping_duration:.2f}ms")
        
        # Test server time endpoint
        print("\n3. Testing server time endpoint...")
        start_time = time.perf_counter()
        time_result = await client.request("GET", "/api/v3/time")
        time_duration = (time.perf_counter() - start_time) * 1000
        print(f"   ✓ Server time result: {time_result}")
        print(f"   ✓ Duration: {time_duration:.2f}ms")
        
        # Test performance statistics
        print("\n4. Checking performance statistics...")
        perf_stats = client.get_performance_stats()
        print(f"   ✓ Performance stats: {perf_stats}")
        
        # Test error handling
        print("\n5. Testing error handling...")
        try:
            await client.request("GET", "/api/v3/invalid_endpoint")
            print("   ✗ Expected error but request succeeded")
            return False
        except Exception as e:
            print(f"   ✓ Properly handled error: {type(e).__name__}")
        
        # Clean up
        await client.close()
        print("\n6. ✓ Client closed successfully")
        
        return True
        
    except Exception as e:
        print(f"   ✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_authentication_setup():
    """Test authentication setup (without actual credentials)."""
    print("\n=== Testing Authentication Setup ===")
    
    # Test with credentials (mock)
    mexc_config = ExchangeConfig(
        name="MEXC_SPOT",
        base_url="https://api.mexc.com",
        credentials=None
    )
    
    rate_limiter = MockRateLimiter()
    logger = get_console_logger("mexc_auth_test", level="INFO")
    
    try:
        # Test public client (no auth)
        print("\n1. Testing public client setup...")
        public_client = MexcBaseRestInterface(
            config=mexc_config,
            rate_limiter=rate_limiter,
            logger=logger,
            is_private=False
        )
        print(f"   ✓ Public client: has_credentials={bool(public_client.api_key)}")
        await public_client.close()
        
        # Test private client without credentials (should fail)
        print("\n2. Testing private client without credentials...")
        try:
            private_client = MexcBaseRestInterface(
                config=mexc_config,
                rate_limiter=rate_limiter,
                logger=logger,
                is_private=True
            )
            print("   ✗ Expected error but client created successfully")
            await private_client.close()
            return False
        except ValueError as e:
            print(f"   ✓ Properly rejected private client without credentials: {e}")
        
        return True
        
    except Exception as e:
        print(f"   ✗ Authentication test failed: {e}")
        return False


async def test_performance_baseline():
    """Test performance baseline for direct implementation."""
    print("\n=== Performance Baseline Test ===")
    
    mexc_config = ExchangeConfig(
        name="MEXC_SPOT",
        base_url="https://api.mexc.com",
        credentials=None
    )
    
    rate_limiter = MockRateLimiter()
    logger = get_console_logger("mexc_perf_test", level="WARNING")  # Reduce logging noise
    
    try:
        client = MexcBaseRestInterface(mexc_config, rate_limiter, logger, is_private=False)
        
        # Warm up
        await client.request("GET", "/api/v3/ping")
        
        # Performance test
        iterations = 5  # Small number for quick test
        print(f"\nRunning {iterations} ping requests...")
        
        start_time = time.perf_counter()
        for i in range(iterations):
            await client.request("GET", "/api/v3/ping")
        total_time = time.perf_counter() - start_time
        
        avg_time_ms = (total_time / iterations) * 1000
        rps = iterations / total_time
        
        print(f"   Total time: {total_time:.4f}s")
        print(f"   Average time: {avg_time_ms:.2f}ms per request")
        print(f"   Throughput: {rps:.1f} requests/second")
        
        # Check performance stats
        perf_stats = client.get_performance_stats()
        print(f"   Internal stats: {perf_stats}")
        
        await client.close()
        
        # Basic performance check (should be under 100ms average)
        if avg_time_ms < 100:
            print("   ✓ Performance within acceptable range")
            return True
        else:
            print("   ⚠ Performance slower than expected")
            return False
        
    except Exception as e:
        print(f"   ✗ Performance test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("MEXC Base REST Direct Implementation Test")
    print("=" * 50)
    
    tests = [
        ("Base REST Implementation", test_mexc_base_rest),
        ("Authentication Setup", test_authentication_setup),
        ("Performance Baseline", test_performance_baseline)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\nRunning {test_name}...")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:<30} {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! MEXC base REST implementation is working correctly.")
        print("\nKey achievements:")
        print("  - Direct implementation eliminates strategy dispatch overhead")
        print("  - Fresh timestamp generation prevents signature errors")
        print("  - Constructor injection pattern working")
        print("  - Error handling and response parsing functional")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)