#!/usr/bin/env python3
"""
REST Transport Strategy System Demo

Demonstrates the new strategy-based REST transport system with HFT performance
monitoring and flexible exchange-specific configurations.

Usage:
    # Public API demo
    PYTHONPATH=src python src/examples/rest_transport_demo.py

    # Private API demo (requires credentials)
    MEXC_API_KEY=your_key MEXC_SECRET_KEY=your_secret \
    PYTHONPATH=src python src/examples/rest_transport_demo.py --private

    # Performance benchmark
    PYTHONPATH=src python src/examples/rest_transport_demo.py --benchmark
"""

import asyncio
import argparse
import time
import logging
from typing import Dict, Any

from core.transport.rest import (
    create_transport_manager, create_transport_from_config, RestTransportManager,
    RestStrategyFactory, RequestMetrics
)
from core.config.structs import ExchangeConfig, ExchangeCredentials, NetworkConfig, RateLimitConfig, WebSocketConfig


async def demo_public_api():
    """Demonstrate public API usage with different exchanges."""
    print("🚀 Public API Demo - Strategy-Based Transport")
    print("=" * 60)
    
    # Test MEXC public API
    print("\n📊 Testing MEXC Public API")
    async with create_transport_manager("mexc", is_private=False) as mexc_transport:
        try:
            # Get ticker data
            ticker_response = await mexc_transport.get(
                "/api/v3/ticker/24hr",
                params={"symbol": "BTCUSDT"}
            )
            print(f"✅ MEXC Ticker: {ticker_response.get('symbol', 'N/A')} - Price: {ticker_response.get('lastPrice', 'N/A')}")
            
            # Get performance summary
            perf_summary = mexc_transport.get_performance_summary()
            print(f"📈 MEXC Performance: {perf_summary['avg_latency_ms']:.2f}ms avg, HFT compliant: {perf_summary['hft_compliant']}")
            
        except Exception as e:
            print(f"❌ MEXC Error: {e}")
    
    # Test Gate.io public API
    print("\n📊 Testing Gate.io Public API")
    async with create_transport_manager("gateio", is_private=False) as gateio_transport:
        try:
            # Get ticker data
            ticker_response = await gateio_transport.get(
                "/api/v4/spot/tickers",
                params={"currency_pair": "BTC_USDT"}
            )
            if isinstance(ticker_response, list) and ticker_response:
                ticker = ticker_response[0]
                print(f"✅ Gate.io Ticker: {ticker.get('currency_pair', 'N/A')} - Price: {ticker.get('last', 'N/A')}")
            
            # Get performance summary
            perf_summary = gateio_transport.get_performance_summary()
            print(f"📈 Gate.io Performance: {perf_summary['avg_latency_ms']:.2f}ms avg, HFT compliant: {perf_summary['hft_compliant']}")
            
        except Exception as e:
            print(f"❌ Gate.io Error: {e}")


async def demo_private_api():
    """Demonstrate private API usage with authentication."""
    print("\n🔐 Private API Demo - Authentication & Rate Limiting")
    print("=" * 60)
    
    import os
    
    # Check for MEXC credentials
    mexc_api_key = os.getenv('MEXC_API_KEY')
    mexc_secret_key = os.getenv('MEXC_SECRET_KEY')
    
    if mexc_api_key and mexc_secret_key:
        print("\n🔑 Testing MEXC Private API")
        async with create_transport_manager(
            "mexc", 
            is_private=True,
            api_key=mexc_api_key,
            secret_key=mexc_secret_key
        ) as mexc_private:
            try:
                # Get account info
                account_response = await mexc_private.get(
                    "/api/v3/account",
                    require_auth=True
                )
                print(f"✅ MEXC Account: {len(account_response.get('balances', []))} balances")
                
                # Get performance summary
                perf_summary = mexc_private.get_performance_summary()
                print(f"📈 MEXC Private Performance: {perf_summary['avg_latency_ms']:.2f}ms avg")
                
            except Exception as e:
                print(f"❌ MEXC Private Error: {e}")
    else:
        print("⚠️  MEXC credentials not found - set MEXC_API_KEY and MEXC_SECRET_KEY environment variables")
    
    # Check for Gate.io credentials
    gateio_api_key = os.getenv('GATEIO_API_KEY')
    gateio_secret_key = os.getenv('GATEIO_SECRET_KEY')
    
    if gateio_api_key and gateio_secret_key:
        print("\n🔑 Testing Gate.io Private API")
        async with create_transport_manager(
            "gateio",
            is_private=True,
            api_key=gateio_api_key,
            secret_key=gateio_secret_key
        ) as gateio_private:
            try:
                # Get account info
                account_response = await gateio_private.get(
                    "/api/v4/spot/accounts",
                    require_auth=True
                )
                print(f"✅ Gate.io Account: {len(account_response)} balances")
                
                # Get performance summary
                perf_summary = gateio_private.get_performance_summary()
                print(f"📈 Gate.io Private Performance: {perf_summary['avg_latency_ms']:.2f}ms avg")
                
            except Exception as e:
                print(f"❌ Gate.io Private Error: {e}")
    else:
        print("⚠️  Gate.io credentials not found - set GATEIO_API_KEY and GATEIO_SECRET_KEY environment variables")


