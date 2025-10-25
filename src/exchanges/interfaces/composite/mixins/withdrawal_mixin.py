"""
Withdrawal mixin for spot exchanges only.

This mixin provides withdrawal functionality that should only be
available for spot exchanges, not futures/derivatives exchanges.
It delegates to the underlying REST client for actual implementation.
"""

from typing import Dict, List, Optional, TYPE_CHECKING, Protocol
from exchanges.structs.common import (
    AssetInfo,
    WithdrawalRequest,
    WithdrawalResponse,
    DepositResponse,
    DepositAddress
)
from exchanges.structs.types import AssetName

if TYPE_CHECKING:
    from exchanges.interfaces.rest import PrivateSpotRestInterface
    from infrastructure.logging import HFTLoggerInterface


class WithdrawalMixinProtocol(Protocol):
    """Protocol defining expected attributes for classes using WithdrawalMixin."""
    _rest: Optional['PrivateSpotRestInterface']
    _assets_info: Dict[AssetName, AssetInfo]
    logger: 'HFTLoggerInterface'


class WithdrawalMixin:
    """
    Mixin providing withdrawal functionality for spot exchanges only.
    
    This mixin implements the WithdrawalInterface and delegates all
    operations to the underlying private REST client. It should only
    be mixed into spot exchange implementations, not futures exchanges.
    
    Requirements:
        - The class using this mixin must have a _rest attribute
        - The _rest client must implement WithdrawalInterface
    """
    
    # Type hint to resolve IDE warnings
    _rest: Optional['PrivateSpotRestInterface']
    # assets_info: Dict[AssetName, AssetInfo]
    logger: 'HFTLoggerInterface'
    
    async def get_assets_info(self) -> Dict[AssetName, AssetInfo]:
        """
        Get currency information including deposit/withdrawal status and network details.
        Delegates to REST client.
        
        Returns:
            Dictionary mapping AssetName to AssetInfo with network configurations
            
        Raises:
            NotImplementedError: If private REST client is not available
            ExchangeAPIError: If unable to fetch currency information
        """

        return await self._rest.get_assets_info()

    async def get_deposit_address(self, asset: AssetName, network: Optional[str] = None) -> DepositAddress:
        return await self._rest.get_deposit_address(asset, network)
    
    async def submit_withdrawal(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """
        Submit a withdrawal request to the exchange.
        Delegates to REST client.
        
        Args:
            request: Withdrawal request parameters
            
        Returns:
            WithdrawalResponse with withdrawal details
            
        Raises:
            NotImplementedError: If private REST client is not available
            ExchangeAPIError: If withdrawal submission fails
        """
        if not hasattr(self, '_rest') or self._rest is None:
            raise NotImplementedError("Private REST client required for withdrawal operations")
        
        return await self._rest.submit_withdrawal(request)
    
    async def cancel_withdrawal(self, withdrawal_id: str) -> bool:
        """
        Cancel a pending withdrawal.
        Delegates to REST client.
        
        Args:
            withdrawal_id: Exchange withdrawal ID to cancel
            
        Returns:
            True if cancellation successful, False otherwise
            
        Raises:
            NotImplementedError: If private REST client is not available
            ExchangeAPIError: If cancellation fails
        """

        return await self._rest.cancel_withdrawal(withdrawal_id)
    
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse | None:
        """
        Get current status of a withdrawal.
        Delegates to REST client.
        
        Args:
            withdrawal_id: Exchange withdrawal ID
            
        Returns:
            WithdrawalResponse with current status
            
        Raises:
            NotImplementedError: If private REST client is not available
            ExchangeAPIError: If withdrawal not found or query fails
        """

        return await self._rest.get_withdrawal_status(withdrawal_id)
    
    async def get_withdrawal_history(
        self,
        asset: Optional[AssetName] = None,
        limit: int = 100
    ) -> List[WithdrawalResponse]:
        """
        Get withdrawal history.
        Delegates to REST client.
        
        Args:
            asset: Optional asset filter
            limit: Maximum number of withdrawals to return
            
        Returns:
            List of historical withdrawals
            
        Raises:
            NotImplementedError: If private REST client is not available
        """
        if not hasattr(self, '_rest') or self._rest is None:
            raise NotImplementedError("Private REST client required for withdrawal operations")
        
        return await self._rest.get_withdrawal_history(asset, limit)
    
    async def get_deposit_history(
        self,
        asset: Optional[AssetName] = None,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[DepositResponse]:
        """
        Get deposit history with optional time filtering.
        Delegates to REST client.
        
        Args:
            asset: Optional asset filter
            limit: Maximum number of deposits to return
            start_time: Optional start time in milliseconds since epoch
            end_time: Optional end time in milliseconds since epoch
            
        Returns:
            List of historical deposits
            
        Raises:
            NotImplementedError: If private REST client is not available
            ExchangeAPIError: If unable to fetch deposit history
        """

        return await self._rest.get_deposit_history(asset, limit, start_time, end_time)
    
    async def deposit_history(
        self,
        asset: Optional[AssetName] = None,
        limit: int = 100
    ) -> List[DepositResponse]:
        """
        Get deposit history (legacy method for backward compatibility).
        Delegates to REST client.
        
        Args:
            asset: Optional asset filter
            limit: Maximum number of deposits to return
            
        Returns:
            List of historical deposits
        """
        if not hasattr(self, '_rest') or self._rest is None:
            raise NotImplementedError("Private REST client required for deposit operations")
        
        return await self._rest.deposit_history(asset, limit)
    
    # Additional helper methods specific to composite usage
    
    def _has_withdrawal_capability(self) -> bool:
        """
        Check if this exchange instance has withdrawal capability.
        
        Returns:
            True if private REST client is available for withdrawals
        """
        return hasattr(self, '_rest') and self._rest is not None
    
    async def get_withdrawal_limits(
        self,
        asset: AssetName,
        network: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get withdrawal limits for an asset and network.
        Leverages the validate methods from WithdrawalInterface.
        
        Args:
            asset: Asset name
            network: Network/chain name
            
        Returns:
            Dictionary with 'min', 'max', and 'fee' limits
            
        Raises:
            NotImplementedError: If private REST client is not available
        """
        if not self._has_withdrawal_capability():
            raise NotImplementedError("Private REST client required for withdrawal operations")
        
        # Use the inherited method from WithdrawalInterface
        return await self.get_withdrawal_limits_for_asset(asset, network)
    
    async def validate_withdrawal(self, request: WithdrawalRequest) -> None:
        """
        Validate withdrawal request parameters before submission.
        
        Args:
            request: Withdrawal request to validate
            
        Raises:
            ValueError: If validation fails
            NotImplementedError: If private REST client is not available
        """
        if not self._has_withdrawal_capability():
            raise NotImplementedError("Private REST client required for withdrawal validation")
        
        return await self.validate_withdrawal_request(request)