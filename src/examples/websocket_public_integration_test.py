"""
AI-Agent WebSocket Public API Integration Test

Automated integration testing for public WebSocket functionality across exchanges.
Outputs structured JSON results for AI agent consumption with standardized test outcomes,
performance metrics, and real-time data validation.

Usage:
    python src/examples/websocket_public_integration_test.py mexc
    python src/examples/websocket_public_integration_test.py gateio
    python src/examples/websocket_public_integration_test.py mexc --output results.json
    python src/examples/websocket_public_integration_test.py gateio --timeout 60 --monitor-time 20

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

from exchanges.structs.common import Symbol, OrderBook, Trade
from exchanges.structs.types import AssetName
from config.config_manager import HftConfig
from exchanges.transport_factory import create_websocket_client, create_public_handlers
from exchanges.structs import ExchangeEnum
from examples.integration_test_framework import (
    IntegrationTestRunner, TestCategory, TestStatus, EXIT_CODE_SUCCESS, EXIT_CODE_FAILED_TESTS, EXIT_CODE_ERROR,
    EXIT_CODE_CONFIG_ERROR
)


class WebSocketDataCollector:
    """Collects and validates WebSocket data for testing."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.orderbook_updates = {}
        self.trade_updates = {}
        self.update_counts = {}
        self.error_count = 0
        self.connection_events = []
        
    async def handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """Handle orderbook updates and collect metrics."""
        symbol_key = f"{symbol.base}/{symbol.quote}"
        
        # Store latest orderbook
        self.orderbook_updates[symbol_key] = {
            "timestamp": orderbook.timestamp,
            "bids_count": len(orderbook.bids),
            "asks_count": len(orderbook.asks),
            "best_bid": orderbook.bids[0].price if orderbook.bids else None,
            "best_ask": orderbook.asks[0].price if orderbook.asks else None,
            "spread": (orderbook.asks[0].price - orderbook.bids[0].price) if orderbook.bids and orderbook.asks else None
        }
        
        # Track update counts
        if symbol_key not in self.update_counts:
            self.update_counts[symbol_key] = {"orderbook": 0, "trades": 0}
        self.update_counts[symbol_key]["orderbook"] += 1
    
    async def handle_trades_update(self, symbol: Symbol, trades: List[Trade]) -> None:
        """Handle trade updates and collect metrics."""
        symbol_key = f"{symbol.base}/{symbol.quote}"
        
        # Store latest trades
        if symbol_key not in self.trade_updates:
            self.trade_updates[symbol_key] = []
        
        # Add new trades
        for trade in trades:
            self.trade_updates[symbol_key].append({
                "price": trade.price,
                "quantity": trade.quantity,
                "side": trade.side.name,
                "timestamp": trade.timestamp,
                "is_maker": trade.is_maker
            })
        
        # Keep only last 100 trades
        if len(self.trade_updates[symbol_key]) > 100:
            self.trade_updates[symbol_key] = self.trade_updates[symbol_key][-100:]
        
        # Track update counts
        if symbol_key not in self.update_counts:
            self.update_counts[symbol_key] = {"orderbook": 0, "trades": 0}
        self.update_counts[symbol_key]["trades"] += len(trades)
    
    def handle_state_change(self, state: str) -> None:
        """Handle WebSocket state changes."""
        self.connection_events.append({
            "timestamp": time.time(),
            "event": "state_change",
            "state": state
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of collected data."""
        total_orderbook_updates = sum(
            counts["orderbook"] for counts in self.update_counts.values()
        )
        total_trade_updates = sum(
            counts["trades"] for counts in self.update_counts.values()
        )
        
        return {
            "symbols_with_orderbook_data": len(self.orderbook_updates),
            "symbols_with_trade_data": len(self.trade_updates),
            "total_orderbook_updates": total_orderbook_updates,
            "total_trade_updates": total_trade_updates,
            "connection_events": len(self.connection_events),
            "error_count": self.error_count
        }


class WebSocketPublicIntegrationTest:
    """WebSocket Public API integration test suite for AI agents."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.websocket = None
        self.data_collector = WebSocketDataCollector(exchange_name)
        self.test_runner = IntegrationTestRunner(
            exchange=self.exchange_name,
            test_suite="WEBSOCKET_PUBLIC_API"
        )
        
    async def setup(self) -> Dict[str, Any]:
        """Setup WebSocket connection for testing."""
        try:
            config_manager = HftConfig()
            config = config_manager.get_exchange_config(self.exchange_name.lower())
            exchange_enum = ExchangeEnum(self.exchange_name)
            
            # Create handler object using factory
            handlers = create_public_handlers(
                orderbook_diff_handler=self.data_collector.handle_orderbook_update,
                trades_handler=self.data_collector.handle_trades_update
            )
            
            # Create WebSocket instance using factory
            self.websocket = create_websocket_client(
                exchange=exchange_enum,
                config=config,
                handlers=handlers,
                is_private=False
            )
            
            return {
                "setup_successful": True,
                "websocket_class": type(self.websocket).__name__,
                "config_loaded": True,
                "handlers_configured": True
            }
        except Exception as e:
            raise ConnectionError(f"Failed to setup {self.exchange_name} WebSocket: {str(e)}")
    
    async def teardown(self) -> None:
        """Clean up WebSocket resources."""
        if self.websocket:
            await self.websocket.close()
    
    async def test_connection_establishment(self) -> Dict[str, Any]:
        """Test WebSocket connection establishment."""
        start_time = time.time()
        
        try:
            # Test symbols for connection
            test_symbols = [
                Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False),
                Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=False)
            ]
            
            # Initialize connection
            await self.websocket.initialize(test_symbols)
            execution_time = (time.time() - start_time) * 1000
            
            # Wait a moment for connection to stabilize
            await asyncio.sleep(2)
            
            # Check connection status
            is_connected = self.websocket.is_connected()
            
            return {
                "connection_established": is_connected,
                "test_symbols_count": len(test_symbols),
                "test_symbols": [f"{s.base}/{s.quote}" for s in test_symbols],
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "connection_time_acceptable": execution_time < 10000  # 10 seconds max
            }
        except Exception as e:
            raise ConnectionError(f"WebSocket connection failed: {str(e)}")
    
    async def test_data_reception(self, monitor_seconds: int = 15) -> Dict[str, Any]:
        """Test real-time data reception."""
        start_time = time.time()
        
        try:
            # Monitor WebSocket for specified duration
            await asyncio.sleep(monitor_seconds)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Get data summary
            summary = self.data_collector.get_summary()
            
            # Validate data quality
            has_orderbook_data = summary["symbols_with_orderbook_data"] > 0
            has_trade_data = summary["symbols_with_trade_data"] > 0
            has_any_data = has_orderbook_data or has_trade_data
            
            # Check data freshness (orderbooks should be recent)
            recent_data = True
            current_time = time.time() * 1000  # Convert to milliseconds
            
            for symbol_key, orderbook in self.data_collector.orderbook_updates.items():
                if orderbook["timestamp"] > 0:
                    age_ms = current_time - orderbook["timestamp"]
                    if age_ms > 60000:  # More than 1 minute old
                        recent_data = False
                        break
            
            return {
                "monitor_duration_seconds": monitor_seconds,
                "has_orderbook_data": has_orderbook_data,
                "has_trade_data": has_trade_data,
                "has_any_data": has_any_data,
                "data_freshness_ok": recent_data,
                "symbols_with_orderbook_data": summary["symbols_with_orderbook_data"],
                "symbols_with_trade_data": summary["symbols_with_trade_data"],
                "total_orderbook_updates": summary["total_orderbook_updates"],
                "total_trade_updates": summary["total_trade_updates"],
                "execution_time_ms": execution_time,
                "data_points_received": summary["total_orderbook_updates"] + summary["total_trade_updates"],
                "error_count": summary["error_count"]
            }
        except Exception as e:
            raise ValueError(f"Data reception monitoring failed: {str(e)}")
    
    async def test_orderbook_data_quality(self) -> Dict[str, Any]:
        """Test orderbook data quality and structure."""
        start_time = time.time()
        
        try:
            # Analyze collected orderbook data
            orderbook_quality_results = []
            
            for symbol_key, orderbook_data in self.data_collector.orderbook_updates.items():
                quality_check = {
                    "symbol": symbol_key,
                    "has_timestamp": orderbook_data["timestamp"] > 0,
                    "has_bids": orderbook_data["bids_count"] > 0,
                    "has_asks": orderbook_data["asks_count"] > 0,
                    "has_valid_spread": orderbook_data["spread"] is not None and orderbook_data["spread"] >= 0,
                    "best_bid": orderbook_data["best_bid"],
                    "best_ask": orderbook_data["best_ask"],
                    "spread": orderbook_data["spread"],
                    "bids_count": orderbook_data["bids_count"],
                    "asks_count": orderbook_data["asks_count"]
                }
                
                # Overall quality score
                quality_checks = [
                    quality_check["has_timestamp"],
                    quality_check["has_bids"],
                    quality_check["has_asks"],
                    quality_check["has_valid_spread"]
                ]
                quality_check["quality_score"] = sum(quality_checks) / len(quality_checks)
                
                orderbook_quality_results.append(quality_check)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Calculate overall quality metrics
            symbols_analyzed = len(orderbook_quality_results)
            avg_quality_score = (
                sum(result["quality_score"] for result in orderbook_quality_results) / symbols_analyzed
                if symbols_analyzed > 0 else 0
            )
            
            return {
                "symbols_analyzed": symbols_analyzed,
                "average_quality_score": avg_quality_score,
                "quality_details": orderbook_quality_results[:3],  # First 3 symbols
                "execution_time_ms": execution_time,
                "high_quality_data": avg_quality_score >= 0.8
            }
        except Exception as e:
            raise ValueError(f"Orderbook quality analysis failed: {str(e)}")
    
    async def test_trade_data_quality(self) -> Dict[str, Any]:
        """Test trade data quality and structure."""
        start_time = time.time()
        
        try:
            # Analyze collected trade data
            trade_quality_results = []
            
            for symbol_key, trades_list in self.data_collector.trade_updates.items():
                if trades_list:
                    recent_trades = trades_list[-5:]  # Last 5 trades
                    
                    quality_check = {
                        "symbol": symbol_key,
                        "trades_count": len(trades_list),
                        "has_recent_trades": len(recent_trades) > 0,
                        "sample_trades": []
                    }
                    
                    # Analyze recent trades
                    valid_trades = 0
                    for trade in recent_trades:
                        is_valid = all([
                            trade["price"] > 0,
                            trade["amount"] > 0,
                            trade["timestamp"] > 0,
                            trade["side"] in ["BUY", "SELL"]
                        ])
                        
                        if is_valid:
                            valid_trades += 1
                        
                        quality_check["sample_trades"].append({
                            "price": trade["price"],
                            "amount": trade["amount"],
                            "side": trade["side"],
                            "is_valid": is_valid
                        })
                    
                    quality_check["valid_trades_ratio"] = valid_trades / len(recent_trades) if recent_trades else 0
                    trade_quality_results.append(quality_check)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Calculate overall trade quality metrics
            symbols_analyzed = len(trade_quality_results)
            avg_validity_ratio = (
                sum(result["valid_trades_ratio"] for result in trade_quality_results) / symbols_analyzed
                if symbols_analyzed > 0 else 0
            )
            
            return {
                "symbols_with_trades": symbols_analyzed,
                "average_validity_ratio": avg_validity_ratio,
                "trade_details": trade_quality_results[:2],  # First 2 symbols
                "execution_time_ms": execution_time,
                "high_quality_trades": avg_validity_ratio >= 0.9
            }
        except Exception as e:
            raise ValueError(f"Trade quality analysis failed: {str(e)}")
    
    async def test_performance_metrics(self) -> Dict[str, Any]:
        """Test WebSocket performance metrics."""
        start_time = time.time()
        
        try:
            # Get WebSocket performance metrics
            metrics = self.websocket.get_performance_metrics()
            execution_time = (time.time() - start_time) * 1000
            
            # Analyze performance data
            connection_uptime = metrics.get("connection_uptime_seconds", 0)
            messages_processed = metrics.get("messages_processed", 0)
            error_count = metrics.get("error_count", 0)
            connection_state = metrics.get("connection_state", "Unknown")
            
            # Calculate performance indicators
            uptime_acceptable = connection_uptime >= 10  # At least 10 seconds
            error_rate = error_count / max(messages_processed, 1)
            low_error_rate = error_rate <= 0.05  # Less than 5% error rate
            
            return {
                "connection_state": connection_state,
                "connection_uptime_seconds": connection_uptime,
                "messages_processed": messages_processed,
                "error_count": error_count,
                "error_rate": error_rate,
                "uptime_acceptable": uptime_acceptable,
                "low_error_rate": low_error_rate,
                "performance_good": uptime_acceptable and low_error_rate,
                "execution_time_ms": execution_time
            }
        except Exception as e:
            raise ValueError(f"Performance metrics collection failed: {str(e)}")
    
    async def run_all_tests(self, timeout_seconds: int = 30, monitor_seconds: int = 15) -> None:
        """Run complete WebSocket public API test suite."""
        try:
            # Setup
            await self.test_runner.run_test_with_timeout(
                self.setup,
                "websocket_setup",
                TestCategory.CONFIGURATION,
                timeout_seconds=10,
                expected_behavior="WebSocket configuration loaded and client initialized"
            )
            
            # Test connection establishment
            await self.test_runner.run_test_with_timeout(
                self.test_connection_establishment,
                "connection_test",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="WebSocket connection established successfully with test symbols"
            )
            
            # Test data reception
            await self.test_runner.run_test_with_timeout(
                self.test_data_reception,
                "data_reception_test",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=monitor_seconds + 10,
                expected_behavior="Real-time market data received for subscribed symbols",
                monitor_seconds=monitor_seconds
            )
            
            # Test orderbook data quality
            await self.test_runner.run_test_with_timeout(
                self.test_orderbook_data_quality,
                "orderbook_quality_test",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Orderbook data has valid structure with proper bids/asks ordering"
            )
            
            # Test trade data quality
            await self.test_runner.run_test_with_timeout(
                self.test_trade_data_quality,
                "trade_quality_test",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Trade data has valid structure with required fields"
            )
            
            # Test performance metrics
            await self.test_runner.run_test_with_timeout(
                self.test_performance_metrics,
                "performance_test",
                TestCategory.PERFORMANCE,
                timeout_seconds=timeout_seconds,
                expected_behavior="WebSocket maintains good performance with low error rate"
            )
            
        finally:
            # Always cleanup
            await self.teardown()


