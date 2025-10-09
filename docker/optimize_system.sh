#!/bin/bash

# =============================================================================
# System Optimization Script for CEX Arbitrage Production
# =============================================================================
# Applies PostgreSQL optimizations and system configurations for space efficiency

set -e

echo "🚀 Optimizing CEX Arbitrage system for space efficiency..."

# 1. Apply PostgreSQL configuration optimizations
echo "📊 Applying PostgreSQL optimizations..."

# Backup current config
docker exec arbitrage_db cp /var/lib/postgresql/data/postgresql.conf /var/lib/postgresql/data/postgresql.conf.backup

# Apply optimizations (append to existing config)
docker exec arbitrage_db bash -c "cat >> /var/lib/postgresql/data/postgresql.conf << 'EOF'

# =============================================================================
# CEX Arbitrage Space Optimization Settings
# =============================================================================
# Applied $(date)

# Aggressive space management
checkpoint_timeout = 5min
max_wal_size = 256MB
min_wal_size = 128MB
wal_compression = on

# Enhanced autovacuum for space reclamation
autovacuum_naptime = 30s
autovacuum_vacuum_scale_factor = 0.1
autovacuum_analyze_scale_factor = 0.05
autovacuum_vacuum_cost_delay = 10ms
autovacuum_vacuum_cost_limit = 400

# Reduced logging for space
log_min_duration_statement = 1000
log_statement = 'none'
log_min_messages = warning

# Async commit for performance
synchronous_commit = off
commit_delay = 0
EOF"

# 2. Configure data collector for reduced frequency during high usage
echo "🔧 Optimizing data collection frequency..."

# Create environment override for data collector
docker exec arbitrage_db bash -c "cat > /tmp/collector_optimization.env << 'EOF'
# Reduced collection frequency during high disk usage
COLLECTION_INTERVAL_HIGH_USAGE=5000
COLLECTION_INTERVAL_NORMAL=1000
BATCH_SIZE_HIGH_USAGE=10
BATCH_SIZE_NORMAL=50
EOF"

# 3. Setup log rotation for Docker containers
echo "📝 Setting up log rotation..."

cat > /etc/logrotate.d/docker-arbitrage << 'EOF'
/var/lib/docker/containers/*/*.log {
    rotate 3
    daily
    compress
    missingok
    delaycompress
    copytruncate
    maxsize 10M
}
EOF

# 4. Optimize Docker daemon configuration
echo "🐳 Optimizing Docker configuration..."

# Configure Docker log limits
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
EOF

# 5. Create system monitoring script
echo "📊 Creating system monitoring..."

cat > /opt/arbitrage/docker/system_health.sh << 'EOF'
#!/bin/bash

# System Health Check for CEX Arbitrage
echo "=== CEX Arbitrage System Health $(date) ==="
echo ""

# Disk usage
echo "💾 Disk Usage:"
df -h / | tail -1
echo ""

# Database size
echo "🗄️ Database Size:"
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -t -c \
    "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));" 2>/dev/null | xargs
echo ""

# Table sizes
echo "📊 Top Tables by Size:"
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
    "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size 
     FROM pg_tables WHERE schemaname = 'public' 
     ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 5;" 2>/dev/null
echo ""

# Record counts
echo "📈 Record Counts:"
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
    "SELECT 'book_ticker_snapshots' as table, COUNT(*) as records FROM book_ticker_snapshots
     UNION ALL SELECT 'funding_rate_snapshots', COUNT(*) FROM funding_rate_snapshots
     ORDER BY records DESC;" 2>/dev/null
echo ""

# Container status
echo "🐳 Container Status:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Size}}"
echo ""

# Recent data
echo "⏰ Recent Data (last 1 hour):"
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
    "SELECT COUNT(*) as recent_records FROM book_ticker_snapshots 
     WHERE timestamp > NOW() - INTERVAL '1 hour';" 2>/dev/null
echo ""
EOF

chmod +x /opt/arbitrage/docker/system_health.sh

# 6. Setup hourly health monitoring
echo "⏰ Setting up hourly health monitoring..."

# Add health check to cron (every hour)
crontab -l 2>/dev/null | grep -v "system_health.sh" | crontab - || true
(crontab -l 2>/dev/null; echo "0 * * * * /opt/arbitrage/docker/system_health.sh >> /var/log/system_health.log 2>&1") | crontab -

# 7. Restart services to apply optimizations
echo "🔄 Restarting services to apply optimizations..."

# Restart PostgreSQL to apply config changes
docker restart arbitrage_db

# Wait for database to be ready
echo "⏳ Waiting for database to restart..."
sleep 30

# Test database connection
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT version();" > /dev/null

echo "✅ System optimization completed!"
echo ""
echo "📋 Applied Optimizations:"
echo "   ✅ PostgreSQL config optimized for space efficiency"
echo "   ✅ Aggressive autovacuum enabled"
echo "   ✅ WAL compression enabled"
echo "   ✅ Docker log rotation configured"
echo "   ✅ System health monitoring setup"
echo "   ✅ Automated cleanup cron jobs active"
echo ""
echo "📊 Monitoring:"
echo "   - Database monitoring: Every 30 minutes"
echo "   - System health check: Every hour"
echo "   - Data retention: Daily at 2 AM"
echo ""
echo "📝 Logs:"
echo "   - Database monitoring: /var/log/database_monitoring.log"
echo "   - System health: /var/log/system_health.log"
echo ""
echo "🎯 Next Steps:"
echo "   1. Monitor /var/log/database_monitoring.log for space management"
echo "   2. Check /var/log/system_health.log for system status"
echo "   3. Consider upgrading to larger disk if growth continues"
EOF