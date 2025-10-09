# Balance Snapshot Functionality Implementation Plan

## Executive Summary

This plan implements comprehensive balance snapshot functionality for the CEX arbitrage system, following the existing normalized database schema pattern with HFT-optimized performance requirements. The implementation will track account balances across all supported exchanges (MEXC_SPOT, GATEIO_SPOT, GATEIO_FUTURES) with proper foreign key relationships and sub-10ms query performance.

## Current System Analysis

### Database Architecture
- **Normalized Schema**: Uses foreign key relationships with `exchanges` and `symbols` tables
- **TimescaleDB Integration**: Hypertables with optimized chunk intervals for time-series data
- **HFT Performance**: Sub-millisecond query targets with comprehensive indexing
- **Existing Models**: `BookTickerSnapshot`, `FundingRateSnapshot`, `TradeSnapshot` follow consistent patterns

### Balance Structure Analysis
From `BasePrivateComposite.balances` property:
```python
@property
def balances(self) -> Dict[AssetName, AssetBalance]:
    """Get current account balances (thread-safe)."""
    return self._balances.copy()
```

`AssetBalance` structure contains:
- `asset: AssetName` - Asset symbol (BTC, USDT, etc.)
- `available: float` - Available balance for trading
- `locked: float` - Locked balance in orders
- Additional exchange-specific fields

## Implementation Plan

### Phase 1: Database Schema Implementation

#### 1.1 Balance Snapshots Table Schema

**SQL Table Definition:**
```sql
-- Balance snapshots table - NORMALIZED SCHEMA (follows existing pattern)
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),  -- Foreign key to exchanges table
    
    -- Asset identification
    asset_name VARCHAR(20) NOT NULL,  -- BTC, USDT, ETH, etc.
    
    -- Balance data (HFT optimized)
    available_balance NUMERIC(20,8) NOT NULL DEFAULT 0,
    locked_balance NUMERIC(20,8) NOT NULL DEFAULT 0,
    total_balance NUMERIC(20,8) GENERATED ALWAYS AS (available_balance + locked_balance) STORED,
    
    -- Exchange-specific fields (optional)
    frozen_balance NUMERIC(20,8) DEFAULT 0,  -- Some exchanges track frozen balances
    borrowing_balance NUMERIC(20,8) DEFAULT 0,  -- Margin/futures borrowing
    interest_balance NUMERIC(20,8) DEFAULT 0,  -- Interest accumulation
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- HFT Performance Constraints
    CONSTRAINT chk_positive_balances CHECK (
        available_balance >= 0 AND 
        locked_balance >= 0 AND 
        frozen_balance >= 0 AND 
        borrowing_balance >= 0
    ),
    CONSTRAINT chk_valid_asset_name CHECK (asset_name ~ '^[A-Z0-9]+$'),
    CONSTRAINT chk_valid_timestamp CHECK (timestamp >= '2020-01-01'::timestamptz),
    
    -- Optimized primary key for time-series partitioning
    PRIMARY KEY (timestamp, exchange_id, asset_name)
);

-- Convert to TimescaleDB hypertable (optimized for balance collection)
SELECT create_hypertable('balance_snapshots', 'timestamp', 
    chunk_time_interval => INTERVAL '6 hours',  -- Balance data changes less frequently
    if_not_exists => TRUE);
```

#### 1.2 Database Indexes (HFT-Optimized)

```sql
-- Core indexes for balance_snapshots (sub-10ms queries)
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_time 
    ON balance_snapshots(exchange_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_asset_time 
    ON balance_snapshots(asset_name, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_asset_time 
    ON balance_snapshots(exchange_id, asset_name, timestamp DESC);

-- Index for recent balance queries (most common pattern)
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_recent 
    ON balance_snapshots(timestamp DESC) WHERE timestamp > NOW() - INTERVAL '24 hours';

-- Index for asset-specific queries across exchanges
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_asset_recent 
    ON balance_snapshots(asset_name, exchange_id, timestamp DESC) 
    WHERE timestamp > NOW() - INTERVAL '7 days';

-- Index for non-zero balances (analytics optimization)
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_active_balances 
    ON balance_snapshots(exchange_id, asset_name, timestamp DESC) 
    WHERE total_balance > 0;
```

#### 1.3 Data Retention Policy

