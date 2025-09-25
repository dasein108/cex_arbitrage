# AI-Agent Integration Testing Framework

Comprehensive integration testing suite designed for AI agents to automatically test exchange implementations. This framework provides structured JSON output, standardized error codes, and machine-readable test results suitable for automated analysis and validation.

## Overview

The AI-Agent Integration Testing Framework enables automated testing of exchange integrations across REST and WebSocket APIs. It follows the HFT system's clean architecture principles with SOLID compliance and provides structured output for AI agent consumption.

### Key Features

- **Machine-Readable Output**: Structured JSON results with standardized fields
- **Standardized Exit Codes**: Clear success/failure indicators for automation
- **Performance Metrics**: HFT-compliant performance monitoring and validation
- **Error Classification**: Standardized error codes and categorization
- **Timeout Management**: Configurable timeouts with proper error handling
- **SOLID Compliance**: Clean architecture following project standards

## Test Suite Components

### 1. Integration Test Framework (`integration_test_framework.py`)

Core framework providing structured testing infrastructure:

```python
from examples.integration_test_framework import (
    IntegrationTestRunner, TestCategory, TestStatus, TestMetrics
)
```

**Key Classes:**
- `IntegrationTestRunner`: Main test execution engine
- `TestResult`: Structured test result container
- `IntegrationTestReport`: Comprehensive test report generator
- `TestMetrics`: Performance metrics collection

### 2. REST API Integration Tests

#### REST Public API Test (`rest_public_integration_test.py`)

Tests public REST API functionality without authentication:

```bash
# Basic usage (defaults to mexc)
python src/examples/rest_public_integration_test.py
python src/examples/rest_public_integration_test.py mexc_spot
python src/examples/rest_public_integration_test.py gateio_spot

# With JSON output
python src/examples/rest_public_integration_test.py --output results.json
python src/examples/rest_public_integration_test.py mexc_spot --output results.json

# Custom timeout
python src/examples/rest_public_integration_test.py gateio_spot --timeout 60
```

**Tests Performed:**
- Exchange setup and configuration
- Ping connectivity test
- Server time synchronization
- Exchange info retrieval and validation
- Orderbook data structure and quality
- Recent trades data structure and quality

#### REST Private API Test (`rest_private_integration_test.py`)

Tests private REST API functionality with authentication:

```bash
# Requires API credentials
export MEXC_API_KEY="your_api_key"
export MEXC_SECRET_KEY="your_secret_key"

# Basic usage (defaults to mexc)
python src/examples/rest_private_integration_test.py
python src/examples/rest_private_integration_test.py mexc_spot
python src/examples/rest_private_integration_test.py gateio_spot --output private_results.json
```

**Tests Performed:**
- Authentication and credential validation
- Account balance retrieval
- Asset-specific balance queries
- Open orders listing
- Order status queries (expects failures for non-existent orders)
- Order placement simulation (designed to fail safely)
- Order cancellation simulation (expects failures)

### 3. WebSocket API Integration Tests

#### WebSocket Public API Test (`websocket_public_integration_test.py`)

Tests public WebSocket real-time data streaming:

```bash
# Basic usage (defaults to mexc)
python src/examples/websocket_public_integration_test.py
python src/examples/websocket_public_integration_test.py mexc_spot
python src/examples/websocket_public_integration_test.py gateio_spot

# Custom monitoring duration
python src/examples/websocket_public_integration_test.py --monitor-time 30
python src/examples/websocket_public_integration_test.py mexc_spot --monitor-time 30

# Full customization
python src/examples/websocket_public_integration_test.py gateio_futures --timeout 60 --monitor-time 20 --output ws_results.json
```

**Tests Performed:**
- WebSocket connection establishment
- Real-time data reception monitoring
- Orderbook data quality and structure validation
- Trade data quality and structure validation
- Performance metrics and connection stability

#### WebSocket Private API Test (`websocket_private_integration_test.py`)

Tests private WebSocket real-time account data streaming:

