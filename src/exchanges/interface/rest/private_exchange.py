from abc import abstractmethod
from typing import Dict, List, Optional
from structs.exchange import (
    Symbol,
    Order,
    OrderId,
    OrderType,
    Side,
    AssetBalance,
    AssetName,
    ExchangeName
)

# Import the base interface
from exchanges.interface.rest.base_exchange import BaseExchangeInterface


class PrivateExchangeInterface(BaseExchangeInterface):
    """Abstract interface for private exchange operations (trading, account management)"""
    
    def __init__(self, exchange: ExchangeName, api_key: str, secret_key: str, base_url: str):
        self.exchange = exchange
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        
    
    @abstractmethod
    async def get_account_balance(self) -> Dict[AssetName, AssetBalance]:
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
        quantity: Optional[float] = None,
        price: Optional[float] = None
    ) -> Order:
        """Modify an existing order (if supported)"""
        pass
    
    @abstractmethod
    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        order_type: OrderType,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        time_in_force: Optional[str] = None,
    ) -> Order:
        """Place a new order"""
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
    
    # @abstractmethod
    # async def get_order_history(
    #     self,
    #     symbol: Symbol,
    #     limit: int = 500,
    #     start_time: Optional[int] = None,
    #     end_time: Optional[int] = None
    # ) -> List[Order]:
    #     """Get order history"""
    #     pass
    #
    # @abstractmethod
    # async def get_trade_history(
    #     self,
    #     symbol: Symbol,
    #     limit: int = 500,
    #     start_time: Optional[int] = None,
    #     end_time: Optional[int] = None
    # ) -> List[Trade]:
    #     """Get account trade history"""
    #     pass
    
