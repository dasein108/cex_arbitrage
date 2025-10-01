# REST Architecture Refactoring Plan

## Overview

Refactor the REST architecture from strategy pattern to direct implementation for better HFT performance and simpler code paths. Eliminate strategy dispatch overhead and move exchange-specific logic directly into exchange implementations.

## Current Architecture Issues

### Strategy Pattern Overhead
```
BaseRestInterface → RestManager → StrategySet {
  - AuthStrategy         (~0.5μs dispatch)
  - RetryStrategy        (~0.3μs dispatch)  
  - RateLimitStrategy    (~0.4μs dispatch)
  - ExceptionHandlerStrategy (~0.2μs dispatch)
  - RequestStrategy      (~0.3μs dispatch)
}
Total overhead: ~1.7μs per request
```

### Problems
- Multiple abstraction layers add latency
- Strategy dispatch overhead in HFT context
- Complex debugging through strategy composition
- Code scattered across multiple strategy classes
- Difficult to optimize for exchange-specific patterns

## Target Architecture

### Direct Implementation Pattern
```
BaseRestInterface (minimal) → ExchangeBaseRest → SpecificRestImplementation

MexcBaseRest → {
  - MexcPublicSpotRest
  - MexcPrivateSpotRest
}

GateioBaseSpotRest → {
  - GateioPublicSpotRest
  - GateioPrivateSpotRest
}

GateioBaseFuturesRest → {
  - GateioPublicFuturesRest
  - GateioPrivateFuturesRest
}
```

### Key Principles
- **Direct Method Calls**: No strategy dispatch
- **Constructor Injection**: Dependencies injected at creation
- **Decorator-Based Retry**: Cross-cutting concerns via decorators
- **Exchange-Specific Optimization**: Each exchange optimizes its own flow
- **Minimal Base Interface**: Just coordination, no business logic

## Implementation Plan

### Phase 1: Create Exchange Base Classes

#### 1.1 MEXC Base Implementation
```python
# File: src/exchanges/integrations/mexc/rest/mexc_base_rest.py
class MexcBaseRest:
    """Base REST client for MEXC with direct implementation pattern."""
    
    def __init__(self, config: ExchangeConfig, rate_limiter: RateLimiter, 
                 logger: HFTLoggerInterface, is_private: bool = False):
        self.config = config
        self.rate_limiter = rate_limiter  # Constructor injected
        self.logger = logger
        self.is_private = is_private
        self.api_key = config.credentials.api_key if is_private else None
        self.secret_key = config.credentials.secret_key if is_private else None
        
        # Direct session management
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def _authenticate(self, method: HTTPMethod, endpoint: str, 
                          params: Dict, data: Dict) -> Dict[str, Any]:
        """Direct MEXC authentication implementation."""
        if not self.is_private:
            return {}
            
        # Generate fresh timestamp
        timestamp = str(int(time.time() * 1000))
        
        # Build signature string (MEXC-specific)
        auth_params = {**params, **data} if data else params.copy()
        auth_params.update({
            'timestamp': int(timestamp),
            'recvWindow': 5000
        })
        
        # Generate signature
        signature_string = urlencode(auth_params)
        signature = hmac.new(
            self.secret_key.encode(),
            signature_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Return auth headers and params
        return {
            'headers': {
                'X-MEXC-APIKEY': self.api_key,
                'Content-Type': 'application/json'
            },
            'params': {**auth_params, 'signature': signature}
        }
    
    def _handle_error(self, status: int, response_text: str) -> Exception:
        """Direct MEXC error handling."""
        # MEXC-specific error parsing
        try:
            error_data = json.loads(response_text)
            code = error_data.get('code', status)
            message = error_data.get('msg', response_text)
            
            # MEXC-specific error mapping
            if code == 700002:
                return ExchangeRestError(status, f"MEXC Error {code}: Signature invalid")
            elif code == 429:
                return RateLimitErrorRest(status, f"MEXC Rate limit: {message}")
            else:
                return ExchangeRestError(status, f"MEXC Error {code}: {message}")
        except:
            return ExchangeRestError(status, f"MEXC HTTP {status}: {response_text}")
    
    def _parse_response(self, response_text: str) -> Any:
        """Direct MEXC response parsing with msgspec."""
        if not response_text:
            return None
        try:
            return msgspec.json.decode(response_text)
        except Exception as e:
            raise ExchangeRestError(400, f"Invalid JSON: {response_text[:100]}...")
    
    @retry_decorator(
        max_attempts=3,
        backoff="exponential", 
        base_delay=0.1,
        exceptions=(aiohttp.ClientConnectionError, asyncio.TimeoutError)
    )
    async def _request(self, method: HTTPMethod, endpoint: str, 
                      params: Optional[Dict] = None, 
                      data: Optional[Dict] = None) -> Any:
        """Core request implementation with direct handling."""
        
        # Rate limiting
        await self.rate_limiter.acquire(endpoint)
        
        try:
            # Ensure session
            await self._ensure_session()
            
            # Authentication
            auth_data = await self._authenticate(method, endpoint, params or {}, data or {})
            
            # Merge auth data
            final_headers = auth_data.get('headers', {})
            final_params = auth_data.get('params') or params
            
            # Build URL
            url = f"{self.config.base_url}{endpoint}"
            
            # Execute request
            async with self._session.request(
                method.value, url, 
                params=final_params,
                json=data,
                headers=final_headers
            ) as response:
                response_text = await response.text()
                
                # Error handling
                if response.status >= 400:
                    raise self._handle_error(response.status, response_text)
                
                # Parse response
                return self._parse_response(response_text)
                
        finally:
            self.rate_limiter.release(endpoint)
    
    async def request(self, method: HTTPMethod, endpoint: str,
                     params: Optional[Dict] = None,
                     data: Optional[Dict] = None) -> Any:
        """Public request method with metrics."""
        start_time = time.perf_counter()
        
        try:
            result = await self._request(method, endpoint, params, data)
            
            # Metrics
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.logger.metric("mexc_request_duration_ms", duration_ms,
                             tags={"endpoint": endpoint, "method": method.value})
            
            return result
            
        except Exception as e:
            # Error metrics
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.logger.metric("mexc_request_errors", 1,
                             tags={"endpoint": endpoint, "error": type(e).__name__})
            raise
```