```bash
# Requires API credentials
export MEXC_API_KEY="your_api_key"
export MEXC_SECRET_KEY="your_secret_key"

# Basic usage (defaults to mexc)
python src/examples/websocket_private_integration_test.py
python src/examples/websocket_private_integration_test.py mexc_spot --monitor-time 30 --output private_ws_results.json
python src/examples/websocket_private_integration_test.py gateio_futures
```

**Tests Performed:**
- Authentication and private WebSocket connection
- Private data monitoring (balance, order, trade updates)
- Balance data quality and structure validation
- Order data quality and structure validation
- Connection stability and performance analysis

## Usage for AI Agents

### Command-Line Interface

All test scripts follow a consistent CLI pattern:

```bash
python src/examples/{test_script}.py <exchange> [options]

Options:
  --output, -o     Output JSON file path
  --timeout, -t    Test timeout in seconds (default: 30)
  --monitor-time, -m  Data monitoring duration for WebSocket tests (default: 15-20)
  --verbose, -v    Enable verbose output
```

### Exit Codes

Standardized exit codes for automation:

- `0`: All tests passed successfully
- `1`: Some tests failed but no critical errors
- `2`: Test errors occurred (connection, authentication, etc.)
- `3`: Test timeout
- `4`: Configuration error (missing credentials, unsupported exchange)

### JSON Output Format

All tests produce structured JSON output:

```json
{
  "exchange": "MEXC",
  "test_suite": "REST_PUBLIC_API",
  "overall_status": "PASSED",
  "total_tests": 6,
  "passed": 6,
  "failed": 0,
  "errors": 0,
  "duration_ms": 1234.56,
  "test_results": [
    {
      "test_name": "ping_test",
      "test_category": "REST_PUBLIC",
      "status": "PASSED",
      "exchange": "MEXC",
      "duration_ms": 123.45,
      "metrics": {
        "execution_time_ms": 123.45,
        "network_requests": 1,
        "data_points_received": 0,
        "error_count": 0
      },
      "details": {
        "ping_result": {},
        "latency_acceptable": true
      },
      "expected_behavior": "Ping returns successful response within acceptable latency",
      "actual_behavior": "Test completed successfully"
    }
  ],
  "summary_metrics": {
    "total_execution_time_ms": 1234.56,
    "total_network_requests": 12,
    "success_rate": 1.0
  },
  "system_info": {
    "test_framework": "AI-Agent Integration Test Framework v1.0",
    "architecture": "HFT Clean src-only Architecture"
  }
}
```

### AI-Agent Result Parsing

Each test outputs a condensed result block for easy parsing:

```
=== AI-AGENT-RESULT-START ===
{
  "exchange": "MEXC",
  "test_suite": "REST_PUBLIC_API",
  "status": "PASSED",
  "total_tests": 6,
  "passed": 6,
  "failed": 0,
  "errors": 0,
  "duration_ms": 1234.56,
  "success_rate": 1.0
}
=== AI-AGENT-RESULT-END ===
```

## Integration Test Scenarios

### New Exchange Integration Testing

To test a new exchange integration:

1. **Configuration Setup**
   ```bash
   # Add exchange configuration to config.yaml
   # Set environment variables for credentials
   ```

2. **Public API Testing**
   ```bash
   python src/examples/rest_public_integration_test.py new_exchange
   python src/examples/websocket_public_integration_test.py new_exchange
   ```

3. **Private API Testing** (with credentials)
   ```bash
   python src/examples/rest_private_integration_test.py new_exchange
   python src/examples/websocket_private_integration_test.py new_exchange
   ```

4. **Result Analysis**
   ```bash
   # Check exit codes and parse JSON output
   # Validate all tests pass or identify specific failures
   ```

### Continuous Integration Pipeline

Example CI pipeline integration:

