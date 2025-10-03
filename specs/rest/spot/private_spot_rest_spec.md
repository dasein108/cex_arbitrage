# PrivateSpotRest Interface Specification

## Overview

The `PrivateSpotRest` interface defines the contract for authenticated spot trading operations via REST API. This interface combines trading capabilities with withdrawal functionality, providing complete account management for spot exchanges.

## Interface Purpose and Responsibilities

### Primary Purpose
- Enable authenticated trading operations on spot exchanges
- Provide account balance and order management capabilities
- Support cryptocurrency withdrawal operations
- Ensure HFT-compliant execution with sub-50ms latency

### Core Responsibilities
1. **Trading Operations**: Order placement, cancellation, and status queries
2. **Account Management**: Balance tracking and updates
3. **Withdrawal Processing**: Cryptocurrency withdrawal submissions
4. **Trade History**: Access to historical trading data

## Architectural Position

```
PrivateTradingInterface (parent - common trading ops)
    └── WithdrawalInterface (mixin - withdrawal ops)
            └── PrivateSpotRest (combines both)
                    ├── MexcPrivateRest (concrete)
                    ├── GateioPrivateRest (concrete)
                    └── [Other exchange implementations]
```

## Interface Composition

### From PrivateTradingInterface

#### 1. `get_account_balance() -> Dict[AssetName, AssetBalance]`
**Purpose**: Retrieve current account balances
**HFT Requirements**: 
- Must complete within 100ms
- No caching allowed (real-time trading data)
**Returns**: Dictionary mapping assets to balance information

#### 2. `place_order(order_params: OrderParams) -> Order`
**Purpose**: Submit a new trading order
**HFT Requirements**: 
- Must complete within 50ms (critical path)
- Immediate order ID return required
**Returns**: Order struct with exchange order ID

#### 3. `cancel_order(symbol: Symbol, order_id: OrderId) -> Order`
**Purpose**: Cancel an existing order
**HFT Requirements**: 
- Must complete within 50ms
- Must handle partial fills correctly
**Returns**: Updated Order struct with cancellation status

#### 4. `get_order(symbol: Symbol, order_id: OrderId) -> Order`
**Purpose**: Query current order status
**HFT Requirements**: 
- Must complete within 50ms
- Real-time status required (no caching)
**Returns**: Current Order struct

#### 5. `get_open_orders(symbol: Optional[Symbol] = None) -> List[Order]`
**Purpose**: Retrieve all open orders
**HFT Requirements**: 
- Must complete within 100ms
- Critical for risk management
**Returns**: List of open Order structs

### From WithdrawalInterface

#### 1. `withdraw(request: WithdrawalRequest) -> WithdrawalResponse`
**Purpose**: Submit cryptocurrency withdrawal request
**Security Requirements**: 
- Must validate address format
- Must check withdrawal limits
- Must handle 2FA if required
**Returns**: WithdrawalResponse with transaction ID

#### 2. `get_withdrawal_status(withdrawal_id: str) -> WithdrawalResponse`
**Purpose**: Query withdrawal status
**Returns**: Current withdrawal status and details

#### 3. `get_withdrawal_history(asset: Optional[AssetName] = None, limit: int = 100) -> List[WithdrawalResponse]`
**Purpose**: Retrieve withdrawal history
**Returns**: List of historical withdrawals

## Data Flow Patterns

### Order Lifecycle Flow
```
1. place_order() called with parameters
2. Order validated locally (symbol, precision)
3. Signed REST request sent to exchange
4. Order ID returned immediately
5. Order struct created and returned
6. Status updates via get_order() or WebSocket
```

### Balance Update Flow
```
1. get_account_balance() called
2. Authenticated REST request sent
3. Response parsed to AssetBalance structs
4. Returned without caching (HFT rule)
5. Composite layer updates internal state
```

### Withdrawal Flow
```
1. withdraw() called with validated request
2. Security checks performed
3. Signed request with withdrawal params
4. Withdrawal ID returned
5. Status tracked via get_withdrawal_status()
```

## HFT Performance Requirements

### Latency Targets
- **Order Operations**: <50ms (critical path)
- **Balance Queries**: <100ms
- **Open Orders**: <100ms
- **Withdrawal Operations**: <500ms (non-critical)

### Reliability Requirements
- 99.9% availability for trading operations
- Automatic retry for transient failures
- Circuit breaker for persistent errors
- Graceful degradation support

## Authentication and Security

