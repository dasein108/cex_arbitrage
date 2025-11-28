# Emergency Log Rotation Fix - Production Deployment Instructions

## Overview

This document provides step-by-step instructions for deploying the emergency log rotation fix to resolve the hanging `docker logs arbitrage_collector -n 1` issue on the production HFT trading system.

**Problem**: Large log files (>500MB) causing Docker log commands to hang and timeout
**Solution**: Deploy log rotation configuration and perform emergency log cleanup
**Impact**: Zero-downtime deployment with immediate log command responsiveness

## Prerequisites

- SSH access to the production server (acidpictures1)
- Current working directory: `/opt/arbitrage/docker/`
- Docker and docker-compose installed and running
- Container `arbitrage_collector` currently running

## Deployment Steps

### Step 1: Deploy Log Rotation Configuration

Execute the deployment script to apply log rotation settings:

```bash
cd /opt/arbitrage/docker
./scripts/deploy_log_rotation.sh
```

**What this does:**
- Verifies current system state and configuration
- Creates backup of current container state
- Gracefully restarts the data_collector service with new log rotation settings
- Waits for container health confirmation
- Tests log command responsiveness
- Verifies active log rotation configuration

**Expected output:**
```
[2025-11-23 XX:XX:XX] === LOG ROTATION DEPLOYMENT FOR HFT PRODUCTION SYSTEM ===
[SUCCESS] Pre-deployment checks passed
[SUCCESS] Backup created in: backups/deployment_YYYYMMDD_HHMMSS
[SUCCESS] Log rotation configuration verified
[SUCCESS] Service redeployment completed
[SUCCESS] Container is running
[SUCCESS] Log responsiveness verification completed
[SUCCESS] ✓ JSON file log driver is active
[SUCCESS] ✓ Log size rotation is configured
[SUCCESS] ✓ Log file rotation is configured
[SUCCESS] Deployment completed successfully!
```

### Step 2: Execute Emergency Log Cleanup

If log files are still large after deployment, run the emergency cleanup:

```bash
cd /opt/arbitrage/docker
./scripts/emergency_log_cleanup.sh
```

**What this does:**
- Safely truncates large log files while preserving recent entries
- Creates backup of recent log entries for debugging
- Preserves last 1000 lines of logs
- Forces Docker log rotation
- Verifies container health after cleanup

**Expected output:**
```
[2025-11-23 XX:XX:XX] === EMERGENCY LOG CLEANUP FOR HFT PRODUCTION SYSTEM ===
[SUCCESS] Production environment checks passed
[SUCCESS] Backup created: /opt/arbitrage/docker/logs/emergency_backup/...
[SUCCESS] Log cleanup completed:
[SUCCESS]   - Original size: XXXXmb
[SUCCESS]   - New size: XXmb
[SUCCESS]   - Lines preserved: 1000
[SUCCESS]   - Space saved: XXXXmb
[SUCCESS] Container health verification completed
```

### Step 3: Verify the Fix

Run comprehensive verification to ensure everything works:

```bash
cd /opt/arbitrage/docker
./scripts/verify_log_fix.sh
```

**What this tests:**
- Container status and health
- Log command responsiveness (10 iterations)
- Different log command variations
- Log rotation configuration verification
- Log file size and rotation status
- Application health and data collection
- Performance benchmark for HFT compliance

**Expected output:**
```
[SUCCESS] ✓ Container is running and healthy
[SUCCESS] ✓ Log commands are responsive
[SUCCESS] ✓ Log rotation configuration is active
[SUCCESS] ✓ Log file size is managed
[SUCCESS] ✓ Application is collecting data
[SUCCESS] ALL TESTS PASSED - LOG ROTATION FIX VERIFIED
```

### Step 4: Test Log Commands

Manually verify that the problematic command now works:

```bash
# This should respond immediately (previously hanging)
docker logs arbitrage_collector -n 1

# Test other variations
docker logs arbitrage_collector -n 5
docker logs arbitrage_collector -n 10
docker logs arbitrage_collector --tail 20
docker logs arbitrage_collector --since 1m
```

All commands should respond within 1 second.

## Log Rotation Configuration

The deployed configuration sets these limits:

