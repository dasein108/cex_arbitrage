"""
Signal Types and Utilities

Core signal types, enumerations, and validation utilities
for the strategy signal system.
"""

from .signal_types import Signal
from .performance_metrics import PerformanceMetrics

__all__ = [
    'Signal',
    'PerformanceMetrics'
]