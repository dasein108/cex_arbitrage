from typing import Dict, Any

from infrastructure.networking.http import RequestStrategy, RequestContext, HTTPMethod, PerformanceTargets
from config.structs import ExchangeConfig


class GateioRequestStrategy(RequestStrategy):
    """Gate.io-specific request configuration based on ExchangeConfig."""

    def __init__(self, exchange_config: ExchangeConfig, logger=None, **kwargs):
        """
        Initialize Gate.io request strategy from ExchangeConfig.
        
        Args:
            exchange_config: Exchange configuration containing base_url and settings
            logger: Optional HFT logger injection
            **kwargs: Additional parameters (ignored for compatibility)
        """
        super().__init__(exchange_config.base_url)
        self.exchange_config = exchange_config
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            from infrastructure.logging import get_strategy_logger
            tags = ['gateio', 'rest', 'request']
            logger = get_strategy_logger('rest.request.gateio', tags)
        self.logger = logger

    async def create_request_context(self) -> RequestContext:
        """Create Gate.io request configuration from ExchangeConfig."""
        # Use network config if available, otherwise Gate.io defaults
        if self.exchange_config.network:
            connection_timeout = self.exchange_config.network.connect_timeout
            read_timeout = self.exchange_config.network.request_timeout - connection_timeout
            max_concurrent = 8  # Gate.io default
        else:
            # Gate.io HFT defaults
            connection_timeout = 2.0
            read_timeout = 5.0
            max_concurrent = 8
        
        return RequestContext(
            base_url=self.base_url,
            timeout=connection_timeout + read_timeout,
            max_concurrent=max_concurrent,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            keepalive_timeout=30,  # Gate.io default
            default_headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "HFTArbitrageEngine-Gateio/1.0"
            }
        )

    async def prepare_request(
        self,
        method: HTTPMethod,
        endpoint: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Prepare Gate.io-specific request parameters."""
        request_kwargs = {
            'headers': headers.copy(),
        }

        # Gate.io uses different parameter passing based on method:
        # - GET: Query parameters
        # - POST/PUT/DELETE: JSON body for data, query parameters for filters
        if method == HTTPMethod.GET:
            if params:
                request_kwargs['params'] = params
        elif method in [HTTPMethod.POST, HTTPMethod.PUT]:
            # Gate.io POST/PUT requests use raw JSON data, not json parameter
            # This matches the official example: data=request_content
            if params:
                import json
                request_kwargs['data'] = json.dumps(params, separators=(',', ':'))
                # Ensure Content-Type is set
                request_kwargs['headers']['Content-Type'] = 'application/json'

        return request_kwargs

    def get_performance_targets(self) -> PerformanceTargets:
        """Get Gate.io-specific HFT performance targets."""
        return PerformanceTargets(
            max_latency_ms=50.0,  # Gate.io slightly higher latency than MEXC
            max_retry_attempts=2,  # Fast failure for HFT
            connection_timeout_ms=2000.0,
            read_timeout_ms=5000.0,
            target_throughput_rps=12.0  # Conservative due to stricter rate limits
        )