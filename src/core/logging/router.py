"""
Log Routing Engine

Routes log records to appropriate backends based on configurable rules.
Supports complex routing logic for different message types.

HFT COMPLIANT: Fast rule evaluation, minimal overhead.
"""

from typing import Dict, List, Set, Callable, Any
from .interfaces import LogBackend, LogRecord, LogLevel, LogType, LogRouter


class RuleBasedRouter(LogRouter):
    """
    Router that uses configurable rules to determine backend routing.
    
    Rules are evaluated in order, first match wins.
    """
    
    def __init__(self, rules: List[Dict[str, Any]], backends: Dict[str, LogBackend]):
        """
        Initialize router with rules and backend mapping.
        
        Args:
            rules: List of routing rules
            backends: Map of backend name to backend instance
        """
        self.backends = backends
        self.rules = self._compile_rules(rules)
    
    def get_backends(self, record: LogRecord) -> List[LogBackend]:
        """Get backends for this record based on rules."""
        matching_backends = []
        
        for rule_func, backend_names in self.rules:
            if rule_func(record):
                for name in backend_names:
                    backend = self.backends.get(name)
                    if backend and backend.should_handle(record):
                        matching_backends.append(backend)
        
        return matching_backends
    
    def _compile_rules(self, rules: List[Dict[str, Any]]) -> List[tuple]:
        """Compile rules into fast evaluation functions."""
        compiled = []
        
        for rule in rules:
            # Create filter function based on rule criteria
            conditions = []
            
            # Level conditions
            if 'min_level' in rule:
                min_level = LogLevel(rule['min_level'])
                conditions.append(lambda r, ml=min_level: r.level >= ml)
            
            if 'max_level' in rule:
                max_level = LogLevel(rule['max_level'])
                conditions.append(lambda r, ml=max_level: r.level <= ml)
            
            # Type conditions
            if 'log_types' in rule:
                allowed_types = {LogType(t) for t in rule['log_types']}
                conditions.append(lambda r, at=allowed_types: r.log_type in at)
            
            # Logger name patterns
            if 'logger_patterns' in rule:
                patterns = rule['logger_patterns']
                conditions.append(lambda r, p=patterns: any(pat in r.logger_name for pat in p))
            
            # Exchange filter
            if 'exchanges' in rule:
                exchanges = set(rule['exchanges'])
                conditions.append(lambda r, ex=exchanges: r.exchange in ex)
            
            # Context filters
            if 'context_filters' in rule:
                context_filters = rule['context_filters']
                def check_context(r, filters=context_filters):
                    for key, expected_value in filters.items():
                        if r.context.get(key) != expected_value:
                            return False
                    return True
                conditions.append(check_context)
            
            # Metric name patterns
            if 'metric_patterns' in rule:
                patterns = rule['metric_patterns']
                conditions.append(lambda r, p=patterns: 
                    r.metric_name and any(pat in r.metric_name for pat in p))
            
            # Combine all conditions with AND
            if conditions:
                rule_func = lambda r, conds=conditions: all(cond(r) for cond in conds)
            else:
                # No conditions = match all
                rule_func = lambda r: True
            
            # Backend names for this rule
            backend_names = rule.get('backends', [])
            
            compiled.append((rule_func, backend_names))
        
        return compiled


class SimpleRouter(LogRouter):
    """
    Simple router with predefined routing logic.
    
    Good for standard configurations without complex rules.
    """
    
    def __init__(self, backends: Dict[str, LogBackend]):
        self.backends = backends
    
    def get_backends(self, record: LogRecord) -> List[LogBackend]:
        """Simple routing logic."""
        matching_backends = []
        
        # Route based on type and level
        if record.log_type == LogType.METRIC:
            # Metrics go to Prometheus and Datadog
            for name in ['prometheus', 'datadog']:
                backend = self.backends.get(name)
                if backend and backend.should_handle(record):
                    matching_backends.append(backend)
        
        elif record.log_type == LogType.AUDIT:
            # Audit logs go to file and Elasticsearch
            for name in ['file', 'elasticsearch']:
                backend = self.backends.get(name)
                if backend and backend.should_handle(record):
                    matching_backends.append(backend)
        
        elif record.level >= LogLevel.WARNING:
            # Warnings/errors go to file and console (dev)
            for name in ['file', 'console', 'datadog']:
                backend = self.backends.get(name)
                if backend and backend.should_handle(record):
                    matching_backends.append(backend)
        
        else:
            # Debug/info go to console only (dev)
            backend = self.backends.get('console')
            if backend and backend.should_handle(record):
                matching_backends.append(backend)
        
        return matching_backends


# Example routing configurations

DEVELOPMENT_ROUTING_RULES = [
    {
        'name': 'metrics_to_prometheus',
        'log_types': [LogType.METRIC],
        'backends': ['prometheus']
    },
    {
        'name': 'errors_to_file_and_console',
        'min_level': LogLevel.WARNING,
        'backends': ['file', 'console']
    },
    {
        'name': 'audit_to_file',
        'log_types': [LogType.AUDIT],
        'backends': ['file']
    },
    {
        'name': 'debug_to_console',
        'max_level': LogLevel.INFO,
        'backends': ['console']
    }
]

PRODUCTION_ROUTING_RULES = [
    {
        'name': 'metrics_to_prometheus_and_datadog',
        'log_types': [LogType.METRIC],
        'backends': ['prometheus', 'datadog']
    },
    {
        'name': 'critical_errors_to_all',
        'min_level': LogLevel.CRITICAL,
        'backends': ['file', 'datadog', 'elasticsearch']
    },
    {
        'name': 'errors_to_file_and_datadog',
        'min_level': LogLevel.ERROR,
        'max_level': LogLevel.ERROR,
        'backends': ['file', 'datadog']
    },
    {
        'name': 'warnings_to_file',
        'min_level': LogLevel.WARNING,
        'max_level': LogLevel.WARNING,
        'backends': ['file']
    },
    {
        'name': 'audit_to_file_and_elasticsearch',
        'log_types': [LogType.AUDIT],
        'backends': ['file', 'elasticsearch']
    },
    {
        'name': 'trading_metrics_special',
        'log_types': [LogType.METRIC],
        'metric_patterns': ['trade_', 'arbitrage_', 'latency_'],
        'backends': ['prometheus', 'datadog', 'elasticsearch']
    }
]