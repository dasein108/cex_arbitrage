"""
Consolidated Integration Tests

Unified integration tests that eliminate code duplication and provide
comprehensive testing for both REST and WebSocket functionality.

The integration tests replace separate public/private test files with unified
test suites that support both public and private API testing through command-line flags.
"""

from .rest_integration_test import RestIntegrationTest
from .websocket_integration_test import WebSocketIntegrationTest

__all__ = [
    'RestIntegrationTest',
    'WebSocketIntegrationTest'
]