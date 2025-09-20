# Arbitrage Data Collector - Docker Deployment

This directory contains Docker configuration for deploying the arbitrage data collection system on a server.

## Quick Start

### 1. Development Mode (with Hot-Reload)
```bash
# Clone repository and navigate to docker directory
cd /path/to/cex_arbitrage/docker

# Start in development mode - code changes apply immediately!
./deploy.sh dev
```

### 2. Production Mode
```bash
# Start with optimized settings
./deploy.sh start

# Or manually
docker-compose up -d
```

### 3. Manual Setup
```bash
# Copy environment template
cp .env.example .env

# Edit configuration (important!)
nano .env

# Development with hot-reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Production mode
docker-compose up -d
```

## What Gets Deployed

### Core Services
- **PostgreSQL with TimescaleDB**: Time-series database optimized for financial data
- **Data Collector**: Real-time book ticker collection from MEXC + Gate.io
- **Automated Setup**: Database schema, indexes, and retention policies

### Optional Services
- **PgAdmin**: Web-based database administration (port 8080)
- **Grafana**: Monitoring dashboards (port 3000)

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MEXC WebSocket │    │ Data Collector   │    │ TimescaleDB     │
│   Gate.io WS    ├───►│ (Python)         ├───►│ (PostgreSQL)    │
│                 │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ Optional:        │
                       │ - PgAdmin        │
                       │ - Grafana        │
                       └──────────────────┘
```

## Configuration

### Environment Variables (.env file)

**Database Settings:**
```bash
DB_PASSWORD=your_secure_password_here
```

**Exchange Credentials (Optional):**
```bash
# Leave empty for public data only
MEXC_API_KEY=your_mexc_api_key
MEXC_SECRET_KEY=your_mexc_secret
GATEIO_API_KEY=your_gateio_api_key  
GATEIO_SECRET_KEY=your_gateio_secret
```

**Application Settings:**
```bash
LOG_LEVEL=INFO
SNAPSHOT_INTERVAL=500  # milliseconds
```

### Data Collection Configuration

Edit `../config.yaml` to configure:
- Symbols to monitor
- Collection frequency
- Analytics settings
- Exchange-specific parameters

## Server Requirements

### Minimum
- **CPU**: 2 cores
- **RAM**: 4GB
- **Storage**: 50GB SSD
- **Network**: Stable internet connection

### Recommended
- **CPU**: 4+ cores
- **RAM**: 8GB+
- **Storage**: 100GB+ SSD
- **Network**: Low-latency connection

## Development vs Production Mode

### Development Mode (Hot-Reload)
```bash
# Start with mounted source code
./deploy.sh dev

# Benefits:
# ✅ Code changes apply immediately (no rebuild)
# ✅ Debug logging enabled
# ✅ PgAdmin and Grafana included by default
# ✅ Source code mounted as volume
# ✅ Auto-restart on crashes

# Your code changes in src/ are immediately reflected!
```

### Production Mode (Optimized)
```bash
# Start with built image
./deploy.sh start

# Benefits:
# ✅ Optimized for performance
# ✅ Smaller memory footprint
# ✅ Security hardening
# ✅ Code baked into image
```

## Management Commands

### Basic Operations
```bash
# Development mode (with hot-reload)
./deploy.sh dev

# Production mode
./deploy.sh start

# Stop all services  
./deploy.sh stop

# Restart services
./deploy.sh restart

# Check status
./deploy.sh status

# View logs
./deploy.sh logs
./deploy.sh logs database  # specific service
```

### Maintenance
```bash
# Update to latest version
./deploy.sh update

# Create database backup
./deploy.sh backup

# Health check
./deploy.sh health

# Clean up old data
./deploy.sh cleanup
```

## Data Access

### Database Connection
- **Host**: localhost:5432
- **Database**: arbitrage_data
- **User**: arbitrage_user
- **Password**: (from .env file)

### Key Tables
```sql
-- Real-time book ticker data
SELECT * FROM book_ticker_snapshots 
WHERE timestamp > NOW() - INTERVAL '1 hour';

