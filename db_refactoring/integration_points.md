# Database Integration Points Analysis

**Complete mapping of all files that import from the db/ directory and require updates during refactoring**

## Integration Points Summary

**Total Files Requiring Updates: 16**
- **High Priority**: 8 files (core functionality)
- **Medium Priority**: 5 files (examples and tools) 
- **Low Priority**: 3 files (tests and documentation)

## Core Application Files (High Priority)

### 1. `/src/applications/data_collection/collector.py`
**Current Imports:**
```python
from db.operations import (
    insert_book_ticker_snapshots_batch,
    get_latest_book_ticker_snapshots,
    insert_funding_rate_snapshots_batch,
    insert_balance_snapshots_batch
)
from db.models import BookTickerSnapshot, FundingRateSnapshot, BalanceSnapshot
from db.connection import initialize_database
```

**Usage Patterns:**
- High-frequency book ticker data insertion
- Batch processing for funding rates
- Balance snapshot collection
- Database initialization for collection services

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update usage:
db_manager = DatabaseManager()
await db_manager.initialize()
await db_manager.insert_book_ticker_snapshots(snapshots)
await db_manager.insert_funding_rates(funding_snapshots)
await db_manager.insert_balance_snapshots(balance_snapshots)
```

**Complexity**: High - Core data collection functionality

### 2. `/src/applications/hedged_arbitrage/strategy/exchange_manager.py`
**Current Imports:**
```python
from db.operations import get_exchange_by_enum, get_symbols_by_exchange
from db.cache_operations import cached_get_exchange_by_enum
from db.models import Exchange, Symbol
```

**Usage Patterns:**
- Exchange configuration loading
- Symbol discovery and validation
- Cache-optimized exchange lookups
- Strategy initialization data

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update usage:
db_manager = DatabaseManager()
exchange = await db_manager.get_exchange_by_enum(exchange_enum)
symbols = await db_manager.get_symbols_by_exchange(exchange_id)
```

**Complexity**: High - Critical strategy infrastructure

### 3. `/src/applications/hedged_arbitrage/strategy/mexc_gateio_futures_strategy.py`
**Current Imports:**
```python
from db.operations import insert_book_ticker_snapshots_batch
from db.models import BookTickerSnapshot
```

**Usage Patterns:**
- Strategy-specific data collection
- Real-time market data storage
- Performance tracking data

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update usage:
db_manager = DatabaseManager()
await db_manager.insert_book_ticker_snapshots(snapshots)
```

**Complexity**: Medium - Strategy-specific integration

### 4. `/src/trading/tasks/balance_sync_task.py`
**Current Imports:**
```python
from db.operations import (
    insert_balance_snapshots_batch,
    get_latest_balance_snapshots,
    get_exchange_by_enum
)
from db.models import BalanceSnapshot
from db.cache_operations import cached_get_exchange_by_enum
```

**Usage Patterns:**
- Scheduled balance synchronization
- Multi-exchange balance tracking
- Cache-optimized balance retrieval
- Task scheduling integration

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update usage:
db_manager = DatabaseManager()
await db_manager.insert_balance_snapshots(snapshots)
balances = await db_manager.get_latest_balances(exchange_enum)
exchange = await db_manager.get_exchange_by_enum(exchange_enum)
```

**Complexity**: High - Critical balance management

### 5. `/src/trading/analysis/strategy_backtester.py`
**Current Imports:**
```python
from db.operations import (
    get_book_ticker_snapshots_by_exchange_and_symbol,
    get_symbol_by_exchange_and_pair,
    get_exchange_by_enum_value
)
from db.models import BookTickerSnapshot, Symbol, Exchange
```

**Usage Patterns:**
- Historical data retrieval for backtesting
- Time-series analysis queries
- Symbol and exchange resolution
- Performance analysis data

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update usage:
db_manager = DatabaseManager()
history = await db_manager.get_book_ticker_history(exchange, symbol_base, symbol_quote, hours)
symbol = await db_manager.get_symbol_by_exchange_and_pair(exchange_id, base, quote)
exchange = await db_manager.get_exchange_by_enum(exchange_enum)
```

**Complexity**: High - Critical analysis functionality

### 6. `/src/trading/analysis/delta_neutral_analyzer.py`
**Current Imports:**
```python
from db.operations import get_latest_book_ticker_snapshots, get_balance_database_stats
from db.models import BookTickerSnapshot
```

**Usage Patterns:**
- Real-time market data analysis
- Delta neutral strategy calculations
- Portfolio balance analysis
- Risk assessment data

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update usage:
db_manager = DatabaseManager()
latest_tickers = await db_manager.get_latest_book_tickers()
stats = await db_manager.get_database_stats()
```