async def benchmark_performance():
    """Benchmark HFT performance characteristics."""
    print("\n⚡ HFT Performance Benchmark")
    print("=" * 60)
    
    # Benchmark MEXC
    print("\n🏃 MEXC Performance Test (50 requests)")
    async with create_transport_manager("mexc", is_private=False) as mexc_transport:
        start_time = time.perf_counter()
        
        # Make 50 concurrent requests
        tasks = []
        for i in range(50):
            task = mexc_transport.get(
                "/api/v3/ticker/24hr",
                params={"symbol": "BTCUSDT"}
            )
            tasks.append(task)
        
        # Execute all requests
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful = sum(1 for r in results if not isinstance(r, Exception))
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            print(f"✅ Completed: {successful}/50 requests in {elapsed:.2f}ms")
            print(f"📊 Throughput: {(successful / (elapsed / 1000)):.1f} requests/second")
            
            # Get detailed performance metrics
            perf_summary = mexc_transport.get_performance_summary()
            print(f"📈 HFT Metrics:")
            print(f"   - Average Latency: {perf_summary['avg_latency_ms']:.2f}ms")
            print(f"   - P95 Latency: {perf_summary['p95_latency_ms']:.2f}ms")
            print(f"   - P99 Latency: {perf_summary['p99_latency_ms']:.2f}ms")
            print(f"   - Success Rate: {perf_summary['success_rate']:.1f}%")
            print(f"   - HFT Compliance: {perf_summary['hft_compliance_rate']:.1f}% (<50ms)")
            print(f"   - Rate Limit Hits: {perf_summary['rate_limit_hits']}")
            
            # HFT compliance check
            if perf_summary['hft_compliant']:
                print("🎯 HFT COMPLIANT: >95% requests under 50ms")
            else:
                print("⚠️  HFT VIOLATION: <95% requests under 50ms")
                
        except Exception as e:
            print(f"❌ Benchmark Error: {e}")


async def demo_rate_limiting():
    """Demonstrate rate limiting coordination."""
    print("\n🚦 Rate Limiting Demo")
    print("=" * 60)
    
    async with create_transport_manager("mexc", is_private=False) as transport:
        print("Making rapid requests to test rate limiting...")
        
        start_time = time.perf_counter()
        
        # Make rapid requests
        for i in range(10):
            try:
                response = await transport.get(
                    "/api/v3/ticker/24hr",
                    params={"symbol": "BTCUSDT"}
                )
                elapsed = (time.perf_counter() - start_time) * 1000
                print(f"Request {i+1}: {elapsed:.0f}ms - Price: {response.get('lastPrice', 'N/A')}")
                
            except Exception as e:
                print(f"Request {i+1}: ERROR - {e}")
        
        # Show rate limiting stats
        rate_stats = transport.strategy_set.rate_limit_strategy.get_stats()
        print(f"\n📊 Rate Limiting Stats:")
        print(f"Exchange: {rate_stats['exchange']}")
        print(f"Global Available: {rate_stats['global_available']}")
        
        for endpoint, stats in rate_stats['endpoints'].items():
            if stats['total_requests'] > 0:
                print(f"  {endpoint}: {stats['total_requests']} requests, {stats['available_permits']} permits")


async def demo_strategy_factory():
    """Demonstrate strategy factory patterns."""
    print("\n🏭 Strategy Factory Demo")
    print("=" * 60)
    
    # List available strategies
    available = RestStrategyFactory.list_available_strategies()
    print("Available Strategy Combinations:")
    for exchange, types in available.items():
        print(f"  {exchange}: {', '.join(types)}")
    
    # Create different strategy sets
    print("\nCreating Strategy Sets:")
    
    # MEXC public
    mexc_public = RestStrategyFactory.create_strategies("mexc", is_private=False)
    print(f"✅ MEXC Public: {mexc_public.request_strategy.__class__.__name__}")
    
    # Gate.io public
    gateio_public = RestStrategyFactory.create_strategies("gateio", is_private=False)
    print(f"✅ Gate.io Public: {gateio_public.request_strategy.__class__.__name__}")
    
    # Show performance targets
    mexc_targets = mexc_public.get_performance_targets()
    gateio_targets = gateio_public.get_performance_targets()
    
    print(f"\nPerformance Targets:")
    print(f"  MEXC: {mexc_targets.max_latency_ms}ms max, {mexc_targets.target_throughput_rps} RPS")
    print(f"  Gate.io: {gateio_targets.max_latency_ms}ms max, {gateio_targets.target_throughput_rps} RPS")


