"""
Protocol definitions for runtime capability detection in HFT trading systems.

This module defines runtime-checkable protocols that enable flexible interface
composition without inheritance. These protocols support the separated domain
architecture where public (market data) and private (trading) interfaces are
completely isolated.

## Core Design Principles

1. **Runtime Type Safety**: Use Python's Protocol with @runtime_checkable for
   duck typing support and runtime validation.

2. **Zero Inheritance**: Exchanges can implement capabilities through structural
   compatibility without explicit inheritance chains.

3. **HFT Compliance**: All protocols follow strict performance requirements with
   sub-50ms execution targets for trading operations.

4. **Domain Separation**: Protocols are organized by domain (universal, spot-only,
   futures-only) to support the separated architecture pattern.

## Usage Patterns

### Runtime Capability Detection
```python
if isinstance(exchange, SupportsWithdrawal):
    # Safe to call withdrawal methods
    response = await exchange.withdraw(request)
```

### Type-Safe Function Parameters
```python
def execute_trade(exchange: SupportsTrading) -> Order:
    return await exchange.place_limit_order(...)
```

### Protocol Composition
```python
class MyExchange(SupportsTrading, SupportsBalance):
    # Implement required methods
    pass
```

## Performance Requirements

- Order operations: <50ms end-to-end
- Balance updates: Real-time via WebSocket
- Position tracking: <10ms propagation (futures)
- No caching of real-time trading data

## Related Specifications

- See capabilities-architecture.md for complete architecture overview
- See separated-domain-pattern.md for domain separation details
- See hft-requirements-compliance.md for performance targets
"""

from typing import Protocol, runtime_checkable, Dict, List, Optional
from exchanges.structs.common import (
    Symbol, Order, AssetBalance,
    Position, WithdrawalRequest, WithdrawalResponse
)
from exchanges.structs.types import AssetName
from exchanges.structs.enums import OrderSide


@runtime_checkable
class SupportsTrading(Protocol):
    """
    Protocol for exchanges that support trading operations.
    
    This protocol defines the core trading interface that must be implemented
    by any exchange supporting order management. It's a universal capability
    available for both spot and futures exchanges.
    
    ## HFT Performance Requirements
    
    - place_limit_order: <50ms end-to-end execution
    - place_market_order: <30ms execution for immediate fills
    - cancel_order: <30ms confirmation response
    - get_order_status: <20ms query response
    
    ## Implementation Guidelines
    
    1. All methods must be async for non-blocking execution
    2. Use WebSocket for real-time order updates when available
    3. Implement automatic retry logic for transient failures
    4. Log all operations with HFT performance metrics
    
    ## Error Handling
    
    All methods should raise ExchangeError or its subclasses for failures:
    - InsufficientBalanceError: Not enough funds
    - OrderNotFoundError: Order doesn't exist
    - RateLimitError: API rate limit exceeded
    - NetworkError: Connection issues
    
    Example:
        ```python
        exchange: SupportsTrading = get_exchange()
        
        # Place a limit order
        order = await exchange.place_limit_order(
            symbol=Symbol('BTC', 'USDT'),
            side=OrderSide.BUY,
            quantity=0.001,
            price=50000.0
        )
        
        # Cancel the order
        cancelled = await exchange.cancel_order(
            symbol=order.symbol,
            order_id=order.order_id
        )
        ```
    """
    
    async def place_limit_order(
        self, symbol: Symbol, side: OrderSide, 
        quantity: float, price: float, **kwargs
    ) -> Order: ...
    
    async def place_market_order(
        self, symbol: Symbol, side: OrderSide, 
        quantity: float, **kwargs
    ) -> Order: ...
    
    async def cancel_order(self, symbol: Symbol, order_id: str) -> bool: ...
    
    async def get_order_status(self, symbol: Symbol, order_id: str) -> Order: ...
    
    async def get_order_history(
        self, symbol: Optional[Symbol] = None, limit: int = 100
    ) -> List[Order]: ...


