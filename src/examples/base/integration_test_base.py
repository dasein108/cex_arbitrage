"""
Integration Test Base Class

Provides shared functionality for integration tests to eliminate code duplication
and standardize test patterns across REST and WebSocket integration tests.
"""

import time
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

from config.config_manager import HftConfig
from exchanges.utils.exchange_utils import get_exchange_enum
from exchanges.transport_factory import create_rest_client, create_websocket_client
from ..integration_test_framework import IntegrationTestRunner, TestCategory, TestStatus
from ..utils.constants import TEST_SYMBOLS, DEFAULT_TEST_TIMEOUT


class IntegrationTestBase(ABC):
    """Base class for all integration tests with shared functionality."""
    
    def __init__(self, exchange_name: str, test_suite_name: str):
        self.exchange_name = exchange_name.upper()
        self.test_suite_name = test_suite_name
        self.exchange = None
        self.config = None
        
        self.test_runner = IntegrationTestRunner(
            exchange=self.exchange_name,
            test_suite=test_suite_name
        )
    
    async def setup_exchange(self, is_private: bool = False) -> Dict[str, Any]:
        """Unified setup for all integration tests."""
        try:
            # Load configuration
            config_manager = HftConfig()
            self.config = config_manager.get_exchange_config(self.exchange_name.lower())
            
            # Verify credentials for private tests
            if is_private:
                if not self.config.credentials.api_key or not self.config.credentials.secret_key:
                    raise ValueError(f"{self.exchange_name} API credentials are required for private testing")
            
            # Create exchange client
            exchange_enum = get_exchange_enum(self.exchange_name)
            self.exchange = create_rest_client(
                exchange=exchange_enum,
                is_private=is_private,
                config=self.config
            )
            
            return {
                "setup_successful": True,
                "exchange_class": type(self.exchange).__name__,
                "config_loaded": True,
                "credentials_configured": is_private and bool(self.config.credentials.api_key),
                "api_key_preview": f"{self.config.credentials.api_key[:8]}..." if is_private and self.config.credentials.api_key else None
            }
            
        except Exception as e:
            raise ConnectionError(f"Failed to setup {self.exchange_name} exchange: {str(e)}")
    
    async def teardown(self) -> None:
        """Standardized cleanup for all tests."""
        if self.exchange:
            await self.exchange.close()
            self.exchange = None
    
    def validate_common_fields(self, obj: Any, required_fields: List[str]) -> Dict[str, bool]:
        """Reusable validation logic for common object fields."""
        validation_results = {}
        
        for field in required_fields:
            if hasattr(obj, field):
                value = getattr(obj, field)
                validation_results[f"has_{field}"] = value is not None
                
                # Additional validation for numeric fields
                if field in ["price", "quantity", "amount", "volume"] and value is not None:
                    validation_results[f"{field}_positive"] = float(value) > 0
                elif field in ["timestamp"] and value is not None:
                    validation_results[f"{field}_valid"] = float(value) > 0
            else:
                validation_results[f"has_{field}"] = False
        
        validation_results["all_required_fields_present"] = all(
            validation_results.get(f"has_{field}", False) for field in required_fields
        )
        
        return validation_results
    
    def measure_performance(self, start_time: float) -> Dict[str, float]:
        """Measure and return performance metrics."""
        execution_time = (time.time() - start_time) * 1000
        
        return {
            "execution_time_ms": execution_time,
            "performance_acceptable": execution_time < DEFAULT_TEST_TIMEOUT * 1000,
            "network_requests": 1  # Override in specific tests if needed
        }
    
    def get_test_symbols(self) -> List:
        """Get standard test symbols for integration tests."""
        return TEST_SYMBOLS.copy()
    
    async def run_test_with_standard_validation(self,
                                              test_func,
                                              test_name: str,
                                              test_category: TestCategory,
                                              timeout_seconds: int = DEFAULT_TEST_TIMEOUT,
                                              expected_behavior: str = "") -> None:
        """Run test with standardized validation and error handling."""
        await self.test_runner.run_test_with_timeout(
            test_func,
            test_name,
            test_category,
            timeout_seconds=timeout_seconds,
            expected_behavior=expected_behavior
        )
    
    @abstractmethod
    async def run_all_tests(self, timeout_seconds: int = DEFAULT_TEST_TIMEOUT) -> None:
        """Run complete test suite. Must be implemented by subclasses."""
        pass


