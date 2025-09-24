from typing import Dict, Any

from infrastructure.networking.http import RequestStrategy, RequestContext, HTTPMethod, PerformanceTargets
from config.structs import ExchangeConfig

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger


class MexcRequestStrategy(RequestStrategy):
    """MEXC-specific request configuration based on ExchangeConfig."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None):
        """
        Initialize MEXC request strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing base_url and settings
            logger: Optional HFT logger injection
        """
        super().__init__(exchange_config.base_url)
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            tags = ['mexc', 'public', 'rest', 'request']  # Default to public
            logger = get_strategy_logger('rest.request.mexc.public', tags)
        
        self.logger = logger
        self.exchange_config = exchange_config
        
        # Log strategy initialization
        self.logger.info("MEXC request strategy initialized",
                        base_url=exchange_config.base_url,
                        has_network_config=exchange_config.network is not None)
        
        self.logger.metric("rest_request_strategies_created", 1,
                          tags={"exchange": "mexc"})

    async def create_request_context(self) -> RequestContext:
        """Create MEXC request configuration from ExchangeConfig."""
        # Use network config if available, otherwise MEXC defaults
        if self.exchange_config.network:
            connection_timeout = self.exchange_config.network.connect_timeout
            read_timeout = self.exchange_config.network.request_timeout - connection_timeout
            max_concurrent = 5  # MEXC default
        else:
            # MEXC HFT defaults
            connection_timeout = 1.5
            read_timeout = 4.0
            max_concurrent = 5
        
        return RequestContext(
            base_url=self.base_url,
            timeout=connection_timeout + read_timeout,
            max_concurrent=max_concurrent,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            keepalive_timeout=30,  # MEXC default
            default_headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "HFTArbitrageEngine-MEXC/1.0"
            }
        )

    async def prepare_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Prepare MEXC-specific request parameters."""
        request_kwargs = {
            'headers': headers.copy(),
        }

        # MEXC uses query parameters for authenticated requests (all params in query string)
        # For non-authenticated requests, use JSON body for POST/PUT/DELETE
        if method == HTTPMethod.GET:
            if params:
                request_kwargs['params'] = params
        elif method in [HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.DELETE]:
            # MEXC authenticated endpoints require all parameters in query string
            # The transport manager will add auth parameters to query string
            # For now, add params to JSON body - auth parameters will override to query string
            if params:
                if 'Content-Type' not in headers or headers['Content-Type'] == 'application/json':
                    # Use JSON for complex data (non-authenticated requests)
                    request_kwargs['json'] = params
                else:
                    # Use form data for simple parameters
                    request_kwargs['data'] = params

        return request_kwargs

    def get_performance_targets(self) -> PerformanceTargets:
        """Get MEXC-specific HFT performance targets."""
        return PerformanceTargets(
            max_latency_ms=40.0,  # MEXC has good latency characteristics
            max_retry_attempts=2,  # Fast failure for HFT
            connection_timeout_ms=1500.0,
            read_timeout_ms=4000.0,
            target_throughput_rps=15.0  # Conservative for stability
        )