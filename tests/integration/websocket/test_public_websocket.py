"""
WebSocket Public API Integration Tests

Comprehensive integration testing for public WebSocket functionality across exchanges.
Tests real-time data streaming, connection stability, and HFT performance requirements.

Usage:
    pytest tests/integration/websocket/test_public_websocket.py
    pytest tests/integration/websocket/test_public_websocket.py::test_mexc_websocket -v
    RUN_INTEGRATION_TESTS=1 pytest tests/integration/websocket/test_public_websocket.py --tb=short
"""

import pytest
import asyncio
import time
from typing import Dict, Any, List
from collections import defaultdict

from exchanges.structs.common import Symbol, OrderBook, Trade
from exchanges.structs.types import AssetName
from config.config_manager import HftConfig
from exchanges.exchange_factory import create_websocket_client, create_public_handlers
from exchanges.structs import ExchangeEnum
from tests.integration_test_framework import (
    IntegrationTestRunner, TestCategory, TestStatus
)


class WebSocketDataCollector:
    """Collects and validates WebSocket data for testing."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.orderbook_updates = {}
        self.trade_updates = defaultdict(list)
        self.update_counts = defaultdict(lambda: {"orderbook": 0, "trades": 0})
        self.error_count = 0
        self.connection_events = []
        self.first_message_time = None
        self.last_message_time = None
        self.message_timestamps = []
        
    async def handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """Handle orderbook updates and collect metrics."""
        current_time = time.time()
        symbol_key = f"{symbol.base}/{symbol.quote}"
        
        if self.first_message_time is None:
            self.first_message_time = current_time
        self.last_message_time = current_time
        self.message_timestamps.append(current_time)
        
        # Validate orderbook structure
        is_valid = all([
            len(orderbook.bids) > 0,
            len(orderbook.asks) > 0,
            orderbook.timestamp > 0,
            all(bid.price > 0 and bid.quantity > 0 for bid in orderbook.bids[:5]),
            all(ask.price > 0 and ask.quantity > 0 for ask in orderbook.asks[:5])
        ])
        
        # Store latest orderbook with validation
        self.orderbook_updates[symbol_key] = {
            "timestamp": orderbook.timestamp,
            "bids_count": len(orderbook.bids),
            "asks_count": len(orderbook.asks),
            "best_bid": orderbook.bids[0].price if orderbook.bids else None,
            "best_ask": orderbook.asks[0].price if orderbook.asks else None,
            "spread": (orderbook.asks[0].price - orderbook.bids[0].price) if orderbook.bids and orderbook.asks else None,
            "is_valid": is_valid,
            "received_at": current_time
        }
        
        self.update_counts[symbol_key]["orderbook"] += 1
    
    async def handle_trades_update(self, symbol: Symbol, trades: List[Trade]) -> None:
        """Handle trade updates and collect metrics."""
        current_time = time.time()
        symbol_key = f"{symbol.base}/{symbol.quote}"
        
        if self.first_message_time is None:
            self.first_message_time = current_time
        self.last_message_time = current_time
        self.message_timestamps.append(current_time)
        
        # Process and validate trades
        for trade in trades:
            is_valid = all([
                trade.price > 0,
                trade.quantity > 0,
                trade.timestamp > 0,
                hasattr(trade, 'side'),
                hasattr(trade, 'is_maker')
            ])
            
            trade_data = {
                "price": trade.price,
                "quantity": trade.quantity,
                "side": trade.side.name,
                "timestamp": trade.timestamp,
                "is_maker": trade.is_maker,
                "is_valid": is_valid,
                "received_at": current_time
            }
            
            self.trade_updates[symbol_key].append(trade_data)
        
        # Keep only last 50 trades per symbol
        if len(self.trade_updates[symbol_key]) > 50:
            self.trade_updates[symbol_key] = self.trade_updates[symbol_key][-50:]
        
        self.update_counts[symbol_key]["trades"] += len(trades)
    
    def handle_error(self, error: Exception) -> None:
        """Handle WebSocket errors."""
        self.error_count += 1
        self.connection_events.append({
            "timestamp": time.time(),
            "event": "error",
            "error_type": type(error).__name__,
            "error_message": str(error)
        })
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about collected data."""
        current_time = time.time()
        duration = (self.last_message_time - self.first_message_time) if self.first_message_time else 0
        
        # Calculate message rate
        total_messages = sum(
            counts["orderbook"] + counts["trades"] 
            for counts in self.update_counts.values()
        )
        message_rate = total_messages / duration if duration > 0 else 0
        
        # Calculate latency statistics
        latency_stats = {}
        if len(self.message_timestamps) > 1:
            intervals = [
                self.message_timestamps[i] - self.message_timestamps[i-1]
                for i in range(1, len(self.message_timestamps))
            ]
            if intervals:
                latency_stats = {
                    "min_interval_ms": min(intervals) * 1000,
                    "max_interval_ms": max(intervals) * 1000,
                    "avg_interval_ms": (sum(intervals) / len(intervals)) * 1000
                }
        
        return {
            "duration_seconds": duration,
            "total_messages": total_messages,
            "message_rate_per_second": message_rate,
            "symbols_with_data": len(self.update_counts),
            "orderbook_updates": sum(counts["orderbook"] for counts in self.update_counts.values()),
            "trade_updates": sum(counts["trades"] for counts in self.update_counts.values()),
            "error_count": self.error_count,
            "latency_stats": latency_stats,
            "data_quality": {
                "valid_orderbooks": sum(
                    1 for ob in self.orderbook_updates.values() 
                    if ob.get("is_valid", False)
                ),
                "valid_trades": sum(
                    sum(1 for trade in trades if trade.get("is_valid", False))
                    for trades in self.trade_updates.values()
                )
            }
        }


