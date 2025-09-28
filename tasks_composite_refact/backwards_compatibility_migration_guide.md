# Backwards Compatibility and Migration Guide

## Overview

This document outlines the backwards compatibility strategy and migration path for the composite exchange REST/WebSocket client refactoring. The goal is to ensure zero breaking changes while providing a clear upgrade path.

## Backwards Compatibility Strategy

### Deprecation Timeline

#### Phase 1: Introduction (Immediate)
- **Duration**: Initial release
- **Action**: Introduce new generic properties alongside existing ones
- **Deprecation**: Add deprecation warnings to old properties
- **Support**: Full backwards compatibility maintained

#### Phase 2: Migration Period (2-3 months)
- **Duration**: 2-3 months after Phase 1
- **Action**: Encourage migration to new properties via documentation
- **Deprecation**: Continue deprecation warnings
- **Support**: Full backwards compatibility maintained

#### Phase 3: Cleanup (Future)
- **Duration**: After migration period
- **Action**: Remove deprecated properties in major version bump
- **Deprecation**: Properties removed
- **Support**: Only new generic properties supported

### Backwards Compatibility Implementation

#### Old Property Mapping
```python
class BaseCompositeExchange(Generic[RestClientType, WebSocketClientType], ABC):
    
    # NEW: Generic properties (primary interface)
    _rest: Optional[RestClientType] = None
    _ws: Optional[WebSocketClientType] = None
    _rest_connected: bool = False
    _ws_connected: bool = False
    
    # DEPRECATED: Backwards compatibility properties
    @property
    def _private_rest(self) -> Optional[RestClientType]:
        """
        Backwards compatibility property for private REST client.
        
        .. deprecated:: 1.5.0
           Use :attr:`_rest` instead.
        """
        import warnings
        warnings.warn(
            "_private_rest is deprecated, use _rest instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self._rest if self._is_private else None
    
    @property  
    def _private_ws(self) -> Optional[WebSocketClientType]:
        """
        Backwards compatibility property for private WebSocket client.
        
        .. deprecated:: 1.5.0
           Use :attr:`_ws` instead.
        """
        import warnings
        warnings.warn(
            "_private_ws is deprecated, use _ws instead", 
            DeprecationWarning,
            stacklevel=2
        )
        return self._ws if self._is_private else None
    
    @property
    def _public_rest(self) -> Optional[RestClientType]:
        """
        Backwards compatibility property for public REST client.
        
        .. deprecated:: 1.5.0
           Use :attr:`_rest` instead.
        """
        import warnings
        warnings.warn(
            "_public_rest is deprecated, use _rest instead",
            DeprecationWarning,
            stacklevel=2  
        )
        return self._rest if not self._is_private else None
    
    @property
    def _public_ws(self) -> Optional[WebSocketClientType]:
        """
        Backwards compatibility property for public WebSocket client.
        
        .. deprecated:: 1.5.0
           Use :attr:`_ws` instead.
        """
        import warnings
        warnings.warn(
            "_public_ws is deprecated, use _ws instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self._ws if not self._is_private else None
        
    # DEPRECATED: Connection status properties
    @property
    def _private_rest_connected(self) -> bool:
        """
        Backwards compatibility property for private REST connection status.
        
        .. deprecated:: 1.5.0
           Use :attr:`_rest_connected` instead.
        """
        import warnings
        warnings.warn(
            "_private_rest_connected is deprecated, use _rest_connected instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self._rest_connected if self._is_private else False
        
    @property
    def _private_ws_connected(self) -> bool:
        """
        Backwards compatibility property for private WebSocket connection status.
        
        .. deprecated:: 1.5.0
           Use :attr:`_ws_connected` instead.
        """
        import warnings
        warnings.warn(
            "_private_ws_connected is deprecated, use _ws_connected instead",
            DeprecationWarning, 
            stacklevel=2
        )
        return self._ws_connected if self._is_private else False
        
    @property
    def _public_rest_connected(self) -> bool:
        """
        Backwards compatibility property for public REST connection status.
        
        .. deprecated:: 1.5.0
           Use :attr:`_rest_connected` instead.
        """
        import warnings
        warnings.warn(
            "_public_rest_connected is deprecated, use _rest_connected instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self._rest_connected if not self._is_private else False
        
    @property  
    def _public_ws_connected(self) -> bool:
        """
        Backwards compatibility property for public WebSocket connection status.
        
        .. deprecated:: 1.5.0
           Use :attr:`_ws_connected` instead.
        """
        import warnings
        warnings.warn(
            "_public_ws_connected is deprecated, use _ws_connected instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self._ws_connected if not self._is_private else False
```

