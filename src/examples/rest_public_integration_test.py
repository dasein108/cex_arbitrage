"""
AI-Agent REST Public API Integration Test

Automated integration testing for public REST API functionality across exchanges.
Outputs structured JSON results for AI agent consumption with standardized test outcomes,
performance metrics, and error reporting.

Usage:
    python src/examples/rest_public_integration_test.py mexc
    python src/examples/rest_public_integration_test.py gateio
    python src/examples/rest_public_integration_test.py mexc --output results.json
    python src/examples/rest_public_integration_test.py gateio --timeout 60

Exit Codes:
    0: All tests passed
    1: Some tests failed but no errors
    2: Test errors occurred  
    3: Test timeout
    4: Configuration error
"""

import asyncio
import sys
import argparse
import time
from typing import Dict, Any

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from config.config_manager import HftConfig
from exchanges.structs import ExchangeEnum
from exchanges.integrations.mexc.public_exchange import MexcPublicExchange
from exchanges.integrations.gateio.public_exchange import GateioPublicPublicExchange
from examples.integration_test_framework import (
    IntegrationTestRunner, TestCategory, TestStatus, EXIT_CODE_SUCCESS, EXIT_CODE_FAILED_TESTS, EXIT_CODE_ERROR,
    EXIT_CODE_CONFIG_ERROR
)