**Complexity**: Medium - Analysis tool integration

### 7. `/src/trading/analysis/microstructure_analyzer.py`
**Current Imports:**
```python
from db.operations import get_book_ticker_history, get_recent_trades
from db.models import BookTickerSnapshot, TradeSnapshot
```

**Usage Patterns:**
- Microstructure analysis queries
- Trade flow analysis
- Order flow imbalance calculations
- High-frequency data processing

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update usage:
db_manager = DatabaseManager()
history = await db_manager.get_book_ticker_history(exchange, symbol_base, symbol_quote, hours)
# Note: get_recent_trades may need implementation in DatabaseManager
```

**Complexity**: Medium - Specialized analysis tool

### 8. `/src/trading/analysis/risk_monitor.py`
**Current Imports:**
```python
from db.operations import get_latest_balance_snapshots, get_database_stats
from db.models import BalanceSnapshot
```

**Usage Patterns:**
- Real-time risk monitoring
- Portfolio balance tracking
- System health monitoring
- Alert generation data

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update usage:
db_manager = DatabaseManager()
balances = await db_manager.get_latest_balances()
stats = await db_manager.get_database_stats()
```

**Complexity**: Medium - Risk management integration

## Example and Demo Files (Medium Priority)

### 9. `/src/examples/demo/db_operations_demo.py`
**Current Imports:**
```python
from db.operations import (
    get_exchange_by_enum_value, insert_exchange, get_all_active_exchanges,
    get_symbol_by_exchange_and_pair, insert_symbol, get_symbols_by_exchange,
    insert_book_ticker_snapshot, insert_book_ticker_snapshots_batch,
    get_latest_book_ticker_snapshots, get_database_stats,
    insert_funding_rate_snapshots_batch,
    insert_balance_snapshots_batch, get_latest_balance_snapshots
)
from db.models import Exchange, Symbol, BookTickerSnapshot, FundingRateSnapshot, BalanceSnapshot, SymbolType
from db.connection import initialize_database, get_db_manager
```

**Usage Patterns:**
- Comprehensive demo of all database operations
- Example integration patterns
- Testing and validation workflows
- Educational code examples

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update to single manager pattern:
db_manager = DatabaseManager()
await db_manager.initialize()
# All operations through db_manager.*
```

**Complexity**: High - Comprehensive example requiring all functionality

### 10. `/src/applications/data_collection/test_refactored_collector.py`
**Current Imports:**
```python
from db.operations import insert_book_ticker_snapshots_batch
from db.models import BookTickerSnapshot
from db.connection import initialize_database
```

**Usage Patterns:**
- Test data collection workflows
- Validation of refactored collectors
- Performance testing

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update test patterns:
db_manager = DatabaseManager()
await db_manager.initialize()
await db_manager.insert_book_ticker_snapshots(test_snapshots)
```

**Complexity**: Low - Test file with simple usage

### 11. `/src/applications/data_collection/test_collector_refactoring.py`
**Current Imports:**
```python
from db.connection import initialize_database
from db.operations import get_database_stats
```

**Usage Patterns:**
- Collector refactoring tests
- Performance validation
- System health checks

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update test patterns:
db_manager = DatabaseManager()
await db_manager.initialize()
stats = await db_manager.get_database_stats()
```

**Complexity**: Low - Simple test integration

### 12. `/src/applications/data_collection/test_bookticker_fix.py`
**Current Imports:**
```python
from db.operations import insert_book_ticker_snapshots_batch
from db.models import BookTickerSnapshot
```

**Usage Patterns:**
- BookTicker functionality testing
- Bug fix validation
- Data integrity testing

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update test:
db_manager = DatabaseManager()
await db_manager.insert_book_ticker_snapshots(snapshots)
```

**Complexity**: Low - Focused test file

### 13. `/src/applications/tools/data_fetcher.py`
**Current Imports:**
```python
from db.operations import get_all_active_exchanges, get_symbols_by_exchange
from db.models import Exchange, Symbol
```

