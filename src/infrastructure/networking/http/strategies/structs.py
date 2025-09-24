"""
REST Transport Strategy Data Structures

Common data structures used by REST transport strategies.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Any


@dataclass(frozen=True)
class RequestContext:
    """Request configuration context."""
    base_url: str
    timeout: float
    max_concurrent: int
    connection_timeout: float = 2.0
    read_timeout: float = 5.0
    keepalive_timeout: float = 60.0
    default_headers: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class RateLimitContext:
    """Rate limiting configuration for endpoints."""
    requests_per_second: float
    burst_capacity: int
    endpoint_weight: int = 1
    global_weight: int = 1
    cooldown_period: float = 0.1


@dataclass(frozen=True)
class AuthenticationData:
    """Authentication data containing headers, parameters, and optional request data."""
    headers: Dict[str, str]
    params: Dict[str, Any]
    data: Optional[str] = None  # For exchanges that need to control request body directly


@dataclass(frozen=True)
class PerformanceTargets:
    """HFT performance targets for exchange."""
    max_latency_ms: float = 50.0
    max_retry_attempts: int = 3
    connection_timeout_ms: float = 2000.0
    read_timeout_ms: float = 5000.0
    target_throughput_rps: float = 100.0


@dataclass
class RequestMetrics:
    """HFT-compliant request performance metrics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    rate_limit_hits: int = 0
    sub_50ms_requests: int = 0
    latency_violations: int = 0