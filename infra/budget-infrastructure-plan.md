# Budget Infrastructure Implementation Plan

## Executive Summary

This plan provides a cost-optimized architecture for the 3-tier arbitrage system designed for budget constraints (1-4 CPU servers) while maintaining HFT performance requirements. The solution uses lightweight components and efficient resource utilization to deliver enterprise-grade functionality at minimal cost.

## Budget Constraints & Optimization Strategy

### Server Specifications
- **Trading Server**: 2-4 vCPU, 8GB RAM, 50GB SSD (~$20-40/month)
- **Analytics Server**: 1-2 vCPU, 4GB RAM, 100GB SSD (~$10-20/month)
- **Total Monthly Cost**: $30-60 (excluding exchange fees)

### Cost Optimization Principles
1. **Single-Process Architecture**: Minimize memory overhead
2. **Embedded Databases**: Reduce deployment complexity  
3. **Lightweight Monitoring**: Essential metrics only
4. **Shared Resources**: Multi-purpose components
5. **Efficient Algorithms**: Optimize for CPU-constrained environment

---

## Architecture Overview

### Simplified System Design
```
┌─────────────────────────────────────┐    ┌─────────────────────────────┐
│         Trading Server              │    │     Analytics Server        │
│         (2-4 CPU, 8GB RAM)          │    │     (1-2 CPU, 4GB RAM)     │
├─────────────────────────────────────┤    ├─────────────────────────────┤
│ • Arbitrage Engine                  │    │ • SQLite Analytics DB       │
│ • SQLite Trading DB (embedded)      │────→• Grafana (lightweight)     │
│ • Redis (single instance)           │    │ • Simple HTTP server        │
│ • Lightweight Prometheus exporter   │    │ • Log aggregation           │
│ • Structured logging (JSON files)   │    │ • Backup manager            │
└─────────────────────────────────────┘    └─────────────────────────────┘
```

---

## Database Architecture (Budget Optimized)

### Primary Database: SQLite (Embedded)

**Why SQLite for Budget Setup:**
- **Zero Overhead**: No separate database process
- **ACID Compliance**: Full transaction support
- **High Performance**: >100k writes/sec with WAL mode
- **Zero Administration**: No configuration or maintenance
- **Minimal Memory**: <1MB base memory usage

#### Trading Database Schema
```sql
-- trades.db (Primary trading data)
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    buy_price REAL NOT NULL,
    sell_price REAL NOT NULL,
    amount REAL NOT NULL,
    gross_profit REAL NOT NULL,
    net_profit REAL NOT NULL,
    buy_fee REAL NOT NULL,
    sell_fee REAL NOT NULL,
    execution_latency_ms REAL NOT NULL,
    success INTEGER NOT NULL, -- 0/1 boolean
    failure_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trades_timestamp ON trades(timestamp_ms);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_success ON trades(success);

-- balances.db (Balance snapshots)
CREATE TABLE balance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_ms INTEGER NOT NULL,
    exchange TEXT NOT NULL,
    asset TEXT NOT NULL,
    available REAL NOT NULL,
    locked REAL NOT NULL,
    trigger_event TEXT NOT NULL, -- 'trade', 'manual', 'startup'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_balances_timestamp ON balance_snapshots(timestamp_ms);
CREATE INDEX idx_balances_exchange_asset ON balance_snapshots(exchange, asset);

-- opportunities.db (Opportunity tracking)
CREATE TABLE opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_ms INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    spread_pct REAL NOT NULL,
    potential_profit REAL NOT NULL,
    order_size REAL NOT NULL,
    executed INTEGER NOT NULL, -- 0/1 boolean
    rejection_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_opportunities_timestamp ON opportunities(timestamp_ms);
CREATE INDEX idx_opportunities_executed ON opportunities(executed);
```

### Lightweight Redis (Single Instance)

**Configuration for Budget Server:**
```yaml
# redis.conf (memory optimized)
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1    # Minimal persistence
save 300 10
save 60 10000
tcp-keepalive 300
timeout 300
databases 4   # Reduced from default 16

# Use for:
# DB 0: Active orders and positions
# DB 1: Symbol information cache
# DB 2: Performance counters  
# DB 3: System state
```

### Analytics Database: SQLite (Separate File)

