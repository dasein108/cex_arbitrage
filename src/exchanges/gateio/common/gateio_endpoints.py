"""
Gate.io Endpoint Path Management

Centralized endpoint path construction for Gate.io futures API.
Eliminates code duplication in path building and provides consistent URL management.

Key Features:
- Centralized endpoint definitions
- Consistent path construction patterns
- Template-based path building for parameterized endpoints
- Separation between REST endpoints and signature paths
- Type-safe endpoint access

Architecture: Factory pattern for endpoint path construction
Performance: <1ms path resolution with pre-compiled templates
"""

from typing import Dict, Tuple, Optional
from enum import Enum
from functools import lru_cache


class GateioFuturesEndpoint(Enum):
    """
    Enumeration of Gate.io futures API endpoints.

    Provides type-safe access to all supported endpoints with consistent naming.
    """
    ACCOUNTS = "accounts"
    POSITIONS = "positions"
    SINGLE_POSITION = "single_position"
    ORDERS = "orders"
    SINGLE_ORDER = "single_order"
    CANCEL_ORDER = "cancel_order"
    CANCEL_ALL_ORDERS = "cancel_all_orders"
    ORDER_HISTORY = "order_history"
    LISTEN_KEY = "listen_key"


class GateioFuturesEndpoints:
    """
    Centralized endpoint path management for Gate.io futures API.

    Eliminates code duplication by providing consistent path construction
    for both REST client requests and authentication signature generation.
    """

    # Endpoint path templates (relative to cex URL)
    ENDPOINT_TEMPLATES = {
        GateioFuturesEndpoint.ACCOUNTS: "/accounts",
        GateioFuturesEndpoint.POSITIONS: "/positions",
        GateioFuturesEndpoint.SINGLE_POSITION: "/positions/{contract}",
        GateioFuturesEndpoint.ORDERS: "/orders",
        GateioFuturesEndpoint.SINGLE_ORDER: "/orders/{order_id}",
        GateioFuturesEndpoint.CANCEL_ORDER: "/orders/{order_id}",
        GateioFuturesEndpoint.CANCEL_ALL_ORDERS: "/orders",
        GateioFuturesEndpoint.ORDER_HISTORY: "/orders",
        GateioFuturesEndpoint.LISTEN_KEY: "/user_data_stream",
    }

    # Base paths for different API versions
    FUTURES_USDT_BASE = "/api/v4/futures/usdt"

    @classmethod
    @lru_cache(maxsize=1000)
    def get_endpoint_paths(
        cls,
        endpoint: GateioFuturesEndpoint,
        **params: str
    ) -> Tuple[str, str]:
        """
        Get both REST endpoint and signature path for authentication.

        Args:
            endpoint: The endpoint type to construct paths for
            **params: Parameters for template substitution (e.g., contract="BTC_USDT")

        Returns:
            Tuple of (rest_endpoint, signature_path) where:
            - rest_endpoint: Path for REST client requests (relative to cex URL)
            - signature_path: Full path for signature generation (includes API version)

        Example:
            get_endpoint_paths(GateioFuturesEndpoint.SINGLE_POSITION, contract="BTC_USDT")
            Returns: ("/positions/BTC_USDT", "/api/v4/futures/usdt/positions/BTC_USDT")
        """
        if endpoint not in cls.ENDPOINT_TEMPLATES:
            raise ValueError(f"Unknown endpoint: {endpoint}")

        # Get the template and substitute parameters
        template = cls.ENDPOINT_TEMPLATES[endpoint]

        try:
            rest_endpoint = template.format(**params)
        except KeyError as e:
            raise ValueError(f"Missing required parameter for endpoint {endpoint}: {e}")

        # Create full signature path
        signature_path = f"{cls.FUTURES_USDT_BASE}{rest_endpoint}"

        return rest_endpoint, signature_path

    @classmethod
    def get_rest_endpoint(cls, endpoint: GateioFuturesEndpoint, **params: str) -> str:
        """
        Get REST endpoint path only (for REST client).

        Args:
            endpoint: The endpoint type
            **params: Parameters for template substitution

        Returns:
            REST endpoint path relative to cex URL
        """
        rest_endpoint, _ = cls.get_endpoint_paths(endpoint, **params)
        return rest_endpoint

    @classmethod
    def get_signature_path(cls, endpoint: GateioFuturesEndpoint, **params: str) -> str:
        """
        Get full signature path (for authentication).

        Args:
            endpoint: The endpoint type
            **params: Parameters for template substitution

        Returns:
            Full path for signature generation including API version
        """
        _, signature_path = cls.get_endpoint_paths(endpoint, **params)
        return signature_path

    @classmethod
    def validate_endpoint_params(cls, endpoint: GateioFuturesEndpoint, **params: str) -> bool:
        """
        Validate that all required parameters are provided for an endpoint.

        Args:
            endpoint: The endpoint type to validate
            **params: Parameters to validate

        Returns:
            True if all required parameters are provided

        Raises:
            ValueError: If required parameters are missing
        """
        template = cls.ENDPOINT_TEMPLATES.get(endpoint)
        if not template:
            raise ValueError(f"Unknown endpoint: {endpoint}")

        try:
            template.format(**params)
            return True
        except KeyError as e:
            raise ValueError(f"Missing required parameter for endpoint {endpoint}: {e}")

    @classmethod
    def get_available_endpoints(cls) -> Dict[GateioFuturesEndpoint, str]:
        """
        Get all available endpoints and their templates.

        Returns:
            Dictionary mapping endpoint enums to their path templates
        """
        return cls.ENDPOINT_TEMPLATES.copy()

    @classmethod
    def clear_cache(cls):
        """Clear the LRU cache - useful for testing."""
        cls.get_endpoint_paths.cache_clear()