#### 1.2 MEXC Specific Implementations
```python
# File: src/exchanges/integrations/mexc/rest/mexc_rest_spot_public.py
class MexcPublicSpotRest(MexcBaseRest, PublicSpotRest):
    """MEXC public spot REST implementation."""
    
    def __init__(self, config: ExchangeConfig, rate_limiter: RateLimiter, logger: HFTLoggerInterface):
        super().__init__(config, rate_limiter, logger, is_private=False)
    
    # All existing public methods remain the same
    # They now use self.request() instead of self._rest.request()

# File: src/exchanges/integrations/mexc/rest/mexc_rest_spot_private.py  
class MexcPrivateSpotRest(MexcBaseRest, PrivateSpotRest):
    """MEXC private spot REST implementation."""
    
    def __init__(self, config: ExchangeConfig, rate_limiter: RateLimiter, logger: HFTLoggerInterface):
        super().__init__(config, rate_limiter, logger, is_private=True)
    
    # All existing private methods remain the same
    # They now use self.request() instead of self._rest.request()
```

#### 1.3 Gate.io Base Implementations

```python
# File: src/exchanges/integrations/gateio/rest/gateio_base_spot_rest.py
class GateioBaseSpotRest:
    """Base REST client for Gate.io Spot with direct implementation."""
    
    def __init__(self, config: ExchangeConfig, rate_limiter: RateLimiter,
                 logger: HFTLoggerInterface, is_private: bool = False):
        self.config = config
        self.rate_limiter = rate_limiter
        self.logger = logger
        self.is_private = is_private
        
    async def _authenticate(self, method: HTTPMethod, endpoint: str,
                          params: Dict, data: Dict) -> Dict[str, Any]:
        """Direct Gate.io Spot authentication implementation."""
        if not self.is_private:
            return {}
            
        # Gate.io specific auth logic
        timestamp = str(int(time.time()))
        
        # Build signature string (Gate.io format)
        query_string = urlencode(params) if params else ""
        payload = json.dumps(data, separators=(',', ':')) if data else ""
        payload_hash = hashlib.sha512(payload.encode()).hexdigest()
        
        url_path = f"/api/v4{endpoint}" if not endpoint.startswith("/api/v4") else endpoint
        signature_string = f"{method.value}\n{url_path}\n{query_string}\n{payload_hash}\n{timestamp}"
        
        signature = hmac.new(
            self.config.credentials.secret_key.encode(),
            signature_string.encode(),
            hashlib.sha512
        ).hexdigest()
        
        return {
            'headers': {
                'KEY': self.config.credentials.api_key,
                'SIGN': signature,
                'Timestamp': timestamp,
                'Content-Type': 'application/json'
            },
            'data': payload if payload else None
        }
    
    def _handle_error(self, status: int, response_text: str) -> Exception:
        """Direct Gate.io error handling."""
        # Gate.io specific error patterns
        try:
            error_data = json.loads(response_text)
            message = error_data.get('message', response_text)
            
            if 'RATE_LIMIT' in message.upper():
                return RateLimitErrorRest(status, f"Gate.io Rate limit: {message}")
            else:
                return ExchangeRestError(status, f"Gate.io Error: {message}")
        except:
            return ExchangeRestError(status, f"Gate.io HTTP {status}: {response_text}")

# File: src/exchanges/integrations/gateio/rest/gateio_base_futures_rest.py
class GateioBaseFuturesRest:
    """Base REST client for Gate.io Futures with direct implementation."""
    
    def __init__(self, config: ExchangeConfig, rate_limiter: RateLimiter,
                 logger: HFTLoggerInterface, is_private: bool = False):
        self.config = config
        self.rate_limiter = rate_limiter
        self.logger = logger
        self.is_private = is_private
        
    async def _authenticate(self, method: HTTPMethod, endpoint: str,
                          params: Dict, data: Dict) -> Dict[str, Any]:
        """Direct Gate.io Futures authentication implementation."""
        # Similar to spot but with futures-specific endpoints
        # /api/v4/futures/... instead of /api/v4/spot/...
```