@runtime_checkable
class SupportsBalance(Protocol):
    """
    Protocol for exchanges that support account balance operations.
    
    This protocol defines the interface for querying and managing account balances.
    It's a universal capability required by both spot and futures exchanges for
    proper position and capital management.
    
    ## Real-Time Updates
    
    Balances should be updated in real-time via WebSocket when available:
    - WebSocket updates modify the cached `balances` property
    - REST API calls via `refresh_balances()` provide fallback/recovery
    - No caching of balance data beyond current state (HFT rule)
    
    ## Implementation Requirements
    
    1. `balances` property must return current cached state
    2. WebSocket updates must modify this cached state
    3. `refresh_balances()` forces REST API refresh
    4. All balance values use Decimal for precision
    
    Example:
        ```python
        exchange: SupportsBalance = get_exchange()
        
        # Get cached balances (updated via WebSocket)
        all_balances = exchange.balances
        
        # Get specific asset balance
        btc_balance = await exchange.get_balance(AssetName('BTC'))
        print(f"Available: {btc_balance.available}, Locked: {btc_balance.locked}")
        
        # Force refresh from REST API
        updated = await exchange.refresh_balances()
        ```
    """
    
    @property
    def balances(self) -> Dict[AssetName, AssetBalance]: ...
    
    async def get_balance(self, asset: AssetName) -> AssetBalance: ...
    
    async def refresh_balances(self) -> Dict[AssetName, AssetBalance]: ...


@runtime_checkable
class SupportsWithdrawal(Protocol):
    """Protocol for exchanges that support withdrawal operations (SPOT-ONLY)."""
    
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse: ...
    
    async def cancel_withdrawal(self, withdrawal_id: str) -> bool: ...
    
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse: ...
    
    async def get_withdrawal_history(
        self, asset: Optional[AssetName] = None, limit: int = 100
    ) -> List[WithdrawalResponse]: ...
    
    async def validate_withdrawal_address(
        self, asset: AssetName, address: str, network: Optional[str] = None
    ) -> bool: ...
    
    async def get_withdrawal_limits(
        self, asset: AssetName, network: Optional[str] = None
    ) -> Dict[str, float]: ...


@runtime_checkable
class SupportsPositions(Protocol):
    """Protocol for exchanges that support position management (FUTURES-ONLY)."""
    
    @property
    def positions(self) -> Dict[Symbol, Position]: ...
    
    async def get_position(self, symbol: Symbol) -> Optional[Position]: ...
    
    async def close_position(self, symbol: Symbol, quantity: Optional[float] = None) -> bool: ...
    
    async def get_position_history(
        self, symbol: Optional[Symbol] = None, limit: int = 100
    ) -> List[Position]: ...
    
    async def refresh_positions(self) -> Dict[Symbol, Position]: ...


@runtime_checkable
class SupportsLeverage(Protocol):
    """Protocol for exchanges that support leverage operations (FUTURES-ONLY)."""
    
    async def get_leverage(self, symbol: Symbol) -> int: ...
    
    async def set_leverage(self, symbol: Symbol, leverage: int) -> bool: ...
    
    async def get_max_leverage(self, symbol: Symbol) -> int: ...
    
    async def get_margin_info(self, symbol: Symbol) -> Dict[str, float]: ...
    
    async def add_margin(self, symbol: Symbol, amount: float) -> bool: ...
    
    async def set_margin_mode(self, symbol: Symbol, mode: str) -> bool: ...


@runtime_checkable
class SpotExchange(Protocol):
    """Protocol for spot exchanges (trading + balance + withdrawal)."""
    
    # Trading operations
    async def place_limit_order(
        self, symbol: Symbol, side: OrderSide, 
        quantity: float, price: float, **kwargs
    ) -> Order: ...
    
    async def cancel_order(self, symbol: Symbol, order_id: str) -> bool: ...
    
    # Balance operations
    @property
    def balances(self) -> Dict[AssetName, AssetBalance]: ...
    
    # Withdrawal operations
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse: ...


@runtime_checkable
class FuturesExchange(Protocol):
    """Protocol for futures exchanges (trading + balance + position + leverage)."""
    
    # Trading operations
    async def place_limit_order(
        self, symbol: Symbol, side: OrderSide, 
        quantity: float, price: float, **kwargs
    ) -> Order: ...
    
    async def cancel_order(self, symbol: Symbol, order_id: str) -> bool: ...
    
    # Balance operations
    @property
    def balances(self) -> Dict[AssetName, AssetBalance]: ...
    
    # Position operations
    @property
    def positions(self) -> Dict[Symbol, Position]: ...
    
    async def close_position(self, symbol: Symbol, quantity: Optional[float] = None) -> bool: ...
    
    # Leverage operations
    async def get_leverage(self, symbol: Symbol) -> int: ...
    
    async def set_leverage(self, symbol: Symbol, leverage: int) -> bool: ...