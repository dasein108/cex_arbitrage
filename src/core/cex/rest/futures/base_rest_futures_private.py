from typing import List, Optional
from structs.exchange import (
    Symbol,
    Position
)

from abc import ABC
from core.cex.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface


class PrivateExchangeFuturesRestInterface(PrivateExchangeSpotRestInterface, ABC):
    """Abstract cex for private futures exchange operations (trading, account management)"""

    async def get_positions(self) -> List[Position]:
        """
        Get all open positions for futures trading.
        
        Returns:
            List of Position objects representing current open positions
        """
        raise NotImplementedError("get_positions method not implemented")
    
    async def get_position(self, symbol: Symbol) -> Optional[Position]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: The futures symbol to get position for
            
        Returns:
            Position object if exists, None otherwise
        """
        raise NotImplementedError("get_position method not implemented")
    

