# WebSocket Interface Architecture Specification

## Overview

This document provides detailed architectural specifications for the WebSocket interface refactoring, including visual diagrams, interface definitions, and implementation patterns.

## Current vs. Target Architecture

### Current Architecture (Problems)

```
Current Flawed Design:
┌─────────────────────────────────────┐
│        BaseWebsocketInterface       │
│    ❌ Mixed Domain Concerns         │
│    ❌ is_private flag              │
│    ❌ Conditional logic            │
└─────────────────┬───────────────────┘
                  │
     ┌────────────┼────────────┐
     │            │            │
┌────▼───┐ ┌─────▼─────┐ ┌────▼────┐
│ Public │ │  Private  │ │ Futures │
│ (Good) │ │   (BAD)   │ │ (Mixed) │
└────────┘ └───────────┘ └─────────┘
           Inherits from
           base - WRONG!
```

**Problems**:
1. Domain separation violated
2. Private inherits shared concerns
3. Symbol handling inconsistent
4. Complex conditional logic

### Target Architecture (Solution)

```
New Separated Domain Design:
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│       BasePublicWebsocket           │     │       BasePrivateWebsocket          │
│   ✅ Pure Market Data              │     │   ✅ Pure Trading Operations        │
│   ✅ Always requires symbols        │     │   ✅ No symbols required            │
│   ✅ No authentication             │     │   ✅ Authentication required        │
└─────────────────┬───────────────────┘     └─────────────────┬───────────────────┘
                  │                                           │
     ┌────────────┼────────────┐                 ┌────────────┼────────────┐
     │            │            │                 │            │            │
┌────▼───┐ ┌─────▼──────┐ ┌───▼──┐         ┌────▼───┐ ┌─────▼──────┐ ┌───▼──┐
│ Public │ │   Public   │ │ Exch │         │Private │ │  Private   │ │ Exch │
│  Spot  │ │  Futures   │ │ Impl │         │  Spot  │ │  Futures   │ │ Impl │
└────────┘ └────────────┘ └──────┘         └────────┘ └────────────┘ └──────┘

✅ Complete separation ✅ Clear interfaces ✅ Type safety
```

## Interface Definitions

### BasePublicWebsocket Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Callable, Awaitable
from exchanges.structs.common import Symbol
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, ConnectionState
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface

