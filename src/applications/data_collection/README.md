# 📊 Data Collector MVP

Real-time book ticker data collection system for cryptocurrency arbitrage analysis.

## Overview

The Data Collector captures real-time book ticker snapshots from MEXC and Gate.io exchanges, stores them in PostgreSQL, and provides real-time analytics logging for arbitrage opportunity detection.

## Features

- **Real-time Data Collection**: WebSocket connections to MEXC and Gate.io
- **High-Performance Storage**: Batch inserts to PostgreSQL every 1 second
- **Real-time Analytics**: Live arbitrage opportunity detection and logging
- **Configurable Monitoring**: 20+ trading pairs with configurable thresholds
- **Graceful Operations**: Clean startup/shutdown with signal handling

## Components

### 1. Configuration Management (`config.py`)
- Loads settings from `config.yaml`
- Environment variable support
- Validates all configuration parameters

### 2. Unified WebSocket Manager (`collector.py`)
- Manages connections to multiple exchanges
- In-memory cache of latest book ticker data
- Routes updates to analytics engine

### 3. Real-time Analytics (`analytics.py`)
- Detects arbitrage opportunities between exchanges
- Monitors spread and volume conditions
- Logs meaningful market insights

### 4. Snapshot Scheduler (`collector.py`)
- Captures data every 1 second
- Batch inserts to PostgreSQL for optimal performance
- Performance monitoring and statistics

### 5. Main Orchestrator (`collector.py`)
- Coordinates all components
- Handles initialization and cleanup
- Provides comprehensive status reporting

### 6. CLI Interface (`run.py`)
- Command-line execution with options
- Dry run mode for testing
- Symbol override capabilities
- Status reporting

## Quick Start

### 1. Environment Setup
```bash
# Set database credentials
export POSTGRES_PASSWORD="your_password"
export POSTGRES_HOST="localhost"

# Set exchange API keys (optional for public data)
export MEXC_API_KEY="your_mexc_key"
export MEXC_SECRET_KEY="your_mexc_secret"
export GATEIO_API_KEY="your_gateio_key"
export GATEIO_SECRET_KEY="your_gateio_secret"
```

### 2. Database Setup
```bash
# Create database and run migrations
createdb arbitrage_data
cd /Users/dasein/dev/cex_arbitrage
PYTHONPATH=src python -c "
from db.migrations import run_migrations
import asyncio
asyncio.run(run_migrations())
"
```

### 3. Run Data Collector
```bash
cd src/data_collector

# Show configuration status
python run.py --config ../../config.yaml --status

# Run in dry mode (no database writes)
python run.py --config ../../config.yaml --dry-run

# Run normally
python run.py --config ../../config.yaml

# Run with custom symbols
python run.py --config ../../config.yaml --symbols BTC/USDT,ETH/USDT

# Debug mode
python run.py --config ../../config.yaml --log-level DEBUG
```

## Configuration

The data collector is configured via the `data_collector` section in `config.yaml`:

```yaml
data_collector:
  enabled: true
  snapshot_interval: 1  # seconds
  analytics_interval: 10  # seconds
  exchanges: ["mexc", "gateio"]
  
  analytics:
    arbitrage_threshold: 0.05  # 5% minimum opportunity
    volume_threshold: 1000  # USD minimum volume
    spread_alert_threshold: 0.1  # 10% spread alert
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
INFO: [ANALYTICS] Market Health: 18/20 pairs active, avg spread: 0.028%
...
```

## Performance Targets

- **Snapshot Interval**: 1-second accuracy (±50ms)
- **Processing Time**: <100ms per snapshot
- **Concurrent Pairs**: 20+ trading pairs
- **Database Insert**: <50ms batch operations
- **Data Volume**: ~144K records/hour, ~3.5M/day

## Analytics Features

### Arbitrage Detection
```
[ANALYTICS] Arbitrage Alert: BTCUSDT - MEXC: $50000.50 vs GATEIO: $50001.25 (Opportunity: $0.75, 0.0015%)
```

### Spread Analysis
```
[ANALYTICS] Spread Analysis: ETHUSDT - MEXC: 0.025%, GATEIO: 0.031% (Diff: 0.006%)
```

### Volume Monitoring
```
[ANALYTICS] Volume Alert: ADAUSDT - Low liquidity on MEXC (Bid: $50K, Ask: $30K)
```

### Market Health
```
[ANALYTICS] Market Health: 18/20 pairs active, avg spread: 0.028%, opportunities: 3
[ANALYTICS] Connection Status: MEXC: ✓ (1250 updates/min), GATEIO: ✓ (980 updates/min)
```

## Database Schema

Book ticker snapshots are stored in the `book_ticker_snapshots` table:

```sql
CREATE TABLE book_ticker_snapshots (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,
    symbol_base VARCHAR(20) NOT NULL,
    symbol_quote VARCHAR(20) NOT NULL,
    bid_price NUMERIC(20,8) NOT NULL,
    bid_qty NUMERIC(20,8) NOT NULL,
    ask_price NUMERIC(20,8) NOT NULL,
    ask_qty NUMERIC(20,8) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failures**
   - Check internet connectivity
   - Verify exchange URLs in configuration
   - Check firewall settings

2. **Database Connection Issues**
   - Verify PostgreSQL is running
   - Check database credentials
   - Ensure database exists

3. **No Data Being Collected**
   - Check if data_collector.enabled = true
   - Verify symbols are correctly configured
   - Check logs for error messages

### Logs Location
- Default: Console output
- Configure via logging level: DEBUG, INFO, WARNING, ERROR

### Performance Monitoring
- Use `--log-level DEBUG` for detailed performance metrics
- Monitor database size: typically ~2GB per week
- Check connection health in analytics logs

## Integration

The data collector integrates seamlessly with the existing arbitrage engine:

- **Shares configuration** from main `config.yaml`
- **Uses existing database** infrastructure
- **Follows CLAUDE.md** architectural principles
- **HFT-compliant** performance characteristics

## Future Enhancements

- **WebSocket Health Monitoring**: Automatic reconnection and health checks
- **Data Compression**: Optimize storage for large datasets
- **Real-time Dashboards**: Web interface for monitoring
- **Alert Systems**: Email/Slack notifications for opportunities
- **Historical Analysis**: Backtesting and trend analysis tools