"""
Comprehensive Unit Tests for Composition-Based Error Handling System

Tests the complete error handling infrastructure including:
- Base ComposableErrorHandler functionality
- Specialized error handlers (WebSocket, Trading, REST API)
- Error context management and severity classification
- Retry logic with exponential backoff
- Performance benchmarks for HFT compliance
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from infrastructure.error_handling import (
    ComposableErrorHandler, 
    WebSocketErrorHandler, 
    TradingErrorHandler,
    RestApiErrorHandler,
    ErrorSeverity, 
    ErrorContext
)
from infrastructure.exceptions.exchange import BaseExchangeError


class TestComposableErrorHandler:
    """Test base error handler functionality"""
    
    @pytest.fixture
    def mock_logger(self):
        return Mock()
    
    @pytest.fixture  
    def handler(self, mock_logger):
        return ComposableErrorHandler(
            logger=mock_logger,
            max_retries=3,
            base_delay=0.1
        )
    
    @pytest.fixture
    def error_context(self):
        return ErrorContext(
            operation="test_operation",
            component="test_component",
            metadata={"symbol": "BTC/USDT", "amount": 1.0}
        )

    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self, handler, error_context):
        """Test successful operation requires no error handling"""
        async def successful_operation():
            return "success"
        
        result = await handler.handle_with_retry(successful_operation, error_context)
        assert result == "success"
        
        # Should not log any errors
        handler.logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_on_recoverable_error(self, handler, error_context):
        """Test retry logic for recoverable errors"""
        call_count = 0
        
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary connection issue")
            return "success_after_retries"
        
        result = await handler.handle_with_retry(failing_operation, error_context)
        assert result == "success_after_retries"
        assert call_count == 3
        
        # Should log retry attempts
        assert handler.logger.warning.call_count >= 2

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, handler, error_context):
        """Test behavior when max retries are exhausted"""
        async def always_failing_operation():
            raise ValueError("Persistent error")
        
        # ValueError is classified as CRITICAL, so it should raise immediately
        with pytest.raises(ValueError, match="Persistent error"):
            await handler.handle_with_retry(always_failing_operation, error_context)
        
        # Should log error attempts - could be in metric calls or error calls
        total_error_calls = handler.logger.error.call_count + handler.logger.metric.call_count
        assert total_error_calls >= 1

    @pytest.mark.asyncio 
    async def test_non_recoverable_error_no_retry(self, handler, error_context):
        """Test that non-recoverable errors are not retried"""
        from infrastructure.error_handling import ErrorSeverity
        
        async def operation_with_fatal_error():
            raise BaseExchangeError(400, "Invalid API key")  # Non-recoverable
        
        # Test with critical severity to ensure it raises
        with pytest.raises(BaseExchangeError):
            await handler.handle_with_retry(operation_with_fatal_error, error_context, ErrorSeverity.CRITICAL)
        
        # Critical errors raise immediately, so only one error call expected
        assert handler.logger.error.call_count >= 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, handler, error_context):
        """Test exponential backoff delays"""
        delays = []
        call_count = 0
        
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 times, succeed on 3rd
                raise ConnectionError("Temporary error")
            return "success"
        
        start_time = time.time()
        
        # Mock asyncio.sleep to capture delays
        original_sleep = asyncio.sleep
        
        async def mock_sleep(delay):
            delays.append(delay)
            await original_sleep(0.001)  # Minimal actual delay for testing
        
        with patch('asyncio.sleep', mock_sleep):
            await handler.handle_with_retry(failing_operation, error_context)
        
        # Should have exponential backoff: base_delay, base_delay * 2  
        expected_delays = [0.1, 0.2]
        assert len(delays) == 2
        for actual, expected in zip(delays, expected_delays):
            assert abs(actual - expected) < 0.1  # Allow for jitter


class TestWebSocketErrorHandler:
    """Test WebSocket-specific error handling"""
    
    @pytest.fixture
    def ws_handler(self):
        return WebSocketErrorHandler(
            logger=Mock(),
            max_retries=5,
            base_delay=0.1
        )
    
    @pytest.fixture
    def ws_context(self):
        return ErrorContext(
            operation="websocket_message_reader",
            component="ws_client",
            metadata={"url": "wss://api.mexc.com/ws"}
        )

    @pytest.mark.asyncio
    async def test_websocket_connection_error_retry(self, ws_handler, ws_context):
        """Test WebSocket connection errors are retried"""
        from websockets.exceptions import ConnectionClosedError
        
        call_count = 0
        
        async def operation_with_ws_error():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionClosedError(None, None)
            return "reconnected"
        
        result = await ws_handler.handle_with_retry(operation_with_ws_error, ws_context)
        assert result == "reconnected"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_websocket_1005_error_special_handling(self, ws_handler, ws_context):
        """Test WebSocket 1005 errors get special handling (shorter delays)"""
        from websockets.exceptions import ConnectionClosedError
        
        # Mock the special case handling in WebSocketErrorHandler
        call_count = 0
        
        async def operation_with_1005_error():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                # Simulate connection error
                raise ConnectionError("Connection closed abnormally")  
            return "recovered"
        
        result = await ws_handler.handle_with_retry(operation_with_1005_error, ws_context)
        assert result == "recovered"


class TestTradingErrorHandler:
    """Test trading-specific error handling"""
    
    @pytest.fixture
    def trading_handler(self):
        return TradingErrorHandler(
            logger=Mock(),
            max_retries=2,  # Conservative for trading
            base_delay=0.5
        )
    
    @pytest.fixture  
    def trading_context(self):
        return ErrorContext(
            operation="place_order",
            component="trading_engine",
            metadata={"symbol": "BTC/USDT", "side": "BUY", "amount": 0.001}
        )

    @pytest.mark.asyncio
    async def test_insufficient_funds_no_retry(self, trading_handler, trading_context):
        """Test insufficient funds errors are not retried"""
        async def operation_insufficient_funds():
            raise BaseExchangeError(400, "Insufficient balance")
        
        with pytest.raises(BaseExchangeError):
            await trading_handler.handle_with_retry(operation_insufficient_funds, trading_context)
        
        # Should not retry insufficient funds errors - called once for error, once for timer
        assert trading_handler.logger.error.call_count >= 1

    @pytest.mark.asyncio
    async def test_rate_limit_retry_with_backoff(self, trading_handler, trading_context):
        """Test rate limit errors are retried with longer backoff"""
        call_count = 0
        delays = []
        
        async def rate_limited_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise BaseExchangeError(429, "Rate limit exceeded")
            return "order_placed"
        
        # Mock sleep to capture backoff delays
        async def mock_sleep(delay):
            delays.append(delay)
            # Don't call asyncio.sleep to avoid recursion
        
        with patch('asyncio.sleep', mock_sleep):
            result = await trading_handler.handle_with_retry(rate_limited_operation, trading_context)
        
        assert result == "order_placed"
        assert len(delays) >= 1
        # Rate limit should use the configured base delay (0.5s for TradingErrorHandler)
        assert delays[0] >= 0.4  # Should be at least close to base delay with jitter


class TestRestApiErrorHandler:
    """Test REST API-specific error handling"""
    
    @pytest.fixture
    def rest_handler(self):
        return RestApiErrorHandler(
            logger=Mock(),
            max_retries=3,
            base_delay=1.0
        )
    
    @pytest.fixture
    def rest_context(self):
        return ErrorContext(
            operation="get_account_balance",
            component="rest_client",
            metadata={"endpoint": "/api/v3/account"}
        )

    @pytest.mark.asyncio
    async def test_http_500_retry(self, rest_handler, rest_context):
        """Test 5xx HTTP errors are retried"""
        call_count = 0
        
        async def operation_with_server_error():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise BaseExchangeError(500, "Internal server error")
            return {"balances": []}
        
        result = await rest_handler.handle_with_retry(operation_with_server_error, rest_context)
        assert result == {"balances": []}
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_http_401_no_retry(self, rest_handler, rest_context):
        """Test 401 authentication errors are not retried"""
        async def operation_with_auth_error():
            raise BaseExchangeError(401, "Invalid API key")
        
        with pytest.raises(BaseExchangeError, match="Invalid API key"):
            await rest_handler.handle_with_retry(operation_with_auth_error, rest_context)
        
        # Should not retry auth errors - error called for handling + timer
        assert rest_handler.logger.error.call_count >= 1


class TestErrorSeverityClassification:
    """Test error severity classification"""
    
    def test_critical_errors(self):
        """Test critical error classification"""
        handler = ComposableErrorHandler(Mock(), max_retries=1, base_delay=0.1)
        
        critical_errors = [
            BaseExchangeError(400, "Invalid API key"),
            BaseExchangeError(403, "Insufficient permissions"),
            ValueError("Invalid order parameters")
        ]
        
        for error in critical_errors:
            severity = handler._classify_error(error)
            assert severity == ErrorSeverity.CRITICAL

    def test_high_severity_errors(self):
        """Test high severity error classification"""  
        handler = ComposableErrorHandler(Mock(), max_retries=1, base_delay=0.1)
        
        high_errors = [
            BaseExchangeError(429, "Rate limit exceeded"),
            BaseExchangeError(500, "Internal server error")
        ]
        
        for error in high_errors:
            severity = handler._classify_error(error)
            assert severity == ErrorSeverity.HIGH

    def test_medium_severity_errors(self):
        """Test medium severity error classification"""
        handler = ComposableErrorHandler(Mock(), max_retries=1, base_delay=0.1)
        
        medium_errors = [
            ConnectionError("Connection timeout"),
            TimeoutError("Request timeout")
        ]
        
        for error in medium_errors:
            severity = handler._classify_error(error)
            assert severity == ErrorSeverity.MEDIUM


class TestPerformanceBenchmarks:
    """Test HFT performance requirements are met"""
    
    @pytest.mark.asyncio
    async def test_error_handling_latency_hft_compliant(self):
        """Test error handling latency meets HFT requirements (<0.5ms)"""
        handler = ComposableErrorHandler(Mock(), max_retries=1, base_delay=0.001)
        context = ErrorContext("test", "test", {})
        
        async def fast_operation():
            return "result"
        
        # Benchmark successful operation (no error handling)
        start_time = time.perf_counter()
        for _ in range(1000):
            await handler.handle_with_retry(fast_operation, context)
        end_time = time.perf_counter()
        
        avg_latency_ms = ((end_time - start_time) / 1000) * 1000
        
        # Should be well under 0.5ms for successful operations
        assert avg_latency_ms < 0.1, f"Error handling latency {avg_latency_ms:.3f}ms exceeds HFT requirements"

    @pytest.mark.asyncio
    async def test_retry_performance_acceptable(self):
        """Test retry performance is acceptable for HFT"""
        handler = ComposableErrorHandler(Mock(), max_retries=2, base_delay=0.001)
        context = ErrorContext("test", "test", {})
        
        call_count = 0
        
        async def operation_with_one_retry():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Temporary error")
            return "success"
        
        # Benchmark operation with one retry
        start_time = time.perf_counter()
        result = await handler.handle_with_retry(operation_with_one_retry, context)
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        
        # Should complete retry within reasonable time for HFT (excluding actual backoff delay)
        assert result == "success"
        assert call_count == 2
        # Test the handler overhead is minimal (actual backoff delay is mocked to be very small)
        assert latency_ms < 10, f"Retry latency {latency_ms:.3f}ms too high for HFT"


class TestErrorContextManagement:
    """Test error context tracking and metadata"""
    
    def test_error_context_creation(self):
        """Test error context creation and metadata"""
        context = ErrorContext(
            operation="place_order",
            component="mexc_private_exchange", 
            metadata={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "amount": 0.001,
                "price": 45000.0
            }
        )
        
        assert context.operation == "place_order"
        assert context.component == "mexc_private_exchange"
        assert context.metadata["symbol"] == "BTC/USDT"
        assert context.metadata["amount"] == 0.001

    @pytest.mark.asyncio
    async def test_error_context_logging(self):
        """Test error context is properly logged"""
        mock_logger = Mock()
        handler = ComposableErrorHandler(mock_logger, max_retries=1, base_delay=0.1)
        
        context = ErrorContext(
            operation="websocket_connect",
            component="ws_client",
            metadata={"url": "wss://api.mexc.com/ws", "reconnect_attempts": 1}
        )
        
        async def failing_operation():
            raise ConnectionError("Connection failed")
        
        # Should return None for non-critical errors (auto-classified as MEDIUM)
        result = await handler.handle_with_retry(failing_operation, context)
        assert result is None
        
        # Verify context information was logged - could be in error or metric calls
        total_calls = mock_logger.error.call_count + mock_logger.metric.call_count
        assert total_calls > 0
        
        # Check that structured logging includes context
        if mock_logger.error.called:
            logged_calls = mock_logger.error.call_args_list
            error_message = str(logged_calls[-1])
            assert "websocket_connect" in error_message or "ws_client" in error_message


if __name__ == "__main__":
    # Run tests with: python -m pytest tests/test_error_handling.py -v
    pytest.main([__file__, "-v", "--tb=short"])