- **Max log size per file**: 100MB
- **Max number of files**: 3 (current + 2 rotated)
- **Compression**: Enabled for rotated logs
- **Total max storage**: ~300MB

## Monitoring and Maintenance

### Monitor Log File Sizes

```bash
# Check current log file size
CONTAINER_ID=$(docker ps --filter "name=arbitrage_collector" --format "{{.ID}}")
LOG_PATH=$(docker inspect "$CONTAINER_ID" | jq -r '.[0].LogPath')
ls -lh "$LOG_PATH"

# Monitor in real-time
watch 'docker inspect arbitrage_collector | jq ".[0].LogPath" | xargs ls -lh'
```

### Check Log Rotation Status

```bash
# View active log configuration
docker inspect arbitrage_collector --format '{{json .HostConfig.LogConfig}}' | jq '.'

# Find rotated log files
find /var/lib/docker/containers/$(docker inspect arbitrage_collector --format '{{.Id}}')/  -name '*log*'
```

### Performance Monitoring

```bash
# Test log command performance
time docker logs arbitrage_collector -n 1

# Check container health
docker inspect arbitrage_collector --format '{{.State.Status}}'
docker inspect arbitrage_collector --format '{{.State.Health.Status}}'
```

## Troubleshooting

### If Log Commands Are Still Slow

1. **Check log file size**:
   ```bash
   CONTAINER_ID=$(docker ps --filter "name=arbitrage_collector" --format "{{.ID}}")
   LOG_PATH=$(docker inspect "$CONTAINER_ID" | jq -r '.[0].LogPath')
   du -h "$LOG_PATH"
   ```

2. **Manually trigger log rotation**:
   ```bash
   sudo kill -USR1 $(pgrep dockerd)
   ```

3. **Re-run emergency cleanup**:
   ```bash
   ./scripts/emergency_log_cleanup.sh
   ```

### If Container Health Issues Occur

1. **Check container status**:
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   docker logs arbitrage_collector --tail 50
   ```

2. **Restart if needed**:
   ```bash
   docker-compose -f docker-compose.prod.yml restart data_collector
   ```

3. **Check resource usage**:
   ```bash
   docker stats arbitrage_collector --no-stream
   ```

### If Deployment Fails

The deployment script includes automatic rollback functionality. If deployment fails:

1. **Check rollback status**:
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   ```

2. **Manual recovery**:
   ```bash
   docker-compose -f docker-compose.prod.yml stop data_collector
   docker-compose -f docker-compose.prod.yml up -d data_collector
   ```

3. **Restore from backup**:
   ```bash
   # Backups are created in: backups/deployment_YYYYMMDD_HHMMSS/
   ls -la backups/
   ```

## File Locations

- **Deployment script**: `/opt/arbitrage/docker/scripts/deploy_log_rotation.sh`
- **Emergency cleanup**: `/opt/arbitrage/docker/scripts/emergency_log_cleanup.sh`
- **Verification script**: `/opt/arbitrage/docker/scripts/verify_log_fix.sh`
- **Log rotation config**: `/opt/arbitrage/docker/docker-compose.prod.yml`
- **Backups directory**: `/opt/arbitrage/docker/backups/`
- **Emergency backups**: `/opt/arbitrage/docker/logs/emergency_backup/`

## Success Criteria

After deployment, these conditions should be met:

1. ✅ `docker logs arbitrage_collector -n 1` responds within 1 second
2. ✅ Container remains healthy and collecting data
3. ✅ Log files are managed under 100MB per file
4. ✅ Log rotation is actively configured
5. ✅ No errors in application logs
6. ✅ Trading data collection continues uninterrupted

## Contact Information

If issues persist after following these instructions:

1. **Check verification output**: Run `./scripts/verify_log_fix.sh` and share output
2. **Collect diagnostics**: Run `docker-compose -f docker-compose.prod.yml ps` and `docker logs arbitrage_collector --tail 20`
3. **Review backups**: Check `/opt/arbitrage/docker/backups/` for recent deployment backups

---

**Note**: This deployment is designed for zero-downtime operation and maintains HFT trading system requirements. All scripts include comprehensive error handling and rollback capabilities.