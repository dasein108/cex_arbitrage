"""
Consolidated REST Integration Test

Combines public and private REST API integration testing into a single comprehensive test suite.
Eliminates code duplication from separate rest_public_integration_test.py and rest_private_integration_test.py.

Usage:
    python src/examples/integration_tests/rest_integration_test.py mexc
    python src/examples/integration_tests/rest_integration_test.py gateio --include-private
    python src/examples/integration_tests/rest_integration_test.py mexc --include-private --output results.json
"""

import asyncio
import sys
import argparse
import time
from typing import Dict, Any

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

from ..base.integration_test_base import IntegrationTestBase, RestIntegrationTestMixin
from ..integration_test_framework import TestCategory, TestStatus, EXIT_CODE_SUCCESS, EXIT_CODE_FAILED_TESTS, EXIT_CODE_ERROR, EXIT_CODE_CONFIG_ERROR
from ..utils.constants import DEFAULT_TEST_TIMEOUT


class RestIntegrationTest(IntegrationTestBase, RestIntegrationTestMixin):
    """Consolidated REST integration test suite for both public and private APIs."""
    
    def __init__(self, exchange_name: str):
        super().__init__(exchange_name, "REST_CONSOLIDATED_API")
        self.include_private = False
        self.private_exchange = None
    
    async def setup_private_exchange(self) -> Dict[str, Any]:
        """Setup separate private exchange client for private tests."""
        try:
            # Verify credentials
            if not self.config.credentials.api_key or not self.config.credentials.secret_key:
                raise ValueError(f"{self.exchange_name} API credentials are required for private testing")
            
            from exchanges.exchange_factory import create_rest_client
            from exchanges.utils.exchange_utils import get_exchange_enum
            
            exchange_enum = get_exchange_enum(self.exchange_name)
            self.private_exchange = create_rest_client(
                exchange=exchange_enum,
                is_private=True,
                config=self.config
            )
            
            return {
                "private_setup_successful": True,
                "private_exchange_class": type(self.private_exchange).__name__,
                "api_key_preview": f"{self.config.credentials.api_key[:8]}..."
            }
            
        except Exception as e:
            raise ConnectionError(f"Failed to setup {self.exchange_name} private exchange: {str(e)}")
    
    async def teardown_private_exchange(self) -> None:
        """Clean up private exchange resources."""
        if self.private_exchange:
            await self.private_exchange.close()
            self.private_exchange = None
    
    # Public API Tests (using base class functionality)
    
    async def test_ping(self) -> Dict[str, Any]:
        """Test ping functionality."""
        return await self.test_ping_integration()
    
    async def test_server_time(self) -> Dict[str, Any]:
        """Test server time retrieval."""
        return await self.test_server_time_integration()
    
    async def test_exchange_info(self) -> Dict[str, Any]:
        """Test exchange info retrieval."""
        return await self.test_exchange_info_integration()
    
    async def test_orderbook(self) -> Dict[str, Any]:
        """Test orderbook retrieval with comprehensive validation."""
        start_time = time.time()
        symbol = self.get_test_symbols()[0]
        
        try:
            result = await self.exchange.get_orderbook(symbol, limit=10)
            performance = self.measure_performance(start_time)
            
            # Comprehensive orderbook validation
            has_bids = len(result.bids) > 0
            has_asks = len(result.asks) > 0
            has_timestamp = result.timestamp > 0
            
            # Check price ordering
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
            
            # Check spread
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
                "data_points_received": len(result.bids) + len(result.asks),
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"Orderbook test failed: {str(e)}")
    
    async def test_recent_trades(self) -> Dict[str, Any]:
        """Test recent trades retrieval with validation."""
        start_time = time.time()
        symbol = self.get_test_symbols()[0]
        
        try:
            result = await self.exchange.get_recent_trades(symbol, limit=10)
            performance = self.measure_performance(start_time)
            
            trades_count = len(result)
            has_trades = trades_count > 0
            
            # Validate sample trades
            valid_trades = []
            for trade in result[:3]:  # Check first 3 trades
                validation = self.validate_common_fields(trade, [
                    "price", "quantity", "timestamp", "side", "is_maker"
                ])
                valid_trades.append(validation)
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "trades_count": trades_count,
                "has_trades": has_trades,
                "sample_trade_validations": valid_trades,
                "data_points_received": trades_count,
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"Recent trades test failed: {str(e)}")
    
    async def test_ticker_info(self) -> Dict[str, Any]:
        """Test ticker info retrieval with validation."""
        start_time = time.time()
        symbol = self.get_test_symbols()[0]
        
        try:
            # Test single symbol and all symbols
            single_result = await self.exchange.get_ticker_info(symbol)
            all_start = time.time()
            all_result = await self.exchange.get_ticker_info()
            
            performance = self.measure_performance(start_time)
            all_execution_time = (time.time() - all_start) * 1000
            
            # Validate ticker data
            single_ticker_exists = symbol in single_result
            ticker = single_result.get(symbol)
            
            ticker_validation = {}
            if ticker:
                ticker_validation = self.validate_common_fields(ticker, [
                    "last_price", "volume", "price_change_percent", "high_price", "low_price"
                ])
            
            return {
                "test_symbol": f"{symbol.base}/{symbol.quote}",
                "single_ticker_exists": single_ticker_exists,
                "ticker_validation": ticker_validation,
                "all_symbols_count": len(all_result),
                "has_multiple_symbols": len(all_result) > 1,
                "single_request_time_ms": performance["execution_time_ms"] - all_execution_time,
                "all_symbols_request_time_ms": all_execution_time,
                "performance_acceptable": all_execution_time < 10000,
                "data_points_received": 1 + len(all_result),
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"Ticker info test failed: {str(e)}")
    
    # Private API Tests (only run if include_private=True)
    
    async def test_account_balance(self) -> Dict[str, Any]:
        """Test account balance retrieval."""
        start_time = time.time()
        
        try:
            result = await self.private_exchange.get_balances()
            performance = self.measure_performance(start_time)
            
            balances_count = len(result)
            has_balances = balances_count > 0
            
            # Analyze balance data
            non_zero_balances = [
                {
                    "asset": balance.asset,
                    "free": balance.available,
                    "locked": balance.locked,
                    "total": balance.total,
                    "validation": self.validate_common_fields(balance, ["asset", "free", "locked"])
                }
                for balance in result[:5] if balance.available > 0 or balance.locked > 0
            ]
            
            return {
                "total_balances": balances_count,
                "has_balances": has_balances,
                "non_zero_balances": non_zero_balances,
                "data_points_received": balances_count,
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"Account balance test failed: {str(e)}")
    
    async def test_open_orders(self) -> Dict[str, Any]:
        """Test open orders retrieval."""
        start_time = time.time()
        
        try:
            result = await self.private_exchange.get_open_orders()
            performance = self.measure_performance(start_time)
            
            orders_count = len(result)
            
            # Validate sample orders
            sample_orders = []
            for order in result[:3]:  # First 3 orders
                validation = self.validate_common_fields(order, [
                    "order_id", "symbol", "side", "order_type", "quantity", "price", "status"
                ])
                sample_orders.append({
                    "order_id": order.order_id,
                    "symbol": f"{order.symbol.base}/{order.symbol.quote}",
                    "validation": validation
                })
            
            return {
                "open_orders_count": orders_count,
                "has_open_orders": orders_count > 0,
                "sample_orders": sample_orders,
                "data_points_received": orders_count,
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"Open orders test failed: {str(e)}")
    
    async def test_trading_functionality(self) -> Dict[str, Any]:
        """Test basic trading operations (place/cancel - expect failures for safety)."""
        start_time = time.time()
        symbol = Symbol(base=AssetName('ADA'), quote=AssetName('USDT'), is_futures=False)
        
        place_order_result = {
            "order_placed": False,
            "error_message": "Not attempted",
            "note": "Intentionally skipped to avoid accidental trades"
        }
        
        cancel_order_result = {
            "order_cancelled": False,
            "error_message": "Not attempted", 
            "note": "Intentionally skipped - no order to cancel"
        }
        
        # Test cancel all orders (safe operation)
        cancel_all_result = {}
        try:
            cancelled_orders = await self.private_exchange.cancel_all_orders(symbol)
            cancel_all_result = {
                "cancel_all_successful": True,
                "cancelled_count": len(cancelled_orders),
                "orders_cancelled": [
                    {
                        "order_id": order.order_id,
                        "status": order.status.name
                    } for order in cancelled_orders[:3]  # Show first 3
                ]
            }
        except Exception as e:
            cancel_all_result = {
                "cancel_all_successful": False,
                "error_message": str(e),
                "note": "This is expected if no orders exist"
            }
        
        performance = self.measure_performance(start_time)
        
        return {
            "test_symbol": f"{symbol.base}/{symbol.quote}",
            "place_order_test": place_order_result,
            "cancel_order_test": cancel_order_result,
            "cancel_all_test": cancel_all_result,
            "safety_note": "Order placement tests skipped to prevent accidental trading",
            **performance
        }
    
    async def run_all_tests(self, timeout_seconds: int = DEFAULT_TEST_TIMEOUT) -> None:
        """Run complete REST integration test suite."""
        try:
            # Setup public exchange
            await self.run_test_with_standard_validation(
                self.setup_exchange,
                "public_exchange_setup",
                TestCategory.CONFIGURATION,
                timeout_seconds=10,
                expected_behavior="Public exchange configuration loaded and REST client initialized"
            )
            
            # Public API Tests
            await self.run_test_with_standard_validation(
                self.test_ping,
                "ping_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Ping returns successful response within acceptable latency"
            )
            
            await self.run_test_with_standard_validation(
                self.test_server_time,
                "server_time_test", 
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Server time retrieved and within reasonable range of local time"
            )
            
            await self.run_test_with_standard_validation(
                self.test_exchange_info,
                "exchange_info_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Exchange info contains valid symbol data with required fields"
            )
            
            await self.run_test_with_standard_validation(
                self.test_orderbook,
                "orderbook_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Orderbook retrieved with valid bids/asks and proper ordering"
            )
            
            await self.run_test_with_standard_validation(
                self.test_recent_trades,
                "recent_trades_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Recent trades retrieved with valid trade data structure"
            )
            
            await self.run_test_with_standard_validation(
                self.test_ticker_info,
                "ticker_info_test",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="24hr ticker statistics retrieved for single symbol and all symbols"
            )
            
            # Private API Tests (only if requested)
            if self.include_private:
                await self.run_test_with_standard_validation(
                    self.setup_private_exchange,
                    "private_exchange_setup",
                    TestCategory.CONFIGURATION,
                    timeout_seconds=10,
                    expected_behavior="Private exchange setup with valid API credentials"
                )
                
                await self.run_test_with_standard_validation(
                    self.test_account_balance,
                    "account_balance_test",
                    TestCategory.REST_PRIVATE,
                    timeout_seconds=timeout_seconds,
                    expected_behavior="Account balance retrieved with valid balance data"
                )
                
                await self.run_test_with_standard_validation(
                    self.test_open_orders,
                    "open_orders_test",
                    TestCategory.REST_PRIVATE,
                    timeout_seconds=timeout_seconds,
                    expected_behavior="Open orders retrieved (empty list is acceptable)"
                )
                
                await self.run_test_with_standard_validation(
                    self.test_trading_functionality,
                    "trading_functionality_test",
                    TestCategory.REST_PRIVATE,
                    timeout_seconds=timeout_seconds,
                    expected_behavior="Trading operations tested safely (place/cancel order functionality)"
                )
            
        finally:
            # Always cleanup
            await self.teardown()
            await self.teardown_private_exchange()


