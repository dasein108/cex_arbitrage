"""
Pytest configuration and fixtures for maker limit strategy tests

Provides common test fixtures and configuration for the strategy test suite.
"""

import pytest
import asyncio
from unittest.mock import Mock
from typing import Generator

# Set up asyncio event loop for async tests
@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_logger():
    """Provide a mock logger for testing"""
    return Mock()


# Configure pytest to handle async tests properly
pytest_plugins = ["pytest_asyncio"]