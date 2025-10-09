# PostgreSQL Space Management Guide

## 🚨 Emergency Resolution Summary

**Date**: October 9, 2025  
**Issue**: PostgreSQL consuming 15GB of 25GB disk space, causing server crashes  
**Resolution**: Successfully implemented 3-day retention policy and automated monitoring

## 📊 Root Cause Analysis

### The Problem
- **Database growth**: 6.69M records in 2 days (3.35M records/day)
- **Growth rate**: 139K records/hour across 59 MEXC trading symbols
- **Space distribution**: 15GB TimescaleDB hypertable chunks
- **Server capacity**: Only 25GB total disk space

### Space Breakdown (Before Fix)
```
Total Disk: 25GB (100% full)
├── PostgreSQL: 15GB
│   ├── TimescaleDB chunks: 12GB (_timescaledb_internal schema)
│   ├── Main table data: 583MB
│   ├── WAL logs: 993MB
│   └── Indexes: ~1GB
├── Docker images: 2.1GB
├── System files: 4GB
└── Swap: 2.1GB
```

## ✅ Solutions Implemented

### 1. Emergency Cleanup (Immediate)
- **Truncated all data tables** to free space immediately
- **Freed 1.2GB disk space** (98% → 94% usage)
- **Database operational** with 1.7GB free space

### 2. Retention Policies (Long-term)
Updated `docker/init-db.sql` with aggressive retention:
```sql
-- Main time-series data: 3 days (reduced from 7 days)
SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '3 days');
SELECT add_retention_policy('orderbook_depth', INTERVAL '3 days');
SELECT add_retention_policy('trade_snapshots', INTERVAL '3 days');

-- Supporting data: 7-14 days (reduced from 30-90 days)
SELECT add_retention_policy('funding_rate_snapshots', INTERVAL '7 days');
SELECT add_retention_policy('order_flow_metrics', INTERVAL '7 days');
SELECT add_retention_policy('arbitrage_opportunities', INTERVAL '14 days');
```

### 3. Automated Monitoring
#### Daily Cleanup Script (`/opt/arbitrage/docker/daily_cleanup.sh`)
- **Scheduled**: Every day at 2 AM
- **Adaptive cleanup**:
  - Disk > 90%: Keep 12 hours of data
  - Disk > 80%: Keep 24 hours of data  
  - Disk < 80%: Keep 72 hours of data
- **Automatic Docker cleanup** if disk > 85%

#### Hourly Monitoring
- **Disk alerts**: Hourly check for >95% usage
- **Log location**: `/var/log/disk_alerts.log`

### 4. Enhanced Migration System
Updated `src/db/migrations.py` with:
- **Retention policy verification** function
- **Manual retention update** capability
- **Detailed reporting** of current policies

## 📋 Current System State

### Space Usage (After Fix)
```
Total Disk: 25GB
├── Used: 22GB (94%)
├── Free: 1.7GB (6%) ✅
└── Critical threshold: 95%
```

### Automated Tasks
```bash
# Daily cleanup at 2 AM
0 2 * * * /opt/arbitrage/docker/daily_cleanup.sh

# Hourly disk monitoring  
0 * * * * [disk monitoring script]

# Database monitoring every 30 minutes
*/30 * * * * /opt/arbitrage/docker/database_monitoring.sh
```

## 🔧 Manual Operations

### Emergency Cleanup (If needed)
```bash
# SSH to server
ssh -i ~/.ssh/deploy_ci root@31.192.233.13

# Run immediate cleanup
/opt/arbitrage/docker/daily_cleanup.sh

# Truncate tables if critical (LAST RESORT)
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "TRUNCATE TABLE book_ticker_snapshots;"
```

### Check System Status
```bash
# Disk usage
df -h /

# Database size
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));"

# Record counts
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT COUNT(*) FROM book_ticker_snapshots;"

# Check logs
tail -f /var/log/database_cleanup.log
tail -f /var/log/disk_alerts.log
```

### Update Retention Policies
```python
# Using Python API
from db.migrations import update_retention_policies
result = await update_retention_policies(retention_days=3)
```

## 📈 Sustainable Growth Targets

### Data Volume Thresholds
- **Sustainable**: ~150K records/hour with 3-day retention
- **Warning**: >200K records/hour  
- **Critical**: >300K records/hour

### Space Budget
- **Database**: 1.5GB max (3 days of data)
- **Safety buffer**: 2GB free space minimum
- **Critical threshold**: 95% disk usage

### Performance Targets
- **Daily cleanup**: <5 minutes execution
- **Database queries**: <10ms average
- **Space reclamation**: >500MB per cleanup cycle

## 🚀 Future Improvements

### Short-term (1-2 weeks)
- [ ] **Upgrade disk**: 25GB → 50GB minimum
- [ ] **Implement table partitioning** for better management
- [ ] **Add compression** for older data

### Long-term (1-3 months)
- [ ] **TimescaleDB optimization**: Proper hypertable configuration
- [ ] **Data archival**: Long-term storage solution
- [ ] **Distributed database**: Multi-node setup
- [ ] **Cloud migration**: Managed database services

## 📞 Emergency Contacts

### Critical Thresholds
- **95% disk usage**: Automatic alerts triggered
- **98% disk usage**: Data collection stops automatically
- **99% disk usage**: Manual intervention required

### Emergency Actions
1. **Immediate**: Run daily cleanup script
2. **If critical**: Truncate data tables  
3. **If persistent**: Upgrade disk size
4. **If recurring**: Review data collection rate

---

**Last Updated**: October 9, 2025  
**Status**: ✅ Operational with automated monitoring  
**Next Review**: Monitor for 48 hours to confirm stability