```sql
-- Balance snapshots: Keep 14 days for detailed analysis (HFT server optimized)
SELECT add_retention_policy('balance_snapshots', INTERVAL '14 days', if_not_exists => TRUE);
```

### Phase 2: Database Operations Implementation

#### 2.1 Balance Snapshot Model (`src/db/models.py`)

```python
class BalanceSnapshot(msgspec.Struct):
    """
    Balance snapshot data structure.
    
    Represents account balances for a specific asset at a specific moment.
    Optimized for high-frequency balance tracking and analysis.
    Works with normalized database schema using exchange_id foreign keys.
    """
    # Database fields (normalized schema)
    exchange_id: int
    
    # Asset identification
    asset_name: str
    
    # Balance data
    available_balance: float
    locked_balance: float
    total_balance: Optional[float] = None  # Calculated field
    
    # Optional exchange-specific fields
    frozen_balance: Optional[float] = None
    borrowing_balance: Optional[float] = None
    interest_balance: Optional[float] = None
    
    # Timing
    timestamp: datetime
    created_at: Optional[datetime] = None
    id: Optional[int] = None
    
    # Transient fields for convenience (not stored in DB)
    exchange_name: Optional[str] = None
    
    @classmethod
    def from_asset_balance_and_exchange(
        cls,
        exchange_name: str,
        asset_balance: AssetBalance,
        timestamp: datetime,
        exchange_id: Optional[int] = None
    ) -> "BalanceSnapshot":
        """
        Create BalanceSnapshot from AssetBalance and exchange info.
        
        Args:
            exchange_name: Exchange identifier (MEXC_SPOT, GATEIO_SPOT, etc.)
            asset_balance: AssetBalance object from private exchange interface
            timestamp: Snapshot timestamp
            exchange_id: Database exchange_id (required for normalized schema)
            
        Returns:
            BalanceSnapshot instance
        """
        if exchange_id is None:
            raise ValueError("exchange_id is required for normalized database schema")
            
        # Calculate total balance
        total_balance = asset_balance.available + asset_balance.locked
        if hasattr(asset_balance, 'frozen'):
            total_balance += getattr(asset_balance, 'frozen', 0)
            
        return cls(
            exchange_id=exchange_id,
            asset_name=str(asset_balance.asset).upper(),
            available_balance=asset_balance.available,
            locked_balance=asset_balance.locked,
            total_balance=total_balance,
            frozen_balance=getattr(asset_balance, 'frozen', None),
            borrowing_balance=getattr(asset_balance, 'borrowing', None),
            interest_balance=getattr(asset_balance, 'interest', None),
            timestamp=timestamp,
            # Store transient fields for convenience
            exchange_name=exchange_name.upper()
        )
    
    def to_asset_balance(self) -> AssetBalance:
        """
        Convert back to AssetBalance object.
        
        Returns:
            AssetBalance object reconstructed from snapshot data
        """
        from exchanges.structs.types import AssetName
        return AssetBalance(
            asset=AssetName(self.asset_name),
            available=self.available_balance,
            locked=self.locked_balance
        )
    
    def get_total_balance(self) -> float:
        """
        Calculate total balance including all components.
        
        Returns:
            Total balance across all balance types
        """
        total = self.available_balance + self.locked_balance
        if self.frozen_balance:
            total += self.frozen_balance
        if self.borrowing_balance:
            total += self.borrowing_balance
        if self.interest_balance:
            total += self.interest_balance
        return total
    
    def is_active_balance(self) -> bool:
        """
        Check if this is an active balance (total > 0).
        
        Returns:
            True if total balance is greater than zero
        """
        return self.get_total_balance() > 0
```

#### 2.2 Database Operations (`src/db/operations.py`)

**Add these functions to existing operations.py:**

