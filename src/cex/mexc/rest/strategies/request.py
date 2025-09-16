from typing import Dict, Any

from core.transport.rest import RequestStrategy, RequestContext, HTTPMethod, PerformanceTargets


class MexcRequestStrategy(RequestStrategy):
    """MEXC-specific request configuration with aggressive HFT settings."""

    def __init__(self, base_url: str = "https://api.mexc.com", **kwargs):
        super().__init__(base_url, **kwargs)

    async def create_request_context(self) -> RequestContext:
        """Create MEXC-optimized request configuration."""
        return RequestContext(
            base_url=self.base_url,
            timeout=8.0,  # Aggressive timeout for HFT
            max_concurrent=5,  # MEXC-specific concurrency limit
            connection_timeout=1.5,  # Fast connection establishment
            read_timeout=4.0,  # Fast read timeout
            keepalive_timeout=30,  # Shorter keepalive for fresh connections
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
