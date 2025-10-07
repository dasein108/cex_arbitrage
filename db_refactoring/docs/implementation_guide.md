# Database Refactoring Implementation Guide

## Quick Start

This guide provides step-by-step instructions for implementing the database refactoring plan. Follow these instructions to transform the current denormalized schema into a normalized, high-performance architecture.

## Prerequisites

### System Requirements
- PostgreSQL 12+ (for generated columns and advanced indexing)
- Python 3.9+ with asyncpg
- Access to current cex_arbitrage database
- Minimum 1GB available disk space for migration

### Before You Begin
1. **Backup your database**: Create a full backup before starting
2. **Review the plan**: Read [README.md](../README.md) for complete overview
3. **Verify dependencies**: Ensure all application dependencies are installed
4. **Check disk space**: Migration will temporarily double storage requirements

## Phase-by-Phase Implementation

### Phase 1: Foundation (Week 1)
**Goal**: Create reference tables and cache infrastructure

#### Step 1.1: Exchange Reference Table (Day 1)
```bash
# Navigate to project root
cd /Users/dasein/dev/cex_arbitrage

# Run exchange table migration
psql -U postgres -d cex_arbitrage -f db_refactoring/migrations/002_create_exchanges.sql

# Verify migration success
python db_refactoring/scripts/validate_migration.py --phase 1
```

#### Step 1.2: Symbol Reference Table (Day 2)
```bash
# Run symbol table migration
psql -U postgres -d cex_arbitrage -f db_refactoring/migrations/003_create_symbols.sql

# Validate symbol population
psql -U postgres -d cex_arbitrage -c "SELECT COUNT(*) FROM symbols;"
```

#### Step 1.3: Cache Infrastructure (Day 3)
```bash
# Implement cache layer
cp db_refactoring/templates/cache.py src/db/cache.py

# Update models.py with new structures
# Follow detailed instructions in tasks/phase1_tasks.md

# Test cache performance
python -c "
import asyncio
from src.db.cache import ClassifierCache
cache = ClassifierCache()
asyncio.run(cache.initialize_from_database())
print('Cache loaded successfully')
"
```

#### Phase 1 Validation
```bash
# Run comprehensive Phase 1 validation
python db_refactoring/scripts/validate_migration.py --phase 1

# Expected output: All tests passing with <1ms performance
```

### Phase 2: Migration (Week 2)
**Goal**: Migrate data to normalized tables

#### Step 2.1: Create Normalized Tables
```bash
# Create normalized market data tables
psql -U postgres -d cex_arbitrage -f db_refactoring/migrations/004_create_normalized_tables.sql

# Verify table creation
psql -U postgres -d cex_arbitrage -c "\\d book_ticker_snapshots_v2"
```

#### Step 2.2: Data Migration
```bash
# Run incremental data migration
python db_refactoring/scripts/migrate_data.py --batch-size 10000 --verify

# Monitor progress
tail -f migration.log
```

#### Step 2.3: Validation
```bash
# Validate data integrity
python db_refactoring/scripts/validate_migration.py --phase 2

# Compare record counts
psql -U postgres -d cex_arbitrage -c "
SELECT 
    (SELECT COUNT(*) FROM book_ticker_snapshots) as original_count,
    (SELECT COUNT(*) FROM book_ticker_snapshots_v2) as migrated_count;
"
```

### Phase 3: Integration (Week 3)
**Goal**: Update application code to use normalized schema

#### Step 3.1: Update Models
```python
# Update src/db/models.py
# Add new normalized model classes
# Follow templates in db_refactoring/templates/

# Example update:
class BookTickerSnapshotV2(msgspec.Struct):
    id: Optional[int] = None
    symbol_id: int  # Foreign key to symbols table
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    timestamp: datetime
    created_at: Optional[datetime] = None
```

#### Step 3.2: Update Operations
```python
# Update src/db/operations.py
# Modify functions to use symbol_id instead of string fields

async def insert_book_ticker_snapshot_v2(snapshot: BookTickerSnapshotV2) -> int:
    """Insert using normalized schema."""
    # Implementation using symbol_id foreign key
```

#### Step 3.3: Cache Integration
```python
# Update src/db/connection.py
# Initialize cache on database connection

from .cache import ClassifierCache

class DatabaseManager:
    def __init__(self):
        self.cache = ClassifierCache()
    
    async def initialize(self, config: DatabaseConfig):
        # Existing initialization...
        await self.cache.initialize_from_database()
```

### Phase 4: Extensions (Week 4)
**Goal**: Add balance and execution tracking

#### Step 4.1: Balance Tracking
```bash
# Create balance tracking tables
psql -U postgres -d cex_arbitrage -f db_refactoring/migrations/005_create_balance_tracking.sql

# Test balance operations
python -c "
from src.db.operations import insert_account_balance
# Test balance tracking functionality
"
```

#### Step 4.2: Execution Tracking
```bash
# Create execution tracking tables
psql -U postgres -d cex_arbitrage -f db_refactoring/migrations/006_create_execution_tracking.sql

# Verify analytics views
psql -U postgres -d cex_arbitrage -c "SELECT * FROM arbitrage_opportunities LIMIT 5;"
```

## Task Execution Guide

### Daily Task Structure

Each day follows this pattern:
1. **Morning**: Review task list and dependencies
2. **Implementation**: Execute tasks in order (15-30 min each)
3. **Validation**: Run tests after each major task
4. **Evening**: Update progress and plan next day

### Task Tracking

Use the provided task tracker:
```bash
# View current task status
cat db_refactoring/tasks/task_tracker.md

# Update task status as you complete them
# Mark completed tasks with ✅ in the tracker
```

### Error Handling

