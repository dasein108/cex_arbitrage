# Database Refactoring Migration Tasks

**Step-by-step implementation plan for migrating from 12-file database layer to unified DatabaseManager**

## Phase 1: Create New DatabaseManager (Estimated: 2-3 days)

### Task 1.1: Create Core DatabaseManager Class (8 hours)

**Subtask 1.1.1: Set up basic class structure (2 hours)**
- [ ] Create `/src/db/database_manager.py` 
- [ ] Implement `__init__`, core variables, and logging setup
- [ ] Add built-in caching infrastructure with TTL management
- [ ] Implement cache helper methods (`_cache_get`, `_cache_set`, `_cache_invalidate`)

**Subtask 1.1.2: Implement connection management (2 hours)**
- [ ] Implement `initialize()` method with HftConfig integration
- [ ] Add asyncpg connection pool setup with HFT optimizations
- [ ] Implement `close()` method and proper cleanup
- [ ] Add connection health checks and error handling

**Subtask 1.1.3: Add basic utility methods (2 hours)**
- [ ] Implement `_cleanup_expired_cache()` with TTL enforcement
- [ ] Add `get_performance_stats()` for monitoring
- [ ] Implement `get_database_stats()` for system health
- [ ] Add `_warm_essential_cache()` for initialization

**Subtask 1.1.4: Create comprehensive tests (2 hours)**
- [ ] Set up test infrastructure for DatabaseManager
- [ ] Add unit tests for caching functionality
- [ ] Test connection management and error scenarios
- [ ] Add performance benchmarks for cache operations

### Task 1.2: Implement Exchange Operations (4 hours)

**Subtask 1.2.1: Core exchange queries (2 hours)**
- [ ] Implement `get_exchange_by_enum()` with caching
- [ ] Add `get_exchange_by_id()` with cache integration
- [ ] Implement `get_all_exchanges()` with cache management
- [ ] Add proper error handling and logging

**Subtask 1.2.2: Exchange modification operations (2 hours)**
- [ ] Implement `insert_exchange()` with cache invalidation
- [ ] Add exchange update functionality if needed
- [ ] Ensure proper transaction handling
- [ ] Test cache invalidation on modifications

### Task 1.3: Implement Symbol Operations (6 hours)

**Subtask 1.3.1: Basic symbol queries (3 hours)**
- [ ] Implement `get_symbol_by_id()` with caching
- [ ] Add `get_symbols_by_exchange()` with efficient cache keys
- [ ] Implement `get_symbol_by_exchange_and_pair()` lookup
- [ ] Optimize cache key strategies for symbol operations

**Subtask 1.3.2: Symbol modification operations (3 hours)**
- [ ] Implement `insert_symbol()` with proper cache invalidation
- [ ] Add bulk symbol insertion for efficiency
- [ ] Ensure proper foreign key handling for exchange_id
- [ ] Test symbol cache invalidation patterns

### Task 1.4: Implement BookTicker Operations (6 hours)

**Subtask 1.4.1: BookTicker insertion (3 hours)**
- [ ] Implement `insert_book_ticker_snapshots()` with deduplication
- [ ] Add batch processing with ON CONFLICT handling
- [ ] Optimize for high-frequency insertion patterns
- [ ] Add proper timestamp handling and validation

**Subtask 1.4.2: BookTicker queries (3 hours)**
- [ ] Implement `get_latest_book_tickers()` with caching
- [ ] Add `get_book_ticker_history()` for analysis
- [ ] Implement efficient filtering by exchange/symbol
- [ ] Optimize query performance with proper indexing

### Task 1.5: Implement Balance Operations (4 hours)

**Subtask 1.5.1: Balance data management (2 hours)**
- [ ] Implement `insert_balance_snapshots()` with conflict resolution
- [ ] Add proper float handling for HFT performance
- [ ] Ensure exchange_id foreign key relationships
- [ ] Test batch insertion performance

**Subtask 1.5.2: Balance queries (2 hours)**
- [ ] Implement `get_latest_balances()` with caching
- [ ] Add `get_balance_history()` for tracking
- [ ] Implement efficient filtering and aggregation
- [ ] Test cache efficiency for balance operations

### Task 1.6: Implement Funding Rate Operations (3 hours)

**Subtask 1.6.1: Funding rate insertion (1.5 hours)**
- [ ] Implement `insert_funding_rates()` with validation
- [ ] Add funding_time constraint handling (> 0)
- [ ] Ensure proper timestamp and next_funding_time handling
- [ ] Test batch processing for funding rates

**Subtask 1.6.2: Funding rate queries (1.5 hours)**
- [ ] Implement `get_latest_funding_rates()` with caching
- [ ] Add filtering by exchange and symbol
- [ ] Optimize for futures trading requirements
- [ ] Test cache performance for funding data