```python
# Balance Operations
# Similar pattern to BookTicker and FundingRate operations

async def insert_balance_snapshots_batch(snapshots: List[BalanceSnapshot]) -> int:
    """
    Insert balance snapshots in batch for optimal performance.
    
    Args:
        snapshots: List of BalanceSnapshot objects
        
    Returns:
        Number of records inserted/updated
    """
    if not snapshots:
        return 0
        
    db = get_db_manager()
    
    # Prepare batch insert with ON CONFLICT handling
    query = """
    INSERT INTO balance_snapshots (
        timestamp, exchange_id, asset_name, 
        available_balance, locked_balance, frozen_balance,
        borrowing_balance, interest_balance, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (timestamp, exchange_id, asset_name) 
    DO UPDATE SET
        available_balance = EXCLUDED.available_balance,
        locked_balance = EXCLUDED.locked_balance,
        frozen_balance = EXCLUDED.frozen_balance,
        borrowing_balance = EXCLUDED.borrowing_balance,
        interest_balance = EXCLUDED.interest_balance,
        created_at = EXCLUDED.created_at
    """
    
    # Prepare data for batch insert
    batch_data = []
    for snapshot in snapshots:
        batch_data.append((
            snapshot.timestamp,
            snapshot.exchange_id,
            snapshot.asset_name.upper(),
            snapshot.available_balance,
            snapshot.locked_balance,
            snapshot.frozen_balance or 0,
            snapshot.borrowing_balance or 0,
            snapshot.interest_balance or 0,
            snapshot.created_at or datetime.now()
        ))
    
    try:
        # Execute batch insert
        await db.executemany(query, batch_data)
        
        logger.debug(f"Successfully inserted/updated {len(snapshots)} balance snapshots")
        return len(snapshots)
        
    except Exception as e:
        logger.error(f"Failed to insert balance snapshots: {e}")
        raise

async def get_latest_balance_snapshots(
    exchange_name: Optional[str] = None,
    asset_name: Optional[str] = None
) -> Dict[str, BalanceSnapshot]:
    """
    Get latest balance snapshot for each exchange/asset combination.
    
    Args:
        exchange_name: Filter by exchange (optional)
        asset_name: Filter by asset (optional)
        
    Returns:
        Dictionary mapping "exchange_asset" to latest BalanceSnapshot
    """
    db = get_db_manager()
    
    # Build dynamic WHERE clause
    where_conditions = []
    params = []
    param_counter = 1
    
    if exchange_name:
        where_conditions.append(f"e.enum_value = ${param_counter}")
        params.append(exchange_name.upper())
        param_counter += 1
    
    if asset_name:
        where_conditions.append(f"bs.asset_name = ${param_counter}")
        params.append(asset_name.upper())
        param_counter += 1
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    query = f"""
        SELECT DISTINCT ON (bs.exchange_id, bs.asset_name)
               bs.id, bs.exchange_id, bs.asset_name,
               bs.available_balance, bs.locked_balance, bs.frozen_balance,
               bs.borrowing_balance, bs.interest_balance,
               bs.timestamp, bs.created_at,
               e.enum_value as exchange_name
        FROM balance_snapshots bs
        JOIN exchanges e ON bs.exchange_id = e.id
        {where_clause}
        ORDER BY bs.exchange_id, bs.asset_name, bs.timestamp DESC
    """
    
    try:
        rows = await db.fetch(query, *params)
        
        latest_balances = {}
        for row in rows:
            snapshot = BalanceSnapshot(
                id=row['id'],
                exchange_id=row['exchange_id'],
                asset_name=row['asset_name'],
                available_balance=float(row['available_balance']),
                locked_balance=float(row['locked_balance']),
                frozen_balance=float(row['frozen_balance']) if row['frozen_balance'] else None,
                borrowing_balance=float(row['borrowing_balance']) if row['borrowing_balance'] else None,
                interest_balance=float(row['interest_balance']) if row['interest_balance'] else None,
                timestamp=row['timestamp'],
                created_at=row['created_at'],
                exchange_name=row['exchange_name']
            )
            
            key = f"{snapshot.exchange_name}_{snapshot.asset_name}"
            latest_balances[key] = snapshot
        
        logger.debug(f"Retrieved {len(latest_balances)} latest balance snapshots")
        return latest_balances
        
    except Exception as e:
        logger.error(f"Failed to retrieve latest balance snapshots: {e}")
        raise

async def get_balance_history(
    exchange_name: str,
    asset_name: str,
    hours_back: int = 24
) -> List[BalanceSnapshot]:
    """
    Get historical balance data for a specific exchange/asset.
    
    Args:
        exchange_name: Exchange identifier
        asset_name: Asset symbol
        hours_back: How many hours of history to retrieve
        
    Returns:
        List of BalanceSnapshot objects ordered by timestamp
    """
    db = get_db_manager()
    
    timestamp_from = datetime.utcnow() - timedelta(hours=hours_back)
    
    query = """
        SELECT bs.id, bs.exchange_id, bs.asset_name,
               bs.available_balance, bs.locked_balance, bs.frozen_balance,
               bs.borrowing_balance, bs.interest_balance,
               bs.timestamp, bs.created_at,
               e.enum_value as exchange_name
        FROM balance_snapshots bs
        JOIN exchanges e ON bs.exchange_id = e.id
        WHERE e.enum_value = $1 
          AND bs.asset_name = $2
          AND bs.timestamp >= $3
        ORDER BY bs.timestamp ASC
    """
    
    try:
        rows = await db.fetch(
            query,
            exchange_name.upper(),
            asset_name.upper(),
            timestamp_from
        )
        
        snapshots = []
        for row in rows:
            snapshot = BalanceSnapshot(
                id=row['id'],
                exchange_id=row['exchange_id'],
                asset_name=row['asset_name'],
                available_balance=float(row['available_balance']),
                locked_balance=float(row['locked_balance']),
                frozen_balance=float(row['frozen_balance']) if row['frozen_balance'] else None,
                borrowing_balance=float(row['borrowing_balance']) if row['borrowing_balance'] else None,
                interest_balance=float(row['interest_balance']) if row['interest_balance'] else None,
                timestamp=row['timestamp'],
                created_at=row['created_at'],
                exchange_name=row['exchange_name']
            )
            snapshots.append(snapshot)
        
        logger.debug(f"Retrieved {len(snapshots)} historical balance snapshots for {exchange_name} {asset_name}")
        return snapshots
        
    except Exception as e:
        logger.error(f"Failed to retrieve balance history: {e}")
        raise
```