If you encounter errors:

1. **Check Dependencies**:
   ```bash
   # Verify prerequisite tables exist
   psql -U postgres -d cex_arbitrage -c "\\dt"
   ```

2. **Review Logs**:
   ```bash
   # Check PostgreSQL logs for detailed error messages
   tail -f /var/log/postgresql/postgresql.log
   ```

3. **Rollback if Needed**:
   ```bash
   # Emergency rollback
   python db_refactoring/scripts/rollback_procedures.py --phase 1 --backup
   ```

## Performance Monitoring

### Continuous Performance Tracking

Monitor performance at each step:

```bash
# Run performance benchmarks
python db_refactoring/scripts/performance_test.py

# Expected targets:
# - Symbol resolution: <1μs (cache hit)
# - Database queries: <5ms average
# - Cache loading: <100ms for full dataset
```

### Performance Validation Queries

```sql
-- Test symbol lookup performance
EXPLAIN ANALYZE 
SELECT id FROM symbols s 
JOIN exchanges e ON s.exchange_id = e.id 
WHERE e.enum_value = 'MEXC_SPOT' 
AND s.base_asset = 'BTC' 
AND s.quote_asset = 'USDT';

-- Should show index scan with <1ms execution time
```

## Troubleshooting Guide

### Common Issues

#### 1. Migration Fails - Table Dependencies
```bash
# Check for foreign key violations
psql -U postgres -d cex_arbitrage -c "
SELECT conname, conrelid::regclass, confrelid::regclass 
FROM pg_constraint 
WHERE contype = 'f' AND connamespace = 'public'::regnamespace;
"

# Solution: Ensure parent tables exist before creating child tables
```

#### 2. Performance Degradation
```bash
# Check index usage
psql -U postgres -d cex_arbitrage -c "
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read 
FROM pg_stat_user_indexes 
ORDER BY idx_scan DESC;
"

# Solution: Verify indexes are being used, rebuild if necessary
```

#### 3. Cache Initialization Fails
```python
# Debug cache loading
import asyncio
from src.db.cache import ClassifierCache

async def debug_cache():
    cache = ClassifierCache()
    try:
        await cache.initialize_from_database()
        print("Cache loaded successfully")
    except Exception as e:
        print(f"Cache error: {e}")
        # Check database connection and table structure

asyncio.run(debug_cache())
```

#### 4. Data Inconsistency
```bash
# Verify data integrity
python db_refactoring/scripts/validate_migration.py --phase 2

# Check for orphaned records
psql -U postgres -d cex_arbitrage -c "
SELECT 'Orphaned symbols' as issue, COUNT(*) 
FROM symbols s 
LEFT JOIN exchanges e ON s.exchange_id = e.id 
WHERE e.id IS NULL;
"
```

## Testing Strategy

### Unit Testing
```bash
# Run unit tests for each component
cd src/
python -m pytest tests/db/ -v

# Test specific functionality
python -m pytest tests/db/test_cache.py::test_symbol_resolution_performance
```

### Integration Testing
```bash
# Full integration test
python db_refactoring/scripts/integration_test.py

# Test data consistency
python db_refactoring/scripts/data_integrity_check.py
```

### Load Testing
```bash
# Simulate high-frequency operations
python db_refactoring/scripts/load_test.py --duration 60 --operations 1000

# Monitor system resources during test
htop
```

## Deployment Checklist

### Pre-Deployment
- [ ] All unit tests passing
- [ ] Integration tests successful
- [ ] Performance benchmarks met
- [ ] Rollback procedures tested
- [ ] Documentation updated

### Deployment Steps
1. **Backup Production**: Create full database backup
2. **Deploy in Stages**: Use blue-green deployment if possible
3. **Monitor Closely**: Watch performance metrics and error rates
4. **Validate Functionality**: Run post-deployment tests
5. **Rollback Plan Ready**: Have immediate rollback capability

### Post-Deployment
- [ ] Performance monitoring active
- [ ] Error rates within normal ranges
- [ ] Cache performance optimal
- [ ] Data integrity validated
- [ ] Team notification sent

## Success Criteria

### Phase 1 Success
- ✅ Exchange and symbol tables operational
- ✅ Cache providing <1μs symbol resolution
- ✅ All existing functionality preserved
- ✅ Performance targets met

### Phase 2 Success  
- ✅ All data migrated accurately
- ✅ Normalized tables operational
- ✅ Backward compatibility maintained
- ✅ No data loss

### Phase 3 Success
- ✅ Application code updated
- ✅ Cache integrated
- ✅ Performance improved
- ✅ HFT targets achieved

### Phase 4 Success
- ✅ Balance tracking operational
- ✅ Execution monitoring active
- ✅ Analytics providing insights
- ✅ System production-ready

## Support and Resources

### Documentation
- [Schema Design](schema_design.md) - Complete schema documentation
- [Cache Architecture](cache_architecture.md) - Cache implementation details
- [Performance Targets](performance_targets.md) - HFT compliance requirements

### Tools and Scripts
- `validate_migration.py` - Automated testing and validation
- `rollback_procedures.py` - Emergency rollback procedures
- `performance_test.py` - Performance benchmarking
- `data_integrity_check.py` - Data consistency validation

### Getting Help
1. **Review Documentation**: Check relevant .md files in docs/
2. **Run Validation**: Use automated validation scripts
3. **Check Logs**: Review PostgreSQL and application logs
4. **Rollback if Needed**: Use emergency procedures if critical issues arise

---

**Remember**: This is a complex migration affecting the core data architecture. Take it step by step, validate frequently, and don't hesitate to rollback if issues arise. The goal is a more performant, maintainable system - but not at the cost of data integrity or system stability.