### Authentication Methods
```python
# Signature generation pattern
def _sign_request(self, params: Dict) -> Dict:
    """Generate HMAC signature for request"""
    timestamp = int(time.time() * 1000)
    params['timestamp'] = timestamp
    signature = hmac.new(
        self.config.secret.encode(),
        urlencode(params).encode(),
        hashlib.sha256
    ).hexdigest()
    params['signature'] = signature
    return params
```

### Security Requirements
- API credentials stored securely
- Request signing for all private endpoints
- Nonce/timestamp to prevent replay attacks
- IP whitelisting support
- Rate limit compliance

## Implementation Guidelines

### 1. Order Placement Pattern
```python
async def place_order(self, params: OrderParams) -> Order:
    # Validate locally first
    self._validate_order_params(params)
    
    # Format for exchange
    exchange_params = self._format_order_params(params)
    
    # Sign and send
    response = await self._transport_manager.post(
        endpoint="/order",
        data=self._sign_request(exchange_params)
    )
    
    # Parse and return
    return self._parse_order(response)
```

### 2. Error Handling Pattern

```python
async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
    try:
        response = await self._transport_manager.delete(
            endpoint=f"/order/{order_id}",
            data=self._sign_request({"symbol": str(symbol)})
        )
        return self._parse_order(response)
    except ExchangeAPIError as e:
        if e.code == "ORDER_NOT_FOUND":
            # Order already filled or cancelled
            return await self.fetch_order(symbol, order_id)
        raise
```

### 3. Balance Management Pattern
```python
async def get_account_balance(self) -> Dict[AssetName, AssetBalance]:
    # No caching - always fetch fresh (HFT rule)
    response = await self._transport_manager.get(
        endpoint="/account",
        params=self._sign_request({})
    )
    
    balances = {}
    for asset_data in response['balances']:
        asset = AssetName(asset_data['asset'])
        balances[asset] = AssetBalance(
            asset=asset,
            available=Decimal(asset_data['free']),
            locked=Decimal(asset_data['locked'])
        )
    return balances
```

## Dependencies and Relationships

### External Dependencies
- `exchanges.structs.common`: Core data structures
- `exchanges.structs.types`: Type definitions (AssetName, OrderId)
- `exchanges.interfaces.rest.interfaces`: Parent interfaces
- `infrastructure.exceptions`: Error handling

### Internal Relationships
- **Parents**: PrivateTradingInterface, WithdrawalInterface
- **Used By**: CompositePrivateExchange
- **Siblings**: PrivateFuturesRest (extends for futures)

## Implementation Checklist

When implementing PrivateSpotRest for a new exchange:

- [ ] Implement all PrivateTradingInterface methods
- [ ] Implement all WithdrawalInterface methods
- [ ] Add proper request signing logic
- [ ] Implement exchange-specific order formatting
- [ ] Add balance parsing logic
- [ ] Handle exchange-specific error codes
- [ ] Test order lifecycle completely
- [ ] Verify no caching of trading data
- [ ] Add withdrawal address validation
- [ ] Document API quirks and limitations

## Critical Safety Rules

### HFT Caching Policy
```
NEVER CACHE:
- Account balances (change with each trade)
- Order status (execution state)
- Open orders (real-time state)

SAFE TO CACHE:
- Withdrawal limits (static rules)
- Asset precision (static config)
- Fee schedules (rarely change)
```

### Order Safety
- Always validate precision before submission
- Check minimum order sizes
- Verify symbol is tradeable
- Handle partial fills correctly
- Track order lifecycle completely

## Monitoring and Observability

### Key Metrics
- Order placement latency
- Order success/rejection rates
- Balance query latency
- Withdrawal processing time
- API error rates by type

### Critical Alerts
- Order placement >50ms
- Balance query failures
- Repeated order rejections
- Withdrawal failures
- Authentication errors

## Testing Requirements

### Unit Tests
- Mock exchange responses
- Test error handling paths
- Verify signature generation
- Test order validation

### Integration Tests
- Real order placement (testnet)
- Balance updates after trades
- Order cancellation scenarios
- Withdrawal flow (testnet)

### Performance Tests
- Measure operation latencies
- Test under load (100+ req/sec)
- Verify no memory leaks
- Test connection pooling

## Future Enhancements

1. **Advanced Order Types**: OCO, iceberg orders
2. **Batch Operations**: Multiple orders in one request
3. **Margin Trading**: Leverage and borrowing
4. **Sub-accounts**: Multi-account management