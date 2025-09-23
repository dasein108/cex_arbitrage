# 📊 Data Collector MVP - PostgreSQL Implementation Plan

## Overview
Create a real-time book ticker data collector that captures snapshots from MEXC and Gate.io exchanges, stores them in PostgreSQL, and provides basic real-time analytics logging for arbitrage opportunity analysis.

## Project Structure
```
src/data_collector/
├── __init__.py
├── collector.py         # Main collector class
├── config.py           # Simple config loader  
├── analytics.py        # Real-time analytics stub
└── run.py              # Entry point script
```

## Detailed Implementation Tasks

### Task 1: Database Setup
**File:** `db/migrations/002_create_book_ticker_snapshots.sql`
```sql
CREATE TABLE book_ticker_snapshots (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    bid_price DECIMAL(20,8) NOT NULL,
    bid_quantity DECIMAL(20,8) NOT NULL,
    ask_price DECIMAL(20,8) NOT NULL,
    ask_quantity DECIMAL(20,8) NOT NULL,
    spread DECIMAL(20,8) GENERATED ALWAYS AS (ask_price - bid_price) STORED,
    spread_pct DECIMAL(10,6) GENERATED ALWAYS AS ((ask_price - bid_price) / bid_price * 100) STORED,
    snapshot_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_book_ticker_time ON book_ticker_snapshots(snapshot_time);
CREATE INDEX idx_book_ticker_exchange_symbol ON book_ticker_snapshots(exchange, symbol);
```

**File:** `db/models.py` (extend existing)
- Add BookTickerSnapshot model
- Define fields matching table structure
- Add serialization methods

### Task 2: Configuration Management
**File:** `src/data_collector/config.py`
- Load symbols from existing `config.yaml`
- PostgreSQL connection settings
- Collector settings (intervals, thresholds)
- Environment variable support

**Configuration Structure:**
```yaml
data_collector:
  enabled: true
  snapshot_interval: 1  # seconds
  analytics_interval: 10  # seconds for summary
  database:
    host: "localhost"
    port: 5432
    database: "arbitrage_data"
    user: "arbitrage_user"
    password: "${POSTGRES_PASSWORD}"
  exchanges: ["mexc", "gateio"]
  analytics:
    arbitrage_threshold: 0.05  # %
    volume_threshold: 1000  # USD
    spread_alert_threshold: 0.1  # %
```

### Task 3: Unified WebSocket Manager
**File:** `src/data_collector/collector.py`
- Create `UnifiedWebSocketManager` class
- Instantiate `MexcWebsocketPublic` and `GateioWebsocketPublic`
- Subscribe to book ticker channels for configured symbols
- Maintain in-memory cache: `{exchange_symbol: BookTicker}`
- Route updates to analytics engine

**Key Methods:**
- `async def initialize(symbols: List[Symbol])`
- `async def start_collection()`
- `async def stop_collection()`
- `def get_latest_book_ticker(exchange: str, symbol: str) -> BookTicker`

### Task 4: Real-time Analytics Stub
**File:** `src/data_collector/analytics.py`

**Analytics Engine Class:**
- `RealTimeAnalytics`
- Process each book ticker update
- Calculate spreads and arbitrage opportunities
- Log meaningful analytics information

**Analytics Methods:**
- `def on_book_ticker_update(exchange: str, symbol: str, book_ticker: BookTicker)`
- `def calculate_arbitrage_opportunities() -> List[ArbitrageOpportunity]`
- `def log_spread_analysis(symbol: str)`
- `def log_volume_alerts(symbol: str)`
- `def log_market_health_summary()`

**Analytics Logging Examples:**
```python
INFO: [ANALYTICS] Arbitrage Alert: BTCUSDT - MEXC: $50000.50 vs GATEIO: $50001.25 (Opportunity: $0.75, 0.0015%)
INFO: [ANALYTICS] Spread Analysis: ETHUSDT - MEXC: 0.025%, GATEIO: 0.031% (Diff: 0.006%)
INFO: [ANALYTICS] Volume Alert: ADAUSDT - Low liquidity detected on MEXC (Bid: $50K, Ask: $30K)
INFO: [ANALYTICS] Market Health: 18/20 pairs active, avg spread: 0.028%, total opportunities: 3
INFO: [ANALYTICS] Connection Status: MEXC: ✓ (1250 updates/min), GATEIO: ✓ (980 updates/min)
```

### Task 5: Snapshot Scheduler
**File:** `src/data_collector/collector.py` (extend)
- `SnapshotScheduler` class
- Asyncio-based 1-second timer
- Capture all cached book ticker data
- Batch insert to PostgreSQL
- Trigger analytics calculations

**Key Methods:**
- `async def start_snapshot_schedule()`
- `async def take_snapshot()`
- `async def store_snapshots(snapshots: List[BookTickerSnapshot])`
- `def log_snapshot_statistics()`

