"""
Request Strategy Interface

Strategy for HTTP request configuration and execution.
Handles connection setup, request formatting, and performance targets.

HFT COMPLIANT: <100μs configuration overhead.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

from ..structs import HTTPMethod
from .structs import RequestContext, PerformanceTargets


class RequestStrategy(ABC):
    """
    Strategy for HTTP request configuration and execution.
    
    Handles connection setup, request formatting, and performance targets.
    HFT COMPLIANT: <100μs configuration overhead.
    """
    
    @abstractmethod
    async def create_request_context(self) -> RequestContext:
        """
        Create request configuration.
        
        Returns:
            RequestContext with URL, timeouts, connection limits
        """
        pass
    
    @abstractmethod
    async def prepare_request(
        self, 
        method: HTTPMethod, 
        endpoint: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Prepare request parameters with exchange-specific formatting.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Request parameters
            headers: Request headers
            
        Returns:
            Prepared request parameters for aiohttp
        """
        pass
    
    @abstractmethod
    def get_performance_targets(self) -> PerformanceTargets:
        """
        Get HFT performance targets for this exchange.
        
        Returns:
            PerformanceTargets with latency and throughput requirements
        """
        pass

    def __init__(self, base_url: str, **kwargs):
        self.base_url = base_url