#### 1.4 Gate.io Specific Implementations
```python
# Spot implementations
class GateioPublicSpotRest(GateioBaseSpotRest, PublicSpotRest): ...
class GateioPrivateSpotRest(GateioBaseSpotRest, PrivateSpotRest): ...

# Futures implementations  
class GateioPublicFuturesRest(GateioBaseFuturesRest, PublicFuturesRest): ...
class GateioPrivateFuturesRest(GateioBaseFuturesRest, PrivateFuturesRest): ...
```

### Phase 2: Simplify BaseRestInterface

```python
# File: src/exchanges/interfaces/rest/rest_base.py
class BaseRestInterface(ABC):
    """Minimal REST interface - just coordination."""
    
    def __init__(self, config: ExchangeConfig, is_private: bool = False, 
                 logger: Optional[HFTLoggerInterface] = None):
        self.exchange_name = config.name
        self.logger = logger or get_exchange_logger(config.name, 'rest')
        
        # Create exchange-specific REST client with injected dependencies
        self._rest_client = self._create_rest_client(config, is_private)
    
    @abstractmethod
    def _create_rest_client(self, config: ExchangeConfig, is_private: bool):
        """Create exchange-specific REST client."""
        pass
    
    async def request(self, method: HTTPMethod, endpoint: str, 
                     params: dict = None, data: dict = None, headers: dict = None):
        """Direct delegation to exchange implementation."""
        # Minimal logging
        with LoggingTimer(self.logger, "rest_request") as timer:
            result = await self._rest_client.request(method, endpoint, params, data)
            
            # Basic metrics
            self.logger.metric("rest_requests_completed", 1,
                             tags={"exchange": self.exchange_name})
            
            return result
```

### Phase 3: Factory Pattern for REST Clients

