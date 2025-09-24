"""
Futures private REST interface with trading and position capabilities.

This interface provides futures trading operations without withdrawal
functionality (which is not available for futures exchanges).
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from exchanges.interfaces.rest.trading_interface import PrivateTradingInterface
from exchanges.structs.common import Symbol, Position


class PrivateFuturesRest(PrivateTradingInterface, ABC):
    """
    Futures private REST interface - Trading + Position capabilities.
    
    Provides:
    - All common trading operations (from PrivateTradingInterface)
    - Futures-specific position management
    - Leverage and margin operations
    
    Does NOT provide:
    - Withdrawal operations (not supported for futures)
    
    This interface is for futures exchanges that support trading
    and position management but not cryptocurrency withdrawals.
    """

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get all open positions for futures trading.
        
        Returns:
            List of Position objects representing current open positions
        """
        pass
    
    @abstractmethod
    async def get_position(self, symbol: Symbol) -> Optional[Position]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: The futures symbol to get position for
            
        Returns:
            Position object if exists, None otherwise
        """
        pass

    # @abstractmethod
    # async def set_leverage(self, symbol: Symbol, leverage: int) -> bool:
    #     """
    #     Set leverage for a symbol.
    #
    #     Args:
    #         symbol: Trading symbol
    #         leverage: Leverage multiplier to set
    #
    #     Returns:
    #         True if leverage set successfully
    #
    #     Raises:
    #         ExchangeAPIError: If leverage setting fails
    #     """
    #     pass
    #
    # @abstractmethod
    # async def get_leverage(self, symbol: Symbol) -> int:
    #     """
    #     Get current leverage for a symbol.
    #
    #     Args:
    #         symbol: Trading symbol
    #
    #     Returns:
    #         Current leverage multiplier
    #
    #     Raises:
    #         ExchangeAPIError: If leverage query fails
    #     """
    #     pass
    #
    # @abstractmethod
    # async def set_margin_mode(self, symbol: Symbol, margin_mode: str) -> bool:
    #     """
    #     Set margin mode for a symbol (isolated/cross).
    #
    #     Args:
    #         symbol: Trading symbol
    #         margin_mode: Margin mode ('isolated' or 'cross')
    #
    #     Returns:
    #         True if margin mode set successfully
    #
    #     Raises:
    #         ExchangeAPIError: If margin mode setting fails
    #     """
    #     pass
    #
    # @abstractmethod
    # async def add_margin(self, symbol: Symbol, amount: float) -> bool:
    #     """
    #     Add margin to a position.
    #
    #     Args:
    #         symbol: Trading symbol
    #         amount: Amount of margin to add
    #
    #     Returns:
    #         True if margin added successfully
    #
    #     Raises:
    #         ExchangeAPIError: If margin addition fails
    #     """
    #     pass
    