### Phase 3: Task Implementation

#### 3.1 Balance Sync Task (`src/trading/tasks/balance_sync_task.py`)

```python
"""
Balance Sync Task

Periodic task to collect and store balance snapshots from all configured exchanges.
Follows HFT performance requirements with sub-10ms database operations.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from trading.tasks.base_task import BaseTask
from config.structs import TaskConfig
from db.models import BalanceSnapshot
from db.operations import insert_balance_snapshots_batch
from db.symbol_manager import get_exchange_id
from exchanges.structs.common import AssetBalance
from exchanges.structs.types import AssetName
from infrastructure.logging import HFTLoggerInterface


class BalanceSyncTask(BaseTask):
    """
    Task for periodic balance snapshot collection and storage.
    
    Collects balances from all configured private exchanges and stores
    them in normalized database schema with HFT-optimized performance.
    """
    
    def __init__(self, config: TaskConfig, logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize balance sync task.
        
        Args:
            config: Task configuration
            logger: Optional HFT logger instance
        """
        super().__init__(config, logger)
        self.sync_interval_seconds = config.params.get('sync_interval_seconds', 300)  # 5 minutes default
        self.min_balance_threshold = config.params.get('min_balance_threshold', 0.0001)
        self.exchange_clients = {}  # Will be populated during initialization
        
    async def initialize(self) -> None:
        """Initialize task with exchange clients."""
        await super().initialize()
        
        # Exchange clients will be injected by the task manager
        # This follows the dependency injection pattern used throughout the system
        
        self.logger.info("Balance sync task initialized",
                        sync_interval=self.sync_interval_seconds,
                        min_threshold=self.min_balance_threshold)
    
    async def run(self) -> None:
        """Main task execution loop."""
        try:
            while not self.should_stop():
                await self._collect_and_store_balances()
                await asyncio.sleep(self.sync_interval_seconds)
                
        except Exception as e:
            self.logger.error("Balance sync task failed", error=str(e))
            raise
    
    async def _collect_and_store_balances(self) -> None:
        """
        Collect balances from all exchanges and store snapshots.
        """
        timestamp = datetime.utcnow()
        all_snapshots = []
        
        for exchange_name, client in self.exchange_clients.items():
            try:
                # Get exchange ID for normalized schema
                exchange_id = await get_exchange_id(exchange_name)
                if not exchange_id:
                    self.logger.warning(f"Exchange ID not found for {exchange_name}")
                    continue
                
                # Collect balances from private exchange client
                balances = client.balances  # Non-blocking property access
                
                # Convert to balance snapshots
                exchange_snapshots = []
                for asset_name, asset_balance in balances.items():
                    # Skip dust balances (optimization)
                    if asset_balance.available + asset_balance.locked < self.min_balance_threshold:
                        continue
                    
                    snapshot = BalanceSnapshot.from_asset_balance_and_exchange(
                        exchange_name=exchange_name,
                        asset_balance=asset_balance,
                        timestamp=timestamp,
                        exchange_id=exchange_id
                    )
                    exchange_snapshots.append(snapshot)
                
                all_snapshots.extend(exchange_snapshots)
                
                self.logger.debug(f"Collected {len(exchange_snapshots)} balance snapshots from {exchange_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to collect balances from {exchange_name}",
                                error=str(e))
                continue
        
        # Store all snapshots in batch for optimal performance
        if all_snapshots:
            try:
                inserted_count = await insert_balance_snapshots_batch(all_snapshots)
                self.logger.info("Balance snapshots stored successfully",
                               total_snapshots=len(all_snapshots),
                               inserted_count=inserted_count,
                               timestamp=timestamp)
                
            except Exception as e:
                self.logger.error("Failed to store balance snapshots",
                                error=str(e), snapshot_count=len(all_snapshots))
                raise
        else:
            self.logger.debug("No balance snapshots to store")
    
    def add_exchange_client(self, exchange_name: str, client) -> None:
        """
        Add exchange client for balance collection.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC_SPOT')
            client: Private exchange client instance
        """
        self.exchange_clients[exchange_name] = client
        self.logger.debug(f"Added exchange client for {exchange_name}")
    
    async def cleanup(self) -> None:
        """Cleanup task resources."""
        self.exchange_clients.clear()
        await super().cleanup()
```

