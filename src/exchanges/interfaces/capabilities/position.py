"""
Position capability interface for futures/derivatives position management.

FUTURES-ONLY capability for exchanges that support leveraged trading.
Not available for spot exchanges.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from exchanges.structs.common import Symbol, Position


class PositionCapability(ABC):
    """
    Position management operations capability.
    
    FUTURES-ONLY: Only available for futures/derivatives exchanges.
    Provides position tracking and management.
    """
    
    @property
    @abstractmethod
    def positions(self) -> Dict[Symbol, Position]:
        """
        Get current open positions.
        
        Returns:
            Dictionary mapping symbols to position information
        """
        pass
    
    @abstractmethod
    async def get_position(self, symbol: Symbol) -> Optional[Position]:
        """
        Get position for specific symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position information if exists, None otherwise
            
        Raises:
            ExchangeError: If position query fails
        """
        pass
    
    @abstractmethod
    async def close_position(self, symbol: Symbol, quantity: Optional[float] = None) -> bool:
        """
        Close an open position.
        
        Args:
            symbol: Trading symbol
            quantity: Optional quantity to close (None = close all)
            
        Returns:
            True if position closed successfully
            
        Raises:
            ExchangeError: If position closing fails
        """
        pass
    
    @abstractmethod
    async def get_position_history(
        self,
        symbol: Optional[Symbol] = None,
        limit: int = 100
    ) -> List[Position]:
        """
        Get historical positions.
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum number of positions to return
            
        Returns:
            List of historical positions
        """
        pass
    
    @abstractmethod
    async def refresh_positions(self) -> Dict[Symbol, Position]:
        """
        Refresh all positions from REST API.
        
        Returns:
            Updated dictionary of all positions
            
        Raises:
            ExchangeError: If position refresh fails
        """
        pass