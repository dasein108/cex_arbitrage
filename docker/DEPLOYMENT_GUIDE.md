# CEX Arbitrage - Complete Deployment Infrastructure Guide

## 🚀 Production-Grade Deployment Infrastructure

This directory contains a **sophisticated, enterprise-grade deployment system** specifically optimized for high-frequency trading (HFT) cryptocurrency arbitrage operations. The infrastructure supports multiple deployment scenarios with comprehensive automation.

## **Core Infrastructure Components**

### **Essential Deployment Scripts**

#### **1. `deploy.sh` - Master Deployment Orchestrator**
**Purpose**: Complete production deployment automation for remote servers
- **Target Server**: 31.192.233.13 (4GB optimized)
- **Authentication**: SSH key-based (`~/.ssh/deploy_ci`)
- **Features**: Zero-downtime deployment, database initialization, Docker automation

**Commands**:
```bash
./deploy.sh deploy   # Full deployment (sync + setup + deploy + rebuild)
./deploy.sh update   # Update code/config and restart collector (no rebuild)
./deploy.sh rebuild  # Rebuild Docker image with new dependencies
./deploy.sh sync     # Sync code only (no restart)
```

**Key Capabilities**:
- **Automatic Docker Installation**: Installs Docker/Docker Compose if missing
- **4GB Server Optimization**: Swap setup, memory management
- **Database Management**: Schema initialization, constraint fixing, verification
- **Zero-Downtime Updates**: Smart container restart strategies
- **Production Hardening**: Proper permissions, security configuration

#### **2. `start-dev.sh` - Development Environment Manager**
**Purpose**: One-command development environment with production-like monitoring
- **Local Development**: Full stack on localhost
- **Service Orchestration**: Database → Data Collector → Monitoring
- **Health Monitoring**: Automated readiness checks

**Features**:
- **Intelligent Startup**: Waits for database readiness before starting dependent services
- **Monitoring Integration**: Grafana (localhost:3000) + PgAdmin (localhost:8080)
- **Development Authentication**: Simplified credentials for local testing
- **Service Health**: Real-time container status monitoring

**Access Points**:
- Grafana: http://localhost:3000 (admin/dev_grafana)
- PgAdmin: http://localhost:8080 (admin@example.com/dev_admin)
- Database: localhost:5432 (arbitrage_user/dev_password_2024)

#### **3. `rebuild.sh` - Container Lifecycle Manager**
**Purpose**: Sophisticated Docker image management for CI/CD workflows
- **Selective Rebuilds**: Target specific containers (data_collector)
- **Environment Support**: Local and server environments
- **Cache Management**: No-cache rebuilds for dependency changes

**Commands**:
```bash
./rebuild.sh local           # Rebuild data_collector locally
./rebuild.sh server          # Rebuild data_collector on server  
./rebuild.sh restart-local   # Rebuild and restart locally
./rebuild.sh restart-server  # Rebuild and restart on server
./rebuild.sh clean           # Clean up old images and cache
./rebuild.sh logs            # Show data_collector logs
./rebuild.sh status          # Container status and recent logs
```

**HFT Optimizations**:
- **Minimal Downtime**: Smart container stop/start sequences
- **Image Efficiency**: Multi-stage builds, layer optimization
- **Debug Support**: Comprehensive logging and status monitoring

#### **4. `cleanup-server.sh` - Production Maintenance System**
**Purpose**: Automated server resource optimization for 4GB production servers
- **Disk Space Management**: Docker, logs, APT cache cleanup
- **Database Analysis**: TimescaleDB compression and space monitoring
- **System Health**: Deep analysis of resource usage

**Commands**:
```bash
./cleanup-server.sh docker     # Clean Docker images, containers, cache
./cleanup-server.sh logs       # Clean log files and journal
./cleanup-server.sh database   # Analyze database space usage
./cleanup-server.sh analyze    # Deep system analysis
./cleanup-server.sh all        # Run all safe cleanup operations
./cleanup-server.sh aggressive # Aggressive Docker cleanup (DANGEROUS)
```

**Advanced Features**:
- **TimescaleDB Analysis**: Chunk analysis, compression status, table sizes
- **Resource Monitoring**: Real-time disk usage, largest directories/files
- **Smart Cleanup**: Preserves active containers while cleaning unused resources

### **Docker Compose Configurations**

#### **Core Deployment Files**

1. **`docker-compose.yml`** - Base infrastructure configuration
   - PostgreSQL/TimescaleDB with optimized settings
   - Data collector container with source mounting
   - Network configuration and volume management

2. **`docker-compose.dev.yml`** - Development environment overrides
   - Hot-reload for source code changes
   - Development-friendly logging levels
   - Simplified authentication

3. **`docker-compose.prod.yml`** - Production optimizations
   - Resource limits for 4GB servers
   - Security hardening
   - Production logging configuration

4. **`docker-compose.local-monitoring.yml`** - **Essential for your needs**
   - Local Grafana + PgAdmin connecting to remote production database
   - Optimized for monitoring remote infrastructure
   - Minimal resource footprint

5. **`docker-compose.prometheus.yml`** - Complete monitoring stack
   - Prometheus metrics collection
   - Alertmanager notifications
   - Extended monitoring capabilities