#### Factory Method Compatibility
```python
# NEW: Generic factory methods (primary interface)
@abstractmethod
async def _create_rest_client(self) -> RestClientType:
    """Create exchange-specific REST client."""
    pass

@abstractmethod  
async def _create_websocket_client(self) -> Optional[WebSocketClientType]:
    """Create exchange-specific WebSocket client."""
    pass

# DEPRECATED: Old factory methods (for backwards compatibility)
async def _create_private_rest(self) -> RestClientType:
    """
    Backwards compatibility method for creating private REST client.
    
    .. deprecated:: 1.5.0
       Use :meth:`_create_rest_client` instead.
    """
    import warnings
    warnings.warn(
        "_create_private_rest is deprecated, use _create_rest_client instead",
        DeprecationWarning,
        stacklevel=2
    )
    if not self._is_private:
        raise ValueError("_create_private_rest can only be called on private exchanges")
    return await self._create_rest_client()

async def _create_private_websocket(self) -> Optional[WebSocketClientType]:
    """
    Backwards compatibility method for creating private WebSocket client.
    
    .. deprecated:: 1.5.0
       Use :meth:`_create_websocket_client` instead.
    """
    import warnings
    warnings.warn(
        "_create_private_websocket is deprecated, use _create_websocket_client instead",
        DeprecationWarning,
        stacklevel=2
    )
    if not self._is_private:
        raise ValueError("_create_private_websocket can only be called on private exchanges")
    return await self._create_websocket_client()

async def _create_public_rest(self) -> RestClientType:
    """
    Backwards compatibility method for creating public REST client.
    
    .. deprecated:: 1.5.0
       Use :meth:`_create_rest_client` instead.
    """
    import warnings
    warnings.warn(
        "_create_public_rest is deprecated, use _create_rest_client instead",
        DeprecationWarning,
        stacklevel=2
    )
    if self._is_private:
        raise ValueError("_create_public_rest can only be called on public exchanges")
    return await self._create_rest_client()

async def _create_public_websocket(self) -> Optional[WebSocketClientType]:
    """
    Backwards compatibility method for creating public WebSocket client.
    
    .. deprecated:: 1.5.0
       Use :meth:`_create_websocket_client` instead.
    """
    import warnings
    warnings.warn(
        "_create_public_websocket is deprecated, use _create_websocket_client instead",
        DeprecationWarning,
        stacklevel=2
    )
    if self._is_private:
        raise ValueError("_create_public_websocket can only be called on public exchanges")
    return await self._create_websocket_client()
```

## Migration Guide

### For Exchange Implementers

#### Before (Old Pattern)
```python
class MexcCompositePublic(CompositePublicSpotExchange):
    
    async def _create_public_rest(self) -> PublicSpotRest:
        return MexcPublicRest(self.config, self.logger)
        
    async def _create_public_websocket(self) -> Optional[PublicSpotWebsocket]:
        handlers = self._create_inner_websocket_handlers()
        return MexcPublicWebsocket(
            config=self.config,
            handlers=handlers,
            logger=self.logger,
            connection_handler=self._handle_connection_state
        )
        
    def some_method(self):
        if self._public_rest:
            await self._public_rest.get_symbols_info()
        if self._public_ws:
            await self._public_ws.subscribe(['BTCUSDT'])
```

