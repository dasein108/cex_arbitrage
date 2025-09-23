"""
Simplified Message Routing for HFT Logging

Simple, fast routing logic for standard HFT configurations.
HFT COMPLIANT: <1μs routing decisions.
"""

import os
from typing import Dict, List
from .interfaces import LogBackend, LogRecord, LogLevel, LogType, LogRouter


class SimpleRouter(LogRouter):
    """
    Simple router with predefined routing logic.
    
    Fast, hardcoded routing for standard HFT configurations.
    Use when you don't need complex rule configuration.
    """
    
    def __init__(self, backends: Dict[str, LogBackend], environment: str = None):
        self.backends = backends
        self.environment = environment or os.getenv('ENVIRONMENT', 'dev')
        self.is_dev = self.environment.lower() in ('dev', 'development', 'local', 'test')
    
    def get_backends(self, record: LogRecord) -> List[LogBackend]:
        """Simple routing logic for HFT use cases."""
        matching_backends = []
        
        # Route based on log type and level
        if record.log_type == LogType.METRIC:
            # Metrics go to Prometheus (and optionally others)
            for name in ['prometheus', 'prometheus_histogram']:
                backend = self.backends.get(name)
                if backend and backend.should_handle(record):
                    matching_backends.append(backend)
        
        elif record.log_type == LogType.AUDIT:
            # Audit logs go to file and optionally Elasticsearch
            for name in ['file', 'audit_file', 'elasticsearch']:
                backend = self.backends.get(name)
                if backend and backend.should_handle(record):
                    matching_backends.append(backend)
        
        elif record.level >= LogLevel.WARNING:
            # Warnings/errors go to file and console (dev)
            backend_names = ['file', 'python_bridge']
            if self.is_dev:
                backend_names.append('console')
            
            for name in backend_names:
                backend = self.backends.get(name)
                if backend and backend.should_handle(record):
                    matching_backends.append(backend)
        
        else:
            # Debug/info messages go to console (dev only) and python bridge
            backend_names = ['python_bridge']
            if self.is_dev:
                backend_names.append('console')
            
            for name in backend_names:
                backend = self.backends.get(name)
                if backend and backend.should_handle(record):
                    matching_backends.append(backend)
        
        return matching_backends


def create_router(backends: Dict[str, LogBackend], environment: str = None) -> LogRouter:
    """
    Create a router instance.
    
    Args:
        backends: Available backends
        environment: Environment name (dev, prod, test)
        
    Returns:
        SimpleRouter instance (only router type supported now)
    """
    return SimpleRouter(backends, environment)