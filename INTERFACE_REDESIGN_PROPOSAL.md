# Interface Architecture Redesign Proposal

## Problem Analysis

The current interface architecture has misaligned capabilities:

1. **Withdrawal operations** are in `CompositePrivateExchange` but only available for spot exchanges
2. **Leverage operations** are futures-only but mixed with general trading
3. **Position management** is futures-specific but not properly separated
4. **Trading operations** are duplicated across spot/futures inheritance chains

## Proposed New Architecture

### 1. Core Interface Hierarchy

```
BaseCompositeExchange (connection & state management)
├── CompositePublicExchange (market data only)
├── CompositePrivateSpotExchange (spot trading + withdrawals)  
└── CompositePrivateFuturesExchange (futures trading + leverage + positions)
```

### 2. Capability-Based Mixins

Each exchange type inherits only the capabilities it actually supports:

```python
# Spot exchanges get withdrawal capabilities
class CompositePrivateSpotExchange(
    CompositePublicExchange, 
    TradingCapability,
    BalanceCapability, 
    WithdrawalCapability
):
    pass

# Futures exchanges get leverage and position capabilities  
class CompositePrivateFuturesExchange(
    CompositePublicExchange,
    TradingCapability,
    BalanceCapability,
    LeverageCapability,
    PositionCapability
):
    pass
```

### 3. Concrete Interface Definitions

#### A. CompositePrivateSpotExchange

```python
from abc import abstractmethod
from typing import Dict, List, Optional
from exchanges.structs.common import (
    Symbol, AssetBalance, Order, WithdrawalRequest, WithdrawalResponse
)
from .base_public_exchange import CompositePublicExchange
from ..capabilities.trading import TradingCapability
from ..capabilities.balance import BalanceCapability
from ..capabilities.withdrawal import WithdrawalCapability


class CompositePrivateSpotExchange(
    CompositePublicExchange,
    TradingCapability,
    BalanceCapability,
    WithdrawalCapability
):
    """
    Private spot exchange with trading and withdrawal capabilities.
    
    Provides:
    - Market data (inherited from CompositePublicExchange)
    - Spot trading (buy/sell orders)
    - Balance management
    - Cryptocurrency withdrawals (SPOT-ONLY)
    """

    def __init__(self, config):
        super().__init__(config)
        self._tag = f'{config.name}_private_spot'

        # Spot-specific state
        self._balances: Dict[str, AssetBalance] = {}
        self._open_orders: Dict[Symbol, List[Order]] = {}

    # Properties (from capabilities)
    @property
    @abstractmethod
    def balances(self) -> Dict[str, AssetBalance]:
        """Get current spot balances."""
        pass

    @property
    @abstractmethod
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """Get current open spot orders."""
        pass

    # Trading operations (from TradingCapability)
    # Implementation inherits from capability interface

    # Balance operations (from BalanceCapability)  
    # Implementation inherits from capability interface

    # Withdrawal operations (from WithdrawalCapability)
    # Implementation inherits from capability interface

    # Spot-specific initialization
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        await super().initialize(symbols)
        await self._load_balances()
        await self._load_open_orders()

    async def _refresh_exchange_data(self) -> None:
        await super()._refresh_exchange_data()
        await self._load_balances()
        await self._load_open_orders()
```

#### B. CompositePrivateFuturesExchange