**Usage Patterns:**
- Data fetching utilities
- Exchange and symbol discovery
- Batch data processing tools

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update tool:
db_manager = DatabaseManager()
exchanges = await db_manager.get_all_exchanges()
symbols = await db_manager.get_symbols_by_exchange(exchange_id)
```

**Complexity**: Medium - Utility tool integration

## Test Files (Low Priority)

### 14. `/src/db/test_comprehensive_db.py`
**Current Imports:**
```python
from db.operations import *
from db.models import *
from db.connection import initialize_database
```

**Usage Patterns:**
- Comprehensive database testing
- Integration test suite
- Performance benchmarking

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update all test patterns to use unified manager
```

**Complexity**: Medium - Comprehensive test update required

### 15. `/src/db/test_fixed_operations.py`
**Current Imports:**
```python
from db.operations import insert_book_ticker_snapshots_batch
from db.models import BookTickerSnapshot
```

**Usage Patterns:**
- Specific operation testing
- Bug fix validation
- Regression testing

**Migration Changes:**
```python
# Replace with:
from db.database_manager import DatabaseManager

# Update specific tests
```

**Complexity**: Low - Simple test file

## Documentation Files (Low Priority)

### 16. `/src/trading/analysis/README.md`
**Current References:**
```markdown
from db.operations import get_latest_book_ticker_snapshots
from db.models import BookTickerSnapshot
```

**Usage Patterns:**
- Code documentation
- Usage examples
- Integration guides

**Migration Changes:**
```markdown
# Update documentation to show DatabaseManager usage:
from db.database_manager import DatabaseManager

db_manager = DatabaseManager()
await db_manager.initialize()
```

**Complexity**: Low - Documentation update

## Migration Strategy by Priority

### Phase 1: High Priority Files (Core Functionality)
**Files 1-5, 9**: Critical system components that must work correctly
- Focus on complete functionality preservation
- Extensive testing required
- Performance validation essential

### Phase 2: Medium Priority Files (Tools and Examples)  
**Files 6-8, 10-13**: Important but not critical for core operations
- Update after core components are stable
- Use as validation of DatabaseManager completeness
- Good integration testing opportunities

### Phase 3: Low Priority Files (Tests and Documentation)
**Files 14-16**: Support files that can be updated last
- Update tests to validate new implementation
- Update documentation to reflect new patterns
- Clean up old references and examples

## Common Migration Patterns

### Pattern 1: Replace Import Statements
```python
# OLD:
from db.operations import insert_book_ticker_snapshots_batch
from db.models import BookTickerSnapshot
from db.connection import initialize_database

# NEW:
from db.database_manager import DatabaseManager
```

### Pattern 2: Replace Initialization
```python
# OLD:
await initialize_database(db_config)
# Later use db.operations functions

# NEW:
db_manager = DatabaseManager()
await db_manager.initialize()
# Use db_manager methods
```

### Pattern 3: Replace Cache Operations
```python
# OLD:
from db.cache_operations import cached_get_exchange_by_enum
exchange = cached_get_exchange_by_enum(exchange_enum)

# NEW:
exchange = await db_manager.get_exchange_by_enum(exchange_enum)
# Caching is built-in to DatabaseManager
```

### Pattern 4: Replace Model Usage
```python
# OLD:
from db.models import BookTickerSnapshot
snapshot = BookTickerSnapshot.from_symbol_id_and_data(...)

# NEW:
# Use plain dictionaries with DatabaseManager
snapshot = {
    'symbol_id': symbol_id,
    'bid_price': bid_price,
    # ... other fields
}
```

## Validation Checklist

### Pre-Migration Validation
- [ ] Identify all import statements in each file
- [ ] Document current usage patterns
- [ ] Note any custom model methods being used
- [ ] Identify performance-critical operations

### Post-Migration Validation
- [ ] All imports updated correctly
- [ ] All functionality preserved
- [ ] Performance maintained or improved
- [ ] Tests pass for each file
- [ ] Integration tests pass end-to-end

### Risk Assessment
**High Risk Files**: 1, 2, 4, 5, 9 - Core functionality
**Medium Risk Files**: 3, 6, 7, 8 - Important features
**Low Risk Files**: 10-16 - Support and testing

## Migration Time Estimates

**Per File Estimates:**
- **High Priority**: 2-4 hours each (complex integration)
- **Medium Priority**: 1-2 hours each (moderate changes)
- **Low Priority**: 0.5-1 hour each (simple updates)

**Total Estimated Time**: 20-30 hours for all integration points

**Critical Path**: Files 1, 2, 4, 5 must be completed first as they contain core application functionality.