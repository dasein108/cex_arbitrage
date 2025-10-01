#!/usr/bin/env python3
"""
MEXC Direct Implementation Test

Test script to validate the MEXC direct implementation REST refactoring.
Compares performance between strategy pattern and direct implementation.

Usage:
    python test_mexc_direct_implementation.py
"""

import asyncio
import time
import sys
import os
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config.structs import ExchangeConfig, ExchangeCredentials
from exchanges.factory.rest_factory import create_rest_client, create_rest_client_legacy
from infrastructure.logging import get_console_logger


async def test_mexc_basic_functionality():
    """Test basic MEXC functionality with direct implementation."""
    print("=== Testing MEXC Basic Functionality ===")
    
    # Create MEXC config (public endpoints only)
    mexc_config = ExchangeConfig(
        name="MEXC_SPOT",
        base_url="https://api.mexc.com",
        credentials=None  # Public endpoints don't need credentials
    )
    
    try:
        # Test direct implementation
        print("\n1. Testing direct implementation...")
        direct_client = create_rest_client(mexc_config, is_private=False)
        
        # Test basic connectivity
        start_time = time.perf_counter()
        ping_result = await direct_client.request("GET", "/api/v3/ping")
        ping_time = (time.perf_counter() - start_time) * 1000
        
        print(f"   ✓ Ping successful: {ping_result} ({ping_time:.2f}ms)")
        
        # Test server time
        start_time = time.perf_counter()
        server_time = await direct_client.get_server_time()
        time_call_duration = (time.perf_counter() - start_time) * 1000
        
        print(f"   ✓ Server time: {server_time} ({time_call_duration:.2f}ms)")
        
        # Test symbols info (partial)
        start_time = time.perf_counter()
        symbols_info = await direct_client.get_symbols_info()
        symbols_duration = (time.perf_counter() - start_time) * 1000
        
        print(f"   ✓ Retrieved {len(symbols_info)} symbols ({symbols_duration:.2f}ms)")
        
        # Get performance stats
        perf_stats = direct_client.get_performance_stats()
        print(f"   ✓ Performance stats: {perf_stats}")
        
        await direct_client.close()
        print("   ✓ Direct implementation test completed successfully")
        
        return True
        
    except Exception as e:
        print(f"   ✗ Direct implementation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_performance_comparison():
    """Compare performance between direct and legacy implementations."""
    print("\n=== Performance Comparison ===")
    
    # Create MEXC config
    mexc_config = ExchangeConfig(
        name="MEXC_SPOT",
        base_url="https://api.mexc.com",
        credentials=None
    )
    
    iterations = 10  # Reduced for quick testing
    
    try:
        print(f"\nRunning {iterations} iterations of /api/v3/ping...")
        
        # Test direct implementation
        print("\n1. Testing direct implementation performance...")
        direct_client = create_rest_client(mexc_config, is_private=False)
        
        # Warm up
        await direct_client.request("GET", "/api/v3/ping")
        
        start_time = time.perf_counter()
        for i in range(iterations):
            await direct_client.request("GET", "/api/v3/ping")
        direct_time = time.perf_counter() - start_time
        
        direct_avg_ms = (direct_time / iterations) * 1000
        print(f"   Direct implementation: {direct_time:.4f}s total, {direct_avg_ms:.2f}ms avg")
        
        await direct_client.close()
        
        # Test legacy implementation
        print("\n2. Testing legacy implementation performance...")
        legacy_client = create_rest_client_legacy(mexc_config, is_private=False)
        
        # Warm up
        await legacy_client.request("GET", "/api/v3/ping")
        
        start_time = time.perf_counter()
        for i in range(iterations):
            await legacy_client.request("GET", "/api/v3/ping")
        legacy_time = time.perf_counter() - start_time
        
        legacy_avg_ms = (legacy_time / iterations) * 1000
        print(f"   Legacy implementation: {legacy_time:.4f}s total, {legacy_avg_ms:.2f}ms avg")
        
        await legacy_client.close()
        
        # Calculate improvement
        speedup = legacy_time / direct_time
        overhead_reduction_us = ((legacy_time - direct_time) / iterations) * 1_000_000
        improvement_pct = ((legacy_time - direct_time) / legacy_time) * 100
        
        print(f"\n3. Performance Analysis:")
        print(f"   Speedup factor: {speedup:.2f}x")
        print(f"   Overhead reduction: {overhead_reduction_us:.1f}μs per request")
        print(f"   Performance improvement: {improvement_pct:.1f}%")
        
        if speedup > 1.1:  # At least 10% improvement
            print("   ✓ Performance improvement achieved!")
            return True
        else:
            print("   ⚠ Performance improvement below target")
            return False
            
    except Exception as e:
        print(f"   ✗ Performance comparison failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_error_handling():
    """Test error handling in direct implementation."""
    print("\n=== Error Handling Test ===")
    
    mexc_config = ExchangeConfig(
        name="MEXC_SPOT", 
        base_url="https://api.mexc.com",
        credentials=None
    )
    
    try:
        direct_client = create_rest_client(mexc_config, is_private=False)
        
        # Test invalid endpoint (should get 404)
        print("\n1. Testing invalid endpoint handling...")
        try:
            await direct_client.request("GET", "/api/v3/invalid_endpoint_test")
            print("   ✗ Expected error but request succeeded")
            return False
        except Exception as e:
            print(f"   ✓ Properly handled error: {type(e).__name__}: {e}")
        
        await direct_client.close()
        print("   ✓ Error handling test completed")
        return True
        
    except Exception as e:
        print(f"   ✗ Error handling test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("MEXC Direct Implementation Test Suite")
    print("=" * 50)
    
    # Set up basic logging
    logger = get_console_logger("test", level="INFO")
    
    # Run tests
    tests = [
        ("Basic Functionality", test_mexc_basic_functionality),
        ("Performance Comparison", test_performance_comparison), 
        ("Error Handling", test_error_handling)
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
        print(f"{test_name:<25} {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! MEXC direct implementation is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)