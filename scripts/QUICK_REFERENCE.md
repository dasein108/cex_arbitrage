# Quick Reference Guide - PostgreSQL Space Crisis

## 🚨 EMERGENCY COMMANDS (Copy & Paste Ready)

### 1. Connect to Server
```bash
ssh -i ~/.ssh/deploy_ci root@31.192.233.13
```

### 2. Immediate Space Check
```bash
df -h
docker system df
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));"
```

### 3. Emergency Cleanup (IMMEDIATE ACTION)
```bash
# Stop non-essential containers
docker stop $(docker ps --format "{{.Names}}" | grep -v "arbitrage_db")

# Emergency database cleanup (6-hour retention)
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
SELECT remove_retention_policy('book_ticker_snapshots', true);
SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '6 hours');
SELECT remove_retention_policy('orderbook_depth', true);
SELECT add_retention_policy('orderbook_depth', INTERVAL '2 hours');
SELECT run_job(job_id) FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention';
VACUUM FULL;"

# Docker cleanup
docker system prune -a -f --volumes
```

### 4. Nuclear Option (IF ABOVE INSUFFICIENT)
```bash
# Complete Docker reset (DESTROYS ALL CONTAINERS)
docker stop $(docker ps -q)
docker system prune -a -f --volumes
docker rm $(docker ps -aq)
docker rmi $(docker images -q) -f

# Rebuild database only
cd /opt/arbitrage
docker-compose up -d database
```

### 5. Verify Results
```bash
df -h
docker system df
echo "Database size:"
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));"
```

---

## 📊 CRITICAL THRESHOLDS

| Metric | Current | Emergency | Target |
|--------|---------|-----------|--------|
| Disk Usage | 99% | >95% | <85% |
| Database Size | 9.5GB | >12GB | <5GB |
| Docker Usage | 5.2GB | >10GB | <3GB |
| Available Space | 446MB | <500MB | >3GB |

---

## 🔍 DIAGNOSTIC COMMANDS

### Database Analysis
```bash
# Table sizes
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"

# Chunk analysis
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
SELECT hypertable_name, COUNT(*) as chunks, pg_size_pretty(SUM(pg_total_relation_size(chunk_schema||'.'||chunk_name))) as total_size
FROM timescaledb_information.chunks GROUP BY hypertable_name;"

# Data age
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
SELECT 'book_ticker_snapshots' as table, MIN(timestamp) as oldest, MAX(timestamp) as newest, COUNT(*) as rows FROM book_ticker_snapshots;"
```

### Docker Analysis
```bash
# Container sizes
docker ps --size

# Image sizes
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# Volume sizes
docker volume ls -q | xargs -I {} docker run --rm -v {}:/data alpine sh -c "echo {}; du -sh /data"

# Overlay2 size
du -sh /var/lib/docker/overlay2/
```

---

## ⚡ SPACE RECOVERY ESTIMATES

### Emergency Cleanup (Conservative)
```
Database: 9.5GB → 7GB (-2.5GB)
Docker: 5.2GB → 3GB (-2.2GB)
Total Freed: ~4.7GB
Result: 99% → 85% disk usage
```

### Nuclear Reset (Aggressive)
```
Database: 9.5GB → 1.5GB (-8GB)
Docker: 5.2GB → 1.5GB (-3.7GB)
Total Freed: ~11.7GB
Result: 99% → 55% disk usage
```

---

## 🛠️ RECOVERY PROCEDURES

### If Database Becomes Inaccessible
```bash
docker restart arbitrage_db
docker logs arbitrage_db --tail 50
# If still failing:
docker-compose down database
docker volume rm arbitrage_postgres_data
docker-compose up -d database
```

### If Data Collection Stops
```bash
docker restart arbitrage_collector
docker logs arbitrage_collector --tail 50
# Check config and restart if needed:
docker-compose restart
```

### If System Becomes Unresponsive
```bash
# Force stop all containers
docker kill $(docker ps -q)
# Clean everything
docker system prune -a -f --volumes
# Restart essential services
cd /opt/arbitrage && docker-compose up -d database
```

---

## 📞 SUCCESS VERIFICATION

After each cleanup step, verify:
```bash
echo "=== SPACE CHECK ==="
df -h | grep -E "(Filesystem|/dev|/$)"
echo ""
echo "=== DATABASE SIZE ==="
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));" 2>/dev/null || echo "Database not accessible"
echo ""
echo "=== DOCKER USAGE ==="
docker system df 2>/dev/null || echo "Docker not accessible"
echo ""
echo "=== SERVICES STATUS ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```

**Target Results:**
- Disk usage: <90% (ideally <85%)
- Database size: <8GB (ideally <5GB)
- Docker usage: <5GB (ideally <3GB)
- All essential containers running

---

## 🚨 IMMEDIATE ACTION DECISION TREE

```
Current Disk Usage: 99%
├── >98% → NUCLEAR RESET (immediate)
├── 95-98% → EMERGENCY CLEANUP
├── 90-95% → STANDARD CLEANUP
└── <90% → MONITORING ONLY

Database Size: 9.5GB
├── >12GB → EMERGENCY RETENTION (6h)
├── 8-12GB → AGGRESSIVE RETENTION (24h)
├── 5-8GB → NORMAL RETENTION (3d)
└── <5GB → STANDARD RETENTION (7d)
```

---

## 📋 COPY-PASTE EMERGENCY SEQUENCE

**Execute in order, check disk space after each step:**

```bash
# Step 1: Immediate Docker cleanup
docker container prune -f && docker image prune -a -f && docker volume prune -f

# Step 2: Emergency DB retention
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT remove_retention_policy('book_ticker_snapshots', true); SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '6 hours'); SELECT run_job(job_id) FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention';"

# Step 3: Check results
df -h && docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));"

# Step 4: If still critical, nuclear option
# docker stop $(docker ps -q) && docker system prune -a -f --volumes
```

**Expected time to recovery: 15-30 minutes**