class RestPublicIntegrationTest:
    """REST Public API integration test suite for AI agents."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.exchange = None
        self.test_runner = IntegrationTestRunner(
            exchange=self.exchange_name,
            test_suite="REST_PUBLIC_API"
        )
        
    def _create_exchange_client(self, exchange_name: str, config):
        """Create exchange client using standard constructors."""
        if exchange_name.upper() == "MEXC":
            return MexcPublicExchange(config=config)
        elif exchange_name.upper() == "GATEIO":
            return GateioPublicPublicExchange(config=config)
        else:
            raise ValueError(f"Unsupported exchange: {exchange_name}")
    
    async def setup(self) -> Dict[str, Any]:
        """Setup exchange connection for testing."""
        try:
            config_manager = HftConfig()
            config = config_manager.get_exchange_config(self.exchange_name.lower())
            self.exchange = self._create_exchange_client(self.exchange_name, config)
            
            return {
                "setup_successful": True,
                "exchange_class": type(self.exchange).__name__,
                "config_loaded": True
            }
        except Exception as e:
            raise ConnectionError(f"Failed to setup {self.exchange_name} exchange: {str(e)}")
    
    async def teardown(self) -> None:
        """Clean up resources."""
        if self.exchange:
            await self.exchange.close()
    
    async def test_ping(self) -> Dict[str, Any]:
        """Test ping functionality."""
        start_time = time.time()
        
        try:
            result = await self.exchange.ping()
            execution_time = (time.time() - start_time) * 1000
            
            return {
                "ping_result": result,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "response_received": True,
                "latency_acceptable": execution_time < 5000  # 5 second max for ping
            }
        except Exception as e:
            raise ConnectionError(f"Ping failed: {str(e)}")
    
    async def test_get_server_time(self) -> Dict[str, Any]:
        """Test server time retrieval."""
        start_time = time.time()
        
        try:
            result = await self.exchange.get_server_time()
            execution_time = (time.time() - start_time) * 1000
            current_time = time.time() * 1000  # Convert to milliseconds
            
            # Validate server time is reasonable (within 1 hour of local time)
            time_diff = abs(result - current_time)
            time_valid = time_diff < 3600000  # 1 hour in milliseconds
            
            return {
                "server_time": result,
                "local_time": current_time,
                "time_difference_ms": time_diff,
                "time_valid": time_valid,
                "execution_time_ms": execution_time,
                "network_requests": 1
            }
        except Exception as e:
            raise ValueError(f"Server time retrieval failed: {str(e)}")
    
    async def test_get_exchange_info(self) -> Dict[str, Any]:
        """Test exchange info retrieval."""
        start_time = time.time()
        
        try:
            result = await self.exchange.get_exchange_info()
            execution_time = (time.time() - start_time) * 1000
            
            # Validate exchange info structure
            symbols_count = len(result)
            has_symbols = symbols_count > 0
            
            # Check first few symbols for required fields
            sample_symbols = []
            for i, (symbol, info) in enumerate(result.items()):
                if i >= 3:  # Check first 3 symbols
                    break
                sample_symbols.append({
                    "symbol": f"{symbol.base}/{symbol.quote}",
                    "exchange": info.exchange,
                    "base_precision": info.base_precision,
                    "quote_precision": info.quote_precision,
                    "has_required_fields": all([
                        hasattr(info, 'base_precision'),
                        hasattr(info, 'quote_precision'),
                        hasattr(info, 'min_base_amount'),
                        hasattr(info, 'min_quote_amount')
                    ])
                })
            
            return {
                "total_symbols": symbols_count,
                "has_symbols": has_symbols,
                "sample_symbols": sample_symbols,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": symbols_count
            }
        except Exception as e:
            raise ValueError(f"Exchange info retrieval failed: {str(e)}")
    
    async def test_get_orderbook(self) -> Dict[str, Any]:
        """Test orderbook retrieval."""
        start_time = time.time()
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
        
        try:
            result = await self.exchange.get_orderbook(symbol, limit=5)
            execution_time = (time.time() - start_time) * 1000
            
            # Validate orderbook structure
            has_bids = len(result.bids) > 0
            has_asks = len(result.asks) > 0
            has_timestamp = result.timestamp > 0
            
            # Check price ordering (bids descending, asks ascending)
            bids_ordered = True
            asks_ordered = True
            
            if len(result.bids) > 1:
                bids_ordered = all(
                    result.bids[i].price >= result.bids[i+1].price 
                    for i in range(len(result.bids)-1)
                )
            
            if len(result.asks) > 1:
                asks_ordered = all(
                    result.asks[i].price <= result.asks[i+1].price 
                    for i in range(len(result.asks)-1)
                )
            
            # Check spread if both sides exist
            spread = None
            spread_positive = True
            if has_bids and has_asks:
                spread = result.asks[0].price - result.bids[0].price
                spread_positive = spread >= 0
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "timestamp": result.timestamp,
                "bids_count": len(result.bids),
                "asks_count": len(result.asks),
                "has_bids": has_bids,
                "has_asks": has_asks,
                "has_timestamp": has_timestamp,
                "bids_ordered_correctly": bids_ordered,
                "asks_ordered_correctly": asks_ordered,
                "spread": spread,
                "spread_positive": spread_positive,
                "best_bid": result.bids[0].price if has_bids else None,
                "best_ask": result.asks[0].price if has_asks else None,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": len(result.bids) + len(result.asks)
            }
        except Exception as e:
            raise ValueError(f"Orderbook retrieval failed: {str(e)}")
    
    async def test_get_recent_trades(self) -> Dict[str, Any]:
        """Test recent trades retrieval."""
        start_time = time.time()
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
        
        try:
            result = await self.exchange.get_recent_trades(symbol, limit=5)
            execution_time = (time.time() - start_time) * 1000
            
            # Validate trades structure
            trades_count = len(result)
            has_trades = trades_count > 0
            
            # Check trade data validity
            trade_samples = []
            for i, trade in enumerate(result[:3]):  # Check first 3 trades
                trade_samples.append({
                    "price": trade.price,
                    "quantity": trade.quantity,
                    "side": trade.side.name,
                    "timestamp": trade.timestamp,
                    "is_maker": trade.is_maker,
                    "has_required_fields": all([
                        trade.price > 0,
                        trade.quantity > 0,
                        trade.timestamp > 0,
                        hasattr(trade, 'side'),
                        hasattr(trade, 'is_maker')
                    ])
                })
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "trades_count": trades_count,
                "has_trades": has_trades,
                "trade_samples": trade_samples,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": trades_count
            }
        except Exception as e:
            raise ValueError(f"Recent trades retrieval failed: {str(e)}")
    
    async def test_get_historical_trades(self) -> Dict[str, Any]:
        """Test historical trades retrieval."""
        start_time = time.time()
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
        
        try:
            # Test with timestamp filtering (24 hours ago to now)
            now_ms = int(time.time() * 1000)
            from_ms = now_ms - (24 * 60 * 60 * 1000)  # 24 hours ago
            
            result = await self.exchange.get_historical_trades(
                symbol, 
                limit=10, 
                timestamp_from=from_ms, 
                timestamp_to=now_ms
            )
            execution_time = (time.time() - start_time) * 1000
            
            # Validate trades structure
            trades_count = len(result)
            has_trades = trades_count > 0
            
            # Check trade data validity
            trade_samples = []
            timestamps_in_range = True
            
            for i, trade in enumerate(result[:3]):  # Check first 3 trades
                in_range = from_ms <= trade.timestamp <= now_ms
                timestamps_in_range = timestamps_in_range and in_range
                
                trade_samples.append({
                    "price": trade.price,
                    "quantity": trade.quantity,
                    "side": trade.side.name,
                    "timestamp": trade.timestamp,
                    "trade_id": trade.trade_id,
                    "timestamp_in_range": in_range,
                    "has_required_fields": all([
                        trade.price > 0,
                        trade.quantity > 0,
                        trade.timestamp > 0,
                        hasattr(trade, 'side'),
                        hasattr(trade, 'timestamp')
                    ])
                })
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "trades_count": trades_count,
                "has_trades": has_trades,
                "timestamp_from": from_ms,
                "timestamp_to": now_ms,
                "timestamps_in_range": timestamps_in_range,
                "trade_samples": trade_samples,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": trades_count,
                "supports_timestamp_filtering": True  # Will be overridden for MEXC
            }
        except Exception as e:
            raise ValueError(f"Historical trades retrieval failed: {str(e)}")
    
    async def test_get_ticker_info(self) -> Dict[str, Any]:
        """Test ticker info retrieval."""
        start_time = time.time()
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
        
        try:
            # Test single symbol ticker
            single_result = await self.exchange.get_ticker_info(symbol)
            
            # Test all symbols ticker (limited fetch for performance)
            all_start = time.time()
            all_result = await self.exchange.get_ticker_info()
            all_execution_time = (time.time() - all_start) * 1000
            
            total_execution_time = (time.time() - start_time) * 1000
            
            # Validate ticker structure
            single_ticker_exists = symbol in single_result
            ticker = single_result.get(symbol)
            
            ticker_data = {}
            if ticker:
                ticker_data = {
                    "symbol": f"{ticker.symbol.base}/{ticker.symbol.quote}",
                    "last_price": ticker.last_price,
                    "price_change": ticker.price_change,
                    "price_change_percent": ticker.price_change_percent,
                    "high_price": ticker.high_price,
                    "low_price": ticker.low_price,
                    "volume": ticker.volume,
                    "quote_volume": ticker.quote_volume,
                    "open_time": ticker.open_time,
                    "close_time": ticker.close_time,
                    "bid_price": ticker.bid_price,
                    "ask_price": ticker.ask_price,
                    "has_required_fields": all([
                        ticker.last_price > 0,
                        ticker.volume >= 0,
                        ticker.quote_volume >= 0,
                        hasattr(ticker, 'price_change_percent'),
                        hasattr(ticker, 'high_price'),
                        hasattr(ticker, 'low_price')
                    ])
                }
            
            # Validate all symbols response
            all_symbols_count = len(all_result)
            has_multiple_symbols = all_symbols_count > 1
            
            return {
                "test_symbol": f"{symbol.base}/{symbol.quote}",
                "single_ticker_exists": single_ticker_exists,
                "ticker_data": ticker_data,
                "all_symbols_count": all_symbols_count,
                "has_multiple_symbols": has_multiple_symbols,
                "single_request_time_ms": total_execution_time - all_execution_time,
                "all_symbols_request_time_ms": all_execution_time,
                "total_execution_time_ms": total_execution_time,
                "network_requests": 2,
                "data_points_received": 1 + all_symbols_count,
                "performance_acceptable": all_execution_time < 10000  # 10 second max for all tickers
            }
        except Exception as e:
            raise ValueError(f"Ticker info retrieval failed: {str(e)}")
    
    async def run_all_tests(self, timeout_seconds: int = 30) -> None:
        """Run complete REST public API test suite."""
        try:
            # Setup
            await self.test_runner.run_test_with_timeout(
                self.setup,
                "exchange_setup",
                TestCategory.CONFIGURATION,
                timeout_seconds=10,
                expected_behavior="Exchange configuration loaded and REST client initialized"
            )
            
            # Test ping
            await self.test_runner.run_test_with_timeout(
                self.test_ping,
                "ping_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Ping returns successful response within acceptable latency"
            )
            
            # Test server time
            await self.test_runner.run_test_with_timeout(
                self.test_get_server_time,
                "server_time_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Server time retrieved and within reasonable range of local time"
            )
            
            # Test exchange info
            await self.test_runner.run_test_with_timeout(
                self.test_get_exchange_info,
                "exchange_info_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Exchange info contains valid symbol data with required fields"
            )
            
            # Test orderbook
            await self.test_runner.run_test_with_timeout(
                self.test_get_orderbook,
                "orderbook_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Orderbook retrieved with valid bids/asks and proper ordering"
            )
            
            # Test recent trades
            await self.test_runner.run_test_with_timeout(
                self.test_get_recent_trades,
                "recent_trades_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Recent trades retrieved with valid trade data structure"
            )
            
            # Test historical trades
            await self.test_runner.run_test_with_timeout(
                self.test_get_historical_trades,
                "historical_trades_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Historical trades retrieved with timestamp filtering capability"
            )
            
            # Test ticker info
            await self.test_runner.run_test_with_timeout(
                self.test_get_ticker_info,
                "ticker_info_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="24hr ticker statistics retrieved for single symbol and all symbols"
            )
            
        finally:
            # Always cleanup
            await self.teardown()


async def main():
    """Main entry point for AI agent integration testing."""
    parser = argparse.ArgumentParser(description="REST Public API Integration Test for AI Agents")
    parser.add_argument("exchange", nargs="?", default="mexc", help="Exchange name (mexc, gateio) - defaults to mexc")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Test timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Validate exchange
    supported_exchanges = ["mexc", "gateio"]
    if args.exchange.lower() not in supported_exchanges:
        print(f"Error: Unsupported exchange '{args.exchange}'. Supported: {supported_exchanges}")
        sys.exit(EXIT_CODE_CONFIG_ERROR)
    
    # Convert to ExchangeEnum
    exchange_enum = ExchangeEnum(args.exchange.upper() + "_SPOT")
    
    # Create test suite
    test_suite = RestPublicIntegrationTest(exchange_enum.value)
    
    try:
        # Run tests
        await test_suite.run_all_tests(timeout_seconds=args.timeout)
        
        # Generate and output results
        if args.output:
            json_result = test_suite.test_runner.output_json_result(args.output)
            if args.verbose:
                print(f"Results saved to: {args.output}")
        else:
            json_result = test_suite.test_runner.output_json_result()
            if args.verbose:
                print(json_result)
        
        # Print summary for AI agent
        test_suite.test_runner.print_summary_for_agent()
        
        # Determine exit code
        report = test_suite.test_runner.generate_report()
        if report.overall_status == TestStatus.PASSED:
            sys.exit(EXIT_CODE_SUCCESS)
        elif report.overall_status == TestStatus.FAILED:
            sys.exit(EXIT_CODE_FAILED_TESTS)
        elif report.overall_status == TestStatus.ERROR:
            sys.exit(EXIT_CODE_ERROR)
        else:
            sys.exit(EXIT_CODE_ERROR)
            
    except KeyboardInterrupt:
        print("Test interrupted by user")
        sys.exit(EXIT_CODE_ERROR)
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        sys.exit(EXIT_CODE_ERROR)


# Pytest test functions
import pytest

@pytest.mark.asyncio
async def test_mexc_rest_public_integration():
    """Test MEXC REST public API integration."""
    test_suite = RestPublicIntegrationTest("mexc")
    try:
        await test_suite.run_all_tests(timeout_seconds=30)
        report = test_suite.test_runner.generate_report()
        assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary}"
    except Exception as e:
        pytest.fail(f"MEXC public integration test failed: {str(e)}")

@pytest.mark.asyncio
async def test_gateio_rest_public_integration():
    """Test Gate.io REST public API integration."""
    test_suite = RestPublicIntegrationTest("gateio")
    try:
        await test_suite.run_all_tests(timeout_seconds=30)
        report = test_suite.test_runner.generate_report()
        assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary}"
    except Exception as e:
        pytest.fail(f"Gate.io public integration test failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())