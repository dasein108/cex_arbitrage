# PostgreSQL Space Crisis Resolution Plan
## CEX Arbitrage Production Server Emergency Response

**Server:** `ssh -i ~/.ssh/deploy_ci root@31.192.233.13`  
**Current Status:** 9.5GB database on 25GB disk (99% usage, 446MB free)  
**Target:** <5GB sustainable operation

---

## 🚨 IMMEDIATE EXECUTION STEPS

### Phase 1: Critical Analysis (15 minutes)

**Step 1.1: Connect to Production Server**
```bash
ssh -i ~/.ssh/deploy_ci root@31.192.233.13
cd /opt/arbitrage
```

**Step 1.2: Run Space Analysis**
```bash
# Copy analysis script to server
scp -i ~/.ssh/deploy_ci scripts/analyze_db_space.sql root@31.192.233.13:/tmp/

# Connect to database and run analysis
docker exec -i arbitrage_db psql -U arbitrage_user -d arbitrage_data < /tmp/analyze_db_space.sql > /tmp/space_analysis.txt

# Copy results back for review
scp -i ~/.ssh/deploy_ci root@31.192.233.13:/tmp/space_analysis.txt ./space_analysis_$(date +%Y%m%d_%H%M%S).txt
```

**Step 1.3: Docker Storage Analysis**
```bash
# Copy Docker analysis script
scp -i ~/.ssh/deploy_ci scripts/docker_space_analysis.sh root@31.192.233.13:/tmp/
chmod +x /tmp/docker_space_analysis.sh

# Run Docker analysis
/tmp/docker_space_analysis.sh > /tmp/docker_analysis.txt

# Copy results back
scp -i ~/.ssh/deploy_ci root@31.192.233.13:/tmp/docker_analysis.txt ./docker_analysis_$(date +%Y%m%d_%H%M%S).txt
```

### Phase 2: Emergency Cleanup (30 minutes)

**Step 2.1: Immediate Space Recovery**
```bash
# Copy comprehensive cleanup script
scp -i ~/.ssh/deploy_ci scripts/comprehensive_cleanup.sh root@31.192.233.13:/tmp/
chmod +x /tmp/comprehensive_cleanup.sh

# Run emergency cleanup (will prompt for confirmation)
/tmp/comprehensive_cleanup.sh emergency
```

**Expected Result:** 2-4GB space recovery (database: 9.5GB → 6-7GB)

**Step 2.2: Docker Emergency Cleanup**
```bash
# Stop non-essential containers
docker stop $(docker ps --format "{{.Names}}" | grep -v "arbitrage_db")

# Aggressive Docker cleanup
docker system prune -a -f --volumes

# Clean overlay2 storage (if needed)
cd /var/lib/docker
du -sh overlay2/
# If overlay2 is >3GB, proceed with selective cleanup
find overlay2/ -name "diff" -type d -empty -delete
```

**Expected Result:** 2-5GB Docker space recovery

### Phase 3: Database Optimization (45 minutes)

**Step 3.1: Deploy Optimized Schema**
```bash
# Copy optimized schema
scp -i ~/.ssh/deploy_ci scripts/optimized_schema.sql root@31.192.233.13:/tmp/

# Create backup before optimization
docker exec arbitrage_db pg_dump -U arbitrage_user arbitrage_data > /tmp/backup_pre_optimization.sql

# Apply optimized schema (creates new optimized tables)
docker exec -i arbitrage_db psql -U arbitrage_user -d arbitrage_data < /tmp/optimized_schema.sql
```

**Step 3.2: Data Migration (Choose One Option)**