class RestIntegrationTestMixin:
    """Mixin providing common REST integration test functionality."""
    
    async def test_ping_integration(self) -> Dict[str, Any]:
        """Standard ping integration test."""
        start_time = time.time()
        
        try:
            result = await self.exchange.ping()
            performance = self.measure_performance(start_time)
            
            return {
                "ping_result": result,
                "response_received": True,
                "latency_acceptable": performance["execution_time_ms"] < 5000,
                **performance
            }
        except Exception as e:
            raise ConnectionError(f"Ping integration test failed: {str(e)}")
    
    async def test_server_time_integration(self) -> Dict[str, Any]:
        """Standard server time integration test."""
        start_time = time.time()
        
        try:
            result = await self.exchange.get_server_time()
            performance = self.measure_performance(start_time)
            current_time = time.time() * 1000
            
            time_diff = abs(result - current_time)
            time_valid = time_diff < 3600000  # 1 hour tolerance
            
            return {
                "server_time": result,
                "local_time": current_time,
                "time_difference_ms": time_diff,
                "time_valid": time_valid,
                **performance
            }
        except Exception as e:
            raise ValueError(f"Server time integration test failed: {str(e)}")
    
    async def test_exchange_info_integration(self) -> Dict[str, Any]:
        """Standard exchange info integration test."""
        start_time = time.time()
        
        try:
            result = await self.exchange.get_symbols_info()
            performance = self.measure_performance(start_time)
            
            symbols_count = len(result)
            has_symbols = symbols_count > 0
            
            # Validate sample symbols
            sample_symbols = []
            for i, (symbol, info) in enumerate(result.items()):
                if i >= 3:
                    break
                    
                validation = self.validate_common_fields(info, [
                    "base_precision", "quote_precision", "min_base_amount", "min_quote_amount"
                ])
                
                sample_symbols.append({
                    "symbol": f"{symbol.base}/{symbol.quote}",
                    "exchange": info.exchange,
                    **validation
                })
            
            return {
                "total_symbols": symbols_count,
                "has_symbols": has_symbols,
                "sample_symbols": sample_symbols,
                "data_points_received": symbols_count,
                **performance
            }
        except Exception as e:
            raise ValueError(f"Exchange info integration test failed: {str(e)}")


class WebSocketIntegrationTestMixin:
    """Mixin providing common WebSocket integration test functionality."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_collector = None
        self.websocket_client = None
    
    def setup_websocket_data_collector(self):
        """Setup data collector for WebSocket integration tests."""
        from .data_manager import UnifiedDataManager
        self.data_collector = UnifiedDataManager(self.exchange_name)
    
    async def setup_websocket_client(self, is_private: bool = False, symbols: List = None):
        """Setup WebSocket client for integration tests."""
        try:
            if symbols is None:
                symbols = self.get_test_symbols()
            
            exchange_enum = get_exchange_enum(self.exchange_name)
            
            if is_private:
                from exchanges.transport_factory import create_private_handlers
                handlers = create_private_handlers(
                    order_handler=self.data_collector.handle_order_update if hasattr(self.data_collector, 'handle_order_update') else None,
                    balance_handler=self.data_collector.handle_balance_update,
                    trade_handler=self.data_collector.handle_trade_update
                )
            else:
                from exchanges.transport_factory import create_public_handlers
                handlers = create_public_handlers(
                    orderbook_diff_handler=self.data_collector.handle_orderbook_update,
                    trades_handler=self.data_collector.handle_trade_update,
                    book_ticker_handler=self.data_collector.handle_book_ticker_update
                )
            
            self.websocket_client = create_websocket_client(
                exchange=exchange_enum,
                is_private=is_private,
                config=self.config,
                handlers=handlers
            )
            
            return {
                "websocket_setup_successful": True,
                "websocket_class": type(self.websocket_client).__name__,
                "is_private": is_private,
                "symbols_configured": len(symbols) if symbols else 0
            }
            
        except Exception as e:
            raise ConnectionError(f"WebSocket setup failed: {str(e)}")
    
    async def test_websocket_connection_integration(self, symbols: List = None, monitor_duration: int = 10) -> Dict[str, Any]:
        """Standard WebSocket connection integration test."""
        if symbols is None:
            symbols = self.get_test_symbols()
        
        start_time = time.time()
        
        try:
            # Initialize WebSocket
            await self.websocket_client.initialize(symbols)
            
            # Monitor for data
            import asyncio
            await asyncio.sleep(monitor_duration)
            
            # Get performance metrics
            metrics = self.websocket_client.get_performance_metrics()
            data_summary = self.data_collector.get_summary()
            performance = self.measure_performance(start_time)
            
            return {
                "connection_successful": self.websocket_client.is_connected(),
                "symbols_count": len(symbols),
                "monitor_duration": monitor_duration,
                "connection_metrics": metrics,
                "data_summary": data_summary,
                "data_received": data_summary.get("total_orderbook_updates", 0) + data_summary.get("total_trade_updates", 0) > 0,
                **performance
            }
            
        except Exception as e:
            raise ConnectionError(f"WebSocket connection integration test failed: {str(e)}")
        finally:
            if self.websocket_client:
                await self.websocket_client.close()
                self.websocket_client = None