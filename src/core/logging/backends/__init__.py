"""
Logging Backends for HFT System

Collection of high-performance backends for different logging destinations.
Each backend handles its own formatting and output logic.

Available backends:
- ConsoleBackend: DEV environment console output
- FileBackend: High-performance file logging  
- PrometheusBackend: Metrics with batching
- PythonLoggingBridge: Backwards compatibility
"""

from .console import ConsoleBackend
from .file import FileBackend
from .prometheus import PrometheusBackend
from .python_bridge import PythonLoggingBridge

__all__ = [
    'ConsoleBackend',
    'FileBackend', 
    'PrometheusBackend',
    'PythonLoggingBridge'
]