async def demo_config_integration():
    """Demonstrate ExchangeConfig integration."""
    print("\n⚙️  ExchangeConfig Integration Demo")
    print("=" * 60)
    
    # Demo 1: Manual ExchangeConfig creation
    print("📝 Creating Manual ExchangeConfig:")
    mexc_config = ExchangeConfig(
        name="mexc",
        credentials=ExchangeCredentials(
            api_key="demo_api_key_123456",
            secret_key="demo_secret_key_abcdef"
        ),
        base_url="https://api.mexc.com",
        websocket_url="wss://wbs.mexc.com/ws",
        network=NetworkConfig(
            request_timeout=6.0,  # Custom timeout
            connect_timeout=1.5,
            max_retries=2,
            retry_delay=0.3
        ),
        rate_limit=RateLimitConfig(
            requests_per_second=10  # Custom rate limit
        ),
        websocket=WebSocketConfig(
            connect_timeout=8.0,  # Faster WebSocket for MEXC
            heartbeat_interval=25.0,
            max_reconnect_attempts=5,
            reconnect_delay=3.0
        )
    )
    
    print(f"📋 MEXC Config Created:")
    print(f"   Base URL: {mexc_config.base_url}")
    print(f"   Credentials: {mexc_config.credentials.get_preview()}")
    print(f"   Network Timeout: {mexc_config.network.request_timeout}s")
    print(f"   Rate Limit: {mexc_config.rate_limit.requests_per_second} RPS")
    print(f"   WebSocket Timeout: {mexc_config.websocket.connect_timeout}s")
    print(f"   WebSocket Heartbeat: {mexc_config.websocket.heartbeat_interval}s")
    
    # Create transport manager from config
    print(f"\n🚀 Creating Transport from ExchangeConfig:")
    
    try:
        # Public API (no auth needed)
        public_transport = create_transport_from_config(mexc_config, is_private=False)
        print(f"✅ Public Transport: Created with custom network settings")
        
        # Check if it would work for private (credentials available)
        if mexc_config.has_credentials():
            print(f"✅ Private API Ready: Credentials configured")
        else:
            print(f"⚠️  Private API: No credentials configured")
            
        # Show how config values override strategy defaults
        perf_targets = public_transport.strategy_set.get_performance_targets()
        print(f"📊 Applied Configuration:")
        print(f"   Max Latency: {perf_targets.max_latency_ms}ms")
        print(f"   Max Retries: {perf_targets.max_retry_attempts}")
        
    except Exception as e:
        print(f"❌ Config Integration Error: {e}")
    
    # Create Gate.io config with different settings
    gateio_config = ExchangeConfig(
        name="gateio",
        credentials=ExchangeCredentials(
            api_key="",  # No credentials
            secret_key=""
        ),
        base_url="https://api.gateio.ws",
        websocket_url="wss://api.gateio.ws/ws/v4/",
        network=NetworkConfig(
            request_timeout=15.0,  # Very conservative
            connect_timeout=5.0,
            max_retries=4,
            retry_delay=1.0
        ),
        rate_limit=RateLimitConfig(
            requests_per_second=2  # Very conservative
        ),
        websocket=WebSocketConfig(
            connect_timeout=12.0,  # Slower WebSocket for Gate.io
            heartbeat_interval=45.0,
            max_reconnect_attempts=8,
            reconnect_delay=7.0
        )
    )
    
    print(f"\n📋 Gate.io Config Created:")
    print(f"   Base URL: {gateio_config.base_url}")
    print(f"   Credentials: {gateio_config.credentials.get_preview()}")
    print(f"   Network Timeout: {gateio_config.network.request_timeout}s")
    print(f"   Rate Limit: {gateio_config.rate_limit.requests_per_second} RPS")
    print(f"   WebSocket Timeout: {gateio_config.websocket.connect_timeout}s")
    print(f"   WebSocket Heartbeat: {gateio_config.websocket.heartbeat_interval}s")
    
    # Show difference in performance targets
    try:
        gateio_transport = create_transport_from_config(gateio_config, is_private=False)
        gateio_targets = gateio_transport.strategy_set.get_performance_targets()
        
        print(f"\n📊 Configuration Comparison:")
        print(f"   REST Timeout: MEXC {mexc_config.network.request_timeout}s vs Gate.io {gateio_config.network.request_timeout}s")
        print(f"   Rate Limit: MEXC {mexc_config.rate_limit.requests_per_second} RPS vs Gate.io {gateio_config.rate_limit.requests_per_second} RPS")
        print(f"   WebSocket Timeout: MEXC {mexc_config.websocket.connect_timeout}s vs Gate.io {gateio_config.websocket.connect_timeout}s")
        print(f"   WebSocket Heartbeat: MEXC {mexc_config.websocket.heartbeat_interval}s vs Gate.io {gateio_config.websocket.heartbeat_interval}s")
        
    except Exception as e:
        print(f"❌ Gate.io Config Error: {e}")
    
    # Demo 2: Load from YAML config system
    print(f"\n📋 Loading from YAML Configuration System:")
    try:
        from core.config.config_manager import get_exchange_config_struct
        
        # Try to load actual config from config.yaml
        try:
            yaml_mexc_config = get_exchange_config_struct('mexc')
            print(f"✅ MEXC from YAML:")
            print(f"   Base URL: {yaml_mexc_config.base_url}")
            print(f"   Credentials: {yaml_mexc_config.credentials.get_preview()}")
            if yaml_mexc_config.network:
                print(f"   Network Timeout: {yaml_mexc_config.network.request_timeout}s")
            if yaml_mexc_config.rate_limit:
                print(f"   Rate Limit: {yaml_mexc_config.rate_limit.requests_per_second} RPS")
            if yaml_mexc_config.websocket:
                print(f"   WebSocket Timeout: {yaml_mexc_config.websocket.connect_timeout}s")
                print(f"   WebSocket Heartbeat: {yaml_mexc_config.websocket.heartbeat_interval}s")
            
            # Create transport from YAML config and test it
            yaml_transport = create_transport_from_config(yaml_mexc_config, is_private=False)
            print(f"✅ Transport created from YAML config")
            
            # Test actual API call
            try:
                async with yaml_transport:
                    response = await yaml_transport.get("/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"})
                    price = response.get('lastPrice', 'N/A')
                    print(f"🚀 YAML Config API Test: BTC price = {price}")
                    
                    # Show performance
                    perf = yaml_transport.get_performance_summary()
                    print(f"📊 YAML Transport Performance: {perf['avg_latency_ms']:.1f}ms avg")
            except Exception as api_e:
                print(f"⚠️  API Test Error: {api_e}")
            
        except Exception as e:
            print(f"⚠️  YAML MEXC Config: {e}")
        
        try:
            yaml_gateio_config = get_exchange_config_struct('gateio')
            print(f"✅ Gate.io from YAML:")
            print(f"   Base URL: {yaml_gateio_config.base_url}")
            print(f"   Credentials: {yaml_gateio_config.credentials.get_preview()}")
            if yaml_gateio_config.network:
                print(f"   Network Timeout: {yaml_gateio_config.network.request_timeout}s")
            if yaml_gateio_config.rate_limit:
                print(f"   Rate Limit: {yaml_gateio_config.rate_limit.requests_per_second} RPS")
            if yaml_gateio_config.websocket:
                print(f"   WebSocket Timeout: {yaml_gateio_config.websocket.connect_timeout}s")
                print(f"   WebSocket Heartbeat: {yaml_gateio_config.websocket.heartbeat_interval}s")
            
        except Exception as e:
            print(f"⚠️  YAML Gate.io Config: {e}")
            
    except ImportError as e:
        print(f"❌ Config Manager Import Error: {e}")
    except Exception as e:
        print(f"❌ YAML Config System Error: {e}")


