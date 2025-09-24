"""
Simplified Message Routing for HFT Logging

Simple, fast routing logic for standard HFT configurations.
HFT COMPLIANT: <1μs routing decisions.
"""

import os
from typing import Dict, List, Union, Optional
from .interfaces import LogBackend, LogRecord, LogLevel, LogType, LogRouter
from .structs import RouterConfig


class SimpleRouter(LogRouter):
    """
    Simple router with predefined routing logic.
    
    Fast, hardcoded routing for standard HFT configurations.
    Use when you don't need complex rule configuration.
    """
    
    def __init__(self, backends: Dict[str, LogBackend], config: RouterConfig):
        """
        Initialize router with struct configuration.
        
        Args:
            backends: Available backends
            config: RouterConfig struct (required)
        """
        if not isinstance(config, RouterConfig):
            raise TypeError(f"Expected RouterConfig, got {type(config)}")
        
        self.backends = backends
        self.config = config
        
        # Configuration from struct
        self.environment = config.environment or os.getenv('ENVIRONMENT', 'dev')
        self.correlation_tracking = config.correlation_tracking
        self.enable_smart_routing = config.enable_smart_routing
        self.default_backends = config.get_default_backends()
        
        self.is_dev = self.environment.lower() in ('dev', 'development', 'local', 'test')
    
def get_backends(self, record: LogRecord) -> List[LogBackend]:
    """Simple routing logic for HFT use cases."""
    log_type = record.log_type
    level = record.level
    is_dev = self.is_dev

    routes = {
        LogType.METRIC: ['prometheus', 'prometheus_histogram'],
        LogType.AUDIT: ['file', 'audit_file', 'elasticsearch'],
    }

    if log_type in routes:
        backend_names = routes[log_type]
    elif level >= LogLevel.WARNING:
        backend_names = ['file']
        if is_dev:
            backend_names.append('console')
    else:
        backend_names = ['console'] if is_dev else []

    return [
        backend
        for name in backend_names
        if (backend := self.backends.get(name)) and backend.should_handle(record)
    ]


def create_router(backends: Dict[str, LogBackend], config: RouterConfig) -> LogRouter:
    """
    Create a router instance.
    
    Args:
        backends: Available backends
        config: RouterConfig struct (required)
        
    Returns:
        SimpleRouter instance (only router type supported now)
    """
    return SimpleRouter(backends, config)