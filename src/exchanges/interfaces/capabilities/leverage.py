"""
Leverage capability interface for margin and leverage operations.

FUTURES-ONLY capability for exchanges that support leveraged trading.
Not available for spot exchanges.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from infrastructure.data_structures.common import Symbol


class LeverageCapability(ABC):
    """
    Leverage and margin operations capability.
    
    FUTURES-ONLY: Only available for futures/derivatives exchanges.
    Provides leverage adjustment and margin management.
    """
    
    @abstractmethod
    async def get_leverage(self, symbol: Symbol) -> int:
        """
        Get current leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current leverage multiplier
            
        Raises:
            ExchangeError: If leverage query fails
        """
        pass
    
    @abstractmethod
    async def set_leverage(self, symbol: Symbol, leverage: int) -> bool:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage multiplier to set
            
        Returns:
            True if leverage set successfully
            
        Raises:
            ExchangeError: If leverage setting fails
            ValidationError: If leverage value is invalid
        """
        pass
    
    @abstractmethod
    async def get_max_leverage(self, symbol: Symbol) -> int:
        """
        Get maximum allowed leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Maximum leverage multiplier allowed
            
        Raises:
            ExchangeError: If query fails
        """
        pass
    
    @abstractmethod
    async def get_margin_info(self, symbol: Symbol) -> Dict[str, float]:
        """
        Get margin information for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with margin information:
            - 'initial_margin': Initial margin requirement
            - 'maintenance_margin': Maintenance margin requirement
            - 'margin_ratio': Current margin ratio
            - 'available_margin': Available margin for trading
            
        Raises:
            ExchangeError: If margin query fails
        """
        pass
    
    @abstractmethod
    async def add_margin(self, symbol: Symbol, amount: float) -> bool:
        """
        Add margin to an existing position.
        
        Args:
            symbol: Trading symbol
            amount: Amount of margin to add
            
        Returns:
            True if margin added successfully
            
        Raises:
            ExchangeError: If adding margin fails
        """
        pass
    
    @abstractmethod
    async def set_margin_mode(self, symbol: Symbol, mode: str) -> bool:
        """
        Set margin mode (cross/isolated) for a symbol.
        
        Args:
            symbol: Trading symbol
            mode: Margin mode ('cross' or 'isolated')
            
        Returns:
            True if margin mode set successfully
            
        Raises:
            ExchangeError: If setting margin mode fails
            ValidationError: If mode is invalid
        """
        pass