```sql
-- analytics.db (Aggregated data for reporting)
CREATE TABLE daily_performance (
    date TEXT PRIMARY KEY,
    total_trades INTEGER NOT NULL,
    successful_trades INTEGER NOT NULL,
    total_profit REAL NOT NULL,
    avg_profit_per_trade REAL NOT NULL,
    best_symbol TEXT,
    worst_symbol TEXT,
    avg_execution_latency_ms REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE hourly_metrics (
    hour_timestamp TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    exchange TEXT,
    symbol TEXT,
    PRIMARY KEY (hour_timestamp, metric_name, exchange, symbol)
);

CREATE TABLE system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_ms INTEGER NOT NULL,
    event_type TEXT NOT NULL, -- 'error', 'warning', 'info'
    component TEXT NOT NULL,  -- 'exchange', 'arbitrage', 'system'
    message TEXT NOT NULL,
    details TEXT, -- JSON string for additional data
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_timestamp ON system_events(timestamp_ms);
CREATE INDEX idx_events_type ON system_events(event_type);
```

---

## Monitoring Stack (Lightweight)

### Prometheus Metrics (Embedded Exporter)

**Minimal Prometheus Configuration:**
```python
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
import time

class LightweightMetrics:
    """Embedded Prometheus metrics for budget setup"""
    
    def __init__(self):
        self.registry = CollectorRegistry()
        
        # Essential metrics only
        self.trades_total = Counter(
            'arbitrage_trades_total',
            'Total arbitrage trades executed',
            ['exchange_pair', 'result'],
            registry=self.registry
        )
        
        self.execution_duration = Histogram(
            'arbitrage_execution_duration_seconds',
            'Time spent executing arbitrage trades',
            ['exchange_pair'],
            registry=self.registry
        )
        
        self.current_pnl = Gauge(
            'arbitrage_current_pnl_usd',
            'Current P&L in USD',
            ['exchange'],
            registry=self.registry
        )
        
        self.api_request_duration = Histogram(
            'exchange_api_request_duration_seconds',
            'Exchange API request duration',
            ['exchange', 'endpoint', 'method'],
            registry=self.registry
        )
        
        self.websocket_connections = Gauge(
            'websocket_connections_active',
            'Active WebSocket connections',
            ['exchange'],
            registry=self.registry
        )
        
        self.balance_usd = Gauge(
            'exchange_balance_usd',
            'Exchange balance in USD equivalent',
            ['exchange', 'asset'],
            registry=self.registry
        )
    
    def get_metrics(self) -> bytes:
        """Get Prometheus formatted metrics"""
        return generate_latest(self.registry)
```

### Simple HTTP Metrics Server
```python
from aiohttp import web, web_response
import aiohttp
import asyncio

class MetricsServer:
    """Lightweight metrics HTTP server"""
    
    def __init__(self, metrics: LightweightMetrics, port: int = 8080):
        self.metrics = metrics
        self.port = port
        self.app = web.Application()
        self.app.router.add_get('/metrics', self._metrics_handler)
        self.app.router.add_get('/health', self._health_handler)
        
    async def _metrics_handler(self, request) -> web_response.Response:
        """Serve Prometheus metrics"""
        metrics_data = self.metrics.get_metrics()
        return web_response.Response(
            body=metrics_data,
            content_type='text/plain; version=0.0.4; charset=utf-8'
        )
    
    async def _health_handler(self, request) -> web_response.Response:
        """Basic health check"""
        return web_response.json_response({'status': 'healthy', 'timestamp': time.time()})
    
    async def start(self):
        """Start metrics server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        print(f"Metrics server started on port {self.port}")
```

### Structured Logging (JSON Files)

**Budget-Friendly Logging Strategy:**
```python
import json
import logging
import time
from typing import Dict, Any

class JSONFileLogger:
    """Structured logging to JSON files for budget analytics"""
    
    def __init__(self, log_dir: str = "./logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Separate log files by category
        self.loggers = {
            'trades': self._setup_logger('trades'),
            'system': self._setup_logger('system'),
            'errors': self._setup_logger('errors'),
            'performance': self._setup_logger('performance')
        }
    
    def _setup_logger(self, category: str) -> logging.Logger:
        """Setup category-specific logger"""
        logger = logging.getLogger(f"arbitrage.{category}")
        logger.setLevel(logging.INFO)
        
        handler = logging.FileHandler(
            self.log_dir / f"{category}.jsonl",
            mode='a'
        )
        
        # JSON formatter
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def log_trade(self, trade_data: Dict[str, Any]):
        """Log trade execution"""
        record = {
            'timestamp': time.time(),
            'type': 'trade_execution',
            **trade_data
        }
        self.loggers['trades'].info(json.dumps(record))
    
    def log_performance(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """Log performance metric"""
        record = {
            'timestamp': time.time(),
            'type': 'performance_metric',
            'metric': metric_name,
            'value': value,
            'tags': tags or {}
        }
        self.loggers['performance'].info(json.dumps(record))
    
    def log_system_event(self, level: str, message: str, details: Dict[str, Any] = None):
        """Log system event"""
        record = {
            'timestamp': time.time(),
            'type': 'system_event',
            'level': level,
            'message': message,
            'details': details or {}
        }
        self.loggers['system'].info(json.dumps(record))
```