#### After (New Pattern)
```python
from exchanges.interfaces.composite.types import PublicRestType, PublicWebSocketType

class MexcCompositePublic(CompositePublicSpotExchange[MexcPublicRest, MexcPublicWebsocket]):
    
    async def _create_rest_client(self) -> MexcPublicRest:
        return MexcPublicRest(self.config, self.logger)
        
    async def _create_websocket_client(self) -> Optional[MexcPublicWebsocket]:
        handlers = self._create_inner_websocket_handlers()
        return MexcPublicWebsocket(
            config=self.config,
            handlers=handlers,
            logger=self.logger,
            connection_handler=self._handle_connection_state
        )
        
    def some_method(self):
        if self._rest:
            await self._rest.get_symbols_info()
        if self._ws:
            await self._ws.subscribe(['BTCUSDT'])
```

### For Exchange Consumers

#### Before (Old Pattern)
```python
# Private exchange usage
exchange = MexcPrivateExchange(config)
await exchange.initialize()

if exchange._private_rest:
    balances = await exchange._private_rest.get_balances()
    
if exchange._private_ws:
    await exchange._private_ws.subscribe_to_orders()

# Connection status checking
if exchange._private_rest_connected:
    print("Private REST connected")
```

#### After (New Pattern)  
```python
# Private exchange usage  
exchange = MexcPrivateExchange(config)
await exchange.initialize()

if exchange._rest:
    balances = await exchange._rest.get_balances()
    
if exchange._ws:
    await exchange._ws.subscribe_to_orders()

# Connection status checking
if exchange._rest_connected:
    print("REST connected")
```

#### Transition Period (Both Work)
```python
# During transition, both patterns work but old ones emit warnings
exchange = MexcPrivateExchange(config)
await exchange.initialize()

# NEW (recommended, no warnings)
if exchange._rest:
    balances = await exchange._rest.get_balances()

# OLD (deprecated, emits warnings but still works)  
if exchange._private_rest:  # DeprecationWarning emitted
    balances = await exchange._private_rest.get_balances()
```

## Testing Backwards Compatibility

### Unit Tests for Compatibility
```python
import warnings
import pytest
from unittest.mock import AsyncMock
from exchanges.interfaces.composite.base_composite import BaseCompositeExchange

class TestBackwardsCompatibility:
    
    def test_private_rest_deprecation_warning(self):
        """Test that accessing _private_rest emits deprecation warning."""
        exchange = MockPrivateExchange(config)
        exchange._rest = AsyncMock()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            client = exchange._private_rest
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "_private_rest is deprecated" in str(w[0].message)
            assert client is exchange._rest
    
    def test_private_ws_deprecation_warning(self):
        """Test that accessing _private_ws emits deprecation warning.""" 
        exchange = MockPrivateExchange(config)
        exchange._ws = AsyncMock()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            client = exchange._private_ws
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "_private_ws is deprecated" in str(w[0].message)
            assert client is exchange._ws
    
    def test_public_rest_deprecation_warning(self):
        """Test that accessing _public_rest emits deprecation warning."""
        exchange = MockPublicExchange(config)
        exchange._rest = AsyncMock()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            client = exchange._public_rest
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "_public_rest is deprecated" in str(w[0].message)
            assert client is exchange._rest
    
    def test_connection_status_compatibility(self):
        """Test that old connection status properties work."""
        exchange = MockPrivateExchange(config)
        exchange._rest_connected = True
        exchange._ws_connected = False
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            assert exchange._private_rest_connected is True
            assert exchange._private_ws_connected is False
            
            # Should have generated warnings
            assert len(w) == 2
            assert all(issubclass(warning.category, DeprecationWarning) for warning in w)
    
    def test_factory_method_compatibility(self):
        """Test that old factory methods still work."""
        exchange = MockPrivateExchange(config)
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Should call through to new method
            result = await exchange._create_private_rest()
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "_create_private_rest is deprecated" in str(w[0].message)
```

