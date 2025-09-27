# Capabilities Architecture Specification

## Overview

The capabilities architecture introduces a **protocol-based interface composition pattern** that enables runtime capability detection and flexible interface composition without requiring inheritance. This architecture supports the separated domain pattern where public and private exchange interfaces are completely isolated.

## Core Design Principles

### 1. Protocol-Based Composition
- **Runtime Checkable Protocols**: Uses Python's `typing.Protocol` with `@runtime_checkable` decorator
- **Duck Typing Support**: Interfaces work based on structural compatibility, not inheritance
- **Capability Detection**: Runtime checks using `isinstance(exchange, Protocol)` pattern
- **Zero Inheritance Requirement**: Exchanges can implement capabilities without explicit inheritance

### 2. Domain-Specific Capabilities
- **Universal Capabilities**: Trading and Balance (available for both spot and futures)
- **Spot-Only Capabilities**: Withdrawal operations
- **Futures-Only Capabilities**: Position management and Leverage control
- **Composable Design**: Mix and match capabilities based on exchange requirements

### 3. HFT Compliance
- **Sub-50ms Execution**: All trading operations optimized for HFT requirements
- **Real-time Updates**: Balance and position updates via WebSocket
- **No Caching**: Follows strict no-caching policy for real-time trading data
- **Performance Tracking**: Built-in metrics for latency monitoring

## Architecture Components

### Core Protocols (`protocols.py`)

```
Runtime Checkable Protocols
├── SupportsTrading       - Core trading operations
├── SupportsBalance       - Account balance management
├── SupportsWithdrawal    - Withdrawal operations (SPOT)
├── SupportsPositions     - Position management (FUTURES)
├── SupportsLeverage      - Leverage control (FUTURES)
├── SpotExchange          - Complete spot exchange protocol
└── FuturesExchange       - Complete futures exchange protocol
```

### Capability Interfaces

#### 1. Trading Capability (`trading.py`)
**Universal capability for order management**

```python
class TradingCapability(ABC):
    """Core trading operations capability."""
    
    async def place_limit_order(symbol, side, quantity, price) -> Order
    async def place_market_order(symbol, side, quantity) -> Order
    async def cancel_order(symbol, order_id) -> bool
    async def get_order(symbol, order_id) -> Order
```

**Key Features**:
- HFT-compliant with sub-50ms execution targets
- Support for both spot and futures markets
- Flexible kwargs for exchange-specific parameters
- Comprehensive error handling with ExchangeError

#### 2. Balance Capability (`balance.py`)
**Universal capability for balance tracking**

```python
class BalanceCapability(ABC):
    """Account balance operations capability."""
    
    @property
    def balances() -> Dict[AssetName, AssetBalance]
    async def get_balance(asset) -> AssetBalance
    async def refresh_balances() -> Dict[AssetName, AssetBalance]
```

**Key Features**:
- Real-time balance updates via WebSocket
- Cached property access for performance
- Explicit refresh for REST API updates
- Support for both spot and futures accounts

#### 3. Withdrawal Capability (`withdrawal.py`)
**Spot-only capability for fund withdrawals**

```python
class WithdrawalCapability(ABC):
    """Withdrawal operations capability (SPOT-ONLY)."""
    
    async def withdraw(request) -> WithdrawalResponse
    async def cancel_withdrawal(withdrawal_id) -> bool
    async def get_withdrawal_status(withdrawal_id) -> WithdrawalResponse
    async def get_withdrawal_history(asset, limit) -> List[WithdrawalResponse]
    async def validate_withdrawal_address(asset, address, network) -> bool
    async def get_withdrawal_limits(asset, network) -> Dict[str, float]
```

**Key Features**:
- Comprehensive withdrawal lifecycle management
- Address validation with network support
- Withdrawal limits and fee information
- History tracking and status monitoring

#### 4. Position Capability (`position.py`)
**Futures-only capability for position management**

```python
class PositionCapability(ABC):
    """Position management capability (FUTURES-ONLY)."""
    
    @property
    def positions() -> Dict[Symbol, Position]
    async def get_position(symbol) -> Optional[Position]
    async def close_position(symbol, quantity) -> bool
    async def get_position_history(symbol, limit) -> List[Position]
    async def refresh_positions() -> Dict[Symbol, Position]
```

**Key Features**:
- Real-time position updates via WebSocket
- Partial and full position closure
- Historical position tracking
- PnL calculation support

#### 5. Leverage Capability (`leverage.py`)
**Futures-only capability for leverage control**

```python
class LeverageCapability(ABC):
    """Leverage operations capability (FUTURES-ONLY)."""
    
    async def get_leverage(symbol) -> int
    async def set_leverage(symbol, leverage) -> bool
    async def get_max_leverage(symbol) -> int
    async def get_margin_info(symbol) -> Dict[str, float]
    async def add_margin(symbol, amount) -> bool
    async def set_margin_mode(symbol, mode) -> bool
```

**Key Features**:
- Dynamic leverage adjustment
- Margin mode management (cross/isolated)
- Margin addition for position maintenance
- Risk parameter queries

## Usage Patterns

### 1. Runtime Capability Detection