---

## Analytics Server Setup

### Lightweight Grafana Configuration

**Docker Compose for Analytics Server:**
```yaml
# docker-compose.yml (Analytics server)
version: '3.8'

services:
  grafana:
    image: grafana/grafana:latest
    container_name: arbitrage-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
      - GF_INSTALL_PLUGINS=
      - GF_SERVER_ROOT_URL=http://localhost:3000
      - GF_ANALYTICS_REPORTING_ENABLED=false
      - GF_ANALYTICS_CHECK_FOR_UPDATES=false
    volumes:
      - grafana-storage:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    restart: unless-stopped
    mem_limit: 512m
    cpus: 0.5

  prometheus:
    image: prom/prometheus:latest
    container_name: arbitrage-prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=7d'  # 7 day retention for budget
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
      - '--storage.tsdb.min-block-duration=1h'  # Optimize for small data
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-storage:/prometheus
    restart: unless-stopped
    mem_limit: 256m
    cpus: 0.5

volumes:
  grafana-storage:
  prometheus-storage:
```

**Prometheus Configuration (Budget):**
```yaml
# prometheus.yml
global:
  scrape_interval: 15s  # Increased interval to reduce load
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'arbitrage-bot'
    static_configs:
      - targets: ['TRADING_SERVER_IP:8080']
    scrape_interval: 15s
    scrape_timeout: 10s

rule_files:
  - "alert_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - localhost:9093
```

### Simple Analytics Dashboard

**Python Analytics Server:**
```python
from flask import Flask, jsonify, render_template
import sqlite3
import json
from datetime import datetime, timedelta

class AnalyticsServer:
    """Simple analytics server for budget setup"""
    
    def __init__(self, db_path: str):
        self.app = Flask(__name__)
        self.db_path = db_path
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/api/daily-pnl')
        def daily_pnl():
            """Get daily P&L data"""
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        date,
                        total_profit,
                        successful_trades,
                        total_trades
                    FROM daily_performance 
                    ORDER BY date DESC 
                    LIMIT 30
                """)
                
                data = [{
                    'date': row[0],
                    'pnl': row[1],
                    'trades': row[2],
                    'total_trades': row[3]
                } for row in cursor.fetchall()]
                
            return jsonify(data)
        
        @self.app.route('/api/symbol-performance')
        def symbol_performance():
            """Get symbol performance breakdown"""
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        symbol,
                        COUNT(*) as trade_count,
                        SUM(net_profit) as total_profit,
                        AVG(execution_latency_ms) as avg_latency
                    FROM trades 
                    WHERE success = 1 
                    GROUP BY symbol 
                    ORDER BY total_profit DESC
                """)
                
                data = [{
                    'symbol': row[0],
                    'trades': row[1],
                    'profit': row[2],
                    'avg_latency': row[3]
                } for row in cursor.fetchall()]
                
            return jsonify(data)
        
        @self.app.route('/')
        def dashboard():
            """Serve simple HTML dashboard"""
            return render_template('dashboard.html')
    
    def run(self, host='0.0.0.0', port=5000):
        """Run analytics server"""
        self.app.run(host=host, port=port, debug=False)
```

---

## Implementation Plan

### Phase 1: Trading Server Setup (Week 1)

#### Day 1-2: Core Infrastructure
```bash
# Server setup (Ubuntu 20.04 LTS)
sudo apt update && sudo apt upgrade -y
sudo apt install python3.11 python3.11-pip redis-server sqlite3 htop -y

# Python environment
python3.11 -m pip install --user pipx
pipx install poetry
poetry new arbitrage-bot
cd arbitrage-bot

# Dependencies
poetry add aiohttp asyncio msgspec redis sqlite3
poetry add prometheus-client
poetry add --group dev pytest black isort
```

