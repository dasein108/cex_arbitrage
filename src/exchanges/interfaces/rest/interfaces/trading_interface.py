"""
Core trading interface for both spot and futures exchanges.

This interface provides common trading operations that are available
for both spot and futures exchanges.
"""

from abc import abstractmethod, ABC
from typing import Dict, List, Optional
from exchanges.structs.common import (
    Symbol,
    Order,
    AssetBalance
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs.enums import TimeInForce
from exchanges.structs import OrderType, Side

class PrivateTradingInterface(ABC):
    """Abstract interface for private exchange trading operations (both spot and futures)"""
    CAN_MODIFY_ORDERS = False  # Default capability flag for modifying orders

    @abstractmethod
    async def get_balances(self) -> List[AssetBalance]:
        """Get account balance for all assets"""
        pass
    
    @abstractmethod
    async def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """Get balance for a specific asset"""
        pass

    @abstractmethod
    async def modify_order(
        self,
        symbol: Symbol,
        order_id: OrderId,
        qunatity: Optional[float] = None,
        price: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        stop_price: Optional[float] = None
    ) -> Order:
        """Modify an existing order (if supported)"""
        pass
    
    @abstractmethod
    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        order_type: OrderType,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        stop_price: Optional[float] = None,
        iceberg_qty: Optional[float] = None,
        new_order_resp_type: Optional[str] = None
    ) -> Order:
        """Place a new order with comprehensive parameters"""
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Cancel an active order"""
        pass
    
    @abstractmethod
    async def cancel_all_orders(self, symbol: Symbol) -> List[Order]:
        """Cancel all open orders for a symbol"""
        pass
    
    @abstractmethod
    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Query order status"""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """Get all open orders for account or symbol"""
        pass