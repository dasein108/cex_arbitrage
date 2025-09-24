"""
Protocol definitions for runtime capability detection.

These protocols enable type-safe runtime checking of exchange capabilities
without requiring inheritance. Used for determining which operations
an exchange supports at runtime.

Usage:
    if isinstance(exchange, SupportsWithdrawal):
        # Safe to call withdrawal methods
        await exchange.withdraw(request)
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
    """Protocol for exchanges that support trading operations."""
    
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
    """Protocol for exchanges that support balance operations."""
    
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