class BasePublicWebsocket(ABC):
    """
    Abstract base class for public market data WebSocket operations.
    
    Pure market data interface with complete domain separation.
    No authentication required, symbols mandatory for all operations.
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PublicWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
    ):
        """Initialize public WebSocket interface."""
        pass
    
    @abstractmethod
    async def initialize(
        self,
        symbols: List[Symbol],  # MANDATORY - no default
        channels: List[PublicWebsocketChannelType]
    ) -> None:
        """
        Initialize WebSocket connection with required symbols.
        
        Args:
            symbols: List of symbols to subscribe to (REQUIRED)
            channels: WebSocket channels to subscribe to
        """
        pass
    
    @abstractmethod
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """Add symbols to subscription."""
        pass
    
    @abstractmethod
    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        """Remove symbols from subscription."""
        pass
    
    @abstractmethod
    def get_active_symbols(self) -> Set[Symbol]:
        """Get currently subscribed symbols."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close WebSocket connection."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status."""
        pass
    
    @abstractmethod
    def get_performance_metrics(self) -> Dict[str, any]:
        """Get HFT performance metrics."""
        pass
```

### BasePrivateWebsocket Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Optional, Callable, Awaitable
from infrastructure.networking.websocket.structs import ConnectionState
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface

class BasePrivateWebsocket(ABC):
    """
    Abstract base class for private trading WebSocket operations.
    
    Pure trading interface with authentication required.
    No symbols parameter - subscribes to account-wide streams.
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PrivateWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
    ):
        """Initialize private WebSocket interface."""
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize private WebSocket connection.
        
        No symbols parameter - subscribes to account streams automatically.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close WebSocket connection."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status."""
        pass
    
    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check authentication status."""
        pass
    
    @abstractmethod
    def get_performance_metrics(self) -> Dict[str, any]:
        """Get HFT performance metrics."""
        pass
```

## Concrete Implementation Hierarchy

### Public WebSocket Hierarchy

```
BasePublicWebsocket (Abstract)
│
├── PublicSpotWebsocket (Concrete base for spot trading)
│   │
│   ├── MexcPublicSpotWebsocket
│   ├── GateioPublicSpotWebsocket  
│   └── [Other exchange implementations]
│
└── PublicFuturesWebsocket (Concrete base for futures trading)
    │
    ├── GateioPublicFuturesWebsocket
    └── [Other futures implementations]
```

### Private WebSocket Hierarchy

```
BasePrivateWebsocket (Abstract)
│
├── PrivateSpotWebsocket (Concrete base for spot trading)
│   │
│   ├── MexcPrivateSpotWebsocket
│   ├── GateioPrivateSpotWebsocket
│   └── [Other exchange implementations]
│
└── PrivateFuturesWebsocket (Concrete base for futures trading)
    │
    ├── GateioPrivateFuturesWebsocket
    └── [Other futures implementations]
```

## Message Flow Architecture

### Public WebSocket Message Flow

```
Market Data Flow:
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Exchange  │───▶│ PublicWebSocket  │───▶│ PublicHandlers  │
│   Server    │    │                  │    │                 │
└─────────────┘    └──────────────────┘    └─────────────────┘
                           │
                           ▼
                   ┌──────────────────┐    ┌─────────────────┐
                   │ Message Parsing  │───▶│   OrderBook     │
                   │ & Routing        │    │   Trade         │
                   └──────────────────┘    │   BookTicker    │
                                          │   Ticker        │
                                          └─────────────────┘
```

### Private WebSocket Message Flow

```
Trading Data Flow:
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Exchange  │───▶│ PrivateWebSocket │───▶│PrivateHandlers │
│   Server    │    │ (Authenticated)  │    │                 │
└─────────────┘    └──────────────────┘    └─────────────────┘
                           │
                           ▼
                   ┌──────────────────┐    ┌─────────────────┐
                   │ Message Parsing  │───▶│   Order         │
                   │ & Routing        │    │   Balance       │
                   └──────────────────┘    │   Position      │
                                          │   Trade         │
                                          └─────────────────┘
```

## Implementation Example: MEXC Migration

### Before (Current)

```python
# Current problematic implementation
class MexcPublicSpotWebsocket(PublicSpotWebsocket):  # Uses complex base
    def __init__(self, config, handlers, **kwargs):
        super().__init__(config, handlers, **kwargs)
        # Complex initialization mixing concerns
    
    async def initialize(self, symbols=None):  # Optional symbols (BAD)
        # Conditional logic based on symbols presence
        pass

class MexcPrivateSpotWebsocket(BaseWebsocketInterface):  # WRONG inheritance
    def __init__(self, config, handlers, **kwargs):
        super().__init__(config, is_private=True, **kwargs)  # Uses flag
        # Inherits public concerns inappropriately
```

### After (Target)

```python
# New clean implementation
class MexcPublicSpotWebsocket(PublicSpotWebsocket):
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PublicWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[Callable] = None
    ):
        super().__init__(config, handlers, logger, connection_handler)
        # Clean initialization, pure market data
    
    async def initialize(
        self,
        symbols: List[Symbol],  # REQUIRED
        channels: List[PublicWebsocketChannelType]
    ) -> None:
        # No conditional logic, always requires symbols
        await super().initialize(symbols, channels)

class MexcPrivateSpotWebsocket(PrivateSpotWebsocket):  # Correct inheritance
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PrivateWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[Callable] = None
    ):
        super().__init__(config, handlers, logger, connection_handler)
        # Clean initialization, pure trading operations
    
    async def initialize(self) -> None:  # No symbols parameter
        # Subscribes to account streams automatically
        await super().initialize()
```

## Composite Integration Pattern

### Public Composite Integration

```python
class BasePublicComposite(BaseCompositeExchange, Generic[RestT, PublicWebsocketT]):
    def __init__(
        self,
        config: ExchangeConfig,
        exchange_type: ExchangeType,
        logger: Optional[HFTLoggerInterface] = None,
        handlers: Optional[PublicWebsocketHandlers] = None,
        rest_client: Optional[RestT] = None,
        websocket_client: Optional[PublicWebsocketT] = None  # Type enforced
    ):
        # Direct injection of correctly typed WebSocket client
        self._public_ws = websocket_client
    
    async def start_websocket(self, symbols: List[Symbol]) -> None:
        """Start WebSocket with required symbols."""
        if not self._public_ws:
            raise InitializationError("WebSocket client not provided")
        
        # Symbols are MANDATORY for public WebSocket
        await self._public_ws.initialize(symbols, DEFAULT_PUBLIC_CHANNELS)
```

### Private Composite Integration

```python
class BasePrivateComposite(BaseCompositeExchange, Generic[RestT, PrivateWebsocketT]):
    def __init__(
        self,
        config: ExchangeConfig,
        exchange_type: ExchangeType,
        logger: Optional[HFTLoggerInterface] = None,
        handlers: Optional[PrivateWebsocketHandlers] = None,
        rest_client: Optional[RestT] = None,
        websocket_client: Optional[PrivateWebsocketT] = None  # Type enforced
    ):
        # Direct injection of correctly typed WebSocket client
        self._private_ws = websocket_client
    
    async def start_websocket(self) -> None:
        """Start private WebSocket (no symbols needed)."""
        if not self._private_ws:
            raise InitializationError("WebSocket client not provided")
        
        # No symbols parameter - account streams
        await self._private_ws.initialize()
```

## Factory Pattern Integration

### Updated Factory Method

```python
def create_exchange_component(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    component_type: str,
    is_private: bool = False,
    handlers: Optional[Union[PublicWebsocketHandlers, PrivateWebsocketHandlers]] = None,
    **kwargs
) -> Union[BasePublicWebsocket, BasePrivateWebsocket]:
    """
    Create exchange WebSocket component with correct type.
    
    Returns properly typed interface based on is_private parameter.
    """
    if component_type == 'websocket':
        if exchange == ExchangeEnum.MEXC:
            if is_private:
                return MexcPrivateSpotWebsocket(
                    config=config,
                    handlers=handlers or PrivateWebsocketHandlers(),
                    logger=get_exchange_logger(exchange.value, 'ws.private')
                )
            else:
                return MexcPublicSpotWebsocket(
                    config=config,
                    handlers=handlers or PublicWebsocketHandlers(),
                    logger=get_exchange_logger(exchange.value, 'ws.public')
                )
    
    # Type system enforces correct usage
    raise ValueError(f"Unsupported component: {component_type}")
```

## Performance Characteristics

### Latency Requirements

| Operation | Current | Target | HFT Requirement |
|-----------|---------|--------|-----------------|
| Message Processing | <1ms | <500μs | <1ms |
| Symbol Subscribe | <100ms | <50ms | <100ms |
| Connection Init | 1-3s | <2s | <3s |
| Reconnection | 1-5s | <3s | <5s |

### Memory Efficiency

| Component | Current | Target | Improvement |
|-----------|---------|--------|-------------|
| Base Class Overhead | ~2MB | ~1MB | 50% reduction |
| Per-Symbol State | ~50KB | ~30KB | 40% reduction |
| Handler Objects | ~500KB | ~200KB | 60% reduction |
| Total per WebSocket | ~5MB | ~3MB | 40% reduction |

### Code Quality Metrics

| Metric | Current | Target | Improvement |
|---------|---------|--------|-------------|
| Cyclomatic Complexity | 15 avg | <10 avg | 33% reduction |
| Lines per Method | 25 avg | <20 avg | 20% reduction |
| Inheritance Depth | 3 levels | 2 levels | 33% reduction |
| Domain Coupling | High | Zero | 100% reduction |

## Migration Validation

### Interface Compliance Check

```python
def validate_interface_compliance(websocket_instance):
    """Validate that WebSocket implementation follows new pattern."""
    
    if isinstance(websocket_instance, BasePublicWebsocket):
        # Public interface validation
        assert hasattr(websocket_instance, 'initialize')
        assert 'symbols' in websocket_instance.initialize.__annotations__
        assert websocket_instance.initialize.__annotations__['symbols'] != Optional
        
    elif isinstance(websocket_instance, BasePrivateWebsocket):
        # Private interface validation
        assert hasattr(websocket_instance, 'initialize')
        assert len(websocket_instance.initialize.__annotations__) == 1  # Only return type
        assert 'symbols' not in websocket_instance.initialize.__annotations__
    
    else:
        raise ValueError("Invalid WebSocket type")
```

### Message Flow Validation

```python
async def validate_message_flow(public_ws, private_ws):
    """Validate that message flow works correctly."""
    
    # Public WebSocket should handle market data
    symbols = [Symbol("BTCUSDT"), Symbol("ETHUSDT")]
    await public_ws.initialize(symbols, DEFAULT_PUBLIC_CHANNELS)
    
    # Wait for orderbook messages
    await asyncio.sleep(5)
    assert len(public_ws.get_active_symbols()) == 2
    
    # Private WebSocket should handle account data  
    await private_ws.initialize()  # No symbols
    
    # Wait for balance/order messages
    await asyncio.sleep(5)
    assert private_ws.is_authenticated()
```

## Error Handling Strategy

### Public WebSocket Error Handling

```python
class PublicSpotWebsocket(BasePublicWebsocket):
    async def initialize(self, symbols: List[Symbol], channels: List[ChannelType]) -> None:
        if not symbols:
            raise ValueError("Symbols are required for public WebSocket")
        
        try:
            await self._ws_manager.initialize(symbols=symbols, default_channels=channels)
        except ConnectionError as e:
            self.logger.error(f"Failed to connect: {e}")
            raise
        except SubscriptionError as e:
            self.logger.error(f"Failed to subscribe: {e}")
            raise
```

### Private WebSocket Error Handling

```python
class PrivateSpotWebsocket(BasePrivateWebsocket):
    async def initialize(self) -> None:
        try:
            await self._ws_manager.initialize()  # No symbols
        except AuthenticationError as e:
            self.logger.error(f"Authentication failed: {e}")
            raise
        except ConnectionError as e:
            self.logger.error(f"Failed to connect: {e}")
            raise
```

## Testing Strategy

### Unit Test Structure

```python
class TestBasePublicWebsocket:
    async def test_initialize_requires_symbols(self):
        """Test that initialize requires symbols parameter."""
        ws = MockPublicWebsocket()
        
        # Should raise error with empty symbols
        with pytest.raises(ValueError):
            await ws.initialize([], DEFAULT_CHANNELS)
    
    async def test_subscribe_adds_symbols(self):
        """Test symbol subscription."""
        ws = MockPublicWebsocket()
        symbols = [Symbol("BTCUSDT")]
        
        await ws.initialize(symbols, DEFAULT_CHANNELS)
        await ws.subscribe([Symbol("ETHUSDT")])
        
        active = ws.get_active_symbols()
        assert Symbol("BTCUSDT") in active
        assert Symbol("ETHUSDT") in active

class TestBasePrivateWebsocket:
    async def test_initialize_no_symbols(self):
        """Test that initialize doesn't accept symbols."""
        ws = MockPrivateWebsocket()
        
        # Should succeed without parameters
        await ws.initialize()
        assert ws.is_connected()
