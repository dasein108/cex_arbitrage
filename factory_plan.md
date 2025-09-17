# Generic Factory Base Class Implementation Plan

## Overview
Create a universal `BaseExchangeFactory` abstract class that provides standard factory patterns for exchange-based services, eliminating code duplication and ensuring consistency across all factories.

## Core Design Principles
- **Standardized API**: All factories use `inject()` method
- **Auto-Injection**: Built-in dependency resolution infrastructure
- **Generic Type Safety**: Use `TypeVar` for implementation types
- **Factory-to-Factory Coordination**: Automatic dependency resolution
- **No Backward Compatibility**: Clean break for better architecture

## Implementation Tasks

### Phase 1: Base Class Foundation
- [ ] **Task 1.1**: Create `/src/core/factories/` directory structure
- [ ] **Task 1.2**: Create `/src/core/factories/__init__.py` with exports
- [ ] **Task 1.3**: Create `/src/core/factories/base_exchange_factory.py`
  - [ ] **Subtask 1.3.1**: Define `BaseExchangeFactory` generic abstract class
  - [ ] **Subtask 1.3.2**: Implement standard registry patterns (`_implementations`, `_instances`)
  - [ ] **Subtask 1.3.3**: Implement utility methods (`is_registered`, `get_registered_exchanges`, `clear_cache`)
  - [ ] **Subtask 1.3.4**: Implement exchange key normalization (`_normalize_exchange_key`)
  - [ ] **Subtask 1.3.5**: Create auto-injection infrastructure (`_resolve_dependencies`)
  - [ ] **Subtask 1.3.6**: Define abstract methods (`register`, `inject`)

### Phase 2: ExchangeSymbolMapperFactory Refactoring
- [ ] **Task 2.1**: Refactor ExchangeSymbolMapperFactory to inherit from base
  - [ ] **Subtask 2.1.1**: Import `BaseExchangeFactory` and update class definition
  - [ ] **Subtask 2.1.2**: Remove duplicate registry code (`_mapper_classes`, `_mapper_instances`)
  - [ ] **Subtask 2.1.3**: Implement `register()` method using base class patterns
  - [ ] **Subtask 2.1.4**: Implement `inject()` method (rename from old method)
  - [ ] **Subtask 2.1.5**: Remove redundant utility methods now in base class
  - [ ] **Subtask 2.1.6**: Update method signatures and documentation
- [ ] **Task 2.2**: Test ExchangeSymbolMapperFactory with base class
  - [ ] **Subtask 2.2.1**: Create validation test for refactored factory
  - [ ] **Subtask 2.2.2**: Verify registry isolation between factory types
  - [ ] **Subtask 2.2.3**: Test auto-instance creation during registration

### Phase 3: ExchangeMappingsFactory Refactoring  
- [ ] **Task 3.1**: Refactor ExchangeMappingsFactory to inherit from base
  - [ ] **Subtask 3.1.1**: Import `BaseExchangeFactory` and update class definition
  - [ ] **Subtask 3.1.2**: Remove duplicate registry code (`_implementations`, `_instances`)
  - [ ] **Subtask 3.1.3**: Enhance `register()` method with base class + auto-injection
  - [ ] **Subtask 3.1.4**: Implement `inject()` method for consistent API
  - [ ] **Subtask 3.1.5**: Keep `create()` method for backward compatibility (calls `inject()`)
  - [ ] **Subtask 3.1.6**: Remove redundant utility methods now in base class
- [ ] **Task 3.2**: Test ExchangeMappingsFactory auto-injection
  - [ ] **Subtask 3.2.1**: Test enhanced auto-injection with symbol_mapper resolution
  - [ ] **Subtask 3.2.2**: Verify factory-to-factory coordination works
  - [ ] **Subtask 3.2.3**: Test graceful fallback when dependencies unavailable

### Phase 4: RestStrategyFactory Refactoring
- [ ] **Task 4.1**: Refactor RestStrategyFactory to inherit from base
  - [ ] **Subtask 4.1.1**: Import `BaseExchangeFactory` and update class definition
  - [ ] **Subtask 4.1.2**: Remove duplicate registry code (`_strategy_registry`)
  - [ ] **Subtask 4.1.3**: Implement `register()` method for strategy registration
  - [ ] **Subtask 4.1.4**: Implement `inject()` method (rename from `create_strategies`)
  - [ ] **Subtask 4.1.5**: Integrate auto-injection for `symbol_mapper` and `exchange_mappings`
  - [ ] **Subtask 4.1.6**: Update `register_strategies()` to use base class patterns
- [ ] **Task 4.2**: Test RestStrategyFactory with auto-injection
  - [ ] **Subtask 4.2.1**: Test strategy registration and injection
  - [ ] **Subtask 4.2.2**: Verify auto-dependency injection works
  - [ ] **Subtask 4.2.3**: Test with both public and private strategy configurations

### Phase 5: WebSocketStrategyFactory Refactoring
- [ ] **Task 5.1**: Refactor WebSocketStrategyFactory to inherit from base
  - [ ] **Subtask 5.1.1**: Import `BaseExchangeFactory` and update class definition
  - [ ] **Subtask 5.1.2**: Remove duplicate registry code (`_strategy_registry`)
  - [ ] **Subtask 5.1.3**: Implement `register()` method for strategy registration
  - [ ] **Subtask 5.1.4**: Implement `inject()` method (rename from `create_strategies`)
  - [ ] **Subtask 5.1.5**: Integrate auto-injection for `symbol_mapper` and `exchange_mappings`
  - [ ] **Subtask 5.1.6**: Fix `@classmethod` decorator and standardize registration
