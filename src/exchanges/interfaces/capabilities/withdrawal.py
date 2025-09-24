"""
Withdrawal capability interface for crypto withdrawal operations.

SPOT-ONLY capability for exchanges that support withdrawals.
Not available for futures/derivatives exchanges.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from exchanges.structs.common import (
    WithdrawalRequest, WithdrawalResponse
)
from exchanges.structs.types import AssetName


class WithdrawalCapability(ABC):
    """
    Cryptocurrency withdrawal operations capability.
    
    SPOT-ONLY: Only available for spot exchanges.
    Provides withdrawal submission, cancellation, and history.
    """
    
    @abstractmethod
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """
        Submit a withdrawal request.

        Args:
            request: Withdrawal request parameters

        Returns:
            WithdrawalResponse with withdrawal details

        Raises:
            ExchangeError: If withdrawal submission fails
            ValidationError: If request parameters are invalid
        """
        pass

    @abstractmethod
    async def cancel_withdrawal(self, withdrawal_id: str) -> bool:
        """
        Cancel a pending withdrawal.

        Args:
            withdrawal_id: Exchange withdrawal ID to cancel

        Returns:
            True if cancellation successful, False otherwise

        Raises:
            ExchangeError: If cancellation fails
        """
        pass

    @abstractmethod
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """
        Get current status of a withdrawal.

        Args:
            withdrawal_id: Exchange withdrawal ID

        Returns:
            WithdrawalResponse with current status

        Raises:
            ExchangeError: If withdrawal not found or query fails
        """
        pass

    @abstractmethod
    async def get_withdrawal_history(
        self,
        asset: Optional[AssetName] = None,
        limit: int = 100
    ) -> List[WithdrawalResponse]:
        """
        Get withdrawal history.

        Args:
            asset: Optional asset filter
            limit: Maximum number of withdrawals to return

        Returns:
            List of historical withdrawals
        """
        pass

    @abstractmethod
    async def validate_withdrawal_address(
        self,
        asset: AssetName,
        address: str,
        network: Optional[str] = None
    ) -> bool:
        """
        Validate withdrawal address format.

        Args:
            asset: Asset name
            address: Destination address
            network: Network/chain name

        Returns:
            True if address is valid, False otherwise
        """
        pass

    @abstractmethod
    async def get_withdrawal_limits(
        self,
        asset: AssetName,
        network: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get withdrawal limits for an asset.

        Args:
            asset: Asset name
            network: Network/chain name

        Returns:
            Dictionary with 'min', 'max', and 'fee' limits
        """
        pass