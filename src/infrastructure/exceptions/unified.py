"""
Unified Exception Hierarchy for Error Processing

Provides standardized error handling with consistent correlation tracking
and context management across all exchange integrations.

HFT COMPLIANT: Minimal overhead exception creation with correlation tracking.
"""

import time
import uuid
from typing import Optional, Dict, Any
from enum import Enum

from .exchange import ExchangeRestError


class ErrorType(Enum):
    """Standardized error type classification."""
    PARSING = "parsing"
    SUBSCRIPTION = "subscription" 
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class UnifiedExchangeRestError(ExchangeRestError):
    """
    Unified exchange error with correlation tracking and structured context.
    
    Provides consistent error handling across all exchange integrations
    with correlation tracking for debugging and monitoring.
    """
    
    def __init__(
        self, 
        exchange: str,
        error_type: ErrorType,
        message: str,
        correlation_id: Optional[str] = None,
        channel: Optional[str] = None,
        symbol: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None,
        **context
    ):
        """
        Initialize unified exchange error.
        
        Args:
            exchange: Exchange name (e.g., 'mexc', 'gateio')
            error_type: Standardized error type classification
            message: Human-readable error message
            correlation_id: Optional correlation ID for tracking
            channel: WebSocket channel where error occurred
            symbol: Trading symbol related to error
            raw_data: Original raw data that caused the error
            **context: Additional context information
        """
        super().__init__(code=-1, message=message)
        
        self.exchange = exchange
        self.error_type = error_type
        self.correlation_id = correlation_id or self._generate_correlation_id()
        self.channel = channel
        self.symbol = symbol
        self.raw_data = raw_data or {}
        self.context = context
        self.timestamp = time.time()
        
    def _generate_correlation_id(self) -> str:
        """Generate unique correlation ID for error tracking."""
        return f"{self.exchange}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to structured dictionary for logging."""
        return {
            "correlation_id": self.correlation_id,
            "exchange": self.exchange,
            "error_type": self.error_type.value,
            "message": self.message,
            "channel": self.channel,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "raw_data": self.raw_data,
            "context": self.context
        }
    
    def __str__(self) -> str:
        """String representation with correlation tracking."""
        return f"[{self.correlation_id}] {self.exchange}/{self.error_type.value}: {self.message}"


class UnifiedParsingError(UnifiedExchangeRestError):
    """Error during message parsing operations."""
    
    def __init__(self, exchange: str, message: str, **kwargs):
        super().__init__(exchange, ErrorType.PARSING, message, **kwargs)


class UnifiedSubscriptionError(UnifiedExchangeRestError):
    """Error during subscription operations."""
    
    def __init__(self, exchange: str, message: str, **kwargs):
        super().__init__(exchange, ErrorType.SUBSCRIPTION, message, **kwargs)


class UnifiedConnectionError(UnifiedExchangeRestError):
    """Error during connection operations."""
    
    def __init__(self, exchange: str, message: str, **kwargs):
        super().__init__(exchange, ErrorType.CONNECTION, message, **kwargs)


class UnifiedValidationError(UnifiedExchangeRestError):
    """Error during validation operations."""
    
    def __init__(self, exchange: str, message: str, **kwargs):
        super().__init__(exchange, ErrorType.VALIDATION, message, **kwargs)


class UnifiedRateLimitError(UnifiedExchangeRestError):
    """Error due to rate limiting."""
    
    def __init__(self, exchange: str, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(exchange, ErrorType.RATE_LIMIT, message, **kwargs)
        self.retry_after = retry_after