async def main():
    """Main entry point for consolidated REST integration testing."""
    parser = argparse.ArgumentParser(description="Consolidated REST Integration Test")
    parser.add_argument("exchange", nargs="?", default="mexc", 
                       help="Exchange name (mexc, gateio)")
    parser.add_argument("--include-private", action="store_true",
                       help="Include private API tests (requires credentials)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TEST_TIMEOUT,
                       help="Test timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Validate exchange
    supported_exchanges = ["mexc", "gateio"]
    if args.exchange.lower() not in supported_exchanges:
        print(f"Error: Unsupported exchange '{args.exchange}'. Supported: {supported_exchanges}")
        sys.exit(EXIT_CODE_CONFIG_ERROR)
    
    # Create test suite
    test_suite = RestIntegrationTest(args.exchange.upper())
    test_suite.include_private = args.include_private
    
    try:
        # Run tests
        await test_suite.run_all_tests(timeout_seconds=args.timeout)
        
        # Generate and output results
        if args.output:
            test_suite.test_runner.output_json_result(args.output)
            if args.verbose:
                print(f"Results saved to: {args.output}")
        elif args.verbose:
            test_suite.test_runner.output_json_result()
        
        # Print summary
        test_suite.test_runner.print_summary_for_agent()
        
        # Determine exit code
        report = test_suite.test_runner.generate_report()
        if report.overall_status == TestStatus.PASSED:
            sys.exit(EXIT_CODE_SUCCESS)
        elif report.overall_status == TestStatus.FAILED:
            sys.exit(EXIT_CODE_FAILED_TESTS)
        else:
            sys.exit(EXIT_CODE_ERROR)
            
    except KeyboardInterrupt:
        print("Test interrupted by user")
        sys.exit(EXIT_CODE_ERROR)
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        sys.exit(EXIT_CODE_ERROR)


if __name__ == "__main__":
    asyncio.run(main())