class GateioFuturesEndpointBuilder:
    """
    Fluent cex builder for Gate.io futures endpoints.

    Provides a more expressive way to build endpoint paths with method chaining.
    """

    def __init__(self):
        self._endpoint: Optional[GateioFuturesEndpoint] = None
        self._params: Dict[str, str] = {}

    def endpoint(self, endpoint: GateioFuturesEndpoint) -> 'GateioFuturesEndpointBuilder':
        """Set the endpoint type."""
        self._endpoint = endpoint
        return self

    def with_contract(self, contract: str) -> 'GateioFuturesEndpointBuilder':
        """Add contract parameter (for position and order endpoints)."""
        self._params['contract'] = contract
        return self

    def with_order_id(self, order_id: str) -> 'GateioFuturesEndpointBuilder':
        """Add order_id parameter (for order-specific endpoints)."""
        self._params['order_id'] = order_id
        return self

    def build(self) -> Tuple[str, str]:
        """
        Build the endpoint paths.

        Returns:
            Tuple of (rest_endpoint, signature_path)

        Raises:
            ValueError: If endpoint not set or required parameters missing
        """
        if self._endpoint is None:
            raise ValueError("Endpoint must be set before building")

        return GateioFuturesEndpoints.get_endpoint_paths(self._endpoint, **self._params)

    def build_rest_endpoint(self) -> str:
        """Build REST endpoint path only."""
        rest_endpoint, _ = self.build()
        return rest_endpoint

    def build_signature_path(self) -> str:
        """Build signature path only."""
        _, signature_path = self.build()
        return signature_path


# Convenience functions for common patterns
def build_accounts_paths() -> Tuple[str, str]:
    """Build paths for accounts endpoint."""
    return GateioFuturesEndpoints.get_endpoint_paths(GateioFuturesEndpoint.ACCOUNTS)


def build_positions_paths() -> Tuple[str, str]:
    """Build paths for positions endpoint."""
    return GateioFuturesEndpoints.get_endpoint_paths(GateioFuturesEndpoint.POSITIONS)


def build_single_position_paths(contract: str) -> Tuple[str, str]:
    """Build paths for single position endpoint."""
    return GateioFuturesEndpoints.get_endpoint_paths(
        GateioFuturesEndpoint.SINGLE_POSITION,
        contract=contract
    )


def build_orders_paths() -> Tuple[str, str]:
    """Build paths for orders endpoint."""
    return GateioFuturesEndpoints.get_endpoint_paths(GateioFuturesEndpoint.ORDERS)


def build_single_order_paths(order_id: str) -> Tuple[str, str]:
    """Build paths for single order endpoint."""
    return GateioFuturesEndpoints.get_endpoint_paths(
        GateioFuturesEndpoint.SINGLE_ORDER,
        order_id=order_id
    )