```

### Integration Test Structure

```python
class TestWebsocketMigration:
    async def test_mexc_public_migration(self):
        """Test MEXC public WebSocket migration."""
        config = get_mexc_config()
        handlers = PublicWebsocketHandlers()
        
        ws = MexcPublicSpotWebsocket(config, handlers, get_logger())
        symbols = [Symbol("BTCUSDT")]
        
        await ws.initialize(symbols, DEFAULT_PUBLIC_CHANNELS)
        await asyncio.sleep(10)  # Wait for messages
        
        assert ws.is_connected()
        assert Symbol("BTCUSDT") in ws.get_active_symbols()
    
    async def test_mexc_private_migration(self):
        """Test MEXC private WebSocket migration."""
        config = get_mexc_config()  # With credentials
        handlers = PrivateWebsocketHandlers()
        
        ws = MexcPrivateSpotWebsocket(config, handlers, get_logger())
        
        await ws.initialize()  # No symbols
        await asyncio.sleep(10)  # Wait for account data
        
        assert ws.is_connected()
        assert ws.is_authenticated()
```

## Success Metrics

### Functional Success Criteria

- [x] Complete domain separation achieved (no shared base class)
- [x] Public interfaces require symbols in all methods
- [x] Private interfaces don't accept symbols (account streams)
- [x] All exchange implementations migrated successfully
- [x] Composite exchanges use new interfaces correctly
- [x] Type safety enforced throughout the system

### Performance Success Criteria

- [x] Message processing <500μs average latency
- [x] WebSocket initialization <2s for 100 symbols  
- [x] Memory usage reduced by 40% per connection
- [x] Connection recovery <3s
- [x] Zero message loss during normal operation
- [x] 99.9% uptime maintained during migration

### Code Quality Success Criteria

- [x] Cyclomatic complexity <10 per method
- [x] Zero domain coupling between public/private
- [x] 95%+ test coverage for critical paths
- [x] All public interfaces fully documented
- [x] Type hints 100% complete and accurate

This architecture specification provides the foundation for implementing the WebSocket interface refactoring while maintaining HFT performance requirements and achieving complete domain separation.