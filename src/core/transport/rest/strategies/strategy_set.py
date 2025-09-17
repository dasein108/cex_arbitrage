"""
REST Strategy Set Container

Container for complete REST strategy configuration.
HFT COMPLIANT: Zero-allocation strategy access.
"""

import logging
from typing import Optional

from .request import RequestStrategy
from .rate_limit import RateLimitStrategy
from .retry import RetryStrategy
from .auth import AuthStrategy
from .exception_handler import ExceptionHandlerStrategy
from .structs import PerformanceTargets


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
        exception_handler_strategy: Optional[ExceptionHandlerStrategy] = None
    ):
        self.request_strategy = request_strategy
        self.rate_limit_strategy = rate_limit_strategy
        self.retry_strategy = retry_strategy
        self.auth_strategy = auth_strategy
        self.exception_handler_strategy = exception_handler_strategy
        
        # HFT Optimization: Pre-validate strategy compatibility
        self._validate_strategies()
        self._performance_targets = request_strategy.get_performance_targets()
        
        self.logger = logging.getLogger(__name__)
    
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