```python
from exchanges.interfaces.capabilities.protocols import (
    SupportsTrading, SupportsWithdrawal, SupportsLeverage
)

# Check capabilities at runtime
if isinstance(exchange, SupportsTrading):
    order = await exchange.place_limit_order(symbol, side, qty, price)

if isinstance(exchange, SupportsWithdrawal):
    # Safe to call withdrawal methods
    response = await exchange.withdraw(request)

if isinstance(exchange, SupportsLeverage):
    # Futures-specific operations
    await exchange.set_leverage(symbol, 10)
```

### 2. Protocol-Based Type Hints

```python
from typing import Union
from exchanges.interfaces.capabilities.protocols import SpotExchange, FuturesExchange

async def execute_trade(
    exchange: Union[SpotExchange, FuturesExchange],
    symbol: Symbol,
    side: OrderSide,
    quantity: float,
    price: float
) -> Order:
    """Works with any exchange supporting trading protocol."""
    return await exchange.place_limit_order(symbol, side, quantity, price)
```

### 3. Capability Composition in Implementations

```python
from exchanges.interfaces.capabilities import (
    TradingCapability, BalanceCapability, WithdrawalCapability
)

class MexcSpotExchange(
    CompositePrivateExchange,
    TradingCapability,
    BalanceCapability,
    WithdrawalCapability
):
    """MEXC spot exchange with full capability set."""
    
    async def place_limit_order(self, ...):
        # Implementation
        pass
    
    async def withdraw(self, ...):
        # Implementation
        pass
```

### 4. Separated Domain Pattern Integration

```python
# Public domain - no capabilities required
class MexcPublicExchange(CompositePublicExchange):
    """Pure market data interface - no trading capabilities."""
    # Only implements market data methods
    
# Private domain - implements trading capabilities
class MexcPrivateExchange(
    CompositePrivateExchange,
    TradingCapability,
    BalanceCapability
):
    """Pure trading interface with capabilities."""
    # Implements trading and balance operations
```

## Benefits of Capabilities Architecture

### 1. **Flexibility**
- Mix and match capabilities based on exchange features
- No forced implementation of unsupported operations
- Easy to add new capabilities without breaking existing code

### 2. **Type Safety**
- Runtime type checking with protocols
- Clear capability boundaries
- Compile-time and runtime validation

### 3. **Maintainability**
- Single responsibility per capability
- Clear separation of concerns
- Easy to test individual capabilities

### 4. **Extensibility**
- New capabilities can be added independently
- Existing code continues to work
- Protocol-based design supports evolution

### 5. **Performance**
- Zero overhead from inheritance chains
- Direct method calls without virtual dispatch
- HFT-compliant implementation patterns

## Integration with Composite Architecture

### Composite Public Exchange
- **No capabilities required**: Pure market data interface
- **Focus**: Orderbook streaming, symbol info, market data
- **Pattern**: Template method for initialization

### Composite Private Exchange
- **Implements capabilities**: Trading, Balance, Withdrawal/Position/Leverage
- **Focus**: Order execution, account management
- **Pattern**: Capability composition based on exchange type

### Factory Integration
```python
# Factory creates exchanges with appropriate capabilities
public_exchange = await factory.create_public_exchange('mexc_spot')
# No trading capabilities - market data only

private_exchange = await factory.create_private_exchange('mexc_spot')
# Check capabilities at runtime
if isinstance(private_exchange, SupportsTrading):
    await private_exchange.place_limit_order(...)
```

## HFT Compliance Requirements

### Performance Targets
- **Order Placement**: <50ms end-to-end
- **Order Cancellation**: <30ms confirmation
- **Balance Updates**: Real-time via WebSocket
- **Position Updates**: <10ms propagation (futures)

### Critical Rules
- **No Caching**: Real-time trading data must never be cached
- **WebSocket Priority**: Use WebSocket for all real-time updates
- **REST Fallback**: Use REST only for initialization and recovery
- **Error Recovery**: Automatic reconnection and state recovery

## Implementation Guidelines

### 1. Capability Implementation
- Implement only supported capabilities
- Raise `NotImplementedError` for unsupported operations
- Use abstract base classes for structure
- Follow HFT performance requirements

### 2. Error Handling
- Use `ExchangeError` for all exchange-related failures
- Provide detailed error context
- Support automatic retry for transient errors
- Log all errors with HFT logger

### 3. Testing
- Test each capability independently
- Verify runtime protocol checking
- Validate HFT performance targets
- Test error scenarios thoroughly

## Migration Path

### From Inheritance to Capabilities
1. Identify current interface methods
2. Group into logical capabilities
3. Create protocol definitions
4. Implement capabilities in exchanges
5. Update client code to use runtime checks

### Backward Compatibility
- Existing inheritance-based code continues to work
- Gradual migration to protocol-based checks
- No breaking changes to public APIs
- Deprecation warnings for old patterns

## Future Enhancements

### Planned Capabilities
- **OptionsTrading**: Options-specific operations
- **Staking**: Staking and rewards management
- **Lending**: Margin lending operations
- **Analytics**: Advanced market analytics

### Protocol Extensions
- Nested protocol composition
- Generic protocol parameters
- Async protocol properties
- Protocol versioning support

---

*This specification defines the capabilities architecture that enables flexible, type-safe interface composition for the CEX arbitrage engine. The protocol-based design supports the separated domain pattern while maintaining HFT performance requirements.*