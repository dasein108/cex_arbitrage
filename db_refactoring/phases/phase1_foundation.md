# Phase 1: Foundation - Reference Tables & Cache Infrastructure

## Overview
Create the foundational reference tables (exchanges, symbols) and cache infrastructure without affecting existing operations. This phase is purely additive and low-risk.

## Duration: 5 Days
**Target Completion**: Week 1

## Objectives
1. ✅ Create normalized reference tables for exchanges and symbols
2. ✅ Build high-performance cache infrastructure for sub-microsecond lookups  
3. ✅ Populate reference tables with existing data
4. ✅ Establish performance baselines for HFT compliance

## Success Criteria
- [ ] Exchange and Symbol tables operational with proper relationships
- [ ] Cache system provides <1μs symbol resolution
- [ ] All existing data preserved and accessible
- [ ] Zero impact on current system performance
- [ ] Reference integrity maintained with foreign key constraints

## Detailed Task Breakdown

### Day 1: Exchange Reference Table (Tasks P1.1.1 - P1.1.5)

#### Task P1.1.1: Create migration 002_create_exchanges.sql (15 min)
**Deliverable**: SQL migration script for exchanges table

```sql
-- File: src/db/migrations/002_create_exchanges.sql
-- This will be the exact content created
```

**Validation**:
- [ ] Migration script executes without errors
- [ ] Table structure matches schema design
- [ ] Indexes created for performance

#### Task P1.1.2: Add Exchange model class (20 min) 
**Deliverable**: Exchange msgspec.Struct in models.py

**Key Requirements**:
- Consistent with existing msgspec.Struct pattern
- Maps to ExchangeEnum values correctly
- Supports cache serialization

**Validation**:
- [ ] Model instantiates correctly
- [ ] All fields properly typed
- [ ] Enum mapping functional

#### Task P1.1.3: Create exchange lookup functions (25 min)
**Deliverable**: Database lookup functions in operations.py

**Functions to implement**:
- `get_exchange_by_enum(enum_value: ExchangeEnum) -> Optional[Exchange]`
- `get_exchange_by_id(exchange_id: int) -> Optional[Exchange]` 
- `get_all_active_exchanges() -> List[Exchange]`

**Validation**:
- [ ] Functions return correct data types
- [ ] Performance meets <1ms target
- [ ] Error handling for missing exchanges

#### Task P1.1.4: Add exchange CRUD operations (30 min)
**Deliverable**: Full CRUD operations for Exchange table

**Operations to implement**:
- `insert_exchange()` - Add new exchange
- `update_exchange()` - Modify exchange data
- `deactivate_exchange()` - Soft delete
- `get_exchange_stats()` - Analytics

**Validation**:
- [ ] All CRUD operations functional
- [ ] Constraints properly enforced
- [ ] Audit trail maintained

#### Task P1.1.5: Validate exchange table (15 min)
**Deliverable**: Validation report and test data

**Validation Steps**:
- [ ] Insert test data for all current exchanges
- [ ] Verify foreign key constraints
- [ ] Check index performance
- [ ] Validate enum mapping accuracy

### Day 2: Symbol Reference Table (Tasks P1.2.1 - P1.2.5)

#### Task P1.2.1: Create migration 003_create_symbols.sql (20 min)
**Deliverable**: SQL migration script for symbols table

**Key Features**:
- Foreign key relationship to exchanges
- Unique constraints for exchange+symbol combinations
- Performance indexes for HFT operations
- Trading rules and precision fields

#### Task P1.2.2: Add Symbol model class (25 min)
**Deliverable**: Symbol msgspec.Struct in models.py

**Key Requirements**:
- Includes trading rules (precision, min/max sizes)
- Relationships to Exchange model
- Cache-optimized structure

#### Task P1.2.3: Create symbol lookup functions (30 min)
**Deliverable**: High-performance symbol lookup functions

**Critical Functions**:
- `get_symbol_id(exchange: ExchangeEnum, base: str, quote: str) -> Optional[int]`
- `get_symbol_by_id(symbol_id: int) -> Optional[Symbol]`
- `get_symbols_by_exchange(exchange: ExchangeEnum) -> List[Symbol]`

**Performance Target**: <1μs for cached lookups

#### Task P1.2.4: Add symbol CRUD operations (30 min)
**Deliverable**: Complete symbol management operations

**Operations**:
- Symbol creation with validation
- Trading rules updates
- Symbol activation/deactivation
- Cross-exchange symbol discovery

#### Task P1.2.5: Validate symbol table (15 min)
**Deliverable**: Symbol table validation and test population

**Validation**:
- [ ] Populate with current symbol combinations
- [ ] Verify relationship integrity
- [ ] Test performance benchmarks

### Day 3: Cache Infrastructure (Tasks P1.3.1 - P1.3.6)

#### Task P1.3.1: Create cache.py module (20 min)
**Deliverable**: Cache module structure and interfaces

**File**: `src/db/cache.py`
**Structure**:
```python
# Cache module structure
class ExchangeCache(msgspec.Struct):
    """Cached exchange metadata for sub-microsecond lookups."""
    
class SymbolCache(msgspec.Struct):
    """Cached symbol metadata for ultra-fast resolution."""
    
class ClassifierCache:
    """HFT-optimized cache manager."""
```

#### Task P1.3.2: Implement ExchangeCache struct (25 min)
**Deliverable**: ExchangeCache with optimized lookup methods

