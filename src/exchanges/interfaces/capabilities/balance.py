"""
Balance capability interface for account balance operations.

Universal capability available for both spot and futures exchanges.
Provides account balance tracking functionality.

HFT COMPLIANT: Real-time balance updates via WebSocket.
"""

from abc import ABC, abstractmethod
from typing import Dict
from exchanges.structs.common import AssetBalance
from exchanges.structs.types import AssetName


class BalanceCapability(ABC):
    """
    Account balance operations capability.
    
    Available for both spot and futures exchanges.
    Provides balance queries and real-time updates.
    """
    
    @property
    @abstractmethod
    def balances(self) -> Dict[AssetName, AssetBalance]:
        """
        Get current account balances.
        
        Returns:
            Dictionary mapping asset names to balance information
        """
        pass
    
    @abstractmethod
    async def get_balance(self, asset: AssetName) -> AssetBalance:
        """
        Get balance for specific asset.
        
        Args:
            asset: Asset name to query
            
        Returns:
            Balance information for the asset
            
        Raises:
            ExchangeError: If balance query fails
        """
        pass
    
    @abstractmethod
    async def refresh_balances(self) -> Dict[AssetName, AssetBalance]:
        """
        Refresh all account balances from REST API.
        
        Returns:
            Updated dictionary of all balances
            
        Raises:
            ExchangeError: If balance refresh fails
        """
        pass