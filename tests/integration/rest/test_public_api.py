"""
REST Public API Integration Tests

Comprehensive integration testing for public REST API functionality across exchanges.
Tests are designed to validate exchange implementations and ensure HFT compliance.

Usage:
    pytest tests/integration/rest/test_public_api.py
    pytest tests/integration/rest/test_public_api.py::test_mexc_public_api -v
    pytest tests/integration/rest/test_public_api.py -k "orderbook" --tb=short
"""

import pytest
import asyncio
import time
from typing import Dict, Any

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from config.config_manager import HftConfig
from exchanges.structs import ExchangeEnum
from tests.integration_test_framework import (
    IntegrationTestRunner, TestCategory, TestStatus, HFTComplianceValidator
)


class PublicAPIIntegrationTest:
    """Public API integration test suite."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.exchange = None
        self.test_runner = IntegrationTestRunner(
            exchange=self.exchange_name,
            test_suite="REST_PUBLIC_API_V2"
        )
        
    def _create_exchange_client(self, exchange_name: str, config):
        """Create exchange client using unified factory pattern."""
        if exchange_name.upper() == "MEXC_SPOT":
            from exchanges.integrations.mexc.public_exchange import MexcPublicExchange
            return MexcPublicExchange(config=config)
        elif exchange_name.upper() == "GATEIO_SPOT":
            from exchanges.integrations.gateio.public_exchange import GateioPublicExchange
            return GateioPublicExchange(config=config)
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
                "config_loaded": True,
                "exchange_name": self.exchange_name
            }
        except Exception as e:
            raise ConnectionError(f"Failed to setup {self.exchange_name} exchange: {str(e)}")
    
    async def teardown(self) -> None:
        """Clean up resources."""
        if self.exchange:
            await self.exchange.close()
    
    async def test_ping(self) -> Dict[str, Any]:
        """Test ping functionality with HFT latency requirements."""
        start_time = time.perf_counter()
        
        try:
            result = await self.exchange.ping()
            execution_time = (time.perf_counter() - start_time) * 1000
            
            return {
                "ping_result": result,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "response_received": True,
                "hft_latency_compliant": execution_time < 1000,  # 1 second max
                "data_points_received": 1
            }
        except Exception as e:
            raise ConnectionError(f"Ping failed: {str(e)}")
    
    async def test_get_server_time(self) -> Dict[str, Any]:
        """Test server time retrieval with validation."""
        start_time = time.perf_counter()
        
        try:
            result = await self.exchange.get_server_time()
            execution_time = (time.perf_counter() - start_time) * 1000
            current_time = time.time() * 1000
            
            time_diff = abs(result - current_time)
            time_valid = time_diff < 3600000  # 1 hour tolerance
            
            return {
                "server_time": result,
                "local_time": current_time,
                "time_difference_ms": time_diff,
                "time_valid": time_valid,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": 1,
                "hft_latency_compliant": execution_time < 1000
            }
        except Exception as e:
            raise ValueError(f"Server time retrieval failed: {str(e)}")
    
    async def test_get_exchange_info(self) -> Dict[str, Any]:
        """Test exchange info retrieval and validation."""
        start_time = time.perf_counter()
        
        try:
            result = await self.exchange.get_symbols_info()
            execution_time = (time.perf_counter() - start_time) * 1000
            
            symbols_count = len(result)
            has_symbols = symbols_count > 0
            
            # Validate symbol structure
            sample_symbols = []
            valid_symbols_count = 0
            
            for i, (symbol, info) in enumerate(result.items()):
                if i >= 5:  # Check first 5 symbols
                    break
                    
                is_valid = all([
                    hasattr(info, 'base_precision'),
                    hasattr(info, 'quote_precision'),
                    hasattr(info, 'min_base_amount'),
                    hasattr(info, 'min_quote_amount'),
                    info.base_precision >= 0,
                    info.quote_precision >= 0
                ])
                
                if is_valid:
                    valid_symbols_count += 1
                
                sample_symbols.append({
                    "symbol": f"{symbol.base}/{symbol.quote}",
                    "exchange": info.exchange,
                    "base_precision": info.base_precision,
                    "quote_precision": info.quote_precision,
                    "is_valid": is_valid
                })
            
            return {
                "total_symbols": symbols_count,
                "has_symbols": has_symbols,
                "sample_symbols": sample_symbols,
                "valid_symbols_count": valid_symbols_count,
                "validation_rate": valid_symbols_count / len(sample_symbols) if sample_symbols else 0,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": symbols_count,
                "hft_latency_compliant": execution_time < 5000  # 5 seconds for exchange info
            }
        except Exception as e:
            raise ValueError(f"Exchange info retrieval failed: {str(e)}")
    
    async def test_get_orderbook(self) -> Dict[str, Any]:
        """Test orderbook retrieval with market data validation."""
        start_time = time.perf_counter()
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
        
        try:
            result = await self.exchange.get_orderbook(symbol, limit=10)
            execution_time = (time.perf_counter() - start_time) * 1000
            
            # Comprehensive orderbook validation
            has_bids = len(result.bids) > 0
            has_asks = len(result.asks) > 0
            has_timestamp = result.timestamp > 0
            
            # Price and quantity validation
            valid_bids = all(bid.price > 0 and bid.quantity > 0 for bid in result.bids)
            valid_asks = all(ask.price > 0 and ask.quantity > 0 for ask in result.asks)
            
            # Order validation (bids descending, asks ascending)
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
            
            # Spread calculation and validation
            spread = None
            spread_positive = True
            spread_reasonable = True
            
            if has_bids and has_asks:
                best_bid = result.bids[0].price
                best_ask = result.asks[0].price
                spread = best_ask - best_bid
                spread_positive = spread >= 0
                spread_pct = (spread / best_bid) * 100 if best_bid > 0 else 0
                spread_reasonable = spread_pct < 5.0  # 5% max spread for major pairs
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "timestamp": result.timestamp,
                "bids_count": len(result.bids),
                "asks_count": len(result.asks),
                "has_bids": has_bids,
                "has_asks": has_asks,
                "has_timestamp": has_timestamp,
                "valid_bids": valid_bids,
                "valid_asks": valid_asks,
                "bids_ordered_correctly": bids_ordered,
                "asks_ordered_correctly": asks_ordered,
                "spread": spread,
                "spread_positive": spread_positive,
                "spread_reasonable": spread_reasonable,
                "best_bid": result.bids[0].price if has_bids else None,
                "best_ask": result.asks[0].price if has_asks else None,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": len(result.bids) + len(result.asks),
                "hft_latency_compliant": execution_time < 2000  # 2 seconds for orderbook
            }
        except Exception as e:
            raise ValueError(f"Orderbook retrieval failed: {str(e)}")
    
    async def test_get_recent_trades(self) -> Dict[str, Any]:
        """Test recent trades retrieval with trade data validation."""
        start_time = time.perf_counter()
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
        
        try:
            result = await self.exchange.get_recent_trades(symbol, limit=10)
            execution_time = (time.perf_counter() - start_time) * 1000
            
            trades_count = len(result)
            has_trades = trades_count > 0
            
            # Validate trade data quality
            valid_trades_count = 0
            trade_samples = []
            
            for i, trade in enumerate(result[:5]):  # Check first 5 trades
                is_valid = all([
                    trade.price > 0,
                    trade.quantity > 0,
                    trade.timestamp > 0,
                    hasattr(trade, 'side'),
                    hasattr(trade, 'is_maker')
                ])
                
                if is_valid:
                    valid_trades_count += 1
                
                trade_samples.append({
                    "price": trade.price,
                    "quantity": trade.quantity,
                    "side": trade.side.name,
                    "timestamp": trade.timestamp,
                    "is_maker": trade.is_maker,
                    "is_valid": is_valid
                })
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "trades_count": trades_count,
                "has_trades": has_trades,
                "valid_trades_count": valid_trades_count,
                "validation_rate": valid_trades_count / len(trade_samples) if trade_samples else 0,
                "trade_samples": trade_samples,
                "execution_time_ms": execution_time,
                "network_requests": 1,
                "data_points_received": trades_count,
                "hft_latency_compliant": execution_time < 2000
            }
        except Exception as e:
            raise ValueError(f"Recent trades retrieval failed: {str(e)}")
    
    async def run_all_tests(self, timeout_seconds: int = 30) -> None:
        """Run complete REST public API test suite."""
        try:
            # Setup
            await self.test_runner.run_test_with_timeout(
                self.setup,
                "exchange_setup",
                TestCategory.CONFIGURATION,
                timeout_seconds=15,
                expected_behavior="Exchange client initialized with valid configuration"
            )
            
            # Core API tests
            await self.test_runner.run_test_with_timeout(
                self.test_ping,
                "ping_connectivity",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Ping returns successful response within HFT latency limits"
            )
            
            await self.test_runner.run_test_with_timeout(
                self.test_get_server_time,
                "server_time_sync",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Server time retrieved and synchronized within acceptable range"
            )
            
            await self.test_runner.run_test_with_timeout(
                self.test_get_exchange_info,
                "exchange_metadata",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Exchange info contains valid symbols with proper metadata"
            )
            
            await self.test_runner.run_test_with_timeout(
                self.test_get_orderbook,
                "orderbook_data_quality",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Orderbook data is valid, ordered, and contains reasonable spreads"
            )
            
            await self.test_runner.run_test_with_timeout(
                self.test_get_recent_trades,
                "trade_data_quality",
                TestCategory.REST_PUBLIC,
                timeout_seconds=timeout_seconds,
                expected_behavior="Recent trades data is valid and properly structured"
            )
            
        finally:
            await self.teardown()


# Pytest test functions
@pytest.mark.asyncio
@pytest.mark.integration
async def test_mexc_public_api_integration():
    """Test MEXC REST public API integration with HFT compliance."""
    test_suite = PublicAPIIntegrationTest("mexc_spot")
    await test_suite.run_all_tests(timeout_seconds=30)
    
    report = test_suite.test_runner.generate_report()
    
    # Save detailed report
    test_suite.test_runner.save_report(f"mexc_public_api_report.json")
    
    # Validate results
    assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary_metrics}"
    assert report.compliance_status["overall_compliant"], f"HFT compliance failed: {report.compliance_status}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gateio_public_api_integration():
    """Test Gate.io REST public API integration with HFT compliance."""
    test_suite = PublicAPIIntegrationTest("gateio_spot")
    await test_suite.run_all_tests(timeout_seconds=30)
    
    report = test_suite.test_runner.generate_report()
    
    # Save detailed report
    test_suite.test_runner.save_report(f"gateio_public_api_report.json")
    
    # Validate results
    assert report.overall_status == TestStatus.PASSED, f"Tests failed: {report.summary_metrics}"
    assert report.compliance_status["overall_compliant"], f"HFT compliance failed: {report.compliance_status}"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("exchange", ["mexc_spot", "gateio_spot"])
async def test_exchange_public_api_compliance(exchange):
    """Parameterized test for all supported exchanges."""
    test_suite = PublicAPIIntegrationTest(exchange)
    await test_suite.run_all_tests(timeout_seconds=30)
    
    report = test_suite.test_runner.generate_report()
    
    # Validate HFT compliance
    assert report.compliance_status["performance_compliant"], f"Performance requirements not met for {exchange}"
    assert report.summary_metrics["success_rate"] >= 0.95, f"Success rate too low for {exchange}: {report.summary_metrics['success_rate']}"


# Standalone execution
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        exchange_name = sys.argv[1]
    else:
        exchange_name = "mexc"
    
    async def main():
        test_suite = PublicAPIIntegrationTest(exchange_name)
        await test_suite.run_all_tests()
        test_suite.test_runner.print_summary_for_agent()
    
    asyncio.run(main())