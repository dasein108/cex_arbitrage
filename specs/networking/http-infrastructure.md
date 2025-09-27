# HTTP Infrastructure Specification

## Overview

The HTTP infrastructure provides high-performance REST API connectivity optimized for HFT trading operations. Built on a strategy composition architecture, it coordinates authentication, rate limiting, retry logic, and error handling to achieve sub-50ms end-to-end latency while maintaining reliability and compliance.

## Core Components

### **RestManager - Strategy-Coordinated Request Execution**

The RestManager serves as the central coordinator for all HTTP operations, orchestrating multiple strategies to ensure optimal performance and reliability.

**Location**: `src/infrastructure/networking/http/rest_manager.py`

#### **Key Features**

1. **Strategy Composition Architecture**
   - All HTTP operations coordinated through composable strategies
   - Zero-allocation strategy access with initialization-time validation
   - Exchange-specific optimizations encapsulated in strategy implementations

2. **HFT Performance Compliance**
   - Sub-50ms end-to-end latency target
   - <1ms coordination overhead
   - Real-time latency percentile tracking (P95, P99)
   - HFT compliance rate monitoring (>95% requests under 50ms)

3. **Optimized Session Management**
   - Connection pooling with keep-alive and DNS caching
   - TCP connector optimization for minimal connection overhead
   - Semaphore-based concurrency control
   - Automatic session recreation on failures

#### **Performance Specifications**

- **Target Latency**: <50ms end-to-end
- **Coordination Overhead**: <1ms
- **HFT Compliance**: >95% requests under performance targets
- **Connection Reuse**: >95% efficiency
- **Throughput**: Configurable per exchange (typically 100+ RPS)

#### **Request Execution Flow**

```
RestManager Request Flow:
1. Session ensured with optimal TCP connector settings
2. Rate limiting permit acquired (RateLimitStrategy)
3. Request prepared with exchange-specific formatting (RequestStrategy)
4. Authentication applied if required (AuthStrategy)
5. Request executed with retry logic (RetryStrategy)
6. Errors handled and classified (ExceptionHandlerStrategy)
7. Rate limiting permit released
8. Performance metrics updated with HFT compliance tracking
```

### **REST Strategy Set Container**

**Location**: `src/infrastructure/networking/http/strategies/strategy_set.py`

The RestStrategySet provides zero-allocation access to all HTTP strategies with comprehensive validation.

```python
class RestStrategySet:
    def __init__(
        self,
        request_strategy: RequestStrategy,           # Required
        rate_limit_strategy: RateLimitStrategy,      # Required
        retry_strategy: RetryStrategy,               # Required
        auth_strategy: Optional[AuthStrategy] = None,           # Optional (public endpoints)
        exception_handler_strategy: Optional[ExceptionHandlerStrategy] = None
    ):
        # All required strategies validated at initialization
        self._validate_strategies()
        self._performance_targets = request_strategy.get_performance_targets()
```

#### **Strategy Validation**
- Required strategies: RequestStrategy, RateLimitStrategy, RetryStrategy
- Optional strategies: AuthStrategy (for public endpoints), ExceptionHandlerStrategy
- Performance targets derived from RequestStrategy

## Strategy Implementations

### **1. RequestStrategy - Request Configuration & Preparation**

**Location**: `src/infrastructure/networking/http/strategies/request.py`

Handles HTTP request configuration, connection setup, and exchange-specific request formatting.

#### **Core Responsibilities**
- **Connection Configuration**: Optimal aiohttp session setup with performance tuning
- **Request Preparation**: Exchange-specific parameter formatting and header management
- **Performance Targets**: HFT compliance requirements definition
- **Base URL Management**: Exchange endpoint configuration

#### **Key Methods**

```python
async def create_request_context() -> RequestContext:
    """Create optimized request configuration"""

async def prepare_request(
    method: HTTPMethod,
    endpoint: str,
    params: Dict[str, Any],
    headers: Dict[str, str]
) -> Dict[str, Any]:
    """Prepare request parameters with exchange-specific formatting"""

def get_performance_targets() -> PerformanceTargets:
    """Define HFT performance requirements for this exchange"""
```

#### **Request Context Configuration**