-- Detected arbitrage opportunities
SELECT * FROM arbitrage_opportunities 
ORDER BY timestamp DESC LIMIT 10;

-- Order flow metrics
SELECT * FROM order_flow_metrics 
WHERE exchange = 'mexc' AND symbol = 'HIPPO/USDT';
```

### PgAdmin Access (Optional)
- **URL**: http://localhost:8080
- **Email**: admin@arbitrage.local
- **Password**: (from .env file)

### Grafana Monitoring (Optional)
- **URL**: http://localhost:3000
- **Username**: admin
- **Password**: (from .env file)

## Performance Optimization

### TimescaleDB Features
- **Automatic Partitioning**: Data automatically partitioned by time
- **Compression**: Older data automatically compressed
- **Continuous Aggregates**: Pre-computed 1-minute OHLC data
- **Retention Policies**: Automatic cleanup of old data

### Monitoring Metrics
```sql
-- Data collection rate
SELECT 
    exchange,
    symbol,
    COUNT(*) as updates_per_minute
FROM book_ticker_snapshots 
WHERE timestamp > NOW() - INTERVAL '1 minute'
GROUP BY exchange, symbol;

-- System performance
SELECT * FROM collector_status 
ORDER BY timestamp DESC LIMIT 10;
```

## Troubleshooting

### Common Issues

**1. Database Connection Failed**
```bash
# Check database status
docker-compose logs database

# Restart database
docker-compose restart database
```

**2. Data Collector Not Starting**
```bash
# Check logs
docker-compose logs data_collector

# Check configuration
./deploy.sh status
```

**3. WebSocket Connection Issues**
```bash
# Test network connectivity
docker-compose exec data_collector ping api.mexc.com
docker-compose exec data_collector ping api.gateio.ws
```

**4. Disk Space Issues**
```bash
# Check disk usage
df -h

# Clean up old Docker images
docker system prune -f

# Check database size
docker-compose exec database psql -U arbitrage_user -d arbitrage_data -c "
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

### Log Files
- **Deployment**: `deployment.log`
- **Application**: `docker-compose logs data_collector`
- **Database**: `docker-compose logs database`

## Security Considerations

### Network Security
- Services bound to localhost by default
- Use firewall rules for external access
- Consider VPN for remote management

### Database Security
- Strong passwords required
- Read-only user for analytics
- Regular backups recommended

### API Credentials
- Store in environment variables only
- Never commit to version control
- Use read-only API keys when possible

## Scaling

### Horizontal Scaling
- Deploy multiple collectors for different symbol sets
- Use separate databases for different asset classes
- Load balance WebSocket connections

### Vertical Scaling
- Increase container memory limits
- Add more CPU cores
- Use faster storage (NVMe SSD)

## Data Pipeline

### Collection Flow
```
WebSocket Data → Data Collector → PostgreSQL → Analytics
```

### Data Processing
1. **Real-time**: WebSocket feeds processed in memory
2. **Storage**: Bulk inserts to TimescaleDB every 500ms
3. **Analytics**: Continuous aggregates for performance
4. **Retention**: Automatic cleanup after 30 days

### Export Options
```bash
# Export recent data
docker-compose exec database pg_dump \
    -U arbitrage_user \
    -t book_ticker_snapshots \
    --where="timestamp > NOW() - INTERVAL '1 day'" \
    arbitrage_data > daily_export.sql

# Export to CSV
docker-compose exec database psql -U arbitrage_user -d arbitrage_data -c "
COPY (
    SELECT * FROM book_ticker_snapshots 
    WHERE timestamp > NOW() - INTERVAL '1 hour'
) TO STDOUT WITH CSV HEADER
" > data_export.csv
```

This Docker setup provides a production-ready data collection system that can run reliably on any server with Docker support.