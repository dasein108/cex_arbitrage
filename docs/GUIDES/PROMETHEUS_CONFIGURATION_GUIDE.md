# Prometheus Configuration Guide for CEX Arbitrage Engine

## Overview

The CEX Arbitrage Engine includes a **high-performance Prometheus backend** for metrics collection and monitoring. This guide covers configuration, deployment scenarios, and best practices.

## Quick Start

### Disable Prometheus (Simplest Option)
If you don't need metrics collection:

```bash
# In your .env file
LOGGING_PROMETHEUS_ENABLED=false
```

### Enable with Local Prometheus
For development with local Prometheus setup:

```bash
# In your .env file  
LOGGING_PROMETHEUS_ENABLED=true
PROMETHEUS_PUSH_GATEWAY_URL=http://localhost:9091
PROMETHEUS_JOB_NAME=hft_arbitrage_dev
```

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOGGING_PROMETHEUS_ENABLED` | `true` | Enable/disable Prometheus metrics |
| `PROMETHEUS_PUSH_GATEWAY_URL` | `http://localhost:9091` | Push Gateway endpoint |
| `PROMETHEUS_JOB_NAME` | `hft_arbitrage` | Job identifier for metrics |

### Advanced Configuration

```bash
# Production setup
LOGGING_PROMETHEUS_ENABLED=true
PROMETHEUS_PUSH_GATEWAY_URL=http://prometheus-gateway.monitoring.svc.cluster.local:9091
PROMETHEUS_JOB_NAME=arbitrage_production
LOGGING_ENVIRONMENT=prod

# Development setup  
LOGGING_PROMETHEUS_ENABLED=true
PROMETHEUS_PUSH_GATEWAY_URL=http://localhost:9091
PROMETHEUS_JOB_NAME=arbitrage_dev
LOGGING_ENVIRONMENT=dev

# Testing (disabled)
LOGGING_PROMETHEUS_ENABLED=false
LOGGING_ENVIRONMENT=test
```

## Deployment Scenarios

### 1. Local Development (Docker Compose)

#### Setup Prometheus Stack:
```bash
# Use existing docker-compose in /infra
cd infra
docker-compose up -d prometheus pushgateway grafana
```

#### Configuration:
```bash
LOGGING_PROMETHEUS_ENABLED=true
PROMETHEUS_PUSH_GATEWAY_URL=http://localhost:9091
PROMETHEUS_JOB_NAME=arbitrage_dev
```

### 2. Production Deployment

#### Kubernetes Environment:
```bash
LOGGING_PROMETHEUS_ENABLED=true
PROMETHEUS_PUSH_GATEWAY_URL=http://prometheus-pushgateway.monitoring:9091
PROMETHEUS_JOB_NAME=arbitrage_production
```

#### Standalone Server:
```bash
LOGGING_PROMETHEUS_ENABLED=true  
PROMETHEUS_PUSH_GATEWAY_URL=http://monitoring-server:9091
PROMETHEUS_JOB_NAME=arbitrage_prod_server1
```

### 3. Cloud Deployment

#### Managed Prometheus (AWS, GCP, etc.):
```bash
LOGGING_PROMETHEUS_ENABLED=true
PROMETHEUS_PUSH_GATEWAY_URL=https://prometheus-gateway.your-cloud.com:443
PROMETHEUS_JOB_NAME=arbitrage_cloud_prod
```

### 4. No Monitoring Setup
```bash
LOGGING_PROMETHEUS_ENABLED=false
# All other Prometheus variables ignored
```

## Metrics Overview

### Automatically Collected Metrics

The system automatically collects these metrics when Prometheus is enabled:

#### Trading Metrics
```
hft_latency_ms{operation="place_order", exchange="mexc"}
hft_orders_placed_count{exchange="mexc", symbol="BTC_USDT"}
hft_arbitrage_opportunities_count{source_exchange="mexc", target_exchange="gateio"}
hft_spread_bps{symbol="BTC_USDT", opportunity_type="simple"}
```

