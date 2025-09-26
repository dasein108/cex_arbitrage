"""
Spot private REST interface with trading and withdrawal capabilities.

This interface combines common trading operations with spot-specific
withdrawal functionality.
"""

from abc import ABC
from exchanges.interfaces.rest.interfaces.trading_interface import PrivateTradingInterface
from exchanges.interfaces.rest.interfaces.withdrawal_interface import WithdrawalInterface


class PrivateSpotRest(PrivateTradingInterface, WithdrawalInterface, ABC):
    """
    Spot private REST interface - Trading + Withdrawal capabilities.
    
    Combines:
    - All common trading operations (from PrivateTradingInterface)
    - Withdrawal operations (from WithdrawalInterface) - SPOT ONLY
    
    This interface is for spot exchanges that support both trading
    and cryptocurrency withdrawals.
    """
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
    