**Features**:
- msgspec.Struct for zero-copy serialization
- Multiple lookup indexes (by enum, by ID)
- Memory-efficient storage

#### Task P1.3.3: Implement SymbolCache struct (25 min) 
**Deliverable**: SymbolCache with multiple access patterns

**Access Patterns**:
- By symbol ID (primary key lookup)
- By exchange + base/quote assets
- By exchange + symbol string
- Search indexes for frontend

#### Task P1.3.4: Create ClassifierCache manager (30 min)
**Deliverable**: Cache manager with initialization and updates

**Key Methods**:
- `initialize_from_database()` - One-time load
- `get_symbol_id()` - Sub-microsecond symbol resolution
- `refresh_cache()` - Incremental updates
- `get_cache_stats()` - Performance monitoring

#### Task P1.3.5: Add cache initialization (30 min)
**Deliverable**: Integration with database connection system

**Integration Points**:
- Initialize cache on database connection
- Background refresh mechanisms
- Cache invalidation strategies
- Error handling and fallback

#### Task P1.3.6: Performance benchmarks (20 min)
**Deliverable**: Cache performance validation

**Benchmarks**:
- [ ] Symbol ID resolution: <1μs average
- [ ] Cache loading time: <100ms for full dataset
- [ ] Memory usage: <10MB for 10K symbols
- [ ] Concurrent access performance

### Day 4: Data Population (Tasks P1.4.1 - P1.4.5)

#### Task P1.4.1: Extract unique exchanges (20 min)
**Deliverable**: Analysis of current exchange usage

**Process**:
1. Query current `book_ticker_snapshots` for unique exchanges
2. Map to ExchangeEnum values
3. Identify any missing or deprecated exchanges
4. Create mapping documentation

#### Task P1.4.2: Extract unique symbols (25 min)
**Deliverable**: Complete symbol inventory from current data

**Process**:
1. Extract all unique (exchange, base, quote) combinations
2. Analyze symbol formats and variations
3. Identify trading rules from current data
4. Create symbol population script

#### Task P1.4.3: Populate exchanges table (15 min)
**Deliverable**: Exchanges table fully populated

**Population Data**:
- MEXC_SPOT with current configuration
- GATEIO_SPOT with current configuration  
- GATEIO_FUTURES with current configuration
- Metadata from ExchangeEnum mappings

#### Task P1.4.4: Populate symbols with relationships (30 min)
**Deliverable**: Symbols table populated with foreign key relationships

**Process**:
1. Create symbols linked to appropriate exchanges
2. Populate trading rules where available
3. Set initial precision and size data
4. Mark all as active initially

#### Task P1.4.5: Validate data integrity (20 min)
**Deliverable**: Data integrity report and fixes

**Validation Checks**:
- [ ] All foreign key relationships valid
- [ ] No orphaned symbols
- [ ] Exchange enum mappings correct
- [ ] Symbol uniqueness constraints satisfied
- [ ] Data counts match original dataset

### Day 5: Integration Testing & Performance Validation

#### Final Integration Tasks
1. **Cache Loading Test**: Verify cache loads all reference data correctly
2. **Performance Benchmarking**: Validate sub-millisecond operation targets
3. **Integration Testing**: Ensure new tables don't affect existing operations
4. **Documentation**: Complete Phase 1 implementation documentation

## Performance Targets

### Phase 1 Performance Requirements
- **Symbol ID Resolution**: <1μs average (cache hit)
- **Exchange Lookup**: <1μs average (cache hit)  
- **Cache Initialization**: <100ms for complete dataset
- **Database Impact**: Zero performance degradation for existing operations
- **Memory Usage**: <10MB cache footprint for typical symbol set

### Monitoring & Validation
- Continuous performance monitoring during implementation
- Daily cache performance reports
- Integration testing with existing operations
- Rollback procedures ready if performance degrades

## Risk Mitigation

### Low Risk Items (Phase 1 focus)
- ✅ **Additive Changes Only**: No modifications to existing tables
- ✅ **Independent Operations**: Reference tables don't affect current workflows  
- ✅ **Gradual Integration**: Cache can be tested independently

### Contingency Plans
- **Performance Issues**: Fall back to database lookups if cache fails
- **Data Inconsistency**: Validation scripts to verify data integrity
- **Schema Issues**: Migration rollback procedures documented

## Dependencies

### External Dependencies
- Current database access and connection pooling
- ExchangeEnum updates (already completed)
- msgspec library for cache structures

### Phase Dependencies
- **Phase 2 Depends On**: Successful completion of all Phase 1 tasks
- **Critical Path**: Cache infrastructure must be operational before migration

## Success Metrics

### Completion Criteria
- [ ] All 20 Phase 1 tasks completed successfully  
- [ ] Performance targets met or exceeded
- [ ] Zero impact on existing system performance
- [ ] Reference data populated and validated
- [ ] Cache infrastructure operational and tested

### Phase 1 Deliverables
1. ✅ **Exchange Reference Table**: Fully populated and operational
2. ✅ **Symbol Reference Table**: Complete with relationships and trading rules
3. ✅ **Cache Infrastructure**: Sub-microsecond lookup performance
4. ✅ **Performance Baselines**: Documented current system performance
5. ✅ **Integration Framework**: Ready for Phase 2 migration

---

**Next Phase**: [Phase 2: Migration](phase2_migration.md) - Data migration and normalized table creation

**Estimated Total Time**: 25-30 hours across 5 days
**Risk Level**: Low (additive changes only)
**Dependencies**: None (can start immediately)