```python
@dataclass(frozen=True)
class RequestContext:
    base_url: str                           # Exchange API base URL
    timeout: float                          # Request timeout
    max_concurrent: int                     # Maximum concurrent requests
    connection_timeout: float = 2.0         # TCP connection timeout
    read_timeout: float = 5.0              # Socket read timeout
    keepalive_timeout: float = 60.0        # Keep-alive timeout
    default_headers: Optional[Dict[str, str]] = None
```

### **2. AuthStrategy - Authentication & Request Signing**

**Location**: `src/infrastructure/networking/http/strategies/auth.py`

Handles API key authentication and request signing with exchange-specific implementations.

#### **Core Functionality**
- **Request Signing**: Exchange-specific signature generation (HMAC, RSA, etc.)
- **Authentication Headers**: API key, timestamp, and signature header management
- **Endpoint Classification**: Determines which endpoints require authentication
- **Parameter Injection**: Adds authentication parameters to requests

#### **Key Methods**

```python
async def sign_request(
    method: HTTPMethod,
    endpoint: str,
    params: Dict[str, Any],
    json_data: Dict[str, Any],
    timestamp: int
) -> AuthenticationData:
    """Generate authentication data for request"""

def requires_auth(self, endpoint: str) -> bool:
    """Check if endpoint requires authentication"""
```

#### **Authentication Data Structure**

```python
@dataclass(frozen=True)
class AuthenticationData:
    headers: Dict[str, str]     # Authentication headers (API-Key, Sign, etc.)
    params: Dict[str, Any]      # Authentication parameters
    data: Optional[str] = None  # Request body (for exchanges requiring direct control)
```

#### **Performance Target**
- **Signature Generation**: <200μs per request

### **3. RateLimitStrategy - Intelligent Rate Limiting**

**Location**: `src/infrastructure/networking/http/strategies/rate_limit.py`

Implements sophisticated rate limiting with per-endpoint controls and burst capacity management.

#### **Core Features**
- **Per-Endpoint Limits**: Individual rate limits for different API endpoints
- **Burst Capacity**: Allow temporary bursts within limits
- **Weighted Requests**: Different endpoints consume different rate limit weights
- **Global Rate Limiting**: Exchange-wide rate limit coordination
- **Permit System**: Acquire/release permits for request control

#### **Rate Limiting Context**

```python
@dataclass(frozen=True)
class RateLimitContext:
    requests_per_second: float      # Base rate limit
    burst_capacity: int             # Maximum burst size
    endpoint_weight: int = 1        # Endpoint-specific weight
    global_weight: int = 1          # Global rate limit weight
    cooldown_period: float = 0.1    # Cooldown after rate limit hit
```

### **4. RetryStrategy - Intelligent Retry Logic**

**Location**: `src/infrastructure/networking/http/strategies/retry.py`

Provides smart retry logic with exponential backoff, circuit breakers, and error-specific handling.

#### **Core Capabilities**
- **Error Classification**: Different retry policies for different error types
- **Exponential Backoff**: Intelligent delay calculation to avoid overwhelming servers
- **Circuit Breakers**: Automatic failure detection and recovery
- **Rate Limit Handling**: Special handling for 429 responses with server-specified delays
- **Maximum Attempts**: Configurable retry limits per error type

#### **Key Methods**

```python
def should_retry(self, attempt: int, error: Exception) -> bool:
    """Determine if retry should be attempted based on error type"""

async def calculate_delay(self, attempt: int, error: Exception) -> float:
    """Calculate delay before next retry attempt"""

def handle_rate_limit(self, headers: Dict[str, str]) -> float:
    """Extract rate limit delay from response headers"""
```

### **5. ExceptionHandlerStrategy - Error Classification & Recovery**

**Location**: `src/infrastructure/networking/http/strategies/exception_handler.py`

Provides exchange-specific error handling with appropriate exception classification.

#### **Error Handling Features**
- **HTTP Status Code Mapping**: Convert HTTP errors to appropriate exception types
- **Exchange-Specific Errors**: Handle exchange-specific error codes and messages
- **Recovery Guidance**: Provide guidance on whether errors are recoverable
- **Error Context**: Preserve full error context for debugging and monitoring

## Performance Monitoring & HFT Compliance

### **Request Metrics Tracking**