async def main():
    """Main entry point for AI agent integration testing."""
    parser = argparse.ArgumentParser(description="WebSocket Public API Integration Test for AI Agents")
    parser.add_argument("exchange", nargs="?", default="mexc", help="Exchange name (mexc, gateio) - defaults to mexc")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Test timeout in seconds")
    parser.add_argument("--monitor-time", "-m", type=int, default=15, help="Data monitoring duration in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Validate exchange
    supported_exchanges = ["mexc", "gateio"]
    if args.exchange.lower() not in supported_exchanges:
        print(f"Error: Unsupported exchange '{args.exchange}'. Supported: {supported_exchanges}")
        sys.exit(EXIT_CODE_CONFIG_ERROR)
    
    # Convert to ExchangeEnum
    from exchanges.utils.exchange_utils import get_exchange_enum
    exchange_enum = get_exchange_enum(args.exchange)
    
    # Create test suite
    test_suite = WebSocketPublicIntegrationTest(exchange_enum.value)
    
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


# Pytest test functions
import pytest

@pytest.mark.asyncio
async def test_mexc_websocket_public_integration():
    """Test MEXC WebSocket public API integration."""
    test_suite = WebSocketPublicIntegrationTest("mexc")
    try:
        await test_suite.run_all_tests(timeout_seconds=30, monitor_seconds=15)
        report = test_suite.test_runner.generate_report()
        assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary_metrics}"
    except Exception as e:
        pytest.fail(f"MEXC WebSocket public integration test failed: {str(e)}")

@pytest.mark.asyncio
async def test_gateio_websocket_public_integration():
    """Test Gate.io WebSocket public API integration."""
    test_suite = WebSocketPublicIntegrationTest("gateio")
    try:
        await test_suite.run_all_tests(timeout_seconds=30, monitor_seconds=15)
        report = test_suite.test_runner.generate_report()
        assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary_metrics}"
    except Exception as e:
        pytest.fail(f"Gate.io WebSocket public integration test failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())