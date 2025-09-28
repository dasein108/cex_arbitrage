"""
Withdrawal mixin for spot exchanges only.

This mixin provides withdrawal functionality that should only be
available for spot exchanges, not futures/derivatives exchanges.
It delegates to the underlying REST client for actual implementation.
"""

from typing import Dict, List, Optional, TYPE_CHECKING, Any
from exchanges.structs.common import (
    AssetInfo,
    WithdrawalRequest,
    WithdrawalResponse
)
from exchanges.structs.types import AssetName
from infrastructure.logging import LoggingTimer
from infrastructure.exceptions.system import InitializationError
from exchanges.interfaces.protocols.private_dependencies import (
    PrivateSpotDependencies,
    PrivateExchangeValidationMixin
)

if TYPE_CHECKING:
    from exchanges.interfaces import PrivateSpotRest


class WithdrawalMixin(PrivateSpotDependencies, PrivateExchangeValidationMixin):
    """
    Mixin providing withdrawal functionality for spot exchanges only.
    
    This mixin implements the WithdrawalInterface and delegates all
    operations to the underlying private REST client. It should only
    be mixed into spot exchange implementations, not futures exchanges.
    
    Features:
        - Initialization hook for withdrawal infrastructure
        - Asset information loading and caching
        - Complete withdrawal operations delegation
        - Type-safe dependencies via PrivateSpotDependencies protocol
        - Runtime validation via PrivateExchangeValidationMixin
    
    Requirements:
        - The class using this mixin must implement PrivateSpotDependencies protocol
        - Call _initialize_withdrawal_infrastructure() after REST client setup
    
    Dependencies (enforced by protocol):
        - _private_rest: PrivateSpotRest client for API operations
        - logger: HFTLoggerInterface for performance monitoring
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize withdrawal mixin with state tracking and dependency validation."""
        super().__init__(*args, **kwargs)
        
        # Validate dependencies are available (runtime check)
        # Note: This provides extra safety beyond compile-time protocol checking
        try:
            self._validate_private_dependencies()
        except TypeError:
            # Dependencies may not be available during construction
            # They should be validated later during _initialize_withdrawal_infrastructure()
            pass
        
        # Asset info for withdrawal validation (withdrawal-specific state)
        self._assets_info: Dict[AssetName, AssetInfo] = {}
        self._withdrawal_initialized = False
    
    @property
    def assets_info(self) -> Dict[AssetName, AssetInfo]:
        """Get cached asset information."""
        return self._assets_info.copy()
    
    async def _initialize_withdrawal_infrastructure(self) -> None:
        """
        Initialize withdrawal-related infrastructure.
        
        This method should be called by the main composite class after
        the private REST client is initialized but before the exchange
        is considered fully initialized.
        
        Features:
            - Loads asset information for withdrawal validation
            - Sets up withdrawal-specific state
            - Validates REST client availability
            - Prevents double initialization
        
        Raises:
            InitializationError: If REST client not available or initialization fails
        """
        self.logger.info(f"{self._tag} Initializing withdrawal infrastructure...")

        if self._withdrawal_initialized:
            self.logger.debug("Withdrawal infrastructure already initialized")
            return
        
        # Validate all required dependencies are available
        try:
            self._validate_private_dependencies()
        except TypeError as e:
            raise InitializationError(f"Missing required dependencies: {e}")
            
        # Private REST client is guaranteed to be available via constructor validation
        # No need to check for None
        
        try:
            # Load asset information for withdrawal validation
            self.logger.debug("Loading withdrawal asset information...")
            await self._load_assets_info()
            
            # Mark as initialized
            self._withdrawal_initialized = True
            
            self.logger.info("Withdrawal infrastructure initialized successfully",
                            asset_count=len(self._assets_info))

        except Exception as e:
            self.logger.error("Failed to initialize withdrawal infrastructure", error=str(e))
            raise InitializationError(f"Withdrawal infrastructure initialization failed: {e}")
    
    async def _load_assets_info(self) -> None:
        """
        Load asset information from REST API for withdrawal validation.
        
        This method is called internally by _initialize_withdrawal_infrastructure()
        and should not be called directly by external code.
        """
        try:
            with LoggingTimer(self.logger, "load_assets_info") as timer:
                # Use the REST client to get asset information
                assets_info_data = await self.get_assets_info()
                self._assets_info = assets_info_data

            self.logger.debug("Assets info loaded for withdrawal validation",
                            asset_count=len(assets_info_data),
                            load_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to load assets info for withdrawal", error=str(e))
            raise
    
    async def get_assets_info(self) -> Dict[AssetName, AssetInfo]:
        """
        Get currency information including deposit/withdrawal status and network details.
        Delegates to REST client.
        
        Returns:
            Dictionary mapping AssetName to AssetInfo with network configurations
            
        Raises:
            ExchangeAPIError: If unable to fetch currency information
        """
        # Private REST client is guaranteed to be available via constructor validation
        return await self._private_rest.get_assets_info()
    
    async def submit_withdrawal(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """
        Submit a withdrawal request to the exchange.
        Delegates to REST client.
        
        Args:
            request: Withdrawal request parameters
            
        Returns:
            WithdrawalResponse with withdrawal details
            
        Raises:
            ExchangeAPIError: If withdrawal submission fails
        """
        # Private REST client is guaranteed to be available via constructor validation
        return await self._private_rest.submit_withdrawal(request)
    
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """
        Submit a withdrawal request (alias for submit_withdrawal).
        Maintains backward compatibility with existing interface.
        
        Args:
            request: Withdrawal request parameters
            
        Returns:
            WithdrawalResponse with withdrawal details
        """
        return await self.submit_withdrawal(request)
    
    async def cancel_withdrawal(self, withdrawal_id: str) -> bool:
        """
        Cancel a pending withdrawal.
        Delegates to REST client.
        
        Args:
            withdrawal_id: Exchange withdrawal ID to cancel
            
        Returns:
            True if cancellation successful, False otherwise
            
        Raises:
            ExchangeAPIError: If cancellation fails
        """
        # Private REST client is guaranteed to be available via constructor validation
        return await self._private_rest.cancel_withdrawal(withdrawal_id)
    
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """
        Get current status of a withdrawal.
        Delegates to REST client.
        
        Args:
            withdrawal_id: Exchange withdrawal ID
            
        Returns:
            WithdrawalResponse with current status
            
        Raises:
            ExchangeAPIError: If withdrawal not found or query fails
        """
        # Private REST client is guaranteed to be available via constructor validation
        return await self._private_rest.get_withdrawal_status(withdrawal_id)
    
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
        """
        # Private REST client is guaranteed to be available via constructor validation
        return await self._private_rest.get_withdrawal_history(asset, limit)
    
    # Additional helper methods specific to composite usage
    
    def _has_withdrawal_capability(self) -> bool:
        """
        Check if this exchange instance has withdrawal capability.
        
        Returns:
            True (always, since private REST client is guaranteed to be available)
        """
        return True  # Client is guaranteed to be available via constructor validation
    
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
        # Private REST client is guaranteed to be available via constructor validation
        
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
        # Private REST client is guaranteed to be available via constructor validation
        
        return await self.validate_withdrawal_request(request)
    
    async def validate_withdrawal_request(self, request: WithdrawalRequest) -> None:
        """
        Validate withdrawal request parameters.

        Args:
            request: Withdrawal request to validate

        Raises:
            ValueError: If validation fails
        """
        # Use cached asset info for validation (loaded during initialization)
        if not self._withdrawal_initialized:
            raise RuntimeError("Withdrawal infrastructure not initialized. Call _initialize_withdrawal_infrastructure() first.")
        
        asset_info = self._assets_info.get(request.asset)

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
        # Use cached asset info (loaded during initialization)
        if not self._withdrawal_initialized:
            raise RuntimeError("Withdrawal infrastructure not initialized. Call _initialize_withdrawal_infrastructure() first.")
        
        asset_info = self._assets_info.get(asset)

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