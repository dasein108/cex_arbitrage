"""
AI-Agent REST Private API Integration Test

Automated integration testing for private REST API functionality across exchanges.
Outputs structured JSON results for AI agent consumption with standardized test outcomes,
performance metrics, and error reporting.

Requires valid API credentials for authentication.

Usage:
    python src/examples/rest_private_integration_test.py mexc
    python src/examples/rest_private_integration_test.py gateio
    python src/examples/rest_private_integration_test.py mexc --output results.json
    python src/examples/rest_private_integration_test.py gateio --timeout 60

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

from structs.common import Symbol, AssetName, Side, OrderType, TimeInForce
from core.config.config_manager import get_exchange_config
from examples.utils.rest_api_factory import get_exchange_rest_instance
from examples.integration_test_framework import (
    IntegrationTestRunner, TestCategory, TestStatus, TestMetrics,
    EXIT_CODE_SUCCESS, EXIT_CODE_FAILED_TESTS, EXIT_CODE_ERROR, 
    EXIT_CODE_TIMEOUT, EXIT_CODE_CONFIG_ERROR
)


class RestPrivateIntegrationTest:
    """REST Private API integration test suite for AI agents."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.exchange = None
        self.test_runner = IntegrationTestRunner(
            exchange=self.exchange_name,
            test_suite="REST_PRIVATE_API"
        )
        
    async def setup(self) -> Dict[str, Any]:
        """Setup exchange connection with authentication."""
        try:
            config = get_exchange_config(self.exchange_name)
            
            # Verify credentials are available
            if not config.credentials.api_key or not config.credentials.secret_key:
                raise ValueError(f"{self.exchange_name} API credentials are required for private API testing")
            
            self.exchange = get_exchange_rest_instance(self.exchange_name, is_private=True, config=config)
            
            return {
                "setup_successful": True,
                "exchange_class": type(self.exchange).__name__,
                "config_loaded": True,
                "credentials_configured": True,
                "api_key_preview": config.credentials.api_key[:8] + "..." if config.credentials.api_key else None
            }
        except Exception as e:
            raise ConnectionError(f"Failed to setup {self.exchange_name} private exchange: {str(e)}")
    
    async def teardown(self) -> None:
        """Clean up resources."""
        if self.exchange:
            await self.exchange.close()
    
    async def test_get_account_balance(self) -> Dict[str, Any]:
        """Test account balance retrieval."""
        start_time = time.time()
        
        try:
            result = await self.exchange.get_account_balance()
            execution_time = (time.time() - start_time) * 1000
            
            # Validate balance structure
            balances_count = len(result)
            has_balances = balances_count > 0
            
            # Analyze balance data
            non_zero_balances = []
            for balance in result[:5]:  # Check first 5 balances
                if balance.free > 0 or balance.locked > 0:
                    non_zero_balances.append({
                        "asset": balance.asset,
                        "free": balance.free,
                        "locked": balance.locked,
                        "total": balance.total,
                        "has_required_fields": all([
                            hasattr(balance, 'asset'),
                            hasattr(balance, 'free'),
                            hasattr(balance, 'locked'),
                            hasattr(balance, 'total')
                        ])
                    })
            
            return {
                "total_balances": balances_count,
                "has_balances": has_balances,
                "non_zero_balances_count": len(non_zero_balances),
                "sample_balances": non_zero_balances[:3],  # First 3 non-zero balances
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": balances_count,
                "authentication_successful": True
            }
        except Exception as e:
            if "authentication" in str(e).lower() or "unauthorized" in str(e).lower():
                raise PermissionError(f"Authentication failed: {str(e)}")
            raise ValueError(f"Account balance retrieval failed: {str(e)}")
    
    async def test_get_asset_balance(self) -> Dict[str, Any]:
        """Test specific asset balance retrieval."""
        start_time = time.time()
        asset = AssetName('USDT')
        
        try:
            result = await self.exchange.get_asset_balance(asset)
            execution_time = (time.time() - start_time) * 1000
            
            # Validate asset balance
            balance_found = result is not None
            balance_data = None
            
            if result:
                balance_data = {
                    "asset": result.asset,
                    "free": result.free,
                    "locked": result.locked,
                    "total": result.total,
                    "has_balance": result.free > 0 or result.locked > 0
                }
            
            return {
                "requested_asset": asset,
                "balance_found": balance_found,
                "balance_data": balance_data,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": 1 if balance_found else 0
            }
        except Exception as e:
            raise ValueError(f"Asset balance retrieval failed for {asset}: {str(e)}")
    
    async def test_get_open_orders(self) -> Dict[str, Any]:
        """Test open orders retrieval."""
        start_time = time.time()
        
        try:
            result = await self.exchange.get_open_orders()
            execution_time = (time.time() - start_time) * 1000
            
            # Validate orders structure
            orders_count = len(result)
            has_orders = orders_count > 0
            
            # Analyze order data
            order_samples = []
            for order in result[:3]:  # First 3 orders
                order_samples.append({
                    "order_id": order.order_id,
                    "symbol": f"{order.symbol.base}/{order.symbol.quote}",
                    "side": order.side.name,
                    "order_type": order.order_type.name,
                    "quantity": order.quantity,
                    "price": order.price,
                    "status": order.status.name,
                    "filled_quantity": order.filled_quantity,
                    "has_required_fields": all([
                        hasattr(order, 'order_id'),
                        hasattr(order, 'symbol'),
                        hasattr(order, 'side'),
                        hasattr(order, 'order_type'),
                        hasattr(order, 'status')
                    ])
                })
            
            return {
                "open_orders_count": orders_count,
                "has_open_orders": has_orders,
                "sample_orders": order_samples,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": orders_count
            }
        except Exception as e:
            raise ValueError(f"Open orders retrieval failed: {str(e)}")
    
    async def test_get_order_status(self) -> Dict[str, Any]:
        """Test order status retrieval (expects failure for non-existent order)."""
        start_time = time.time()
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
        test_order_id = "test_nonexistent_order_123456789"
        
        try:
            result = await self.exchange.get_order(symbol, test_order_id)
            execution_time = (time.time() - start_time) * 1000
            
            # This should typically fail for non-existent order
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "order_id": test_order_id,
                "order_found": True,  # Unexpected but possible
                "order_data": {
                    "order_id": result.order_id,
                    "status": result.status.name,
                    "side": result.side.name
                } if result else None,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": 1
            }
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_message = str(e).lower()
            
            # Expected error patterns for non-existent orders
            expected_errors = ["not found", "invalid", "does not exist", "unknown"]
            is_expected_error = any(pattern in error_message for pattern in expected_errors)
            
            if is_expected_error:
                # This is expected behavior - order doesn't exist
                return {
                    "symbol": f"{symbol.base}/{symbol.quote}",
                    "order_id": test_order_id,
                    "order_found": False,
                    "expected_error": True,
                    "error_message": str(e),
                    "execution_time_ms": execution_time,
                    "network_requests": 1,
                    "api_validation_working": True
                }
            else:
                # Unexpected error
                raise ValueError(f"Unexpected error for order status: {str(e)}")
    
    async def test_place_order_simulation(self) -> Dict[str, Any]:
        """Test order placement (designed to fail safely)."""
        start_time = time.time()
        symbol = Symbol(base=AssetName('ADA'), quote=AssetName('USDT'), is_futures=False)
        
        try:
            # Place a small order with unrealistic price to trigger rejection
            result = await self.exchange.place_order(
                symbol=symbol,
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                amount=0.01,  # Very small amount
                price=0.00001,  # Unrealistically low price
                time_in_force=TimeInForce.GTC
            )
            execution_time = (time.time() - start_time) * 1000
            
            # Order was actually placed (unexpected but possible)
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "order_placed": True,
                "order_id": result.order_id,
                "side": result.side.name,
                "order_type": result.order_type.name,
                "amount": result.amount,
                "price": result.price,
                "status": result.status.name,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "warning": "Order was actually placed - consider canceling it manually"
            }
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_message = str(e).lower()
            
            # Expected error patterns for order placement
            expected_errors = [
                "insufficient", "balance", "funds", "price", "minimum", 
                "invalid", "too small", "precision", "filter"
            ]
            is_expected_error = any(pattern in error_message for pattern in expected_errors)
            
            if is_expected_error:
                # This is expected behavior - order validation working
                return {
                    "symbol": f"{symbol.base}/{symbol.quote}",
                    "order_placed": False,
                    "expected_error": True,
                    "error_message": str(e),
                    "execution_time_ms": execution_time,
                    "network_requests": 1,
                    "order_validation_working": True
                }
            else:
                # Unexpected error
                raise ValueError(f"Unexpected error for order placement: {str(e)}")
    
    async def test_cancel_order_simulation(self) -> Dict[str, Any]:
        """Test order cancellation (expects failure for non-existent order)."""
        start_time = time.time()
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
        test_order_id = "test_nonexistent_cancel_123456789"
        
        try:
            result = await self.exchange.cancel_order(symbol, test_order_id)
            execution_time = (time.time() - start_time) * 1000
            
            # Order was actually cancelled (unexpected)
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "order_id": test_order_id,
                "order_cancelled": True,
                "result_data": {
                    "order_id": result.order_id,
                    "status": result.status.name
                } if result else None,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "warning": "Non-existent order was somehow cancelled"
            }
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_message = str(e).lower()
            
            # Expected error patterns for non-existent orders
            expected_errors = ["not found", "invalid", "does not exist", "unknown"]
            is_expected_error = any(pattern in error_message for pattern in expected_errors)
            
            if is_expected_error:
                # This is expected behavior
                return {
                    "symbol": f"{symbol.base}/{symbol.quote}",
                    "order_id": test_order_id,
                    "order_cancelled": False,
                    "expected_error": True,
                    "error_message": str(e),
                    "execution_time_ms": execution_time,
                    "network_requests": 1,
                    "api_validation_working": True
                }
            else:
                # Unexpected error
                raise ValueError(f"Unexpected error for order cancellation: {str(e)}")
    
    async def run_all_tests(self, timeout_seconds: int = 30) -> None:
        """Run complete REST private API test suite."""
        try:
            # Setup
            await self.test_runner.run_test_with_timeout(
                self.setup,
                "exchange_setup",
                TestCategory.CONFIGURATION,
                timeout_seconds=10,
                expected_behavior="Exchange configuration loaded and private REST client initialized with valid credentials"
            )
            
            # Test account balance
            await self.test_runner.run_test_with_timeout(
                self.test_get_account_balance,
                "account_balance_test",
                TestCategory.REST_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Account balances retrieved successfully with proper structure"
            )
            
            # Test asset balance
            await self.test_runner.run_test_with_timeout(
                self.test_get_asset_balance,
                "asset_balance_test",
                TestCategory.REST_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Specific asset balance retrieved (may be zero or null)"
            )
            
            # Test open orders
            await self.test_runner.run_test_with_timeout(
                self.test_get_open_orders,
                "open_orders_test",
                TestCategory.REST_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Open orders list retrieved (may be empty)"
            )
            
            # Test order status (expects failure)
            await self.test_runner.run_test_with_timeout(
                self.test_get_order_status,
                "order_status_test",
                TestCategory.REST_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Order status query fails appropriately for non-existent order"
            )
            
            # Test order placement (expects failure)
            await self.test_runner.run_test_with_timeout(
                self.test_place_order_simulation,
                "place_order_test",
                TestCategory.REST_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Order placement fails appropriately due to validation (insufficient funds, invalid price, etc.)"
            )
            
            # Test order cancellation (expects failure)
            await self.test_runner.run_test_with_timeout(
                self.test_cancel_order_simulation,
                "cancel_order_test",
                TestCategory.REST_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Order cancellation fails appropriately for non-existent order"
            )
            
        finally:
            # Always cleanup
            await self.teardown()


async def main():
    """Main entry point for AI agent integration testing."""
    parser = argparse.ArgumentParser(description="REST Private API Integration Test for AI Agents")
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
    
    # Create test suite
    test_suite = RestPrivateIntegrationTest(args.exchange)
    
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
async def test_mexc_rest_private_integration():
    """Test MEXC REST private API integration."""
    test_suite = RestPrivateIntegrationTest("mexc")
    try:
        await test_suite.run_all_tests(timeout_seconds=30)
        report = test_suite.test_runner.generate_report()
        assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary}"
    except Exception as e:
        pytest.fail(f"MEXC integration test failed: {str(e)}")

@pytest.mark.asyncio
async def test_gateio_rest_private_integration():
    """Test Gate.io REST private API integration."""
    test_suite = RestPrivateIntegrationTest("gateio")
    try:
        await test_suite.run_all_tests(timeout_seconds=30)
        report = test_suite.test_runner.generate_report()
        assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary}"
    except Exception as e:
        pytest.fail(f"Gate.io integration test failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())