class WebSocketPublicIntegrationTest:
    """WebSocket public API integration test suite."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.websocket_client = None
        self.data_collector = WebSocketDataCollector(exchange_name)
        self.test_runner = IntegrationTestRunner(
            exchange=self.exchange_name,
            test_suite="WEBSOCKET_PUBLIC_API_V2"
        )
        
    async def setup(self, symbols: List[Symbol]) -> Dict[str, Any]:
        """Setup WebSocket connection for testing."""
        try:
            config_manager = HftConfig()
            config = config_manager.get_exchange_config(self.exchange_name.lower())
            
            # Create exchange enum
            if "mexc" in self.exchange_name.lower():
                exchange_enum = ExchangeEnum.MEXC_SPOT
            elif "gateio" in self.exchange_name.lower():
                exchange_enum = ExchangeEnum.GATEIO_SPOT
            else:
                raise ValueError(f"Unsupported exchange: {self.exchange_name}")
            
            # Create handlers
            handlers = create_public_handlers(
                book_ticker_handler=self._handle_book_ticker,
                orderbook_handler=self.data_collector.handle_orderbook_update,
                trades_handler=self.data_collector.handle_trades_update
            )
            
            # Create WebSocket client
            self.websocket_client = create_websocket_client(
                exchange=exchange_enum,
                config=config,
                is_private=False,
                handlers=handlers
            )
            
            # Import channel types
            from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
            channels = [
                PublicWebsocketChannelType.ORDERBOOK,
                PublicWebsocketChannelType.PUB_TRADE
            ]
            
            return {
                "setup_successful": True,
                "exchange": self.exchange_name,
                "symbols_count": len(symbols),
                "channels": [ch.value for ch in channels],
                "client_created": True
            }
            
        except Exception as e:
            raise ConnectionError(f"Failed to setup WebSocket for {self.exchange_name}: {str(e)}")
    
    async def _handle_book_ticker(self, *args) -> None:
        """Handle book ticker updates (if supported)."""
        # Convert to orderbook format if needed
        pass
    
    async def test_connection_stability(self, symbols: List[Symbol], duration_seconds: int = 30) -> Dict[str, Any]:
        """Test WebSocket connection stability and data flow."""
        start_time = time.perf_counter()
        
        try:
            # Initialize WebSocket
            from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
            channels = [
                PublicWebsocketChannelType.ORDERBOOK,
                PublicWebsocketChannelType.PUB_TRADE
            ]
            
            await self.websocket_client.initialize(symbols, channels)
            
            # Monitor data for specified duration
            await asyncio.sleep(duration_seconds)
            
            # Get statistics
            stats = self.data_collector.get_statistics()
            execution_time = (time.perf_counter() - start_time) * 1000
            
            return {
                "connection_duration_seconds": duration_seconds,
                "execution_time_ms": execution_time,
                "statistics": stats,
                "connection_stable": stats["error_count"] == 0,
                "data_received": stats["total_messages"] > 0,
                "message_rate_adequate": stats["message_rate_per_second"] > 0.1,
                "all_symbols_active": stats["symbols_with_data"] >= len(symbols),
                "network_requests": 1,  # WebSocket connection
                "data_points_received": stats["total_messages"],
                "hft_compliant": all([
                    stats["message_rate_per_second"] > 1.0,  # At least 1 msg/sec
                    stats["error_count"] == 0,
                    stats.get("latency_stats", {}).get("avg_interval_ms", 0) < 1000  # <1sec intervals
                ])
            }
            
        except Exception as e:
            raise ConnectionError(f"Connection stability test failed: {str(e)}")
    
    async def test_data_quality_validation(self, symbols: List[Symbol], duration_seconds: int = 15) -> Dict[str, Any]:
        """Test data quality and validation."""
        start_time = time.perf_counter()
        
        try:
            # Initialize and collect data
            from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
            channels = [
                PublicWebsocketChannelType.ORDERBOOK,
                PublicWebsocketChannelType.PUB_TRADE
            ]
            
            await self.websocket_client.initialize(symbols, channels)
            await asyncio.sleep(duration_seconds)
            
            stats = self.data_collector.get_statistics()
            execution_time = (time.perf_counter() - start_time) * 1000
            
            # Calculate data quality metrics
            total_orderbooks = stats["orderbook_updates"]
            total_trades = stats["trade_updates"]
            valid_orderbooks = stats["data_quality"]["valid_orderbooks"]
            valid_trades = stats["data_quality"]["valid_trades"]
            
            orderbook_quality = valid_orderbooks / max(total_orderbooks, 1)
            trade_quality = valid_trades / max(total_trades, 1)
            
            return {
                "test_duration_seconds": duration_seconds,
                "execution_time_ms": execution_time,
                "data_quality_metrics": {
                    "total_orderbook_updates": total_orderbooks,
                    "valid_orderbook_updates": valid_orderbooks,
                    "orderbook_quality_rate": orderbook_quality,
                    "total_trade_updates": total_trades,
                    "valid_trade_updates": valid_trades,
                    "trade_quality_rate": trade_quality,
                    "overall_quality_score": (orderbook_quality + trade_quality) / 2
                },
                "quality_acceptable": all([
                    orderbook_quality >= 0.95,  # 95% valid orderbooks
                    trade_quality >= 0.95,      # 95% valid trades
                    total_orderbooks > 0,       # Received data
                    total_trades > 0
                ]),
                "network_requests": 1,
                "data_points_received": total_orderbooks + total_trades,
                "hft_data_quality_compliant": orderbook_quality >= 0.99 and trade_quality >= 0.99
            }
            
        except Exception as e:
            raise ValueError(f"Data quality validation failed: {str(e)}")
    
    async def test_performance_metrics(self, symbols: List[Symbol], duration_seconds: int = 20) -> Dict[str, Any]:
        """Test performance metrics and HFT compliance."""
        start_time = time.perf_counter()
        
        try:
            # Initialize WebSocket with performance monitoring
            from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
            channels = [
                PublicWebsocketChannelType.ORDERBOOK,
                PublicWebsocketChannelType.PUB_TRADE
            ]
            
            await self.websocket_client.initialize(symbols, channels)
            await asyncio.sleep(duration_seconds)
            
            stats = self.data_collector.get_statistics()
            execution_time = (time.perf_counter() - start_time) * 1000
            
            # Performance analysis
            throughput = stats["message_rate_per_second"]
            latency_stats = stats.get("latency_stats", {})
            
            return {
                "test_duration_seconds": duration_seconds,
                "execution_time_ms": execution_time,
                "performance_metrics": {
                    "message_throughput_per_second": throughput,
                    "total_messages_processed": stats["total_messages"],
                    "average_message_interval_ms": latency_stats.get("avg_interval_ms", 0),
                    "min_message_interval_ms": latency_stats.get("min_interval_ms", 0),
                    "max_message_interval_ms": latency_stats.get("max_interval_ms", 0),
                    "symbols_streaming": stats["symbols_with_data"],
                    "error_rate": stats["error_count"] / max(stats["total_messages"], 1)
                },
                "hft_performance_compliant": all([
                    throughput >= 10.0,  # At least 10 messages per second
                    latency_stats.get("avg_interval_ms", 1000) <= 500,  # Avg interval ≤ 500ms
                    stats["error_count"] == 0,  # No errors
                    stats["symbols_with_data"] >= len(symbols)  # All symbols active
                ]),
                "network_requests": 1,
                "data_points_received": stats["total_messages"]
            }
            
        except Exception as e:
            raise ValueError(f"Performance metrics test failed: {str(e)}")
    
    async def teardown(self) -> None:
        """Clean up resources."""
        if self.websocket_client:
            await self.websocket_client.close()
    
    async def run_all_tests(self, symbols: List[Symbol], timeout_seconds: int = 60) -> None:
        """Run complete WebSocket public API test suite."""
        try:
            # Setup
            await self.test_runner.run_test_with_timeout(
                lambda: self.setup(symbols),
                "websocket_setup",
                TestCategory.CONFIGURATION,
                timeout_seconds=20,
                expected_behavior="WebSocket client initialized and ready for streaming"
            )
            
            # Connection stability test
            await self.test_runner.run_test_with_timeout(
                lambda: self.test_connection_stability(symbols, duration_seconds=20),
                "connection_stability",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=30,
                expected_behavior="WebSocket connection remains stable and receives data continuously"
            )
            
            # Data quality validation
            await self.test_runner.run_test_with_timeout(
                lambda: self.test_data_quality_validation(symbols, duration_seconds=15),
                "data_quality_validation",
                TestCategory.WEBSOCKET_PUBLIC,
                timeout_seconds=25,
                expected_behavior="All received data passes validation with >95% quality rate"
            )
            
            # Performance metrics
            await self.test_runner.run_test_with_timeout(
                lambda: self.test_performance_metrics(symbols, duration_seconds=15),
                "performance_metrics",
                TestCategory.PERFORMANCE,
                timeout_seconds=25,
                expected_behavior="WebSocket performance meets HFT requirements for throughput and latency"
            )
            
        finally:
            await self.teardown()


# Pytest test functions
@pytest.mark.asyncio
@pytest.mark.integration
async def test_mexc_websocket_integration(test_symbols):
    """Test MEXC WebSocket public API integration."""
    test_suite = WebSocketPublicIntegrationTest("mexc_spot")
    await test_suite.run_all_tests(symbols=test_symbols[:2], timeout_seconds=90)  # Use 2 symbols
    
    report = test_suite.test_runner.generate_report()
    
    # Save report
    test_suite.test_runner.save_report("mexc_websocket_report.json")
    
    # Validate results
    assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary_metrics}"
    assert report.compliance_status["performance_compliant"], f"HFT performance not met: {report.compliance_status}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gateio_websocket_integration(test_symbols):
    """Test Gate.io WebSocket public API integration."""
    test_suite = WebSocketPublicIntegrationTest("gateio_spot")
    await test_suite.run_all_tests(symbols=test_symbols[:2], timeout_seconds=90)  # Use 2 symbols
    
    report = test_suite.test_runner.generate_report()
    
    # Save report
    test_suite.test_runner.save_report("gateio_websocket_report.json")
    
    # Validate results
    assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary_metrics}"
    assert report.compliance_status["performance_compliant"], f"HFT performance not met: {report.compliance_status}"


@pytest.mark.asyncio
@pytest.mark.integration 
@pytest.mark.skipif(
    not pytest.importorskip("pytest", reason="Long-running integration test"),
    reason="Requires extended testing time"
)
async def test_websocket_endurance(test_symbols):
    """Extended endurance test for WebSocket stability."""
    test_suite = WebSocketPublicIntegrationTest("mexc_spot")
    
    # Extended test with longer duration
    symbols = test_symbols[:1]  # Use single symbol for endurance
    await test_suite.setup(symbols)
    
    # Run 5-minute endurance test
    result = await test_suite.test_connection_stability(symbols, duration_seconds=300)
    
    await test_suite.teardown()
    
    # Validate endurance metrics
    assert result["connection_stable"], "Connection not stable during endurance test"
    assert result["statistics"]["total_messages"] > 100, "Insufficient messages during endurance test"


# Standalone execution
if __name__ == "__main__":
    import sys
    
    symbols = [
        Symbol(base=AssetName('BTC'), quote=AssetName('USDT')),
        Symbol(base=AssetName('ETH'), quote=AssetName('USDT'))
    ]
    
    exchange_name = sys.argv[1] if len(sys.argv) > 1 else "mexc_spot"
    
    async def main():
        test_suite = WebSocketPublicIntegrationTest(exchange_name)
        await test_suite.run_all_tests(symbols=symbols)
        test_suite.test_runner.print_summary_for_agent()
    
    asyncio.run(main())