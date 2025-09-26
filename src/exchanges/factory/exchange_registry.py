"""
Exchange Registry for Composite Pattern Factory.

Central registry of all exchange implementations with features and capabilities.
Supports both spot and futures exchanges with type safety and feature detection.
"""

from dataclasses import dataclass, field
from typing import Type, Optional, List, Set, Dict
from enum import Enum

from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicExchange
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateExchange


class ExchangeType(Enum):
    """Exchange type classification."""
    SPOT = "spot"
    FUTURES = "futures"


@dataclass
class ExchangeImplementation:
    """Registry entry for exchange implementation."""
    public_class: Type[CompositePublicExchange]
    private_class: Type[CompositePrivateExchange]
    exchange_type: ExchangeType
    features: Set[str] = field(default_factory=set)
    rate_limits: Dict[str, int] = field(default_factory=dict)
    supported_order_types: Set[str] = field(default_factory=set)


class ExchangeRegistry:
    """Central registry of all exchange implementations."""
    
    IMPLEMENTATIONS = {
        "mexc_spot": ExchangeImplementation(
            public_class=None,  # Will be dynamically imported
            private_class=None,  # Will be dynamically imported
            exchange_type=ExchangeType.SPOT,
            features={"spot", "margin", "websocket", "rest", "24x7"},
            rate_limits={
                "public": 20,  # requests per second
                "private": 10
            },
            supported_order_types={"LIMIT", "MARKET", "STOP_LOSS", "TAKE_PROFIT"}
        ),
        "gateio_spot": ExchangeImplementation(
            public_class=None,  # Will be dynamically imported
            private_class=None,  # Will be dynamically imported
            exchange_type=ExchangeType.SPOT,
            features={"spot", "margin", "websocket", "rest", "lending", "24x7"},
            rate_limits={
                "public": 900,  # requests per second (Gate.io has high limits)
                "private": 10
            },
            supported_order_types={"LIMIT", "MARKET", "STOP_LOSS", "TAKE_PROFIT", "IOC", "FOK"}
        ),
        "gateio_futures": ExchangeImplementation(
            public_class=None,  # Will be dynamically imported
            private_class=None,  # Will be dynamically imported
            exchange_type=ExchangeType.FUTURES,
            features={"futures", "leverage", "positions", "funding_rate", "websocket", "rest", "24x7"},
            rate_limits={
                "public": 900,  # requests per second (Gate.io has high limits)
                "private": 10
            },
            supported_order_types={"LIMIT", "MARKET", "STOP_LOSS", "TAKE_PROFIT", "IOC", "FOK", "REDUCE_ONLY", "CLOSE_POSITION"}
        ),
    }
    
    @classmethod
    def get_implementation(cls, name: str) -> Optional[ExchangeImplementation]:
        """Get implementation by name."""
        return cls.IMPLEMENTATIONS.get(name)
    
    @classmethod
    def list_exchanges(cls, exchange_type: Optional[ExchangeType] = None) -> List[str]:
        """List available exchanges optionally filtered by type."""
        if exchange_type:
            return [
                name for name, impl in cls.IMPLEMENTATIONS.items()
                if impl.exchange_type == exchange_type
            ]
        return list(cls.IMPLEMENTATIONS.keys())
    
    @classmethod
    def has_feature(cls, exchange_name: str, feature: str) -> bool:
        """Check if exchange has a specific feature."""
        impl = cls.get_implementation(exchange_name)
        return impl and feature in impl.features
    
    @classmethod
    def get_rate_limit(cls, exchange_name: str, api_type: str = "public") -> Optional[int]:
        """Get rate limit for exchange and API type."""
        impl = cls.get_implementation(exchange_name)
        return impl.rate_limits.get(api_type) if impl else None
    
    @classmethod
    def supports_order_type(cls, exchange_name: str, order_type: str) -> bool:
        """Check if exchange supports a specific order type."""
        impl = cls.get_implementation(exchange_name)
        return impl and order_type in impl.supported_order_types
    
    @classmethod
    def list_spot_exchanges(cls) -> List[str]:
        """List all spot trading exchanges."""
        return cls.list_exchanges(ExchangeType.SPOT)
    
    @classmethod
    def list_futures_exchanges(cls) -> List[str]:
        """List all futures trading exchanges."""
        return cls.list_exchanges(ExchangeType.FUTURES)
    
    
    @classmethod
    def get_all_features(cls) -> Set[str]:
        """Get all available features across exchanges."""
        all_features = set()
        for impl in cls.IMPLEMENTATIONS.values():
            all_features.update(impl.features)
        return all_features


@dataclass
class ExchangePair:
    """Container for public and private exchange instances."""
    public: CompositePublicExchange
    private: Optional[CompositePrivateExchange] = None
    
    @property
    def has_private(self) -> bool:
        """Check if private exchange is available."""
        return self.private is not None
    
    async def close(self):
        """Close both exchanges."""
        if self.public:
            await self.public.close()
        if self.private:
            await self.private.close()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Dynamic import helper for late binding
def get_exchange_implementation(exchange_name: str) -> ExchangeImplementation:
    """
    Get exchange implementation with dynamic class loading.
    
    This allows us to avoid circular imports while maintaining type safety.
    """
    impl = ExchangeRegistry.get_implementation(exchange_name)
    if not impl:
        raise ValueError(f"Unknown exchange: {exchange_name}")
    
    # Dynamic import based on exchange name
    if exchange_name == "mexc_spot":
        from exchanges.integrations.mexc.mexc_composite_public import MexcCompositePublicExchange
        from exchanges.integrations.mexc.mexc_composite_private import MexcCompositePrivateExchange
        impl.public_class = MexcCompositePublicExchange
        impl.private_class = MexcCompositePrivateExchange
        
    elif exchange_name == "gateio_spot":
        from exchanges.integrations.gateio.gateio_composite_public import GateioCompositePublicExchange
        from exchanges.integrations.gateio.gateio_composite_private import GateioCompositePrivateExchange
        impl.public_class = GateioCompositePublicExchange
        impl.private_class = GateioCompositePrivateExchange
        
    elif exchange_name == "gateio_futures":
        from exchanges.integrations.gateio.gateio_futures_composite_public import GateioFuturesCompositePublicExchange
        from exchanges.integrations.gateio.gateio_futures_composite_private import GateioFuturesCompositePrivateExchange
        impl.public_class = GateioFuturesCompositePublicExchange
        impl.private_class = GateioFuturesCompositePrivateExchange
        
    
    return impl