"""
AI-Agent WebSocket Private API Integration Test

Automated integration testing for private WebSocket functionality across exchanges.
Outputs structured JSON results for AI agent consumption with standardized test outcomes,
performance metrics, and real-time private data validation.

Requires valid API credentials for authentication.

Usage:
    python src/examples/websocket_private_integration_test.py mexc
    python src/examples/websocket_private_integration_test.py gateio
    python src/examples/websocket_private_integration_test.py mexc --output results.json
    python src/examples/websocket_private_integration_test.py gateio --timeout 60 --monitor-time 20

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
from typing import Dict, Any, List

from structs.exchange import Symbol, AssetName, Order, AssetBalance, Trade
from core.config.config_manager import get_exchange_config
from examples.utils.ws_api_factory import get_exchange_websocket_classes
from integration_test_framework import (
    IntegrationTestRunner, TestCategory, TestStatus, TestMetrics,
    EXIT_CODE_SUCCESS, EXIT_CODE_FAILED_TESTS, EXIT_CODE_ERROR, 
    EXIT_CODE_TIMEOUT, EXIT_CODE_CONFIG_ERROR
)


class PrivateWebSocketDataCollector:
    """Collects and validates private WebSocket data for testing."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.balance_updates = []
        self.order_updates = []
        self.trade_updates = []
        self.connection_events = []
        self.error_count = 0
        self.latest_balances = {}
        
    async def handle_balance_update(self, balance_data) -> None:
        """Handle balance updates and collect metrics."""
        self.balance_updates.append({
            "timestamp": time.time(),
            "data": balance_data,
            "data_type": type(balance_data).__name__
        })
        
        # Store latest balance data
        if isinstance(balance_data, AssetBalance):
            self.latest_balances[balance_data.asset] = {
                "free": balance_data.free,
                "locked": balance_data.locked,
                "total": balance_data.total,
                "timestamp": time.time()
            }
        elif isinstance(balance_data, dict):
            # Handle dict format balance updates
            if 'balances' in balance_data:
                for balance in balance_data['balances']:
                    asset = balance.get('asset', 'Unknown')
                    self.latest_balances[asset] = {
                        "free": float(balance.get('free', 0)),
                        "locked": float(balance.get('locked', 0)),
                        "total": float(balance.get('free', 0)) + float(balance.get('locked', 0)),
                        "timestamp": time.time()
                    }
    
    async def handle_order_update(self, order_data) -> None:
        """Handle order updates and collect metrics."""
        self.order_updates.append({
            "timestamp": time.time(),
            "data": order_data,
            "data_type": type(order_data).__name__
        })
    
    async def handle_trade_update(self, trade_data) -> None:
        """Handle trade updates and collect metrics."""
        self.trade_updates.append({
            "timestamp": time.time(),
            "data": trade_data,
            "data_type": type(trade_data).__name__
        })
    
    def handle_state_change(self, state: str) -> None:
        """Handle WebSocket state changes."""
        self.connection_events.append({
            "timestamp": time.time(),
            "event": "state_change",
            "state": state
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of collected private data."""
        return {
            "balance_updates": len(self.balance_updates),
            "order_updates": len(self.order_updates),
            "trade_updates": len(self.trade_updates),
            "connection_events": len(self.connection_events),
            "error_count": self.error_count,
            "assets_with_balance_data": len(self.latest_balances)
        }


class WebSocketPrivateIntegrationTest:
    """WebSocket Private API integration test suite for AI agents."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.websocket = None
        self.data_collector = PrivateWebSocketDataCollector(exchange_name)
        self.test_runner = IntegrationTestRunner(
            exchange=self.exchange_name,
            test_suite="WEBSOCKET_PRIVATE_API"
        )
        
    async def setup(self) -> Dict[str, Any]:
        """Setup private WebSocket connection with authentication."""
        try:
            config = get_exchange_config(self.exchange_name)
            
            # Verify credentials are available
            if not config.credentials.api_key or not config.credentials.secret_key:
                raise ValueError(f"{self.exchange_name} API credentials are required for private WebSocket testing")
            
            # Get WebSocket and REST classes
            websocket_class, private_rest_class = get_exchange_websocket_classes(
                self.exchange_name, is_private=True
            )
            
            # Create private REST client for WebSocket initialization
            private_rest = private_rest_class(config) if private_rest_class else None
            
            # Create WebSocket instance with data handlers
            if private_rest:
                self.websocket = websocket_class(
                    private_rest_client=private_rest,
                    config=config,
                    balance_handler=self.data_collector.handle_balance_update,
                    order_handler=self.data_collector.handle_order_update,
                    trade_handler=self.data_collector.handle_trade_update
                )
            else:
                # Some exchanges might not need REST client
                self.websocket = websocket_class(
                    config=config,
                    balance_handler=self.data_collector.handle_balance_update,
                    order_handler=self.data_collector.handle_order_update,
                    trade_handler=self.data_collector.handle_trade_update
                )
            
            return {
                "setup_successful": True,
                "websocket_class": websocket_class.__name__,
                "config_loaded": True,
                "credentials_configured": True,
                "api_key_preview": config.credentials.api_key[:8] + "..." if config.credentials.api_key else None,
                "handlers_configured": True,
                "private_rest_available": private_rest is not None
            }
        except Exception as e:
            raise ConnectionError(f"Failed to setup {self.exchange_name} private WebSocket: {str(e)}")
    
    async def teardown(self) -> None:
        """Clean up WebSocket resources."""
        if self.websocket:
            await self.websocket.close()
    
    async def test_authentication_and_connection(self) -> Dict[str, Any]:
        """Test WebSocket authentication and connection establishment."""
        start_time = time.time()
        
        try:
            # Initialize private WebSocket connection
            await self.websocket.initialize([])  # Empty list for private channels
            execution_time = (time.time() - start_time) * 1000
            
            # Wait a moment for connection to stabilize
            await asyncio.sleep(3)
            
            # Check connection status
            is_connected = self.websocket.is_connected()
            
            return {
                "authentication_successful": is_connected,
                "connection_established": is_connected,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "connection_time_acceptable": execution_time < 15000  # 15 seconds max for auth
            }
        except Exception as e:
            if "authentication" in str(e).lower() or "unauthorized" in str(e).lower():
                raise PermissionError(f"Authentication failed: {str(e)}")
            raise ConnectionError(f"Private WebSocket connection failed: {str(e)}")
    
    async def test_private_data_monitoring(self, monitor_seconds: int = 20) -> Dict[str, Any]:
        """Test private data reception monitoring."""
        start_time = time.time()
        
        try:
            # Monitor WebSocket for private data
            await asyncio.sleep(monitor_seconds)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Get data summary
            summary = self.data_collector.get_summary()
            
            # Analyze data reception
            has_balance_updates = summary["balance_updates"] > 0
            has_order_updates = summary["order_updates"] > 0
            has_trade_updates = summary["trade_updates"] > 0
            has_any_private_data = has_balance_updates or has_order_updates or has_trade_updates
            
            return {
                "monitor_duration_seconds": monitor_seconds,
                "has_balance_updates": has_balance_updates,
                "has_order_updates": has_order_updates,
                "has_trade_updates": has_trade_updates,
                "has_any_private_data": has_any_private_data,
                "balance_updates_count": summary["balance_updates"],
                "order_updates_count": summary["order_updates"],
                "trade_updates_count": summary["trade_updates"],
                "assets_with_balance_data": summary["assets_with_balance_data"],
                "execution_time_ms": execution_time,
                "data_points_received": summary["balance_updates"] + summary["order_updates"] + summary["trade_updates"],
                "error_count": summary["error_count"],
                "note": "Private data only appears during account activity (trading, deposits, withdrawals, etc.)"
            }
        except Exception as e:
            raise ValueError(f"Private data monitoring failed: {str(e)}")
    
    async def test_balance_data_quality(self) -> Dict[str, Any]:
        """Test balance data quality and structure."""
        start_time = time.time()
        
        try:
            # Analyze collected balance data
            balance_quality_results = []
            
            for update in self.data_collector.balance_updates[-5:]:  # Last 5 updates
                data = update["data"]
                quality_check = {
                    "timestamp": update["timestamp"],
                    "data_type": update["data_type"],
                    "is_structured_type": isinstance(data, AssetBalance),
                    "is_dict_type": isinstance(data, dict),
                    "has_required_fields": False,
                    "sample_data": None
                }
                
                # Check data structure
                if isinstance(data, AssetBalance):
                    quality_check["has_required_fields"] = all([
                        hasattr(data, 'asset'),
                        hasattr(data, 'free'),
                        hasattr(data, 'locked'),
                        hasattr(data, 'total')
                    ])
                    quality_check["sample_data"] = {
                        "asset": data.asset,
                        "free": data.free,
                        "locked": data.locked,
                        "total": data.total
                    }
                elif isinstance(data, dict):
                    quality_check["has_required_fields"] = 'balances' in data or all([
                        key in data for key in ['asset', 'free', 'locked']
                    ])
                    quality_check["sample_data"] = str(data)[:200]  # First 200 chars
                
                balance_quality_results.append(quality_check)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Calculate quality metrics
            updates_analyzed = len(balance_quality_results)
            structured_updates = sum(1 for r in balance_quality_results if r["is_structured_type"])
            valid_updates = sum(1 for r in balance_quality_results if r["has_required_fields"])
            
            return {
                "updates_analyzed": updates_analyzed,
                "structured_updates": structured_updates,
                "valid_updates": valid_updates,
                "structure_ratio": structured_updates / max(updates_analyzed, 1),
                "validity_ratio": valid_updates / max(updates_analyzed, 1),
                "quality_details": balance_quality_results[:3],  # First 3 updates
                "execution_time_ms": execution_time,
                "high_quality_data": (valid_updates / max(updates_analyzed, 1)) >= 0.8 if updates_analyzed > 0 else True
            }
        except Exception as e:
            raise ValueError(f"Balance data quality analysis failed: {str(e)}")
    
    async def test_order_data_quality(self) -> Dict[str, Any]:
        """Test order data quality and structure."""
        start_time = time.time()
        
        try:
            # Analyze collected order data
            order_quality_results = []
            
            for update in self.data_collector.order_updates[-5:]:  # Last 5 updates
                data = update["data"]
                quality_check = {
                    "timestamp": update["timestamp"],
                    "data_type": update["data_type"],
                    "is_structured_type": isinstance(data, Order),
                    "is_dict_type": isinstance(data, dict),
                    "has_required_fields": False,
                    "sample_data": None
                }
                
                # Check data structure
                if isinstance(data, Order):
                    quality_check["has_required_fields"] = all([
                        hasattr(data, 'order_id'),
                        hasattr(data, 'symbol'),
                        hasattr(data, 'side'),
                        hasattr(data, 'order_type'),
                        hasattr(data, 'status')
                    ])
                    quality_check["sample_data"] = {
                        "order_id": data.order_id,
                        "symbol": f"{data.symbol.base}/{data.symbol.quote}",
                        "side": data.side.name,
                        "status": data.status.name,
                        "amount": data.amount
                    }
                elif isinstance(data, dict):
                    order_fields = ['orderId', 'order_id', 'symbol', 'side', 'status']
                    quality_check["has_required_fields"] = any(field in data for field in order_fields)
                    quality_check["sample_data"] = str(data)[:200]  # First 200 chars
                
                order_quality_results.append(quality_check)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Calculate quality metrics
            updates_analyzed = len(order_quality_results)
            structured_updates = sum(1 for r in order_quality_results if r["is_structured_type"])
            valid_updates = sum(1 for r in order_quality_results if r["has_required_fields"])
            
            return {
                "updates_analyzed": updates_analyzed,
                "structured_updates": structured_updates,
                "valid_updates": valid_updates,
                "structure_ratio": structured_updates / max(updates_analyzed, 1),
                "validity_ratio": valid_updates / max(updates_analyzed, 1),
                "quality_details": order_quality_results[:3],  # First 3 updates
                "execution_time_ms": execution_time,
                "high_quality_data": (valid_updates / max(updates_analyzed, 1)) >= 0.8 if updates_analyzed > 0 else True
            }
        except Exception as e:
            raise ValueError(f"Order data quality analysis failed: {str(e)}")
    
    async def test_connection_stability(self) -> Dict[str, Any]:
        """Test WebSocket connection stability and performance."""
        start_time = time.time()
        
        try:
            # Get WebSocket performance metrics
            metrics = self.websocket.get_performance_metrics()
            execution_time = (time.time() - start_time) * 1000
            
            # Analyze connection stability
            connection_uptime = metrics.get("connection_uptime_seconds", 0)
            messages_processed = metrics.get("messages_processed", 0)
            error_count = metrics.get("error_count", 0)
            connection_state = metrics.get("connection_state", "Unknown")
            
            # Calculate stability indicators
            uptime_acceptable = connection_uptime >= 15  # At least 15 seconds
            error_rate = error_count / max(messages_processed, 1)
            low_error_rate = error_rate <= 0.1  # Less than 10% error rate for private
            stable_connection = connection_state == "connected"
            
            return {
                "connection_state": connection_state,
                "connection_uptime_seconds": connection_uptime,
                "messages_processed": messages_processed,
                "error_count": error_count,
                "error_rate": error_rate,
                "uptime_acceptable": uptime_acceptable,
                "low_error_rate": low_error_rate,
                "stable_connection": stable_connection,
                "overall_stability": uptime_acceptable and low_error_rate and stable_connection,
                "execution_time_ms": execution_time
            }
        except Exception as e:
            raise ValueError(f"Connection stability analysis failed: {str(e)}")
    
    async def run_all_tests(self, timeout_seconds: int = 30, monitor_seconds: int = 20) -> None:
        """Run complete WebSocket private API test suite."""
        try:
            # Setup
            await self.test_runner.run_test_with_timeout(
                self.setup,
                "websocket_setup",
                TestCategory.CONFIGURATION,
                timeout_seconds=15,
                expected_behavior="Private WebSocket configuration loaded with valid credentials and client initialized"
            )
            
            # Test authentication and connection
            await self.test_runner.run_test_with_timeout(
                self.test_authentication_and_connection,
                "authentication_test",
                TestCategory.WEBSOCKET_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Private WebSocket authentication successful and connection established"
            )
            
            # Test private data monitoring
            await self.test_runner.run_test_with_timeout(
                self.test_private_data_monitoring,
                "private_data_monitoring_test",
                TestCategory.WEBSOCKET_PRIVATE,
                timeout_seconds=monitor_seconds + 10,
                expected_behavior="Private WebSocket monitors for account data (may be empty if no account activity)",
                monitor_seconds=monitor_seconds
            )
            
            # Test balance data quality
            await self.test_runner.run_test_with_timeout(
                self.test_balance_data_quality,
                "balance_quality_test",
                TestCategory.WEBSOCKET_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Balance data (if received) has valid structure with required fields"
            )
            
            # Test order data quality
            await self.test_runner.run_test_with_timeout(
                self.test_order_data_quality,
                "order_quality_test",
                TestCategory.WEBSOCKET_PRIVATE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Order data (if received) has valid structure with required fields"
            )
            
            # Test connection stability
            await self.test_runner.run_test_with_timeout(
                self.test_connection_stability,
                "stability_test",
                TestCategory.PERFORMANCE,
                timeout_seconds=timeout_seconds,
                expected_behavior="Private WebSocket maintains stable connection with low error rate"
            )
            
        finally:
            # Always cleanup
            await self.teardown()


async def main():
    """Main entry point for AI agent integration testing."""
    parser = argparse.ArgumentParser(description="WebSocket Private API Integration Test for AI Agents")
    parser.add_argument("exchange", help="Exchange name (mexc, gateio)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Test timeout in seconds")
    parser.add_argument("--monitor-time", "-m", type=int, default=20, help="Private data monitoring duration in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Validate exchange
    supported_exchanges = ["mexc", "gateio"]
    if args.exchange.lower() not in supported_exchanges:
        print(f"Error: Unsupported exchange '{args.exchange}'. Supported: {supported_exchanges}")
        sys.exit(EXIT_CODE_CONFIG_ERROR)
    
    # Create test suite
    test_suite = WebSocketPrivateIntegrationTest(args.exchange)
    
    try:
        # Run tests
        await test_suite.run_all_tests(
            timeout_seconds=args.timeout,
            monitor_seconds=args.monitor_time
        )
        
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


if __name__ == "__main__":
    asyncio.run(main())