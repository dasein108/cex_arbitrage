"""
Consolidated WebSocket Integration Test

Combines public and private WebSocket integration testing into a single comprehensive test suite.
Eliminates code duplication from separate websocket_public_integration_test.py and websocket_private_integration_test.py.

Usage:
    python src/examples/integration_tests/websocket_integration_test.py mexc
    python src/examples/integration_tests/websocket_integration_test.py gateio --include-private
    python src/examples/integration_tests/websocket_integration_test.py mexc --include-private --duration 30 --output results.json
"""

import asyncio
import sys
import argparse
import time
from typing import Dict, Any

from exchanges.exchange_factory import create_websocket_client, create_public_handlers
from utils.exchange_utils import get_exchange_enum

from ..base.integration_test_base import IntegrationTestBase, WebSocketIntegrationTestMixin
from ..integration_test_framework import TestCategory, TestStatus, EXIT_CODE_SUCCESS, EXIT_CODE_FAILED_TESTS, EXIT_CODE_ERROR, EXIT_CODE_CONFIG_ERROR
from ..utils.constants import DEFAULT_MONITOR_DURATION


class WebSocketIntegrationTest(IntegrationTestBase, WebSocketIntegrationTestMixin):
    """Consolidated WebSocket integration test suite for both public and private channels."""
    
    def __init__(self, exchange_name: str):
        super().__init__(exchange_name, "WEBSOCKET_CONSOLIDATED_API")
        self.include_private = False
        self.private_websocket_client = None
        self.monitor_duration = DEFAULT_MONITOR_DURATION
        
    async def setup_private_websocket(self) -> Dict[str, Any]:
        """Setup separate private WebSocket client for private tests."""
        try:
            # Verify credentials
            if not self.config.credentials.api_key or not self.config.credentials.secret_key:
                raise ValueError(f"{self.exchange_name} API credentials are required for private WebSocket testing")
            
            from exchanges.exchange_factory import create_websocket_client, create_private_handlers
            from utils.exchange_utils import get_exchange_enum
            
            exchange_enum = get_exchange_enum(self.exchange_name)
            
            # Setup private data handling
            self.setup_data_manager()
            
            handlers = create_private_handlers(
                order_handler=self._handle_order_update,
                balance_handler=self.data_manager.handle_balance_update,
                execution_handler=self._handle_private_trade_update
            )
            
            self.private_websocket_client = create_websocket_client(
                exchange=exchange_enum,
                is_private=True,
                config=self.config,
                handlers=handlers
            )
            
            return {
                "private_websocket_setup_successful": True,
                "private_websocket_class": type(self.private_websocket_client).__name__,
                "api_key_preview": f"{self.config.credentials.api_key[:8]}...",
                "handlers_configured": len([h for h in [handlers.order_handler, handlers.balance_handler, handlers.trade_handler] if h])
            }
            
        except Exception as e:
            raise ConnectionError(f"Failed to setup {self.exchange_name} private WebSocket: {str(e)}")
    
    async def teardown_private_websocket(self) -> None:
        """Clean up private WebSocket resources."""
        if self.private_websocket_client:
            await self.private_websocket_client.close()
            self.private_websocket_client = None
    
    # Public WebSocket Tests
    
    async def test_public_websocket_connection(self) -> Dict[str, Any]:
        """Test public WebSocket connection establishment."""
        start_time = time.time()
        
        try:
            # Setup data manager
            self.setup_data_manager()
            
            # Create public WebSocket client
            exchange_enum = get_exchange_enum(self.exchange_name)
            handlers = create_public_handlers(
                orderbook_diff_handler=self.data_manager.handle_orderbook_update,
                trades_handler=self.data_manager.handle_trade_update,
                book_ticker_handler=self.data_manager.handle_book_ticker_update
            )
            
            self.websocket_client = create_websocket_client(
                exchange=exchange_enum,
                is_private=False,
                config=self.config,
                handlers=handlers
            )
            
            performance = self.measure_performance(start_time)
            
            return {
                "connection_established": True,
                "websocket_class": type(self.websocket_client).__name__,
                "handlers_configured": 3,  # orderbook, trades, book_ticker
                "exchange": self.exchange_name,
                **performance
            }
            
        except Exception as e:
            raise ConnectionError(f"Public WebSocket connection failed: {str(e)}")
    
    async def test_public_websocket_subscriptions(self) -> Dict[str, Any]:
        """Test public WebSocket symbol subscriptions and initialization."""
        start_time = time.time()
        symbols = self.get_test_symbols()[:2]  # Use first 2 symbols for testing
        
        try:
            # Initialize with symbols
            await self.websocket_client.initialize(symbols)
            performance = self.measure_performance(start_time)
            
            # Get connection health
            health_data = {}
            if hasattr(self.websocket_client, 'get_websocket_health'):
                health_data = self.websocket_client.get_websocket_health()
            
            return {
                "symbols_subscribed": len(symbols),
                "subscription_symbols": [f"{s.base}/{s.quote}" for s in symbols],
                "initialization_successful": True,
                "websocket_health": health_data,
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"WebSocket subscription test failed: {str(e)}")
    
    async def test_public_market_data_streaming(self) -> Dict[str, Any]:
        """Test public market data streaming with comprehensive validation."""
        start_time = time.time()
        symbols = self.get_test_symbols()[:2]
        
        try:
            # Monitor for market data
            await asyncio.sleep(self.monitor_duration)
            
            # Get performance summary
            performance_summary = self.get_websocket_performance_summary()
            connection_metrics = performance_summary.get("connection_metrics", {})
            data_summary = performance_summary.get("data_summary", {})
            
            # Analyze received data
            orderbook_updates = data_summary.get("total_orderbook_updates", 0)
            trade_updates = data_summary.get("total_trade_updates", 0)
            book_ticker_updates = data_summary.get("total_book_ticker_updates", 0)
            total_updates = orderbook_updates + trade_updates + book_ticker_updates
            
            # Sample data validation
            sample_data = {}
            if symbols and self.data_manager:
                symbol = symbols[0]
                
                # Check orderbook data
                orderbook = self.data_manager.get_orderbook(symbol)
                if orderbook:
                    sample_data["latest_orderbook"] = {
                        "symbol": f"{symbol.base}/{symbol.quote}",
                        "bids_count": len(orderbook.bids),
                        "asks_count": len(orderbook.asks),
                        "has_valid_spread": len(orderbook.bids) > 0 and len(orderbook.asks) > 0 and orderbook.asks[0].price > orderbook.bids[0].price,
                        "timestamp": orderbook.timestamp
                    }
                
                # Check recent trades
                recent_trades = self.data_manager.get_trades(symbol, limit=3)
                if recent_trades:
                    sample_data["recent_trades"] = {
                        "symbol": f"{symbol.base}/{symbol.quote}",
                        "trade_count": len(recent_trades),
                        "latest_price": recent_trades[0].price if recent_trades else None,
                        "latest_side": recent_trades[0].side.name if recent_trades else None
                    }
                
                # Check book ticker
                book_ticker = self.data_manager.get_book_ticker(symbol)
                if book_ticker:
                    sample_data["book_ticker"] = {
                        "symbol": f"{symbol.base}/{symbol.quote}",
                        "bid_price": book_ticker.bid_price,
                        "ask_price": book_ticker.ask_price,
                        "spread": book_ticker.ask_price - book_ticker.bid_price if book_ticker.bid_price and book_ticker.ask_price else None
                    }
            
            performance = self.measure_performance(start_time)
            
            return {
                "monitor_duration_seconds": self.monitor_duration,
                "symbols_monitored": len(symbols),
                "connection_metrics": connection_metrics,
                "data_summary": data_summary,
                "total_updates_received": total_updates,
                "data_received": total_updates > 0,
                "sample_data": sample_data,
                "performance_acceptable": connection_metrics.get('error_count', 0) == 0,
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"Market data streaming test failed: {str(e)}")
    
    # Private WebSocket Tests (only run if include_private=True)
    
    async def test_private_websocket_connection(self) -> Dict[str, Any]:
        """Test private WebSocket connection with authentication."""
        start_time = time.time()
        
        try:
            # Initialize private connection
            await self.private_websocket_client.initialize([])
            performance = self.measure_performance(start_time)
            
            return {
                "private_connection_established": True,
                "websocket_class": type(self.private_websocket_client).__name__,
                "requires_authentication": True,
                "api_key_preview": f"{self.config.credentials.api_key[:8]}...",
                **performance
            }
            
        except Exception as e:
            raise ConnectionError(f"Private WebSocket connection failed: {str(e)}")
    
    async def test_private_account_streaming(self) -> Dict[str, Any]:
        """Test private account data streaming (orders, balances, trades)."""
        start_time = time.time()
        
        try:
            # Monitor for private account data
            await asyncio.sleep(self.monitor_duration)
            
            # Get performance summary
            performance_summary = self.get_websocket_performance_summary()
            connection_metrics = performance_summary.get("connection_metrics", {})
            data_summary = performance_summary.get("data_summary", {})
            
            # Analyze private data received
            balance_updates = data_summary.get("total_balance_updates", 0)
            order_updates = data_summary.get("total_order_updates", 0)
            private_trade_updates = data_summary.get("total_private_trade_updates", 0)
            total_private_updates = balance_updates + order_updates + private_trade_updates
            
            # Sample private data
            sample_private_data = {}
            if self.data_manager:
                # Check non-zero balances
                balances = self.data_manager.get_non_zero_balances()
                if balances:
                    sample_private_data["balances"] = {
                        "assets_with_balance": list(balances.keys())[:5],  # First 5 assets
                        "total_assets": len(balances)
                    }
            
            performance = self.measure_performance(start_time)
            
            return {
                "monitor_duration_seconds": self.monitor_duration,
                "connection_metrics": connection_metrics,
                "data_summary": data_summary,
                "total_private_updates": total_private_updates,
                "private_data_received": total_private_updates > 0,
                "sample_private_data": sample_private_data,
                "note": "Private messages only appear during account activity (trading, deposits, withdrawals)",
                "authentication_working": connection_metrics.get('connection_state') == 'connected',
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"Private account streaming test failed: {str(e)}")
    
    async def test_websocket_reliability(self) -> Dict[str, Any]:
        """Test WebSocket connection reliability and error handling."""
        start_time = time.time()
        
        try:
            # Get connection health for both public and private (if available)
            public_health = {}
            private_health = {}
            
            if self.websocket_client and hasattr(self.websocket_client, 'get_websocket_health'):
                public_health = self.websocket_client.get_websocket_health()
            
            if self.private_websocket_client and hasattr(self.private_websocket_client, 'get_websocket_health'):
                private_health = self.private_websocket_client.get_websocket_health()
            
            performance = self.measure_performance(start_time)
            
            # Calculate reliability metrics
            total_errors = (
                public_health.get('error_count', 0) + 
                private_health.get('error_count', 0)
            )
            
            total_messages = (
                public_health.get('messages_processed', 0) + 
                private_health.get('messages_processed', 0)
            )
            
            error_rate = (total_errors / total_messages) if total_messages > 0 else 0
            reliability_score = max(0, (1 - error_rate) * 100)
            
            return {
                "public_websocket_health": public_health,
                "private_websocket_health": private_health if self.include_private else "Not tested",
                "total_errors": total_errors,
                "total_messages": total_messages,
                "error_rate_percent": error_rate * 100,
                "reliability_score": reliability_score,
                "reliability_acceptable": reliability_score >= 95.0,
                **performance
            }
            
        except Exception as e:
            raise ValueError(f"WebSocket reliability test failed: {str(e)}")
    
    async def _handle_order_update(self, order) -> None:
        """Handle private order updates for testing."""
        if self.data_manager:
            self.data_manager.handle_connection_event("order_update", {
                "order_id": getattr(order, 'order_id', 'Unknown'),
                "status": getattr(order, 'status', 'Unknown')
            })
    
    async def _handle_private_trade_update(self, trade) -> None:
        """Handle private trade updates for testing."""
        if self.data_manager:
            self.data_manager.handle_connection_event("private_trade_update", trade)
    
    async def run_all_tests(self, timeout_seconds: int = 60) -> None:
        """Run complete WebSocket integration test suite."""
        try:
            # Setup public WebSocket
            await self.run_test_with_standard_validation(
                self.test_public_websocket_connection,
                "public_websocket_connection_test",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=30,
                expected_behavior="Public WebSocket connection established with handlers configured"
            )
            
            await self.run_test_with_standard_validation(
                self.test_public_websocket_subscriptions,
                "public_websocket_subscriptions_test",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=30,
                expected_behavior="WebSocket successfully subscribed to symbols and initialized"
            )
            
            await self.run_test_with_standard_validation(
                self.test_public_market_data_streaming,
                "public_market_data_streaming_test",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Market data streaming with orderbooks, trades, and book ticker updates"
            )
            
            # Private WebSocket Tests (only if requested)
            if self.include_private:
                await self.run_test_with_standard_validation(
                    self.setup_private_websocket,
                    "private_websocket_setup",
                    TestCategory.CONFIGURATION,
                    timeout_seconds=30,
                    expected_behavior="Private WebSocket setup with valid API credentials and handlers"
                )
                
                await self.run_test_with_standard_validation(
                    self.test_private_websocket_connection,
                    "private_websocket_connection_test",
                    TestCategory.WEBSOCKET_PRIVATE,
                    timeout_seconds=30,
                    expected_behavior="Private WebSocket connection established with authentication"
                )
                
                await self.run_test_with_standard_validation(
                    self.test_private_account_streaming,
                    "private_account_streaming_test",
                    TestCategory.WEBSOCKET_PRIVATE,
                    timeout_seconds=timeout_seconds,
                    expected_behavior="Private account data streaming (orders, balances, trades)"
                )
            
            # Reliability test for both connections
            await self.run_test_with_standard_validation(
                self.test_websocket_reliability,
                "websocket_reliability_test",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=10,
                expected_behavior="WebSocket connections maintain reliability with minimal errors"
            )
            
        finally:
            # Always cleanup
            await self.teardown()
            await self.teardown_private_websocket()


async def main():
    """Main entry point for consolidated WebSocket integration testing."""
    parser = argparse.ArgumentParser(description="Consolidated WebSocket Integration Test")
    parser.add_argument("exchange", nargs="?", default="mexc", 
                       help="Exchange name (mexc, gateio)")
    parser.add_argument("--include-private", action="store_true",
                       help="Include private WebSocket tests (requires credentials)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--duration", "-d", type=int, default=DEFAULT_MONITOR_DURATION,
                       help="Monitor duration in seconds for streaming tests")
    parser.add_argument("--timeout", "-t", type=int, default=60,
                       help="Test timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Validate exchange
    supported_exchanges = ["mexc", "gateio"]
    if args.exchange.lower() not in supported_exchanges:
        print(f"Error: Unsupported exchange '{args.exchange}'. Supported: {supported_exchanges}")
        sys.exit(EXIT_CODE_CONFIG_ERROR)
    
    # Create test suite
    test_suite = WebSocketIntegrationTest(args.exchange.upper())
    test_suite.include_private = args.include_private
    test_suite.monitor_duration = args.duration
    
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