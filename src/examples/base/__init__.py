"""
Base classes and utilities for example scripts.

Provides shared functionality to eliminate code duplication across
demo scripts and integration tests.
"""

from .data_manager import UnifiedDataManager
from .integration_test_base import IntegrationTestBase

__all__ = [
    'UnifiedDataManager',
    'IntegrationTestBase'
]