### Task 6: Main Data Collector
**File:** `src/data_collector/collector.py`
- `DataCollector` main orchestrator class
- Coordinate WebSocket manager, analytics, and scheduler
- Handle graceful shutdown
- Error recovery and logging

**Main Collector Structure:**
```python
class DataCollector:
    def __init__(self, config: DataCollectorConfig)
    async def initialize()
    async def start()
    async def stop()
    def get_status() -> Dict[str, Any]
```

### Task 7: Database Operations
**File:** `db/operations.py` (extend existing)
- Add async methods for book ticker operations
- Batch insert optimization
- Connection pool management
- Error handling for database operations

**New Database Methods:**
- `async def insert_book_ticker_snapshots(snapshots: List[BookTickerSnapshot])`
- `async def get_latest_snapshots(limit: int = 100)`
- `async def cleanup_old_snapshots(days: int = 7)`

### Task 8: Entry Point Script
**File:** `src/data_collector/run.py`
- Command-line interface
- Configuration loading
- Signal handling for graceful shutdown
- Performance monitoring and logging

**CLI Features:**
- `python run.py --config config.yaml`
- `python run.py --dry-run` (no database writes)
- `python run.py --symbols BTCUSDT,ETHUSDT` (override symbols)

### Task 9: Integration with Existing Infrastructure
**Modifications to existing files:**
- `config.yaml`: Add data collector configuration section
- `db/migrations.py`: Register new migration
- `db/models.py`: Add BookTickerSnapshot model

## Implementation Priority

### Phase 1: Core Infrastructure (45 minutes)
1. Database migration and model setup
2. Configuration management
3. Basic collector class structure

### Phase 2: WebSocket Integration (60 minutes)
1. Unified WebSocket manager
2. Book ticker caching
3. Basic snapshot scheduler

### Phase 3: Analytics Stub (45 minutes)
1. Real-time analytics calculations
2. Arbitrage opportunity detection
3. Logging and alerts

### Phase 4: Integration & Testing (30 minutes)
1. Entry point script
2. End-to-end integration
3. Basic functionality verification

## Success Criteria
- [ ] Connects to both MEXC and Gate.io WebSockets
- [ ] Receives book ticker updates for configured symbols
- [ ] Stores snapshots every 1 second in PostgreSQL
- [ ] Real-time analytics logs arbitrage opportunities
- [ ] Graceful startup and shutdown
- [ ] Meaningful performance logging

## Technical Specifications

### Performance Targets
- 1-second snapshot interval (±50ms accuracy)
- <100ms processing time per snapshot
- Handle 20+ trading pairs simultaneously
- PostgreSQL batch insert <50ms

### Data Volume Estimates
- 20 pairs × 2 exchanges × 3600 snapshots/hour = 144K records/hour
- Daily: ~3.5M records
- Weekly: ~25M records
- Storage: ~2GB per week

### Error Handling
- WebSocket reconnection (automatic)
- Database connection retry (3 attempts)
- Missing data logging (warn level)
- Critical errors (stop execution)

### Analytics Thresholds
- Arbitrage opportunity: >0.05% price difference
- Volume alert: <$1000 total liquidity
- Spread alert: >0.1% spread
- Connection health: <500 updates/minute

## Environment Setup
```bash
# PostgreSQL setup
createdb arbitrage_data
psql arbitrage_data -f db/migrations/002_create_book_ticker_snapshots.sql

# Environment variables
export POSTGRES_PASSWORD="your_password"
export POSTGRES_HOST="localhost"

# Run collector
cd src/data_collector
python run.py --config ../../config.yaml
```

## Expected Output
```
INFO: Data Collector starting...
INFO: Loaded 20 trading pairs from config
INFO: Connected to PostgreSQL: arbitrage_data
INFO: WebSocket connections: MEXC ✓, GATEIO ✓
INFO: Subscribed to 40 book ticker channels
INFO: [ANALYTICS] Market initialization complete - 20 pairs active
INFO: Starting snapshot scheduler (1-second interval)
INFO: [SNAPSHOT #001] Captured 20 pairs, inserted 40 records in 23ms
INFO: [ANALYTICS] Arbitrage Alert: BTCUSDT - Opportunity: $0.75 (0.0015%)
INFO: [SNAPSHOT #002] Captured 20 pairs, inserted 40 records in 19ms
...
```

## File Sizes Estimate
- `collector.py`: ~250 lines
- `analytics.py`: ~150 lines  
- `config.py`: ~80 lines
- `run.py`: ~100 lines
- Database migration: ~20 lines
- Total: ~600 lines of code

## Dependencies
- asyncio (built-in)
- asyncpg (PostgreSQL driver)
- msgspec (JSON parsing)
- Existing WebSocket infrastructure
- Existing database infrastructure

This plan provides a complete roadmap for implementing the MVP data collector with PostgreSQL storage and real-time analytics stub in approximately 3-4 hours of focused development.