async def main():
    """Main demo orchestrator."""
    parser = argparse.ArgumentParser(description='REST Transport Strategy Demo')
    parser.add_argument('--private', action='store_true', help='Test private API endpoints')
    parser.add_argument('--benchmark', action='store_true', help='Run performance benchmark')
    parser.add_argument('--rate-limit', action='store_true', help='Demo rate limiting')
    parser.add_argument('--factory', action='store_true', help='Demo strategy factory')
    parser.add_argument('--config', action='store_true', help='Demo ExchangeConfig integration')
    parser.add_argument('--all', action='store_true', help='Run all demos')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(level=logging.WARNING)
    
    print("🌟 REST Transport Strategy System Demo")
    print("======================================")
    
    try:
        # Run demos based on arguments
        if args.all or not any([args.private, args.benchmark, args.rate_limit, args.factory, args.config]):
            await demo_public_api()
            await demo_strategy_factory()
        
        if args.private or args.all:
            await demo_private_api()
        
        if args.benchmark or args.all:
            await benchmark_performance()
        
        if args.rate_limit or args.all:
            await demo_rate_limiting()
        
        if args.factory or args.all:
            await demo_strategy_factory()
        
        if args.config or args.all:
            await demo_config_integration()
        
        print("\n✨ Demo completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())