```python
@dataclass
class RequestMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0         # 95th percentile latency
    p99_latency_ms: float = 0.0         # 99th percentile latency
    rate_limit_hits: int = 0
    sub_50ms_requests: int = 0          # HFT compliance counter
    latency_violations: int = 0         # Requests over 50ms
```

### **Performance Targets**

```python
@dataclass(frozen=True)
class PerformanceTargets:
    max_latency_ms: float = 50.0        # HFT latency requirement
    max_retry_attempts: int = 3         # Maximum retry attempts
    connection_timeout_ms: float = 2000.0
    read_timeout_ms: float = 5000.0
    target_throughput_rps: float = 100.0
```

### **HFT Compliance Monitoring**

```python
def get_performance_summary(self) -> Dict[str, Any]:
    """Get comprehensive HFT compliance summary"""
    return {
        "total_requests": total,
        "success_rate": (successful / total) * 100,
        "hft_compliance_rate": (sub_50ms / total) * 100,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
        "p99_latency_ms": p99_latency,
        "hft_compliant": compliance_rate >= 95.0,  # 95% under 50ms target
        "targets": performance_targets
    }
```

## Session Management & Optimization

### **Optimized aiohttp Session Configuration**

```python
# TCP Connector Optimization
connector = aiohttp.TCPConnector(
    limit=100,                      # Total connection pool size
    limit_per_host=max_concurrent,  # Per-host connection limit
    ttl_dns_cache=300,             # DNS cache TTL
    use_dns_cache=True,            # Enable DNS caching
    verify_ssl=True,               # SSL verification
    keepalive_timeout=keepalive_timeout,
    force_close=False              # Keep connections alive
)

# Timeout Configuration
timeout = aiohttp.ClientTimeout(
    total=total_timeout,
    connect=connection_timeout,
    sock_read=read_timeout,
    sock_connect=connection_timeout
)

# Session with High-Performance JSON
session = aiohttp.ClientSession(
    connector=connector,
    timeout=timeout,
    json_serialize=lambda obj: msgspec.json.encode(obj).decode('utf-8'),  # Fast JSON
    headers=default_headers
)
```

### **Connection Pool Management**

- **Connection Reuse**: >95% connection reuse efficiency
- **Keep-Alive Optimization**: 60-second keep-alive timeout
- **DNS Caching**: 5-minute DNS cache TTL
- **Concurrent Connections**: Configurable per-exchange limits

## Usage Examples

### **Basic REST Manager Usage**

```python
from infrastructure.networking.http.rest_manager import RestManager
from infrastructure.networking.http.strategies.strategy_set import RestStrategySet

# Create strategy set (exchange-specific implementations)
strategies = RestStrategySet(
    request_strategy=ExchangeRequestStrategy(base_url="https://api.exchange.com"),
    rate_limit_strategy=ExchangeRateLimitStrategy(),
    retry_strategy=ExchangeRetryStrategy(),
    auth_strategy=ExchangeAuthStrategy(api_key, secret_key),
    exception_handler_strategy=ExchangeExceptionHandler()
)

# Create manager
rest_manager = RestManager(strategy_set=strategies)

# Use as async context manager (recommended)
async with rest_manager as client:
    # GET request
    orderbook = await client.get("/api/v1/depth", params={"symbol": "BTCUSDT"})
    
    # POST request with authentication
    order = await client.post("/api/v1/order", json_data={
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "0.001",
        "price": "50000"
    })
```

### **Direct Request Method Usage**

```python
# Direct request with full control
response = await rest_manager.request(
    method=HTTPMethod.POST,
    endpoint="/api/v1/order",
    params={"symbol": "BTCUSDT"},
    json_data={"side": "BUY", "quantity": "0.001"},
    headers={"Custom-Header": "value"}
)
```

### **Performance Monitoring**

```python
# Get current metrics
metrics = rest_manager.get_metrics()
print(f"Total requests: {metrics.total_requests}")
print(f"Success rate: {metrics.successful_requests / metrics.total_requests * 100:.1f}%")

# Get HFT compliance summary
summary = rest_manager.get_performance_summary()
print(f"HFT compliance: {summary['hft_compliance_rate']:.1f}%")
print(f"P95 latency: {summary['p95_latency_ms']:.2f}ms")
print(f"Compliant: {summary['hft_compliant']}")

# Reset metrics for new measurement period
rest_manager.reset_metrics()
```