### Phase 4: Configuration Integration

#### 4.1 Task Configuration (`config/structs.py`)

**Add balance sync configuration to existing TaskConfig:**

```python
# Add to existing TaskConfig or create BalanceSyncConfig
@dataclass
class BalanceSyncConfig:
    """Configuration for balance sync task."""
    enabled: bool = True
    sync_interval_seconds: int = 300  # 5 minutes
    min_balance_threshold: float = 0.0001  # Skip dust balances
    max_retry_attempts: int = 3
    retry_delay_seconds: int = 30
```

#### 4.2 Configuration Files

**Update `config/mexc_gateio_development.json`:**

```json
{
  "tasks": {
    "balance_sync": {
      "enabled": true,
      "sync_interval_seconds": 300,
      "min_balance_threshold": 0.0001,
      "max_retry_attempts": 3,
      "retry_delay_seconds": 30
    }
  }
}
```

### Phase 5: Database Migration Script

#### 5.1 Migration SQL (`docker/balance_snapshots_migration.sql`)

```sql
-- =============================================================================
-- Balance Snapshots Migration
-- =============================================================================
-- Adds balance snapshot functionality to existing normalized schema

-- Balance snapshots table - NORMALIZED SCHEMA (follows existing pattern)
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),  -- Foreign key to exchanges table
    
    -- Asset identification
    asset_name VARCHAR(20) NOT NULL,  -- BTC, USDT, ETH, etc.
    
    -- Balance data (HFT optimized)
    available_balance NUMERIC(20,8) NOT NULL DEFAULT 0,
    locked_balance NUMERIC(20,8) NOT NULL DEFAULT 0,
    total_balance NUMERIC(20,8) GENERATED ALWAYS AS (available_balance + locked_balance) STORED,
    
    -- Exchange-specific fields (optional)
    frozen_balance NUMERIC(20,8) DEFAULT 0,  -- Some exchanges track frozen balances
    borrowing_balance NUMERIC(20,8) DEFAULT 0,  -- Margin/futures borrowing
    interest_balance NUMERIC(20,8) DEFAULT 0,  -- Interest accumulation
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- HFT Performance Constraints
    CONSTRAINT chk_positive_balances CHECK (
        available_balance >= 0 AND 
        locked_balance >= 0 AND 
        frozen_balance >= 0 AND 
        borrowing_balance >= 0
    ),
    CONSTRAINT chk_valid_asset_name CHECK (asset_name ~ '^[A-Z0-9]+$'),
    CONSTRAINT chk_valid_timestamp CHECK (timestamp >= '2020-01-01'::timestamptz),
    
    -- Optimized primary key for time-series partitioning
    PRIMARY KEY (timestamp, exchange_id, asset_name)
);

-- Convert to TimescaleDB hypertable (optimized for balance collection)
SELECT create_hypertable('balance_snapshots', 'timestamp', 
    chunk_time_interval => INTERVAL '6 hours',  -- Balance data changes less frequently
    if_not_exists => TRUE);

-- HFT-optimized indexes for balance_snapshots
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_time 
    ON balance_snapshots(exchange_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_asset_time 
    ON balance_snapshots(asset_name, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_asset_time 
    ON balance_snapshots(exchange_id, asset_name, timestamp DESC);

-- Index for recent balance queries (most common pattern)
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_recent 
    ON balance_snapshots(timestamp DESC) WHERE timestamp > NOW() - INTERVAL '24 hours';

-- Index for asset-specific queries across exchanges
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_asset_recent 
    ON balance_snapshots(asset_name, exchange_id, timestamp DESC) 
    WHERE timestamp > NOW() - INTERVAL '7 days';

-- Index for non-zero balances (analytics optimization)
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_active_balances 
    ON balance_snapshots(exchange_id, asset_name, timestamp DESC) 
    WHERE total_balance > 0;

-- Data retention policy
SELECT add_retention_policy('balance_snapshots', INTERVAL '14 days', if_not_exists => TRUE);

-- Table ownership
ALTER TABLE balance_snapshots OWNER TO arbitrage_user;

-- Grant permissions
GRANT ALL PRIVILEGES ON balance_snapshots TO arbitrage_user;
GRANT SELECT ON balance_snapshots TO readonly_user;

-- Table comment
COMMENT ON TABLE balance_snapshots IS 'Account balance snapshots across all exchanges with normalized schema relationships';

COMMIT;
```