- [ ] **Task 5.2**: Test WebSocketStrategyFactory with auto-injection
  - [ ] **Subtask 5.2.1**: Test strategy registration and injection
  - [ ] **Subtask 5.2.2**: Verify auto-dependency injection works
  - [ ] **Subtask 5.2.3**: Test with both public and private strategy configurations

### Phase 6: Import Updates and Integration
- [ ] **Task 6.1**: Update all import statements across codebase
  - [ ] **Subtask 6.1.1**: Update imports in exchange implementations
  - [ ] **Subtask 6.1.2**: Update imports in examples and test files
  - [ ] **Subtask 6.1.3**: Update imports in factory coordinator
  - [ ] **Subtask 6.1.4**: Update imports in arbitrage components
- [ ] **Task 6.2**: Update factory coordinator integration
  - [ ] **Subtask 6.2.1**: Update `FactoryCoordinator` to use new `inject()` methods
  - [ ] **Subtask 6.2.2**: Test factory coordination with refactored factories
  - [ ] **Subtask 6.2.3**: Verify auto-injection works in coordinator context

### Phase 7: Comprehensive Testing and Validation
- [ ] **Task 7.1**: Create comprehensive test suite
  - [ ] **Subtask 7.1.1**: Create base class unit tests
  - [ ] **Subtask 7.1.2**: Create integration tests for all factories
  - [ ] **Subtask 7.1.3**: Create auto-injection validation tests
  - [ ] **Subtask 7.1.4**: Create factory coordination tests
- [ ] **Task 7.2**: Performance validation
  - [ ] **Subtask 7.2.1**: Benchmark factory performance vs old implementation
  - [ ] **Subtask 7.2.2**: Verify singleton patterns maintain performance
  - [ ] **Subtask 7.2.3**: Test memory usage with large numbers of exchanges

## Technical Specifications

### Base Class Structure
```python
class BaseExchangeFactory(Generic[T], ABC):
    _implementations: Dict[str, Type[T]] = {}
    _instances: Dict[str, T] = {}
    
    @classmethod
    @abstractmethod
    def register(cls, exchange_name: str, implementation_class: Type[T], **kwargs) -> None
    
    @classmethod
    @abstractmethod  
    def inject(cls, exchange_name: str, **kwargs) -> T
    
    # Standard utility methods implemented in base
    @classmethod
    def is_registered(cls, exchange_name: str) -> bool
    
    @classmethod
    def get_registered_exchanges(cls) -> List[str]
    
    @classmethod
    def clear_cache(cls) -> None
    
    @classmethod
    def _normalize_exchange_key(cls, exchange_name: str) -> str
    
    @classmethod
    def _resolve_dependencies(cls, exchange_name: str, **context) -> Dict[str, Any]
```

### Auto-Injection Pattern
```python
# In base class _resolve_dependencies()
try:
    from core.cex.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
    from core.cex.services.unified_mapper.factory import ExchangeMappingsFactory
    
    # Auto-resolve symbol mapper
    symbol_mapper = ExchangeSymbolMapperFactory.inject(exchange_key)
    resolved['symbol_mapper'] = symbol_mapper
    
    # Auto-resolve exchange mappings
    exchange_mappings = ExchangeMappingsFactory.inject(exchange_key)
    resolved['exchange_mappings'] = exchange_mappings
    
except Exception:
    # Graceful fallback - continue without dependencies
    pass
```

### Factory Method Standardization
- **Old**: `ExchangeSymbolMapperFactory.inject()` ✅ (keep)
- **Old**: `ExchangeMappingsFactory.create()` ❌ → **New**: `inject()`
- **Old**: `RestStrategyFactory.create_strategies()` ❌ → **New**: `inject()`
- **Old**: `WebSocketStrategyFactory.create_strategies()` ❌ → **New**: `inject()`

## Success Criteria

### Code Quality Metrics
- [ ] **50%+ reduction** in factory boilerplate code
- [ ] **Consistent API** across all factory types (`inject()` method)
- [ ] **Generic type safety** with proper `TypeVar` usage
- [ ] **Zero code duplication** in registry management

### Functional Requirements
- [ ] **Auto-injection works** for all factories
- [ ] **Factory-to-factory coordination** seamless
- [ ] **Singleton patterns** maintain performance
- [ ] **Error handling** consistent and graceful

### Integration Requirements
- [ ] **All existing tests pass** with refactored factories
- [ ] **FactoryCoordinator integration** works correctly
- [ ] **Exchange implementations** work without changes
- [ ] **Auto-registration patterns** continue working

## Implementation Order
1. **Phase 1**: Base class foundation (critical infrastructure)
2. **Phase 2**: ExchangeSymbolMapperFactory (simplest case, others depend on it)
3. **Phase 3**: ExchangeMappingsFactory (auto-injection testing)
4. **Phase 4**: RestStrategyFactory (complex strategy management)
5. **Phase 5**: WebSocketStrategyFactory (most complex)
6. **Phase 6**: Import updates and integration
7. **Phase 7**: Testing and validation

## Notes
- **No backward compatibility** - clean break for better architecture
- **Standardize on `inject()`** for all factory methods
- **Auto-injection infrastructure** built into base class
- **Registry isolation** - each factory has separate registries
- **Graceful dependency fallback** when auto-injection fails