#### Day 3-4: Database Setup
```python
# database.py
import sqlite3
import asyncio
import aiosqlite
from pathlib import Path

class DatabaseManager:
    """Lightweight database manager for budget setup"""
    
    def __init__(self, db_dir: str = "./data"):
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(exist_ok=True)
        
        self.db_paths = {
            'trades': self.db_dir / 'trades.db',
            'analytics': self.db_dir / 'analytics.db'
        }
    
    async def initialize(self):
        """Initialize all databases"""
        for db_name, db_path in self.db_paths.items():
            await self._create_tables(db_path, db_name)
    
    async def _create_tables(self, db_path: Path, db_name: str):
        """Create tables for specific database"""
        async with aiosqlite.connect(db_path) as db:
            if db_name == 'trades':
                await self._create_trades_tables(db)
            elif db_name == 'analytics':
                await self._create_analytics_tables(db)
            
            await db.commit()
    
    async def record_trade(self, trade_data: dict):
        """Record trade execution"""
        async with aiosqlite.connect(self.db_paths['trades']) as db:
            await db.execute("""
                INSERT INTO trades (
                    execution_id, timestamp_ms, symbol, buy_exchange, sell_exchange,
                    buy_price, sell_price, amount, gross_profit, net_profit,
                    buy_fee, sell_fee, execution_latency_ms, success, failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data['execution_id'],
                trade_data['timestamp_ms'],
                trade_data['symbol'],
                trade_data['buy_exchange'],
                trade_data['sell_exchange'],
                trade_data['buy_price'],
                trade_data['sell_price'],
                trade_data['amount'],
                trade_data['gross_profit'],
                trade_data['net_profit'],
                trade_data['buy_fee'],
                trade_data['sell_fee'],
                trade_data['execution_latency_ms'],
                trade_data['success'],
                trade_data.get('failure_reason')
            ))
            await db.commit()
```

#### Day 5-7: Monitoring Integration
```python
# monitoring.py
import time
import asyncio
from typing import Dict, Any

class BudgetMonitoring:
    """Lightweight monitoring for budget setup"""
    
    def __init__(self, db_manager, metrics, logger):
        self.db_manager = db_manager
        self.metrics = metrics
        self.logger = logger
        
        # Performance counters
        self.counters = {
            'trades_executed': 0,
            'trades_successful': 0,
            'api_calls': 0,
            'websocket_messages': 0
        }
    
    def record_trade_execution(self, trade_data: Dict[str, Any]):
        """Record trade execution with minimal overhead"""
        # Update counters (O(1))
        self.counters['trades_executed'] += 1
        if trade_data['success']:
            self.counters['trades_successful'] += 1
        
        # Update Prometheus metrics
        result = 'success' if trade_data['success'] else 'failed'
        exchange_pair = f"{trade_data['buy_exchange']}-{trade_data['sell_exchange']}"
        
        self.metrics.trades_total.labels(
            exchange_pair=exchange_pair,
            result=result
        ).inc()
        
        self.metrics.execution_duration.labels(
            exchange_pair=exchange_pair
        ).observe(trade_data['execution_latency_ms'] / 1000.0)
        
        # Log to JSON file (async)
        asyncio.create_task(self.logger.log_trade(trade_data))
        
        # Record to database (async)
        asyncio.create_task(self.db_manager.record_trade(trade_data))
    
    def record_api_call(self, exchange: str, endpoint: str, duration_ms: float, success: bool):
        """Record API call metrics"""
        self.counters['api_calls'] += 1
        
        self.metrics.api_request_duration.labels(
            exchange=exchange,
            endpoint=endpoint,
            method='GET'
        ).observe(duration_ms / 1000.0)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get current performance summary"""
        return {
            'trades_executed': self.counters['trades_executed'],
            'trades_successful': self.counters['trades_successful'],
            'success_rate': (
                self.counters['trades_successful'] / self.counters['trades_executed'] * 100
                if self.counters['trades_executed'] > 0 else 0
            ),
            'api_calls': self.counters['api_calls'],
            'websocket_messages': self.counters['websocket_messages'],
            'timestamp': time.time()
        }
```

### Phase 2: Analytics Server Setup (Week 2)