```bash
#!/bin/bash
# CI Pipeline for Exchange Integration Testing

EXCHANGE="mexc"
RESULTS_DIR="test_results"
mkdir -p $RESULTS_DIR

# Run all test suites
python src/examples/rest_public_integration_test.py $EXCHANGE --output "$RESULTS_DIR/rest_public.json"
PUBLIC_REST_STATUS=$?

python src/examples/websocket_public_integration_test.py $EXCHANGE --output "$RESULTS_DIR/ws_public.json"
PUBLIC_WS_STATUS=$?

# Private tests only if credentials are available
if [[ -n "$MEXC_API_KEY" && -n "$MEXC_SECRET_KEY" ]]; then
    python src/examples/rest_private_integration_test.py $EXCHANGE --output "$RESULTS_DIR/rest_private.json"
    PRIVATE_REST_STATUS=$?
    
    python src/examples/websocket_private_integration_test.py $EXCHANGE --output "$RESULTS_DIR/ws_private.json"
    PRIVATE_WS_STATUS=$?
else
    echo "Skipping private API tests - credentials not available"
    PRIVATE_REST_STATUS=0
    PRIVATE_WS_STATUS=0
fi

# Aggregate results
if [[ $PUBLIC_REST_STATUS -eq 0 && $PUBLIC_WS_STATUS -eq 0 && $PRIVATE_REST_STATUS -eq 0 && $PRIVATE_WS_STATUS -eq 0 ]]; then
    echo "✅ All integration tests passed"
    exit 0
else
    echo "❌ Some integration tests failed"
    exit 1
fi
```

## Performance Validation

### HFT Compliance Metrics

The framework validates HFT performance requirements:

- **REST API Latency**: < 5 seconds for ping, < 50ms for optimal performance
- **WebSocket Connection**: < 15 seconds for establishment
- **Data Quality**: > 80% valid data structure compliance
- **Error Rate**: < 5% for public APIs, < 10% for private APIs
- **Connection Stability**: > 95% uptime during monitoring period

### Performance Metrics Collection

Each test collects detailed performance metrics:

```json
{
  "metrics": {
    "execution_time_ms": 123.45,
    "network_requests": 1,
    "data_points_received": 100,
    "error_count": 0,
    "latency_percentiles": {
      "p50": 45.2,
      "p95": 89.7,
      "p99": 156.3
    }
  }
}
```

## Error Handling and Diagnostics

### Error Classification

Standardized error codes for AI agent processing:

- `CONNECTION_ERROR`: Network connectivity issues
- `AUTHENTICATION_ERROR`: Invalid or missing credentials
- `TIMEOUT_ERROR`: Operation exceeded timeout limit
- `VALIDATION_ERROR`: Data validation failures
- `CONFIGURATION_ERROR`: Missing or invalid configuration
- `API_ERROR`: Exchange-specific API errors

### Diagnostic Information

Each error includes diagnostic details:

```json
{
  "error_message": "Authentication failed: Invalid API key",
  "error_code": "AUTHENTICATION_ERROR",
  "details": {
    "exception_type": "PermissionError",
    "traceback": "...",
    "api_key_preview": "abc12345..."
  }
}
```

## Best Practices for AI Agents

### 1. Automated Testing Workflow

```python
# Example AI agent testing workflow
import subprocess
import json

def test_exchange_integration(exchange_name):
    results = {}
    
    # Test public REST API
    result = subprocess.run([
        "python", "src/examples/rest_public_integration_test.py", 
        exchange_name, "--output", f"rest_public_{exchange_name}.json"
    ], capture_output=True, text=True)
    
    results["rest_public"] = {
        "exit_code": result.returncode,
        "success": result.returncode == 0
    }
    
    # Parse detailed results
    if result.returncode == 0:
        with open(f"rest_public_{exchange_name}.json") as f:
            results["rest_public"]["details"] = json.load(f)
    
    return results
```

### 2. Result Validation

```python
def validate_test_results(test_results):
    """Validate test results for AI agent decision making."""
    
    # Check overall success
    if test_results["overall_status"] != "PASSED":
        return False, f"Tests failed: {test_results['overall_status']}"
    
    # Check success rate
    success_rate = test_results["summary_metrics"]["success_rate"]
    if success_rate < 0.8:  # 80% minimum success rate
        return False, f"Success rate too low: {success_rate}"
    
    # Check performance metrics
    total_time = test_results["summary_metrics"]["total_execution_time_ms"]
    if total_time > 30000:  # 30 seconds maximum
        return False, f"Tests too slow: {total_time}ms"
    
    return True, "All validations passed"
```

### 3. Integration with Exchange Factory

