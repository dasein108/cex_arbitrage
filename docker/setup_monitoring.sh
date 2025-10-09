#!/bin/bash

# =============================================================================
# Setup Database Monitoring and Automated Cleanup
# =============================================================================
# Sets up cron jobs and configures automated database space management

set -e

echo "🔧 Setting up database monitoring and automated cleanup..."

# Copy monitoring script to server
chmod +x database_monitoring.sh
cp database_monitoring.sh /opt/arbitrage/docker/
chmod +x /opt/arbitrage/docker/database_monitoring.sh

# Setup cron job for monitoring (every 30 minutes)
echo "Setting up cron job for database monitoring..."
CRON_JOB="*/30 * * * * /opt/arbitrage/docker/database_monitoring.sh >/dev/null 2>&1"

# Remove existing job if present
crontab -l 2>/dev/null | grep -v "/opt/arbitrage/docker/database_monitoring.sh" | crontab - || true

# Add new job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

# Setup daily retention cleanup (2 AM daily)
RETENTION_JOB="0 2 * * * cd /opt/arbitrage/docker && docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data < automated_retention.sql >/dev/null 2>&1"

# Remove existing retention job if present
crontab -l 2>/dev/null | grep -v "automated_retention.sql" | crontab - || true

# Add retention job
(crontab -l 2>/dev/null; echo "$RETENTION_JOB") | crontab -

echo "✅ Cron jobs configured:"
echo "   - Database monitoring: Every 30 minutes"
echo "   - Data retention: Daily at 2 AM"

# Create log file
touch /var/log/database_monitoring.log
chmod 644 /var/log/database_monitoring.log

# Show current cron jobs
echo ""
echo "📋 Active cron jobs:"
crontab -l

# Test monitoring script
echo ""
echo "🧪 Testing monitoring script..."
/opt/arbitrage/docker/database_monitoring.sh

echo ""
echo "✅ Database monitoring setup completed!"
echo ""
echo "📊 Monitoring will:"
echo "   - Check disk usage every 30 minutes"
echo "   - Alert at 90% disk usage"
echo "   - Emergency cleanup at 95% disk usage"
echo "   - Keep 6 hours of data during emergencies"
echo "   - Keep 24 hours of data during regular cleanup"
echo "   - Automatically stop/start data collection as needed"
echo ""
echo "📝 Logs available at: /var/log/database_monitoring.log"