**Option A: Selective Migration (Preserves 24h data)**
```sql
-- Connect to database
docker exec -it arbitrage_db psql -U arbitrage_user -d arbitrage_data

-- Migrate last 24 hours of critical data
INSERT INTO book_ticker_snapshots_optimized (
    timestamp, exchange_id, symbol_id, bid_price, bid_qty, ask_price, ask_qty, sequence_number
)
SELECT 
    timestamp,
    get_exchange_id(exchange),
    get_symbol_id(symbol_base, symbol_quote),
    bid_price,
    bid_qty,
    ask_price,
    ask_qty,
    sequence_number::INTEGER
FROM book_ticker_snapshots
WHERE timestamp > NOW() - INTERVAL '24 hours';

-- Drop old tables after verification
DROP TABLE book_ticker_snapshots CASCADE;
DROP TABLE orderbook_depth CASCADE;
DROP TABLE trades CASCADE;

-- Vacuum to reclaim space
VACUUM FULL;
```

**Option B: Nuclear Reset (Maximum space recovery)**
```bash
# Complete database reset with optimized schema
/tmp/comprehensive_cleanup.sh nuclear
```

**Expected Result:** Database size reduction to 2-4GB

### Phase 4: Automated Maintenance Setup (15 minutes)

**Step 4.1: Deploy Maintenance Scripts**
```bash
# Copy all maintenance scripts
scp -i ~/.ssh/deploy_ci scripts/automated_maintenance.sh root@31.192.233.13:/opt/arbitrage/
scp -i ~/.ssh/deploy_ci scripts/maintenance_config.conf root@31.192.233.13:/opt/arbitrage/
scp -i ~/.ssh/deploy_ci scripts/space_monitor.sh root@31.192.233.13:/opt/arbitrage/
scp -i ~/.ssh/deploy_ci scripts/monitor_config.conf root@31.192.233.13:/opt/arbitrage/

chmod +x /opt/arbitrage/*.sh
```

**Step 4.2: Install Cron Jobs**
```bash
# Install automated maintenance (every 15 minutes)
/opt/arbitrage/automated_maintenance.sh install-cron "*/15 * * * *"

# Install space monitoring (every 5 minutes)
(crontab -l; echo "*/5 * * * * /opt/arbitrage/space_monitor.sh check") | crontab -

# Verify cron installation
crontab -l
```

**Step 4.3: Start Monitoring**
```bash
# Start continuous monitoring in background
nohup /opt/arbitrage/space_monitor.sh monitor > /var/log/space_monitor.log 2>&1 &

# Check monitoring status
/opt/arbitrage/space_monitor.sh status
```

---

## 📊 VERIFICATION & VALIDATION

### Post-Cleanup Verification Checklist

**Step V.1: Space Verification**
```bash
# Check disk usage
df -h

# Check database size
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
SELECT 
    pg_database.datname,
    pg_size_pretty(pg_database_size(pg_database.datname)) as size
FROM pg_database 
WHERE datname = 'arbitrage_data';"

# Check Docker usage
docker system df
```

**Step V.2: Functionality Verification**
```bash
# Restart data collector
cd /opt/arbitrage
docker-compose up -d data_collector

# Check container health
docker ps
docker logs arbitrage_collector --tail 50

# Verify data collection
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
SELECT COUNT(*), MAX(timestamp) 
FROM book_ticker_snapshots_optimized 
WHERE timestamp > NOW() - INTERVAL '1 hour';"
```

**Step V.3: Performance Verification**
```bash
# Check system performance
top -n 1
iostat -x 1 3

# Monitor for 10 minutes
/opt/arbitrage/space_monitor.sh dashboard
```

---

## 🎯 SUCCESS CRITERIA

| Metric | Current | Target | Critical |
|--------|---------|--------|----------|
| **Disk Usage** | 99% | <85% | <90% |
| **Database Size** | 9.5GB | <5GB | <8GB |
| **Docker Size** | 5.2GB | <3GB | <5GB |
| **Available Space** | 446MB | >3GB | >1GB |

### Expected Improvements

**Conservative Scenario (Emergency Cleanup Only):**
- Database: 9.5GB → 7GB (-26%)
- Docker: 5.2GB → 3GB (-42%)
- Total Freed: ~4.7GB
- **Final Disk Usage: ~85%**

