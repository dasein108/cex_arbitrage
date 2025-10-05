"""
Pytest configuration and fixtures for HFT Arbitrage Engine tests.

Provides common fixtures, test configuration, and utilities for all test suites.
"""

import pytest
import asyncio
from typing import Dict, Any, List
import os
import sys

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import core testing utilities
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from exchanges.structs import ExchangeEnum


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_symbols() -> List[Symbol]:
    """Standard test symbols for exchange testing."""
    return [
        Symbol(base=AssetName('BTC'), quote=AssetName('USDT')),
        Symbol(base=AssetName('ETH'), quote=AssetName('USDT')),
        Symbol(base=AssetName('BNB'), quote=AssetName('USDT')),
    ]


@pytest.fixture
def test_symbol() -> Symbol:
    """Single test symbol for basic tests."""
    return Symbol(base=AssetName('BTC'), quote=AssetName('USDT'))


@pytest.fixture(params=["mexc", "gateio"])
def exchange_name(request) -> str:
    """Parameterized fixture for testing multiple exchanges."""
    return request.param


@pytest.fixture
def supported_exchanges() -> List[str]:
    """List of supported exchanges for testing."""
    return ["mexc", "gateio"]


@pytest.fixture
def test_config() -> Dict[str, Any]:
    """Standard test configuration."""
    return {
        "timeout_seconds": 30,
        "max_retries": 3,
        "batch_size": 100,
        "performance_threshold_ms": 5000,
        "connection_timeout": 10,
    }


@pytest.fixture
def hft_performance_thresholds() -> Dict[str, float]:
    """HFT performance thresholds for validation."""
    return {
        "rest_request_max_ms": 5000,      # 5 seconds for REST requests
        "websocket_message_max_ms": 100,   # 100ms for WebSocket messages
        "json_parsing_max_ms": 50,         # 50ms for JSON parsing
        "orderbook_processing_max_ms": 10,  # 10ms for orderbook processing
        "connection_setup_max_ms": 10000,  # 10 seconds for connection setup
    }


@pytest.fixture
def skip_integration():
    """Skip integration tests if not in CI or specifically requested."""
    return pytest.mark.skipif(
        not (os.getenv('CI') or os.getenv('RUN_INTEGRATION_TESTS')),
        reason="Integration tests require CI environment or RUN_INTEGRATION_TESTS=1"
    )


@pytest.fixture
def skip_performance():
    """Skip performance tests unless specifically requested.""" 
    return pytest.mark.skipif(
        not os.getenv('RUN_PERFORMANCE_TESTS'),
        reason="Performance tests require RUN_PERFORMANCE_TESTS=1"
    )


@pytest.fixture
def mock_credentials() -> Dict[str, str]:
    """Mock credentials for testing (never use real credentials in tests)."""
    return {
        "api_key": "test_api_key_12345",
        "secret_key": "test_secret_key_67890",
        "passphrase": "test_passphrase"
    }