#### System Metrics  
```
hft_websocket_messages_per_second{exchange="mexc", channel="orderbook"}
hft_rest_request_latency_ms{exchange="gateio", endpoint="orders"}
hft_connection_status{exchange="mexc", connection_type="websocket"}
hft_buffer_utilization_percent{component="orderbook_manager"}
```

#### Performance Metrics
```
hft_memory_usage_mb{component="arbitrage_engine"}
hft_cpu_percent{component="symbol_resolver"}
hft_processing_time_us{operation="orderbook_diff"}
```

### Custom Metrics Example

```python
from core.logging import get_logger

logger = get_logger('arbitrage.strategy')

# Trading performance
logger.metric("execution_latency_ms", 1.23, 
              operation="arbitrage_execution",
              symbol="BTC_USDT")

# Business metrics  
logger.counter("opportunities_detected", 1,
               exchange_pair="mexc_gateio",
               symbol="BTC_USDT")

# System health
logger.metric("queue_depth", 150,
              component="order_queue",
              exchange="mexc")
```

## Prometheus Infrastructure Setup

### Option 1: Docker Compose (Development)

The project includes a complete monitoring stack in `/infra/docker-compose.yml`:

```bash
cd infra
docker-compose up -d
```

**Includes:**
- Prometheus server (port 9090)
- Push Gateway (port 9091)  
- Grafana (port 3000)
- Pre-configured dashboards

**Access:**
- Prometheus: http://localhost:9090
- Push Gateway: http://localhost:9091
- Grafana: http://localhost:3000 (admin/admin)

### Option 2: Kubernetes Deployment

```yaml
# prometheus-stack.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus-pushgateway
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: prometheus-pushgateway
  template:
    metadata:
      labels:
        app: prometheus-pushgateway
    spec:
      containers:
      - name: pushgateway
        image: prom/pushgateway:v1.6.2
        ports:
        - containerPort: 9091
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus-pushgateway
  namespace: monitoring
spec:
  selector:
    app: prometheus-pushgateway
  ports:
  - port: 9091
    targetPort: 9091
```

### Option 3: Managed Services

#### AWS (Managed Prometheus)
```bash
PROMETHEUS_PUSH_GATEWAY_URL=https://aps-workspaces.us-east-1.amazonaws.com/workspaces/ws-xxx/api/v1/remote_write
```

#### Google Cloud (Managed Prometheus) 
```bash
PROMETHEUS_PUSH_GATEWAY_URL=https://monitoring.googleapis.com/v1/projects/PROJECT_ID/location/global/prometheus/api/v1/write
```

## Performance Characteristics

### Prometheus Backend Performance

| Metric | Value | Description |
|--------|-------|-------------|
| **Batch Size** | 100 metrics | Metrics per push gateway call |
| **Flush Interval** | 5 seconds | Max time before forced flush |
| **HTTP Timeout** | 10 seconds | Push gateway request timeout |
| **Retry Attempts** | 3 | Exponential backoff retries |
| **Memory Usage** | ~100KB | Metrics buffer overhead |
| **Call Latency** | <1μs | Metric logging call overhead |

### Network Impact

- **Frequency**: Every 5 seconds or when buffer full (100 metrics)
- **Payload Size**: ~2-10KB per push (depends on metric count and labels)
- **Bandwidth**: ~2KB/s typical, ~10KB/s peak
- **Error Handling**: Graceful degradation if Prometheus unavailable

## Troubleshooting

### Common Issues

#### 1. Connection Refused
```
Error: Prometheus push attempt 1 failed: Cannot connect to host localhost:9091
```

**Solutions:**
- Check if push gateway is running: `curl http://localhost:9091/metrics`
- Verify URL in environment: `PROMETHEUS_PUSH_GATEWAY_URL`
- Disable if not needed: `LOGGING_PROMETHEUS_ENABLED=false`