## Implementation Timeline

### Phase 1: Database Foundation (2-3 hours)
1. **Database Schema** (1 hour)
   - Create `balance_snapshots` table with proper constraints
   - Add TimescaleDB hypertable configuration
   - Create HFT-optimized indexes

2. **Database Operations** (1-2 hours)
   - Implement `BalanceSnapshot` model in `models.py`
   - Add batch insert and query functions to `operations.py`
   - Add exchange ID management functions

### Phase 2: Task Implementation (3-4 hours)
1. **Balance Sync Task** (2-3 hours)
   - Implement `BalanceSyncTask` class
   - Add exchange client integration
   - Implement error handling and retry logic

2. **Configuration Integration** (1 hour)
   - Update configuration structs
   - Add task configuration to development/production configs

### Phase 3: Testing & Integration (2-3 hours)
1. **Unit Tests** (1-2 hours)
   - Test database operations
   - Test balance snapshot model conversions
   - Test task execution logic

2. **Integration Testing** (1 hour)
   - Test with live exchange connections
   - Verify database performance
   - Test error scenarios

## Performance Targets (HFT Compliance)

- **Database Insert**: <5ms per batch (up to 100 snapshots)
- **Latest Balance Query**: <3ms per exchange/asset combination
- **Historical Query**: <10ms for 24 hours of data
- **Task Execution**: <30ms total collection time per exchange
- **Memory Usage**: <50MB additional memory footprint

## Risk Mitigation

1. **HFT Caching Policy Compliance**: Balance snapshots are stored historical data (safe to cache)
2. **Database Performance**: Comprehensive indexing and TimescaleDB optimization
3. **Error Handling**: Robust retry logic and graceful degradation
4. **Resource Management**: Configurable thresholds and cleanup policies
5. **Monitoring**: Detailed logging and performance metrics

## Success Criteria

1. ✅ **Schema Compliance**: Follows existing normalized database patterns
2. ✅ **Performance Targets**: Meets sub-10ms query requirements
3. ✅ **HFT Safety**: No violation of real-time data caching policies
4. ✅ **Integration**: Seamless integration with existing task management system
5. ✅ **Monitoring**: Comprehensive logging and error tracking
6. ✅ **Scalability**: Supports all current and future exchange integrations

## Ready for Implementation

This plan is **comprehensive and ready for user approval**. All components follow the existing architectural patterns, maintain HFT performance requirements, and integrate seamlessly with the current codebase structure.

**Next Steps**: Upon approval, implementation can begin with Phase 1 (Database Foundation) and proceed systematically through each phase with proper testing and validation.