#### Day 1-3: Analytics Infrastructure
```bash
# Analytics server setup (1-2 CPU, 4GB RAM)
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io docker-compose python3-pip -y
sudo usermod -aG docker $USER

# Create analytics directory structure
mkdir -p analytics/{grafana/provisioning/{dashboards,datasources},prometheus,logs}
```

#### Day 4-5: Grafana Dashboards
```json
# grafana/provisioning/dashboards/arbitrage-dashboard.json
{
  "dashboard": {
    "id": null,
    "title": "Arbitrage Trading Dashboard",
    "tags": ["arbitrage"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Current P&L",
        "type": "stat",
        "targets": [
          {
            "expr": "arbitrage_current_pnl_usd",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {
              "mode": "thresholds"
            },
            "thresholds": {
              "steps": [
                {"color": "red", "value": null},
                {"color": "yellow", "value": 0},
                {"color": "green", "value": 10}
              ]
            }
          }
        },
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
      },
      {
        "id": 2,
        "title": "Trade Execution Latency",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, arbitrage_execution_duration_seconds)",
            "refId": "A",
            "legendFormat": "P95 Latency"
          }
        ],
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
      }
    ],
    "refresh": "5s",
    "schemaVersion": 27
  }
}
```

#### Day 6-7: Data Pipeline & Testing
```python
# sync_service.py (Analytics server)
import asyncio
import httpx
import sqlite3
import json
from datetime import datetime

class DataSyncService:
    """Sync data from trading server to analytics server"""
    
    def __init__(self, trading_server_url: str, local_db: str):
        self.trading_server_url = trading_server_url
        self.local_db = local_db
        self.client = httpx.AsyncClient()
    
    async def sync_performance_data(self):
        """Sync performance data every minute"""
        while True:
            try:
                # Fetch latest performance data
                response = await self.client.get(f"{self.trading_server_url}/api/performance")
                data = response.json()
                
                # Store in local analytics database
                await self._store_performance_data(data)
                
                await asyncio.sleep(60)  # Sync every minute
                
            except Exception as e:
                print(f"Sync error: {e}")
                await asyncio.sleep(60)
    
    async def _store_performance_data(self, data: dict):
        """Store performance data in analytics database"""
        with sqlite3.connect(self.local_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hourly_metrics (
                    hour_timestamp, metric_name, metric_value, exchange, symbol
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:00:00"),
                'total_trades',
                data['trades_executed'],
                None,
                None
            ))
            conn.commit()
```

### Phase 3: Production Deployment (Week 3)

#### Cost Optimization
```yaml
# Production deployment costs
Trading Server:
  Provider: DigitalOcean/Linode/Vultr
  Spec: 2 vCPU, 8GB RAM, 50GB SSD
  Cost: ~$40/month
  
Analytics Server:
  Provider: Same provider
  Spec: 1 vCPU, 2GB RAM, 25GB SSD  
  Cost: ~$15/month

Total Infrastructure Cost: ~$55/month
```

#### Automated Deployment Script
```bash
#!/bin/bash
# deploy.sh

set -e

echo "Deploying Arbitrage Trading System..."

# Trading server deployment
if [ "$1" == "trading" ]; then
    echo "Deploying trading server..."
    
    # Install dependencies
    sudo apt update
    sudo apt install -y python3.11 python3.11-pip redis-server sqlite3
    
    # Setup application
    git clone https://github.com/your-repo/arbitrage-bot.git
    cd arbitrage-bot
    
    # Install Python dependencies
    pip3.11 install -r requirements.txt
    
    # Initialize databases
    python3.11 -c "from database import DatabaseManager; import asyncio; asyncio.run(DatabaseManager().initialize())"
    
    # Start services
    sudo systemctl enable redis-server
    sudo systemctl start redis-server
    
    # Create systemd service
    sudo cp arbitrage-bot.service /etc/systemd/system/
    sudo systemctl enable arbitrage-bot
    sudo systemctl start arbitrage-bot
    
    echo "Trading server deployed successfully!"

elif [ "$1" == "analytics" ]; then
    echo "Deploying analytics server..."
    
    # Install Docker
    sudo apt update
    sudo apt install -y docker.io docker-compose
    
    # Setup analytics stack
    git clone https://github.com/your-repo/arbitrage-analytics.git
    cd arbitrage-analytics
    
    # Start analytics services
    docker-compose up -d
    
    echo "Analytics server deployed successfully!"
    echo "Grafana available at: http://SERVER_IP:3000"
    echo "Default credentials: admin/admin123"

else
    echo "Usage: $0 [trading|analytics]"
    exit 1
fi
```