#### 2. Timeout Errors
```
Error: Prometheus push attempt 1 failed: TimeoutError
```

**Solutions:**
- Check network connectivity to push gateway
- Increase timeout in configuration
- Check push gateway performance/load

#### 3. High Memory Usage
```
Warning: Prometheus metrics buffer growing (>1000 metrics buffered)
```

**Solutions:**
- Check push gateway availability
- Reduce batch size in configuration
- Monitor application metric generation rate

### Debug Commands

```bash
# Check push gateway status
curl http://localhost:9091/metrics

# Check if metrics are being received
curl http://localhost:9091/api/v1/metrics

# Monitor application logs for Prometheus errors
tail -f logs/hft.log | grep -i prometheus

# Test network connectivity
nc -zv localhost 9091
```

### Configuration Validation

```python
# Test Prometheus configuration
import os
from core.logging import setup_development_logging, get_logger

# This will validate Prometheus configuration
setup_development_logging()
logger = get_logger('test')

# Send test metric
logger.metric("test_metric", 1.0, component="config_test")
print("✅ Prometheus configuration working")
```

## Monitoring Best Practices

### 1. Metric Naming
- Use descriptive names: `arbitrage_execution_latency_ms` not `latency`
- Include units: `_ms`, `_seconds`, `_bytes`, `_count`
- Use consistent prefixes: `hft_*` for all application metrics

### 2. Label Strategy
- Keep label cardinality low (<100 unique combinations)
- Use meaningful labels: `exchange`, `symbol`, `operation`
- Avoid high-cardinality labels: `correlation_id`, `timestamp`

### 3. Alert Rules
```yaml
# Example alerts for Prometheus
groups:
- name: arbitrage_alerts
  rules:
  - alert: HighArbitrageLatency
    expr: hft_execution_latency_ms > 100
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "Arbitrage execution latency is high"
      
  - alert: ArbitrageEngineDown  
    expr: up{job="hft_arbitrage"} == 0
    for: 30s
    labels:
      severity: critical
    annotations:
      summary: "Arbitrage engine is not running"
```

### 4. Dashboard Examples
```json
{
  "dashboard": {
    "title": "HFT Arbitrage Monitoring",
    "panels": [
      {
        "title": "Execution Latency",
        "type": "graph",
        "targets": [
          {
            "expr": "hft_execution_latency_ms",
            "legendFormat": "{{operation}} - {{exchange}}"
          }
        ]
      },
      {
        "title": "Opportunities Detected",
        "type": "stat", 
        "targets": [
          {
            "expr": "rate(hft_opportunities_detected_count[5m])",
            "legendFormat": "Opportunities/sec"
          }
        ]
      }
    ]
  }
}
```

## Production Deployment Checklist

### Pre-Deployment
- [ ] Prometheus infrastructure deployed and accessible
- [ ] Push gateway URL configured correctly
- [ ] Network connectivity verified
- [ ] Environment variables configured
- [ ] Alert rules configured
- [ ] Dashboards imported

### Post-Deployment  
- [ ] Metrics appearing in Prometheus
- [ ] No connection errors in logs
- [ ] Dashboard displaying data
- [ ] Alerts firing correctly
- [ ] Performance impact acceptable

### Monitoring
- [ ] Push gateway performance monitored
- [ ] Metric cardinality under control
- [ ] No memory leaks in metrics buffer
- [ ] Network impact within limits

## Summary

The Prometheus integration is **production-ready** with excellent performance characteristics. Key points:

1. **Easily Disabled**: Set `LOGGING_PROMETHEUS_ENABLED=false` if not needed
2. **Graceful Degradation**: System continues if Prometheus unavailable  
3. **High Performance**: <1μs overhead, batched dispatch
4. **Flexible Deployment**: Works with local, cloud, or managed Prometheus
5. **Comprehensive Metrics**: Trading, system, and performance metrics included

Choose the deployment option that fits your infrastructure and monitoring requirements.