The test framework integrates with the existing exchange factory system:

```python
# Tests use the same factory pattern as production code
from examples.utils.rest_api_factory import get_exchange_rest_class
from examples.utils.ws_api_factory import get_exchange_websocket_classes

# This ensures tests validate the same code paths used in production
```

## Migration from Legacy Demos

### Legacy Demo Files

The original demo files are maintained for reference but deprecated for AI agent use:

- `rest_public_demo.py` → `rest_public_integration_test.py`
- `rest_private_demo.py` → `rest_private_integration_test.py`
- `websocket_public_demo.py` → `websocket_public_integration_test.py`
- `websocket_private_demo.py` → `websocket_private_integration_test.py`

### Key Improvements

1. **Structured Output**: JSON instead of human-readable logs
2. **Standardized Exit Codes**: Machine-readable success/failure indicators
3. **Performance Metrics**: Detailed timing and quality measurements
4. **Error Classification**: Standardized error codes and handling
5. **AI-Agent Optimized**: Designed specifically for automated consumption

## Troubleshooting

### Common Issues

1. **Missing Credentials**
   ```
   Error: Configuration error - API credentials required
   Exit Code: 4
   Solution: Set environment variables for API_KEY and SECRET_KEY
   ```

2. **Connection Timeout**
   ```
   Error: Test timeout after 30 seconds
   Exit Code: 3
   Solution: Increase timeout with --timeout 60 or check network connectivity
   ```

3. **No Market Data**
   ```
   Status: PASSED but no data received
   Solution: Normal for inactive markets; WebSocket connection working correctly
   ```

### Debug Mode

Use verbose output for troubleshooting:

```bash
# Uses default exchange (mexc)
python src/examples/rest_public_integration_test.py --verbose
# Or specify exchange explicitly
python src/examples/rest_public_integration_test.py mexc --verbose
```

## Testing Decorators

The framework includes powerful decorators to eliminate repetitive try-catch patterns and standardize testing:

### Available Decorators

#### `@rest_api_test(api_name)`
For REST API testing with automatic error handling and timing:
```python
from examples.utils.decorators import rest_api_test

@rest_api_test("ping")
async def check_ping(exchange, exchange_name: str):
    return await exchange.ping()
```

#### `@test_method(description, print_result=True, capture_timing=True)`
General-purpose test method decorator:
```python
from examples.utils.decorators import test_method

@test_method("Custom API Test")
async def custom_test(exchange, exchange_name: str):
    return {"result": "success"}
```

#### `@integration_test(test_name, expected_behavior, timeout_seconds=30)`
For integration testing with timeout and structured reporting:
```python
from examples.utils.decorators import integration_test

@integration_test("ping_test", "Server responds to ping", timeout_seconds=10)
async def test_ping(self):
    return await self.exchange.ping()
```

#### `@safe_execution(description, log_errors=True)`
For safe execution with error logging:
```python
from examples.utils.decorators import safe_execution

@safe_execution("Database connection")
async def connect_db():
    # Implementation that might fail
    pass
```

### Benefits

- **Eliminates repetitive try-catch blocks**
- **Standardized output formatting** 
- **Automatic timing capture**
- **Consistent error handling**
- **Structured result format**
- **Reduced code duplication**

### Before and After

**Old way (repetitive):**
```python
async def check_ping(exchange, exchange_name: str):
    print(f"=== {exchange_name.upper()} PING CHECK ===")
    try:
        result = await exchange.ping()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
```

**New way (clean):**
```python
@rest_api_test("ping")
async def check_ping(exchange, exchange_name: str):
    return await exchange.ping()
```

See `examples/utils/decorators_example.py` for complete usage examples.

## Architecture Compliance

This testing framework adheres to the HFT system architecture:

- **SOLID Principles**: Single responsibility, interface segregation
- **Clean Architecture**: Proper separation of concerns
- **Performance First**: HFT-compliant timing and metrics
- **Type Safety**: Comprehensive type annotations
- **Error Propagation**: Unified exception handling
- **DRY Principle**: Decorators eliminate code duplication

The framework serves as both a testing tool and a reference implementation of the project's architectural standards.