```python
# File: src/exchanges/factory/rest_factory.py
def create_rest_client(config: ExchangeConfig, is_private: bool) -> BaseRestInterface:
    """Factory to create exchange-specific REST clients with dependencies."""
    
    # Create exchange-specific rate limiter
    rate_limiter = create_rate_limiter(config)
    
    # Create logger
    logger = get_exchange_logger(config.name, 'rest')
    
    # Create exchange-specific implementation
    if config.name == "MEXC_SPOT":
        if is_private:
            client = MexcPrivateSpotRest(config, rate_limiter, logger)
        else:
            client = MexcPublicSpotRest(config, rate_limiter, logger)
    
    elif config.name == "GATEIO_SPOT":
        if is_private:
            client = GateioPrivateSpotRest(config, rate_limiter, logger)
        else:
            client = GateioPublicSpotRest(config, rate_limiter, logger)
    
    elif config.name == "GATEIO_FUTURES":
        if is_private:
            client = GateioPrivateFuturesRest(config, rate_limiter, logger)
        else:
            client = GateioPublicFuturesRest(config, rate_limiter, logger)
    
    else:
        raise ValueError(f"Unsupported exchange: {config.name}")
    
    return client
```

### Phase 4: Retry Decorators

```python
# File: src/infrastructure/decorators/retry.py
def retry_decorator(max_attempts: int = 3, backoff: str = "exponential",
                   base_delay: float = 0.1, max_delay: float = 5.0,
                   exceptions: Tuple = (Exception,)):
    """Configurable retry decorator for REST requests."""
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        raise
                    
                    # Calculate delay
                    if backoff == "exponential":
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    else:
                        delay = base_delay
                    
                    await asyncio.sleep(delay)
            
            raise last_exception
        return wrapper
    return decorator
```

## Performance Targets

### Current Performance
- Strategy dispatch overhead: ~1.7μs per request
- Total request latency: 40-250ms (including network)
- Memory allocation: Multiple strategy objects per request

### Target Performance  
- Direct call overhead: <0.1μs per request
- Total request latency: <40ms (maintained)
- Memory allocation: Single object per request
- HFT compliance: Sub-50ms for 99% of requests

## Migration Strategy

### Phase 1: MEXC Implementation (Week 1)
- [ ] Create `MexcBaseRest` base class
- [ ] Implement `MexcPublicSpotRest` and `MexcPrivateSpotRest`
- [ ] Add retry decorators
- [ ] Create rate limiter injection
- [ ] Test MEXC functionality

### Phase 2: Gate.io Spot Implementation (Week 2)  
- [ ] Create `GateioBaseSpotRest` base class
- [ ] Implement `GateioPublicSpotRest` and `GateioPrivateSpotRest`
- [ ] Test Gate.io spot functionality
- [ ] Performance comparison with strategy pattern

### Phase 3: Gate.io Futures Implementation (Week 3)
- [ ] Create `GateioBaseFuturesRest` base class  
- [ ] Implement `GateioPublicFuturesRest` and `GateioPrivateFuturesRest`
- [ ] Test Gate.io futures functionality

### Phase 4: Integration & Cleanup (Week 4)
- [ ] Update factory patterns
- [ ] Simplify `BaseRestInterface`
- [ ] Remove strategy pattern code
- [ ] Update documentation
- [ ] Performance validation

## Dependencies & Injection Points

### Constructor Injection
```python
class ExchangeBaseRest:
    def __init__(self, 
                 config: ExchangeConfig,           # Exchange configuration
                 rate_limiter: RateLimiter,        # Rate limiting strategy
                 logger: HFTLoggerInterface,       # Logging interface
                 is_private: bool = False):        # Authentication requirement
```

### Rate Limiter Interface
```python
class RateLimiter:
    async def acquire(self, endpoint: str) -> None: ...
    def release(self, endpoint: str) -> None: ...
```

### Benefits Summary

1. **Performance**: Eliminate ~1.7μs strategy dispatch overhead
2. **Simplicity**: Direct method calls, easier debugging
3. **Optimization**: Exchange-specific optimizations possible
4. **Maintenance**: Less abstraction, clearer code paths
5. **HFT Compliance**: Better latency characteristics

### Risks & Mitigation

1. **Code Duplication**: Use shared utilities and mixins
2. **Testing Complexity**: Create exchange-specific test utilities
3. **Configuration Management**: Centralized config with injection
4. **Monitoring**: Maintain same metrics granularity in base classes

## Success Criteria

- [ ] Sub-50ms latency maintained for 99% of requests
- [ ] Eliminate strategy dispatch overhead (~1.7μs improvement)
- [ ] Maintain existing functionality and error handling
- [ ] Preserve logging and metrics granularity
- [ ] Code coverage maintained at >90%
- [ ] Integration tests pass for all exchanges
- [ ] Performance tests show improvement