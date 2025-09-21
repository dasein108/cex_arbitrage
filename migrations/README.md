# Database Migration System

This directory contains the database migration system for the CEX Arbitrage Engine's trade collection feature.

## 🚀 Quick Start

### Check Migration Status
```bash
./migrate.sh status
```

### Run All Pending Migrations
```bash
./migrate.sh
```

### Preview Migrations (Dry Run)
```bash
./migrate.sh --dry-run
```

### Run Migrations to Specific Version
```bash
./migrate.sh --target 001
```

## 📁 Files Overview

### Migration Scripts
- **`000_create_migration_infrastructure.sql`** - Creates migration tracking infrastructure
- **`001_add_trade_collection_support.sql`** - Adds trade collection schema support

### Infrastructure
- **`run_migrations.py`** - Python migration runner with safe execution
- **`migrate.sh`** - Shell wrapper for easy migration execution
- **`README.md`** - This documentation file

## 🔧 Migration Runner Features

- ✅ **Safe Execution** - Atomic transactions with automatic rollback
- ✅ **Progress Tracking** - Comprehensive migration history 
- ✅ **Performance Monitoring** - Execution time tracking
- ✅ **Validation** - Configuration and dependency validation
- ✅ **Error Handling** - Detailed error reporting and recovery
- ✅ **Dry Run Support** - Preview changes without execution

## 📊 Migration Details

### Migration 000: Infrastructure Setup
Creates the migration tracking system:
- `migration_history` table for tracking applied migrations
- Helper functions for migration status checking
- Proper permissions and ownership setup

### Migration 001: Trade Collection Support
Updates the database schema for trade collection:
- Adds `symbol_base` and `symbol_quote` columns to trades table
- Adds optional trade metadata columns (quote_quantity, is_buyer, is_maker)
- Migrates existing symbol data to base/quote format
- Creates optimized indexes for trade queries
- Adds continuous aggregates for trade analysis
- Updates constraints and permissions

## ⚙️ Configuration

The migration runner uses the same configuration system as the main application:
- Database connection settings from `config.yaml`
- Environment variable substitution support
- Automatic fallback to reasonable defaults

## 🔍 Troubleshooting

### Connection Issues
```bash
# Check database configuration
./migrate.sh status --verbose
```

### Migration Failures
- All migrations run in transactions and auto-rollback on failure
- Check logs for detailed error information
- Verify database permissions and connectivity

### Performance Issues
- Migration execution times are logged
- Large datasets may require longer execution times
- Consider running during maintenance windows

## 📚 Advanced Usage

### Python API
```python
from migrations.run_migrations import MigrationRunner
from db.structs import DatabaseConfig

# Create runner
runner = MigrationRunner(db_config)

# Run migrations programmatically
success = await runner.run_migrations(target_version="001")

# Get migration status
status = await runner.get_migration_status(conn)
```

### Manual SQL Execution
If needed, migration SQL files can be executed manually:
```bash
psql -d cex_arbitrage -f 000_create_migration_infrastructure.sql
psql -d cex_arbitrage -f 001_add_trade_collection_support.sql
```

## 🛡️ Safety Features

- **Atomic Execution** - Each migration runs in a transaction
- **Duplicate Detection** - Prevents re-running applied migrations
- **Version Ordering** - Ensures migrations run in correct sequence
- **Rollback Support** - Automatic rollback on failures
- **Validation Checks** - Comprehensive pre-flight validation

## 📈 Trade Collection Benefits

After running the migrations, the system supports:
- **Real-time Trade Collection** - Parallel to existing book ticker streams
- **Advanced Analytics** - Volume monitoring and momentum detection
- **HFT Performance** - Sub-millisecond processing with batch operations
- **Data Integrity** - Deduplication and validation at all levels
- **Flexible Configuration** - Enable/disable trade collection independently

---

🎯 **Ready to Deploy**: The migration system is production-ready and HFT-compliant.