### Monitoring & Alerting Setup

#### Simple Email Alerts
```python
# alerts.py
import smtplib
from email.mime.text import MIMEText
import asyncio

class SimpleAlerts:
    """Lightweight alerting for budget setup"""
    
    def __init__(self, smtp_config: dict):
        self.smtp_config = smtp_config
        self.alert_thresholds = {
            'max_execution_latency_ms': 100,
            'min_success_rate_pct': 80,
            'max_daily_loss_usd': 50
        }
    
    async def check_and_alert(self, performance_data: dict):
        """Check performance and send alerts if needed"""
        alerts = []
        
        # Check execution latency
        if performance_data.get('avg_latency_ms', 0) > self.alert_thresholds['max_execution_latency_ms']:
            alerts.append(f"High latency: {performance_data['avg_latency_ms']:.2f}ms")
        
        # Check success rate
        if performance_data.get('success_rate', 100) < self.alert_thresholds['min_success_rate_pct']:
            alerts.append(f"Low success rate: {performance_data['success_rate']:.1f}%")
        
        # Send alerts if any
        if alerts:
            await self._send_alert("\n".join(alerts))
    
    async def _send_alert(self, message: str):
        """Send email alert"""
        try:
            msg = MIMEText(f"Arbitrage Alert:\n\n{message}")
            msg['Subject'] = 'Arbitrage Trading Alert'
            msg['From'] = self.smtp_config['from_email']
            msg['To'] = self.smtp_config['to_email']
            
            with smtplib.SMTP(self.smtp_config['smtp_server'], self.smtp_config['port']) as server:
                server.starttls()
                server.login(self.smtp_config['username'], self.smtp_config['password'])
                server.send_message(msg)
                
        except Exception as e:
            print(f"Alert sending failed: {e}")
```

---

## Performance Expectations

### Resource Utilization (Budget Servers)

#### Trading Server (2-4 CPU, 8GB RAM)
- **CPU Usage**: 30-60% average during active trading
- **RAM Usage**: 2-4GB (SQLite + Redis + Python application)
- **Storage**: 100MB-1GB daily growth for trade data
- **Network**: 10-50 Mbps for exchange connections

#### Analytics Server (1-2 CPU, 4GB RAM)  
- **CPU Usage**: 20-40% average
- **RAM Usage**: 1-2GB (Grafana + Prometheus + sync services)
- **Storage**: 50MB-200MB daily growth for metrics
- **Network**: 1-10 Mbps for data sync

### Performance Targets (Budget Optimized)

| Metric | Budget Target | Notes |
|--------|---------------|-------|
| **Trade Execution Latency** | <100ms | Increased from <50ms due to CPU constraints |
| **Database Write Latency** | <10ms | SQLite WAL mode optimization |
| **Monitoring Overhead** | <2% | Reduced metrics collection |
| **Memory Usage** | <6GB total | Optimized for 8GB server |
| **Data Retention** | 90 days | Reduced from 1 year to save storage |

---

## Cost Breakdown & ROI Analysis

### Monthly Infrastructure Costs
```
Trading Server (2 vCPU, 8GB RAM):     $40
Analytics Server (1 vCPU, 2GB RAM):   $15
Domain & SSL Certificate:             $5
Email Service (alerts):               $5
Total Monthly Infrastructure:         $65

Annual Infrastructure Cost:           $780
```

### Break-Even Analysis
```
Target: $10/day profit = $300/month
Infrastructure Cost: $65/month
Net Monthly Profit: $235/month

Break-even: 6.5 days of operation
Annual Net Profit Potential: $2,820
ROI: 361% annually
```

### Scaling Economics
```
Current Setup (Budget):
- Max Symbols: 20-30
- Max Trades/Day: 50-100
- Profit Potential: $10-30/day

Upgrade Path:
- 4 vCPU server: +50% capacity for +$20/month
- Add exchanges: +100% opportunities
- Scale to $50/day with $85/month cost
```

This budget-optimized plan provides a complete arbitrage trading system with comprehensive monitoring for under $65/month while maintaining the core HFT performance characteristics necessary for profitable operation.

The system is designed to be profitable from day one while providing a clear upgrade path as trading volume and profits increase.