### Task 1.7: Add Data Cleanup and Maintenance (2 hours)

**Subtask 1.7.1: Implement cleanup operations (1 hour)**
- [ ] Implement `cleanup_old_data()` with retention policies
- [ ] Add configurable retention periods per data type
- [ ] Ensure safe deletion without foreign key violations
- [ ] Test cleanup performance and data integrity

**Subtask 1.7.2: Add maintenance utilities (1 hour)**
- [ ] Add database health monitoring
- [ ] Implement cache statistics and reporting
- [ ] Add performance monitoring hooks
- [ ] Create maintenance scheduling capabilities

## Phase 2: Update Integration Points (Estimated: 2-3 days)

### Task 2.1: Identify and Document Integration Points (2 hours)

**Subtask 2.1.1: Scan codebase for db imports (1 hour)**
- [ ] Find all files importing from `db.operations`
- [ ] Identify `db.cache_operations` usage patterns
- [ ] Document `db.models` direct usage
- [ ] List `db.connection` integration points

**Subtask 2.1.2: Create migration mapping (1 hour)**
- [ ] Map old function calls to new DatabaseManager methods
- [ ] Document parameter changes and return value differences
- [ ] Identify breaking changes requiring code updates
- [ ] Create compatibility shims if needed

### Task 2.2: Update Data Collection Components (6 hours)

**Subtask 2.2.1: Update collector.py (2 hours)**
- [ ] Replace `db.operations` imports with `DatabaseManager`
- [ ] Update initialization pattern to use new manager
- [ ] Modify book ticker insertion calls
- [ ] Test data collection functionality

**Subtask 2.2.2: Update balance sync task (2 hours)**
- [ ] Replace balance operations imports
- [ ] Update balance snapshot insertion patterns
- [ ] Modify balance retrieval for analytics
- [ ] Test balance synchronization workflow

**Subtask 2.2.3: Update other data collection tools (2 hours)**
- [ ] Update `data_fetcher.py` to use DatabaseManager
- [ ] Modify test collectors and demos
- [ ] Update any symbol sync operations
- [ ] Test all data collection workflows

### Task 2.3: Update Analysis Components (4 hours)

**Subtask 2.3.1: Update strategy backtester (2 hours)**
- [ ] Replace database import patterns
- [ ] Update data retrieval for backtesting
- [ ] Modify symbol and exchange lookups
- [ ] Test backtesting data pipeline

**Subtask 2.3.2: Update analysis tools (2 hours)**
- [ ] Update delta neutral analyzer database calls
- [ ] Modify risk monitor database integration
- [ ] Update microstructure analyzer data access
- [ ] Test all analysis components

### Task 2.4: Update Application Components (4 hours)

**Subtask 2.4.1: Update arbitrage applications (2 hours)**
- [ ] Modify exchange manager database usage
- [ ] Update strategy database integration
- [ ] Test application startup and database connectivity
- [ ] Verify strategy data retrieval

**Subtask 2.4.2: Update demo and example files (2 hours)**
- [ ] Update `db_operations_demo.py` to use DatabaseManager
- [ ] Modify example scripts and demos
- [ ] Update quickstart guides and documentation
- [ ] Test all demo functionality

### Task 2.5: Update Configuration and Utilities (2 hours)

**Subtask 2.5.1: Update configuration management (1 hour)**
- [ ] Ensure HftConfig integration works properly
- [ ] Test database configuration loading
- [ ] Verify connection string generation
- [ ] Test configuration validation

**Subtask 2.5.2: Update utility scripts (1 hour)**
- [ ] Update deployment scripts database usage
- [ ] Modify monitoring script database calls
- [ ] Update maintenance script integration
- [ ] Test all utility scripts

## Phase 3: Testing and Validation (Estimated: 1-2 days)

### Task 3.1: Comprehensive Integration Testing (4 hours)

**Subtask 3.1.1: End-to-end workflow testing (2 hours)**
- [ ] Test complete data collection → storage → retrieval workflow
- [ ] Verify cache performance under load
- [ ] Test concurrent access patterns
- [ ] Validate data integrity across operations

**Subtask 3.1.2: Performance validation (2 hours)**
- [ ] Benchmark DatabaseManager vs. old system
- [ ] Test cache hit ratios and performance
- [ ] Validate memory usage improvements
- [ ] Test startup time and initialization

### Task 3.2: Error Handling and Edge Cases (3 hours)

**Subtask 3.2.1: Test error scenarios (1.5 hours)**
- [ ] Test database connection failures
- [ ] Validate cache timeout and invalidation
- [ ] Test malformed data handling
- [ ] Verify transaction rollback scenarios

