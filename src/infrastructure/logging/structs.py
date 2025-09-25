"""
Logging Configuration Structures

Provides structured configuration for the HFT logging system using msgspec.Struct
for type safety and performance.
"""

from typing import Optional, Dict, Any, List
from msgspec import Struct


class BackendConfig(Struct, frozen=True):
    """
    Base configuration for all logging backends.
    
    Attributes:
        enabled: Whether this backend is active
        min_level: Minimum log level to process (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        environment: Environment name (dev, prod, test)
    """
    enabled: bool = True
    min_level: str = "INFO"
    environment: Optional[str] = None
    
    def validate(self) -> None:
        """Validate backend configuration."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.min_level not in valid_levels:
            raise ValueError(f"Invalid log level: {self.min_level}")


class ConsoleBackendConfig(BackendConfig):
    """
    Console backend configuration.
    
    Attributes:
        color: Enable colored output
        include_context: Include context information
        max_message_length: Maximum message length before truncation
    """
    color: bool = True
    include_context: bool = True
    max_message_length: int = 1000

class FileBackendConfig(BackendConfig):
    """
    File backend configuration.
    
    Attributes:
        path: Log file path
        format: Output format (text or json)
        max_size_mb: Maximum file size in MB before rotation
        backup_count: Number of backup files to keep
        buffer_size: Write buffer size
        flush_interval: Flush interval in seconds
    """
    path: str = "logs/hft.log"
    format: str = "text"
    max_size_mb: int = 100
    backup_count: int = 5
    buffer_size: int = 1024
    flush_interval: float = 1.0
    
    def validate(self) -> None:
        """Validate file backend configuration."""
        super().validate()
        if self.format not in {"text", "json"}:
            raise ValueError(f"Invalid format: {self.format}")
        if self.max_size_mb <= 0:
            raise ValueError("max_size_mb must be positive")
        if self.backup_count < 0:
            raise ValueError("backup_count cannot be negative")


class PrometheusBackendConfig(BackendConfig):
    """
    Prometheus backend configuration.
    
    Attributes:
        push_gateway_url: Prometheus push gateway URL
        job_name: Job name for metrics
        batch_size: Metric batch size before push
        flush_interval: Flush interval in seconds
        histogram_buckets: Histogram bucket boundaries
    """
    push_gateway_url: str = "http://localhost:9091"
    job_name: str = "hft_arbitrage"
    batch_size: int = 100
    flush_interval: float = 5.0
    histogram_buckets: Optional[List[float]] = None
    
    def get_histogram_buckets(self) -> List[float]:
        """Get histogram buckets with defaults if not specified."""
        if self.histogram_buckets:
            return self.histogram_buckets
        # Default buckets for HFT latency tracking (ms)
        return [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0]


class AuditBackendConfig(BackendConfig):
    """
    Audit backend configuration for compliance logging.
    
    Attributes:
        path: Audit log file path
        format: Output format (json recommended for audit)
        include_all_context: Include all context data
        immutable: Make audit logs immutable
    """
    path: str = "logs/audit.log"
    format: str = "json"
    include_all_context: bool = True
    immutable: bool = True
    min_level: str = "INFO"  # Override default


class PerformanceConfig(Struct, frozen=True):
    """
    Performance configuration for HFT logger.
    
    Attributes:
        buffer_size: Ring buffer size for log messages
        batch_size: Batch size for backend dispatch
        dispatch_interval: Dispatch interval in seconds
        max_queue_size: Maximum queue size per backend
        enable_sampling: Enable message sampling for high volume
        sampling_rate: Sampling rate (1.0 = all messages)
    """
    buffer_size: int = 10000
    batch_size: int = 50
    dispatch_interval: float = 0.1
    max_queue_size: int = 50000
    enable_sampling: bool = False
    sampling_rate: float = 1.0
    
    def validate(self) -> None:
        """Validate performance configuration."""
        if self.buffer_size <= 0:
            raise ValueError("buffer_size must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.dispatch_interval <= 0:
            raise ValueError("dispatch_interval must be positive")
        if not 0 < self.sampling_rate <= 1.0:
            raise ValueError("sampling_rate must be between 0 and 1")


class RouterConfig(Struct, frozen=True):
    """
    Router configuration for message routing.
    
    Attributes:
        environment: Environment name (dev, prod, test)
        routing_rules: Routing rules mapping
        default_backends: Default backends for unmatched messages
        enable_smart_routing: Enable intelligent message routing
        correlation_tracking: Enable correlation ID tracking
    """
    environment: Optional[str] = None
    routing_rules: Optional[Dict[str, List[str]]] = None
    default_backends: Optional[List[str]] = None
    enable_smart_routing: bool = True
    correlation_tracking: bool = True
    
    def get_default_backends(self) -> List[str]:
        """Get default backends with fallback."""
        if self.default_backends is not None:
            return self.default_backends
        return ["console", "file"]  # Default fallback


class LoggingConfig(Struct, frozen=True):
    """
    Complete logging configuration.
    
    Attributes:
        environment: Environment name (dev, prod, test)
        console: Console backend configuration
        file: File backend configuration
        prometheus: Prometheus backend configuration
        audit: Audit backend configuration
        performance: Performance settings
        router: Router configuration
        default_context: Default context for all log messages
    """
    environment: str = "dev"
    console: Optional[ConsoleBackendConfig] = None
    file: Optional[FileBackendConfig] = None
    prometheus: Optional[PrometheusBackendConfig] = None
    audit: Optional[AuditBackendConfig] = None
    performance: Optional[PerformanceConfig] = None
    router: Optional[RouterConfig] = None
    default_context: Optional[Dict[str, Any]] = None
    
    def validate(self) -> None:
        """Validate complete configuration."""
        if self.environment not in {"dev", "prod", "test", "staging"}:
            raise ValueError(f"Invalid environment: {self.environment}")
        
        # Validate sub-configurations
        if self.console:
            self.console.validate()
        if self.file:
            self.file.validate()
        if self.prometheus:
            self.prometheus.validate()
        if self.audit:
            self.audit.validate()
        if self.performance:
            self.performance.validate()
    
    def get_enabled_backends(self) -> List[str]:
        """Get list of enabled backend names."""
        enabled = []
        if self.console and self.console.enabled:
            enabled.append("console")
        if self.file and self.file.enabled:
            enabled.append("file")
        if self.prometheus and self.prometheus.enabled:
            enabled.append("prometheus")
        if self.audit and self.audit.enabled:
            enabled.append("audit")
        return enabled
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility."""
        import msgspec
        return msgspec.structs.asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoggingConfig":
        """Create from dictionary."""
        # Convert nested dicts to structs
        if "console" in data and isinstance(data["console"], dict):
            data["console"] = ConsoleBackendConfig(**data["console"])
        if "file" in data and isinstance(data["file"], dict):
            data["file"] = FileBackendConfig(**data["file"])
        if "prometheus" in data and isinstance(data["prometheus"], dict):
            data["prometheus"] = PrometheusBackendConfig(**data["prometheus"])
        if "audit" in data and isinstance(data["audit"], dict):
            data["audit"] = AuditBackendConfig(**data["audit"])
        if "performance" in data and isinstance(data["performance"], dict):
            data["performance"] = PerformanceConfig(**data["performance"])
        if "router" in data and isinstance(data["router"], dict):
            data["router"] = RouterConfig(**data["router"])
        
        return cls(**data)
    
    @classmethod
    def default_development(cls) -> "LoggingConfig":
        """Get default development configuration."""
        return cls(
            environment="dev",
            console=ConsoleBackendConfig(
                enabled=True,
                min_level="DEBUG",
                color=True,
                include_context=True
            ),
            file=FileBackendConfig(
                enabled=True,
                min_level="INFO",
                path="logs/dev.log",
                format="text"
            ),
            performance=PerformanceConfig(
                buffer_size=10000,
                batch_size=50
            ),
            router=RouterConfig(
                default_backends=["console", "file"]
            )
        )
    
    @classmethod
    def default_production(cls) -> "LoggingConfig":
        """Get default production configuration."""
        return cls(
            environment="prod",
            console=ConsoleBackendConfig(
                enabled=False  # No console in production
            ),
            file=FileBackendConfig(
                enabled=True,
                min_level="WARNING",
                path="logs/production.log",
                format="json",
                max_size_mb=500,
                backup_count=10
            ),
            audit=AuditBackendConfig(
                enabled=True,
                min_level="INFO",
                path="logs/audit.log",
                format="json"
            ),
            prometheus=PrometheusBackendConfig(
                enabled=True,
                min_level="INFO",
                push_gateway_url="http://monitoring:9091"
            ),
            performance=PerformanceConfig(
                buffer_size=50000,
                batch_size=100,
                enable_sampling=True,
                sampling_rate=0.1  # Sample 10% in production
            ),
            router=RouterConfig(
                default_backends=["file", "audit"],
                enable_smart_routing=True
            )
        )


class LoggerComponentConfig(Struct, frozen=True):
    """
    Configuration for specific logger component.
    
    Used when creating component-specific loggers.
    
    Attributes:
        name: Logger name
        tags: Hierarchical tags for routing
        default_context: Default context values
        correlation_tracking: Enable correlation ID tracking
        performance_tracking: Enable performance metrics
    """
    name: str
    tags: Optional[List[str]] = None
    default_context: Optional[Dict[str, Any]] = None
    correlation_tracking: bool = False
    performance_tracking: bool = False
    
    def get_strategy_path(self) -> str:
        """Get strategy path from tags."""
        if not self.tags:
            return self.name
        return ".".join(self.tags)