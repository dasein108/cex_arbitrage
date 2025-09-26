"""
Withdrawal interface for spot exchanges only.

This interface provides withdrawal operations that are only available
for spot exchanges, not for futures/derivatives exchanges.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from exchanges.structs.common import (
    AssetInfo,
    WithdrawalRequest,
    WithdrawalResponse
)
from exchanges.structs.types import AssetName


class WithdrawalInterface(ABC):
    """
    Withdrawal operations interface - SPOT ONLY.
    
    Provides cryptocurrency withdrawal functionality that is only
    available for spot exchanges, not futures/derivatives.
    """

    @abstractmethod
    async def get_currency_info(self) -> Dict[AssetName, AssetInfo]:
        """
        Get currency information including deposit/withdrawal status and network details.

        Returns:
            Dictionary mapping AssetName to AssetInfo with network configurations

        Raises:
            ExchangeAPIError: If unable to fetch currency information
        """
        pass

    @abstractmethod
    async def submit_withdrawal(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """
        Submit a withdrawal request to the exchange.

        Args:
            request: Withdrawal request parameters

        Returns:
            WithdrawalResponse with withdrawal details

        Raises:
            ExchangeAPIError: If withdrawal submission fails
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
            ExchangeAPIError: If cancellation fails
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
            ExchangeAPIError: If withdrawal not found
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

    # Withdrawal validation methods (with common implementation)

    async def validate_withdrawal_request(self, request: WithdrawalRequest) -> None:
        """
        Validate withdrawal request parameters.

        Args:
            request: Withdrawal request to validate

        Raises:
            ValueError: If validation fails
        """
        # Get currency info for validation
        currency_info = await self.get_currency_info()
        asset_info = currency_info.get(request.asset)

        if not asset_info:
            raise ValueError(f"Asset {request.asset} not supported")

        if not asset_info.withdraw_enable:
            raise ValueError(f"Withdrawals disabled for asset {request.asset}")

        # Validate network if specified
        if request.network:
            network_info = asset_info.networks.get(request.network)
            if not network_info:
                raise ValueError(f"Network {request.network} not supported for {request.asset}")

            if not network_info.withdraw_enable:
                raise ValueError(f"Withdrawals disabled for {request.asset} on {request.network}")

            # Validate amount limits
            if request.amount < network_info.withdraw_min:
                raise ValueError(f"Amount {request.amount} below minimum {network_info.withdraw_min}")

            if network_info.withdraw_max and request.amount > network_info.withdraw_max:
                raise ValueError(f"Amount {request.amount} exceeds maximum {network_info.withdraw_max}")

            # Validate address format if regex provided
            if network_info.address_regex:
                import re
                if not re.match(network_info.address_regex, request.address):
                    raise ValueError(f"Invalid address format for {request.network}")

            # Validate memo format if required and regex provided
            if network_info.memo_regex and request.memo:
                if not re.match(network_info.memo_regex, request.memo):
                    raise ValueError(f"Invalid memo format for {request.network}")

    async def get_withdrawal_limits_for_asset(
        self,
        asset: AssetName,
        network: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get withdrawal limits for an asset and network.

        Args:
            asset: Asset name
            network: Network/chain name

        Returns:
            Dictionary with 'min', 'max', and 'fee' limits
        """
        currency_info = await self.get_currency_info()
        asset_info = currency_info.get(asset)

        if not asset_info:
            raise ValueError(f"Asset {asset} not supported")

        if network:
            network_info = asset_info.networks.get(network)
            if not network_info:
                raise ValueError(f"Network {network} not supported for {asset}")

            return {
                'min': network_info.withdraw_min,
                'max': network_info.withdraw_max or float('inf'),
                'fee': network_info.withdraw_fee
            }

        # Return limits across all networks if no specific network
        min_amount = float('inf')
        max_amount = 0.0
        min_fee = float('inf')

        for net_info in asset_info.networks.values():
            if net_info.withdraw_enable:
                min_amount = min(min_amount, net_info.withdraw_min)
                if net_info.withdraw_max:
                    max_amount = max(max_amount, net_info.withdraw_max)
                min_fee = min(min_fee, net_info.withdraw_fee)

        return {
            'min': min_amount if min_amount != float('inf') else 0.0,
            'max': max_amount if max_amount > 0 else float('inf'),
            'fee': min_fee if min_fee != float('inf') else 0.0
        }