**Subtask 3.2.2: Test edge cases (1.5 hours)**
- [ ] Test empty data sets and null handling
- [ ] Validate large batch operations
- [ ] Test cache overflow scenarios
- [ ] Verify cleanup operation safety

### Task 3.3: Migration Validation (2 hours)

**Subtask 3.3.1: Data consistency validation (1 hour)**
- [ ] Compare old vs. new system outputs
- [ ] Validate cache consistency
- [ ] Test data migration completeness
- [ ] Verify no data loss during transition

**Subtask 3.3.2: Performance comparison (1 hour)**
- [ ] Benchmark operation latencies
- [ ] Compare memory usage patterns
- [ ] Validate cache efficiency improvements
- [ ] Test system resource utilization

## Phase 4: Cleanup and Documentation (Estimated: 1 day)

### Task 4.1: Remove Old Database Files (2 hours)

**Subtask 4.1.1: Archive old implementation (1 hour)**
- [ ] Create backup of old db/ directory structure
- [ ] Document migration changes and rationale
- [ ] Archive old files for reference
- [ ] Create rollback procedure if needed

**Subtask 4.1.2: Clean up old files (1 hour)**
- [ ] Remove old `operations.py` (2,281 LOC)
- [ ] Remove cache files: `cache.py`, `cache_operations.py`, etc.
- [ ] Remove sync files: `symbol_sync.py`, `exchange_sync.py`
- [ ] Remove old model files and helpers

### Task 4.2: Update Documentation (3 hours)

**Subtask 4.2.1: Update technical documentation (1.5 hours)**
- [ ] Update database integration guides
- [ ] Modify API documentation for new DatabaseManager
- [ ] Update configuration documentation
- [ ] Create migration guide for future developers

**Subtask 4.2.2: Update examples and tutorials (1.5 hours)**
- [ ] Update quickstart guides
- [ ] Modify example code and demos
- [ ] Update troubleshooting guides
- [ ] Create DatabaseManager usage examples

### Task 4.3: Final Validation and Deployment (3 hours)

**Subtask 4.3.1: Production readiness check (1.5 hours)**
- [ ] Run full test suite with new implementation
- [ ] Validate production configuration
- [ ] Test deployment procedures
- [ ] Verify monitoring and logging

**Subtask 4.3.2: Deployment and monitoring (1.5 hours)**
- [ ] Deploy to staging environment
- [ ] Monitor performance metrics
- [ ] Test production workloads
- [ ] Validate system stability

## Risk Mitigation Strategies

### Rollback Plan

**If Issues Arise:**
1. **Phase 1-2**: Simple rollback by reverting new files
2. **Phase 3**: Restore old imports and test thoroughly
3. **Phase 4**: Restore archived files if needed

**Rollback Triggers:**
- Performance degradation >20%
- Data integrity issues
- Critical functionality failures
- Unresolvable integration issues

### Testing Strategy

**Continuous Validation:**
- Run integration tests after each subtask
- Compare performance metrics continuously
- Validate data consistency at each checkpoint
- Monitor memory usage and system resources

**Quality Gates:**
- All tests must pass before proceeding
- Performance must meet or exceed current benchmarks
- No data integrity issues
- All integration points must work correctly

## Success Criteria

### Completion Metrics

**Quantitative Success:**
- [ ] Lines of code reduced from ~7,600 to ~1,000 (85% reduction)
- [ ] File count reduced from 12 to 1 (92% reduction)
- [ ] Integration points reduced from 16 to 1 (94% reduction)
- [ ] Memory usage reduced by 40-60%
- [ ] Test coverage maintained >95%

**Qualitative Success:**
- [ ] All existing functionality preserved
- [ ] Performance equal or better than current system
- [ ] Code maintainability significantly improved
- [ ] Developer onboarding time reduced
- [ ] System complexity significantly reduced

### Validation Checklist

**Before Final Deployment:**
- [ ] All 16 integration points updated and tested
- [ ] Complete test suite passes
- [ ] Performance benchmarks meet targets
- [ ] Documentation updated and accurate
- [ ] Production deployment tested
- [ ] Rollback procedure validated
- [ ] Monitoring and alerting configured

## Timeline Summary

**Total Estimated Time: 6-9 days**

- **Phase 1** (Create DatabaseManager): 2-3 days
- **Phase 2** (Update Integration Points): 2-3 days  
- **Phase 3** (Testing & Validation): 1-2 days
- **Phase 4** (Cleanup & Documentation): 1 day

**Critical Path:**
1. Complete DatabaseManager implementation
2. Update all integration points systematically
3. Comprehensive testing and validation
4. Clean deployment and documentation

This migration plan ensures a **safe, systematic transition** from the complex 12-file database layer to a **simple, unified DatabaseManager class** while preserving all functionality and improving performance.