from abc import ABC, abstractmethod
from typing import Dict, Any

from infrastructure.networking.http import RequestStrategy, RequestContext, HTTPMethod, PerformanceTargets
from config.structs import ExchangeConfig


class BaseExchangeRequestStrategy(RequestStrategy, ABC):
    """
    Base request strategy for exchanges with common request handling patterns.
    
    Provides shared functionality for:
    - Request context creation from ExchangeConfig
    - Common header management
    - Performance target definitions
    - Request preparation patterns
    """

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize base exchange request strategy.
        
        Args:
            exchange_config: Exchange configuration containing base_url and settings
            logger: Optional HFT logger injection
            **kwargs: Additional parameters for exchange-specific needs
        """
        super().__init__(exchange_config.base_url)
        self.exchange_config = exchange_config
        
        # Initialize logger if not provided
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = [self.exchange_name.lower(), 'rest', 'request']
            logger = get_strategy_logger(f'rest.request.{self.exchange_name.lower()}', tags)
        self.logger = logger

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Exchange name for logging and identification."""
        pass

    @abstractmethod
    def get_default_timeouts(self) -> tuple[float, float]:
        """
        Get default timeouts for this exchange.
        
        Returns:
            tuple: (connection_timeout, read_timeout)
        """
        pass

    @abstractmethod
    def get_default_concurrent_limit(self) -> int:
        """Get default maximum concurrent connections for this exchange."""
        pass

    @abstractmethod
    def get_default_headers(self) -> Dict[str, str]:
        """Get exchange-specific default headers."""
        pass

    @abstractmethod
    def get_performance_targets(self) -> PerformanceTargets:
        """Get exchange-specific HFT performance targets."""
        pass

    async def create_request_context(self) -> RequestContext:
        """Create request configuration from ExchangeConfig."""
        # Use network config if available, otherwise exchange defaults
        if self.exchange_config.network:
            connection_timeout = self.exchange_config.network.connect_timeout
            read_timeout = self.exchange_config.network.request_timeout - connection_timeout
            max_concurrent = self.get_default_concurrent_limit()  # Use exchange default
        else:
            connection_timeout, read_timeout = self.get_default_timeouts()
            max_concurrent = self.get_default_concurrent_limit()
        
        return RequestContext(
            base_url=self.base_url,
            timeout=connection_timeout + read_timeout,
            max_concurrent=max_concurrent,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            keepalive_timeout=self._get_keepalive_timeout(),
            default_headers=self.get_default_headers()
        )

    @abstractmethod
    def _get_keepalive_timeout(self) -> int:
        """Get keepalive timeout for this exchange."""
        pass

    async def prepare_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Prepare exchange-specific request parameters."""
        request_kwargs = {
            'headers': headers.copy(),
        }

        # Apply exchange-specific parameter handling
        self._apply_method_specific_params(method, params, request_kwargs)
        
        return request_kwargs

    @abstractmethod
    def _apply_method_specific_params(
        self,
        method: HTTPMethod,
        params: Dict[str, Any],
        request_kwargs: Dict[str, Any]
    ) -> None:
        """
        Apply exchange-specific parameter handling based on HTTP method.
        
        Args:
            method: HTTP method
            params: Request parameters
            request_kwargs: Request kwargs to modify in-place
        """
        pass