**Aggressive Scenario (With Optimization):**
- Database: 9.5GB → 3GB (-68%)
- Docker: 5.2GB → 2GB (-62%)
- Total Freed: ~9.7GB
- **Final Disk Usage: ~65%**

**Nuclear Scenario (Complete Reset):**
- Database: 9.5GB → 1.5GB (-84%)
- Docker: 5.2GB → 1.5GB (-71%)
- Total Freed: ~11.7GB
- **Final Disk Usage: ~55%**

---

## 🔄 ONGOING MAINTENANCE

### Daily Automated Tasks
- **Every 5 minutes:** Space monitoring and health checks
- **Every 15 minutes:** Automated maintenance if thresholds exceeded
- **Every hour:** Database compression of old chunks
- **Every 6 hours:** Aggressive retention policy enforcement
- **Daily:** Metrics cleanup and reporting

### Weekly Manual Tasks
- Review space trends and adjust thresholds
- Analyze database growth patterns
- Optimize chunk intervals if needed
- Update retention policies based on usage

### Emergency Procedures
- **Disk >95%:** Automatic emergency cleanup triggered
- **Database >12GB:** Emergency retention (6-hour data only)
- **System unresponsive:** Nuclear reset procedure

---

## 📁 SCRIPT LOCATIONS

All scripts are available in the `/scripts/` directory:

| Script | Purpose | Usage |
|--------|---------|-------|
| `analyze_db_space.sql` | Database space analysis | `psql < analyze_db_space.sql` |
| `docker_space_analysis.sh` | Docker storage analysis | `./docker_space_analysis.sh` |
| `optimized_schema.sql` | Space-optimized database schema | `psql < optimized_schema.sql` |
| `automated_maintenance.sh` | Automated cleanup and maintenance | `./automated_maintenance.sh check` |
| `comprehensive_cleanup.sh` | Emergency cleanup procedures | `./comprehensive_cleanup.sh emergency` |
| `space_monitor.sh` | Real-time monitoring and alerting | `./space_monitor.sh monitor` |

---

## 🚨 ROLLBACK PROCEDURES

### If Optimization Fails
```bash
# Restore from backup
docker exec -i arbitrage_db psql -U arbitrage_user -d arbitrage_data < /tmp/backup_pre_optimization.sql

# Restart services
docker-compose restart
```

### If Nuclear Reset Needed
```bash
# Complete system reset
./comprehensive_cleanup.sh nuclear

# Restore from latest backup
./comprehensive_cleanup.sh restore /path/to/backup.sql.gz
```

### Emergency Contact Points
- **System becomes unresponsive:** Use nuclear reset
- **Data collection stops:** Restart containers and verify schema
- **Database corruption:** Restore from backup and replay recent data

---

## 📈 MONITORING DASHBOARD

Access real-time monitoring:
```bash
# Live dashboard
/opt/arbitrage/space_monitor.sh dashboard

# Generate report
/opt/arbitrage/space_monitor.sh report

# Check health
/opt/arbitrage/space_monitor.sh status
```

**Key Metrics to Monitor:**
- Disk usage trend (should remain <85%)
- Database growth rate (should be <100MB/day)
- Docker storage accumulation
- Data collection performance
- System response times

---

**📞 EXECUTION CHECKLIST**

- [ ] Phase 1: Analysis completed (space_analysis.txt, docker_analysis.txt)
- [ ] Phase 2: Emergency cleanup completed (>2GB freed)
- [ ] Phase 3: Database optimization completed (database <5GB)
- [ ] Phase 4: Monitoring setup completed (cron jobs active)
- [ ] Verification: All success criteria met
- [ ] Documentation: Results recorded and procedures tested

**Estimated Total Time:** 2-3 hours  
**Risk Level:** Medium (with backups and rollback procedures)  
**Success Probability:** 95% for reaching targets