### **Database Infrastructure**

#### **`init-db.sql` - Complete Database Schema**
**Production-ready TimescaleDB schema optimized for HFT data collection**:

```sql
-- Core tables for arbitrage data
book_ticker_snapshots    # Real-time orderbook snapshots
trades                   # Trade execution records  
arbitrage_opportunities  # Detected arbitrage chances
funding_rates           # Futures funding rate tracking
balances                # Account balance tracking
```

**HFT Optimizations**:
- **TimescaleDB Hypertables**: Automated partitioning for time-series data
- **Compression Policies**: 7-day retention with compression
- **Continuous Aggregates**: Pre-computed OHLCV and spread analytics
- **Optimized Indexes**: Sub-millisecond query performance

#### **`optimize-db.sql` - Resource Optimization**
**4GB server optimizations**:
- Compression policies for space efficiency
- Chunk size optimization for memory usage
- Vacuum and analyze scheduling
- Space reclamation procedures

### **Monitoring & Configuration**

#### **Grafana Provisioning** (`grafana/`)
- **Datasources**: Remote PostgreSQL connection configuration
- **Dashboards**: Pre-built HFT monitoring dashboards
- **Provisioning**: Automated dashboard and datasource setup

#### **Prometheus Configuration** (`prometheus/`)
- **Metrics Collection**: HFT-specific metrics and alerts
- **Alert Rules**: Latency, throughput, and error rate monitoring
- **Service Discovery**: Automatic container discovery

## **Deployment Workflows**

### **Production Deployment (New Server)**
```bash
# Complete production setup
./deploy.sh deploy
```

**What happens**:
1. Code sync via rsync
2. Docker/Docker Compose installation
3. 4GB server optimization (swap setup)
4. Database schema initialization
5. Container orchestration
6. Health verification

### **Code Updates (Existing Server)**
```bash
# Quick updates for configuration/code changes
./deploy.sh update
```

**What happens**:
1. Code sync
2. Configuration reload
3. Smart container restart (preserves database)

### **Dependency Updates**
```bash
# Full rebuild after dependency changes
./deploy.sh rebuild
```

**What happens**:
1. Code sync
2. No-cache image rebuild
3. Container restart with new image

### **Development Environment**
```bash
# Local development with monitoring
./start-dev.sh
```

**What happens**:
1. Database startup and readiness check
2. Data collector with hot-reload
3. Monitoring stack (Grafana + PgAdmin)
4. Service health verification

### **Remote Monitoring Setup**
```bash
# Monitor remote production database locally
cd /Users/dasein/dev/cex_arbitrage/docker
docker-compose -f docker-compose.local-monitoring.yml up -d
```

**Access**:
- Grafana: http://localhost:3000 (admin/local_grafana_2024)
- PgAdmin: http://localhost:8080 (admin@localhost.com/local_pgadmin_2024)
- Remote DB: Connects to 31.192.233.13:5432

## **Infrastructure Architecture**

### **Multi-Environment Support**
- **Development**: Local stack with hot-reload and simplified auth
- **Production**: Hardened 4GB server deployment with resource optimization
- **Monitoring**: Remote monitoring capabilities for production oversight

### **HFT Performance Optimizations**
- **Sub-50ms Latency**: Optimized container networking and database queries
- **Memory Efficiency**: 4GB server optimization with swap management
- **Resource Monitoring**: Real-time performance tracking and alerting

### **Operational Excellence**
- **Zero-Downtime Deployment**: Smart container restart strategies
- **Automated Maintenance**: Disk cleanup, log rotation, resource optimization
- **Comprehensive Monitoring**: Database metrics, system health, trading performance

### **Security & Reliability**
- **SSH Key Authentication**: Secure deployment access
- **Network Isolation**: Container networking with proper segmentation
- **Data Persistence**: Backup directories and persistent volumes
- **Error Recovery**: Automatic restart policies and health checks

## **Quick Reference**

### **Essential Commands**
```bash
# Production deployment
./deploy.sh deploy          # Full deployment
./deploy.sh update           # Quick updates
./deploy.sh rebuild          # Rebuild images

# Development
./start-dev.sh              # Local development environment

# Maintenance
./cleanup-server.sh all     # Server cleanup
./rebuild.sh status         # Container health

# Remote monitoring
docker-compose -f docker-compose.local-monitoring.yml up -d
```

### **Key Files to Maintain**
- ✅ All deployment scripts (deploy.sh, start-dev.sh, rebuild.sh, cleanup-server.sh)
- ✅ All Docker Compose files
- ✅ Database schema files (init-db.sql, optimize-db.sql)
- ✅ Grafana/Prometheus configurations

### **Server Configuration**
- **Target**: 31.192.233.13 (4GB VPS)
- **SSH Key**: ~/.ssh/deploy_ci
- **Remote Path**: /opt/arbitrage
- **Database**: PostgreSQL + TimescaleDB
- **Monitoring**: Optional Grafana/PgAdmin profiles

---

**This deployment infrastructure represents enterprise-grade DevOps practices specifically optimized for high-frequency cryptocurrency trading operations.**