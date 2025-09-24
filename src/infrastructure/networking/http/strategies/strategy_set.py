"""
REST Strategy Set Container

Container for complete REST strategy configuration.
HFT COMPLIANT: Zero-allocation strategy access.
"""

from typing import Optional

from .request import RequestStrategy
from .rate_limit import RateLimitStrategy
from .retry import RetryStrategy
from .auth import AuthStrategy
from .exception_handler import ExceptionHandlerStrategy
from .structs import PerformanceTargets

# HFT Logger Integration
from infrastructure.logging import get_logger


class RestStrategySet:
    """
    Container for complete REST strategy configuration.
    
    HFT COMPLIANT: Zero-allocation strategy access.
    """
    
    def __init__(
        self,
        request_strategy: RequestStrategy,
        rate_limit_strategy: RateLimitStrategy,
        retry_strategy: RetryStrategy,
        auth_strategy: Optional[AuthStrategy] = None,
        exception_handler_strategy: Optional[ExceptionHandlerStrategy] = None,
        logger=None
    ):
        self.request_strategy = request_strategy
        self.rate_limit_strategy = rate_limit_strategy
        self.retry_strategy = retry_strategy
        self.auth_strategy = auth_strategy
        self.exception_handler_strategy = exception_handler_strategy
        
        # Initialize HFT logger with optional injection
        self.logger = logger or get_logger('rest.strategy_set.core')
        
        # HFT Optimization: Pre-validate strategy compatibility
        self._validate_strategies()
        self._performance_targets = request_strategy.get_performance_targets()
        
        # Track strategy set creation metrics
        self.logger.info("REST strategy set created",
                        has_auth=auth_strategy is not None,
                        has_exception_handler=exception_handler_strategy is not None)
        
        self.logger.metric("rest_strategy_sets_created", 1,
                          tags={"type": "core"})
    
    def _validate_strategies(self) -> None:
        """Validate strategy compatibility at initialization."""
        if not all([
            self.request_strategy,
            self.rate_limit_strategy,
            self.retry_strategy
        ]):
            raise ValueError("Request, rate limit, and retry strategies must be provided")
    
    def get_performance_targets(self) -> PerformanceTargets:
        """Get performance targets from request strategy."""
        return self._performance_targets