## Error Handling & Recovery

### **Error Classification System**

The HTTP infrastructure classifies errors into categories for appropriate handling:

1. **Rate Limit Errors (429)**: Handled with server-specified delays
2. **Authentication Errors (401, 403)**: Limited retries, credential verification required
3. **Client Errors (400-499)**: Generally not retried (application logic errors)
4. **Server Errors (500-599)**: Retried with exponential backoff
5. **Connection Errors**: Network-level issues, aggressive retry with backoff
6. **Timeout Errors**: May indicate congestion, moderate retry policy

### **Retry Logic Flow**

```
Request Execution → Error Detection → Error Classification → Retry Decision → Delay Calculation → Retry Attempt
```

### **Circuit Breaker Pattern**

- **Failure Threshold**: Configurable failure rate triggers circuit opening
- **Recovery Period**: Time-based recovery attempts
- **Half-Open State**: Limited requests during recovery testing
- **Health Monitoring**: Continuous endpoint health assessment

## Integration with Exchange Implementations

### **Strategy Implementation Requirements**

Each exchange must implement the following strategies:

1. **RequestStrategy**: Exchange-specific URL, headers, and parameter formatting
2. **RateLimitStrategy**: Exchange-specific rate limits and weights
3. **RetryStrategy**: Exchange-specific retry policies and error handling
4. **AuthStrategy**: Exchange-specific authentication and signing (if required)
5. **ExceptionHandlerStrategy**: Exchange-specific error interpretation (optional)

### **Factory Integration**

```python
# Factory creates appropriate strategy set for each exchange
private_exchange = await factory.create_private_exchange(
    exchange_name='mexc_spot'
)
# REST manager configured with MEXC-specific strategies and rate limits
```

## Configuration Management

### **Strategy-Specific Configuration**

Each strategy can be configured independently:

```python
# Request strategy configuration
request_config = RequestContext(
    base_url="https://api.exchange.com",
    timeout=10.0,
    max_concurrent=50,
    connection_timeout=2.0,
    read_timeout=5.0
)

# Rate limit configuration
rate_limit_config = RateLimitContext(
    requests_per_second=100.0,
    burst_capacity=10,
    endpoint_weight=1,
    global_weight=1
)

# Performance targets
performance_targets = PerformanceTargets(
    max_latency_ms=50.0,
    max_retry_attempts=3,
    target_throughput_rps=100.0
)
```

### **Environment-Specific Tuning**

- **Development**: Higher timeouts, more verbose logging, relaxed rate limits
- **Staging**: Production-like settings with additional monitoring
- **Production**: Optimized for performance, strict HFT compliance

## Security & Authentication

### **API Key Management**

- **Secure Storage**: API keys stored in secure configuration system
- **Rotation Support**: Automatic handling of API key rotation
- **Scope Validation**: Verification of API key permissions for required operations

### **Request Signing**

- **Exchange-Specific Algorithms**: HMAC-SHA256, RSA, or custom signing methods
- **Timestamp Management**: Precise timestamp handling for signature validation
- **Nonce Generation**: Unique request identifiers when required

### **SSL/TLS Security**

- **Certificate Validation**: Full SSL certificate chain verification
- **Modern TLS**: TLS 1.2+ requirement with strong cipher suites
- **Certificate Pinning**: Optional certificate pinning for additional security

## Debugging & Troubleshooting

### **Logging Integration**

Comprehensive logging with HFT logger integration:

- **Request/Response Logging**: Full request and response logging (configurable)
- **Performance Metrics**: Automatic latency and throughput logging
- **Error Context**: Detailed error information with full context
- **Strategy Execution**: Strategy-level execution tracing

### **Common Issues & Solutions**

1. **High Latency**: Check network connectivity, rate limiting, and server response times
2. **Authentication Failures**: Verify API credentials, signature generation, and timestamp sync
3. **Rate Limit Violations**: Review rate limiting configuration and request patterns
4. **Connection Failures**: Check firewall settings, DNS resolution, and SSL configuration
5. **Timeout Issues**: Adjust timeout settings based on network conditions and exchange performance

This specification provides comprehensive coverage of the HTTP infrastructure's strategy-driven architecture, performance optimization features, and integration capabilities within the CEX Arbitrage Engine.