### Integration Tests
```python
class TestIntegrationCompatibility:
    
    async def test_existing_exchange_implementations_still_work(self):
        """Test that existing exchange implementations work unchanged."""
        # Test MEXC
        mexc_exchange = MexcCompositePublic(config)
        await mexc_exchange.initialize()
        
        # Old properties should work (with warnings)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert mexc_exchange._public_rest is not None
            assert mexc_exchange._public_ws is not None
        
        # New properties should work (no warnings)
        assert mexc_exchange._rest is not None
        assert mexc_exchange._ws is not None
        
        # Both should reference the same objects
        assert mexc_exchange._public_rest is mexc_exchange._rest
        assert mexc_exchange._public_ws is mexc_exchange._ws
    
    async def test_mixed_usage_patterns(self):
        """Test that mixed old/new usage patterns work."""
        exchange = MexcCompositePublic(config)
        await exchange.initialize()
        
        # Mix of old and new patterns should work
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            
            # Old pattern
            if exchange._public_rest:
                symbols_old = await exchange._public_rest.get_symbols_info()
            
            # New pattern  
            if exchange._rest:
                symbols_new = await exchange._rest.get_symbols_info()
                
            # Should get same results
            assert symbols_old == symbols_new
```

## Deprecation Warning Management

### Warning Configuration
```python
# For production environments - suppress deprecation warnings
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="exchanges.interfaces.composite")

# For development environments - show all warnings
warnings.filterwarnings("always", category=DeprecationWarning, module="exchanges.interfaces.composite")

# For testing environments - capture warnings for assertions
warnings.filterwarnings("error", category=DeprecationWarning, module="exchanges.interfaces.composite")
```

### Custom Warning Categories
```python
class CompositeExchangeDeprecationWarning(DeprecationWarning):
    """Specific warning category for composite exchange deprecations."""
    pass

# Usage in properties
warnings.warn(
    "_private_rest is deprecated, use _rest instead",
    CompositeExchangeDeprecationWarning,
    stacklevel=2
)
```

## Migration Timeline

### Phase 1: Implementation (Week 1)
- [ ] Implement generic base class with backwards compatibility
- [ ] Update all composite classes to use new structure  
- [ ] Ensure all old properties work with deprecation warnings
- [ ] All tests pass with warnings ignored

### Phase 2: Documentation (Week 2)
- [ ] Update all documentation to use new patterns
- [ ] Add migration guide to developer docs
- [ ] Update code examples and tutorials
- [ ] Add deprecation notices to API documentation

### Phase 3: Internal Migration (Weeks 3-4)
- [ ] Update all internal code to use new patterns
- [ ] Fix deprecation warnings in codebase
- [ ] Update integration tests to use new patterns
- [ ] Performance validation with new structure

### Phase 4: Community Migration (Months 2-3)
- [ ] Announce deprecation to developers
- [ ] Provide migration assistance
- [ ] Monitor usage of deprecated features
- [ ] Collect feedback on new patterns

### Phase 5: Cleanup (Month 4+)
- [ ] Plan removal of deprecated features
- [ ] Major version bump for breaking changes
- [ ] Remove backwards compatibility code
- [ ] Final documentation updates

## Risk Assessment

### Compatibility Risks
- **Risk**: Old code stops working unexpectedly
- **Mitigation**: Comprehensive backwards compatibility properties
- **Detection**: Extensive integration testing

### Migration Risks  
- **Risk**: Developers don't migrate to new patterns
- **Mitigation**: Clear documentation and gradual deprecation
- **Detection**: Usage analytics and warning monitoring

### Performance Risks
- **Risk**: Backwards compatibility adds overhead
- **Mitigation**: Lightweight property implementations
- **Detection**: Performance benchmarking

## Support Strategy

### Documentation Updates
- Update API documentation with new patterns
- Add migration examples for common use cases  
- Create troubleshooting guide for migration issues
- Maintain backwards compatibility reference

### Developer Communication
- Announcement of deprecation timeline
- Migration assistance through issues/discussions
- Regular updates on deprecation progress
- Clear communication of benefits

### Monitoring and Metrics
- Track usage of deprecated vs new patterns
- Monitor performance impact of backwards compatibility
- Collect developer feedback on migration experience
- Track adoption rates of new patterns

---

This migration strategy ensures that the refactoring can be implemented with zero breaking changes while providing a clear path forward for developers to adopt the improved architecture.