```python
from abc import abstractmethod
from typing import Dict, List, Optional
from exchanges.structs.common import Symbol, AssetBalance, Order, Position
from .base_public_exchange import CompositePublicExchange
from ..capabilities.trading import TradingCapability
from ..capabilities.balance import BalanceCapability
from ..capabilities.leverage import LeverageCapability
from ..capabilities.position import PositionCapability


class CompositePrivateFuturesExchange(
    CompositePublicExchange,
    TradingCapability,
    BalanceCapability,
    LeverageCapability,
    PositionCapability
):
    """
    Private futures exchange with trading, leverage, and position capabilities.
    
    Provides:
    - Market data (inherited from CompositePublicExchange)
    - Futures trading (long/short positions)
    - Balance management
    - Leverage control (FUTURES-ONLY)
    - Position management (FUTURES-ONLY)
    
    Does NOT provide:
    - Withdrawal operations (not supported for futures)
    """

    def __init__(self, config):
        super().__init__(config)
        self._tag = f'{config.name}_private_futures'

        # Futures-specific state
        self._balances: Dict[str, AssetBalance] = {}
        self._open_orders: Dict[Symbol, List[Order]] = {}
        self._positions: Dict[Symbol, Position] = {}

    # Properties (from capabilities)
    @property
    @abstractmethod
    def balances(self) -> Dict[str, AssetBalance]:
        """Get current futures balances."""
        pass

    @property
    @abstractmethod
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """Get current open futures orders."""
        pass

    @property
    @abstractmethod
    def positions(self) -> Dict[Symbol, Position]:
        """Get current futures positions."""
        pass

    # Trading operations (from TradingCapability)
    # Implementation inherits from capability interface

    # Balance operations (from BalanceCapability)
    # Implementation inherits from capability interface

    # Leverage operations (from LeverageCapability) 
    # Implementation inherits from capability interface

    # Position operations (from PositionCapability)
    # Implementation inherits from capability interface

    # Futures-specific initialization
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        await super().initialize(symbols)
        await self._load_balances()
        await self._load_open_orders()
        await self._load_positions()

    async def _refresh_exchange_data(self) -> None:
        await super()._refresh_exchange_data()
        await self._load_balances()
        await self._load_open_orders()
        await self._load_positions()
```

### 4. Factory Pattern Updates

```python
class ExchangeFactory:
    @staticmethod
    def create_spot_private_exchange(
        exchange: ExchangeEnum,
        config: ExchangeConfig
    ) -> CompositePrivateSpotExchange:
        """Create spot private exchange with withdrawal capabilities."""
        pass
    
    @staticmethod
    def create_futures_private_exchange(
        exchange: ExchangeEnum, 
        config: ExchangeConfig
    ) -> CompositePrivateFuturesExchange:
        """Create futures private exchange with leverage capabilities."""
        pass
```

## Benefits of This Architecture

### 1. Clear Capability Separation
- **Spot exchanges**: Get withdrawal capabilities they actually support
- **Futures exchanges**: Get leverage/position capabilities they actually support  
- **No capability pollution**: Each exchange type only inherits what it can do

### 2. Type Safety
- **Compile-time validation**: Cannot call withdrawal methods on futures exchanges
- **IDE support**: Auto-completion shows only available methods for each exchange type
- **Factory pattern**: Ensures correct exchange type creation

### 3. Code Clarity
- **Single responsibility**: Each interface has a clear, focused purpose
- **No dead code**: No unused abstract methods that can't be implemented
- **Maintainability**: Easy to understand what each exchange type can do

### 4. HFT Performance Benefits
- **Smaller interface surface**: Fewer methods to implement and maintain
- **Optimized inheritance**: No unnecessary method calls or capability checks
- **Clear data flow**: Each exchange manages only its relevant state

## Migration Strategy

### Phase 1: Create New Interfaces
1. Create `CompositePrivateSpotExchange` with withdrawal capabilities
2. Create updated `CompositePrivateFuturesExchange` without withdrawal capabilities
3. Update capability interfaces if needed

### Phase 2: Update Exchange Implementations  
1. Update MEXC implementation to use new spot interface
2. Update GateIO implementation to use appropriate interface (spot vs futures)
3. Test all trading and withdrawal operations

### Phase 3: Update Factory and Remove Old Interfaces
1. Add new factory methods for spot/futures creation
2. Update existing factory methods to use new interfaces
3. Remove old `CompositePrivateExchange` interface
4. Update all import statements across codebase

This redesign maintains the pragmatic architectural principles from CLAUDE.md while providing proper capability separation and type safety.