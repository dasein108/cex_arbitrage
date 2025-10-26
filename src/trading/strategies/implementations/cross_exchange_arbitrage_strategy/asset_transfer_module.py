"""Asset Transfer Module for Cross-Exchange Arbitrage Strategy.

This module handles secure asset transfers between exchanges for arbitrage operations.
Implements separated domain architecture with HFT-optimized performance patterns.

Key Features:
- Separated network selection and address retrieval
- Just-in-time address validation for security
- HFT-compliant sub-50ms execution targets
- Comprehensive error handling and validation
"""

from typing import Dict, Optional
from datetime import datetime, timedelta

from msgspec import Struct

from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.structs.common import AssetName, AssetInfo, WithdrawalRequest, DepositResponse, NetworkInfo
from exchanges.structs.enums import ExchangeEnum, WithdrawalStatus, DepositStatus
from infrastructure.logging import HFTLoggerInterface
from utils import get_current_timestamp


def fix_tx_id(tx_id: Optional[str]) -> Optional[str]:
    """ Fix tx_id by removing any extra data after colon(MEXC specifics) """
    if not tx_id:
        return tx_id

    return tx_id.split(":")[0]

class TransferRequest(Struct, frozen=False, kw_only=True):
    """Enhanced transfer request with comprehensive deposit and withdrawal tracking."""
    transfer_id: str
    asset: AssetName
    from_exchange: ExchangeEnum
    to_exchange: Optional[ExchangeEnum] = None # can be lazy loaded
    amount: float = 0
    fees: float = 0
    
    # Withdrawal tracking (existing)
    withdrawal_id: str = ""
    withdrawal_status: Optional[WithdrawalStatus] = None
    withdrawal_tx_id: str = ""

    # NEW: Deposit tracking
    deposit_id: Optional[str] = None
    deposit_status: Optional[DepositStatus] = None


    deposit_address: str = ""
    network: Optional[str] = None
    memo: Optional[str] = None
    last_deposit_check: Optional[float] = None
    
    # Enhanced completion tracking
    # completed: bool = False              # True only when BOTH withdrawal and deposit complete
    # deposit_completed: bool = False      # Deposit side complete
    
    # Timestamps
    created_at: Optional[float] = None
    last_status_check: Optional[float] = None

    @property
    def qty(self):
        return self.amount - self.fees

    @property
    def deposit_in_progress(self):
        return self.deposit_status in [DepositStatus.PENDING, DepositStatus.PROCESSING] or self.deposit_status is None

    @property
    def withdrawal_in_progress(self):
        return self.withdrawal_status in [WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING]

    @property
    def deposit_completed(self) -> bool:
        """Check if deposit side is completed."""
        return self.deposit_status == DepositStatus.COMPLETED

    @property
    def withdrawal_completed(self) -> bool:
        """Check if withdrawal side is completed."""
        return self.withdrawal_status == WithdrawalStatus.COMPLETED

    @property
    def deposit_failed(self):
        return self.deposit_status in [DepositStatus.FAILED]

    @property
    def withdrawal_failed(self):
        return self.withdrawal_status in [WithdrawalStatus.FAILED]

    @property
    def completed(self):
        """Check if entire transfer is completed (both sides)."""
        return self.withdrawal_completed and self.deposit_completed

    @property
    def failed(self):
        """Check if entire transfer is completed (both sides)."""
        return self.deposit_failed or self.withdrawal_failed

    @property
    def in_progress(self):
        """Check if either side of transfer is still in progress."""
        return self.withdrawal_in_progress or self.deposit_in_progress


class TransferValidation(Struct):
    """Validation results for transfer feasibility."""
    is_valid: bool
    error_msg: str = ""
    optimal_network: str = ""
    estimated_fee: float = 0.0
    # Address info for just-in-time retrieval
    deposit_address: str = ""
    deposit_memo: Optional[str] = None

class AddressInfo(Struct):
    """Address information for transfers."""
    address: str
    network: str
    memo: Optional[str] = None


class AssetTransferModule:
    """Manages asset transfers between exchanges for arbitrage strategies.
    
    Implements separated domain architecture with optimized network selection
    and just-in-time address retrieval for maximum HFT performance.
    
    Attributes:
        exchanges: Dictionary of exchange interfaces by enum
        active_transfers: Dictionary of active transfer requests by ID
    """
    
    def __init__(self, exchanges: Dict[ExchangeEnum, CompositePrivateSpotExchange],
                 logger: HFTLoggerInterface):
        """Initialize asset transfer module with exchange interfaces.
        
        Args:
            exchanges: Dictionary mapping exchange enums to private spot interfaces
        """
        self.exchanges = exchanges
        self.active_transfers: Dict[str, TransferRequest] = {}
        self.logger = logger

    async def initialize(self):
        """Initialize all exchanges in the module."""
        for exchange in self.exchanges.values():
            await exchange.initialize()

    async def transfer_asset(self, asset: AssetName, from_exchange: ExchangeEnum,
                             to_exchange: ExchangeEnum, amount: float) -> TransferRequest:
        """Start asset transfer between specified exchanges.
        
        Optimized for HFT performance with separated validation and execution phases.
        
        Args:
            asset: Asset to transfer
            from_exchange: Source exchange
            to_exchange: Target exchange  
            amount: Amount to transfer
            
        Returns:
            TransferRequest with transfer details and status
            
        Raises:
            ValueError: If exchanges unavailable or validation fails
        """
        # Validate exchanges exist
        if from_exchange not in self.exchanges or to_exchange not in self.exchanges:
            raise ValueError(f"Exchange not available: {from_exchange} or {to_exchange}")
        
        # Validate transfer feasibility
        validation = await self._validate_transfer(asset, from_exchange, to_exchange, amount)
        if not validation.is_valid:
            raise ValueError(validation.error_msg)
        
        # Create and store transfer request
        transfer_id = f"{asset}_{from_exchange.name}_{to_exchange.name}_{get_current_timestamp()}"
        request = TransferRequest(
            transfer_id=transfer_id,
            asset=asset,
            from_exchange=from_exchange,
            to_exchange=to_exchange,
            amount=amount,
            fees=validation.estimated_fee,
            created_at=get_current_timestamp()
        )

        self.active_transfers[transfer_id] = request
        
        # Execute transfer with just-in-time address retrieval
        await self._execute_transfer(request, validation)
        return request

    async def _validate_transfer(self, asset: AssetName, from_exchange: ExchangeEnum, 
                               to_exchange: ExchangeEnum, amount: float) -> TransferValidation:
        """Validate transfer feasibility without address retrieval.
        
        Performs fast validation checks for network compatibility, balances,
        and withdrawal/deposit capabilities. Address retrieval is deferred
        to execution phase for optimal HFT performance.
        
        Args:
            asset: Asset to transfer
            from_exchange: Source exchange enum
            to_exchange: Target exchange enum
            amount: Transfer amount
            
        Returns:
            TransferValidation with results and optimal network
        """
        source_exchange = self.exchanges[from_exchange]
        target_exchange = self.exchanges[to_exchange]
        
        # Get asset info from loaded exchange data
        source_info = source_exchange.assets_info[asset]
        target_info = target_exchange.assets_info[asset]
        
        # Validate source withdrawal capability
        if not source_info.withdraw_enable:
            return TransferValidation(False, f"{asset} withdrawals disabled on {from_exchange.name}")
        
        # Validate target deposit capability  
        if not target_info.deposit_enable:
            return TransferValidation(False, f"{asset} deposits disabled on {to_exchange.name}")
        
        # Check sufficient balance
        balance = await source_exchange.get_asset_balance(asset)
        if not balance or balance.available < amount:
            return TransferValidation(False, f"Insufficient {asset} balance on {from_exchange.name}")
        
        # Find optimal network for lowest fees and compatibility
        optimal_network = self._select_optimal_network(source_info, target_info, amount)
        if not optimal_network:
            return TransferValidation(False, f"No common networks between {from_exchange.name} and {to_exchange.name}")
        
        estimated_fee = source_info.networks[optimal_network].withdraw_fee
        
        return TransferValidation(
            True, 
            optimal_network=optimal_network, 
            estimated_fee=estimated_fee
        )
    
    def _select_optimal_network(self, source_asset: AssetInfo, target_asset: AssetInfo, amount: float) -> Optional[str]:
        """Find best network by fee and availability - returns only network name.
        
        Optimizes for:
        1. Lowest withdrawal fees
        2. Amount within limits
        3. Both withdrawal and deposit enabled
        
        Args:
            source_asset: Source exchange asset info
            target_asset: Target exchange asset info  
            amount: Transfer amount to validate
            
        Returns:
            Network name if found, None if no suitable network
        """
        common_networks = set(source_asset.networks.keys()) & set(target_asset.networks.keys())
        
        best_network = None
        lowest_fee = float('inf')
        
        for network in common_networks:
            src_net = source_asset.networks[network]
            tgt_net = target_asset.networks[network]
            
            # Validate network capabilities and amount limits
            if (src_net.withdraw_enable and tgt_net.deposit_enable and 
                amount >= src_net.withdraw_min and 
                (not src_net.withdraw_max or amount <= src_net.withdraw_max)):
                
                # Select network with lowest withdrawal fee
                if src_net.withdraw_fee < lowest_fee:
                    lowest_fee = src_net.withdraw_fee
                    best_network = network
        
        return best_network
    
    async def _execute_transfer(self, request: TransferRequest, validation: TransferValidation):
        """Execute transfer using existing withdrawal infrastructure.
        
        Gets deposit address just-in-time for optimal HFT performance.
        Separated address retrieval ensures minimal latency during execution.
        """
        source_exchange = self.exchanges[request.from_exchange]
        target_exchange = self.exchanges[request.to_exchange]
        
        deposit_info = await target_exchange.get_deposit_address(request.asset, validation.optimal_network)

        # Validate we got a valid address
        if not deposit_info.address:
            raise ValueError(f"No valid deposit address for {request.asset} on "
                             f"{target_exchange.config.exchange_enum.name}")

        # Submit withdrawal using validated address
        withdrawal_request = WithdrawalRequest(
            asset=request.asset,
            amount=request.amount,
            address=deposit_info.address,
            network=deposit_info.network,
            memo=deposit_info.memo
        )
        
        response = await source_exchange.submit_withdrawal(withdrawal_request)

        request = self.active_transfers[request.transfer_id]
        request.withdrawal_id = response.withdrawal_id
        request.deposit_address = deposit_info.address
        request.withdrawal_status = response.status
        request.deposit_status = DepositStatus.PENDING
        request.network = deposit_info.network
        request.memo = deposit_info.memo


    async def get_transfer_request(self, exchange_enum: ExchangeEnum,  withdrawal_id: str) -> Optional[TransferRequest]:
        if exchange_enum not in self.exchanges:
            raise Exception(f"Exchange {exchange_enum.name} not available in transfer module")

        exchange = self.exchanges.get(exchange_enum)
        withdrawal_status = await exchange.get_withdrawal_status(withdrawal_id)

        if not withdrawal_status:
            return None

        request = TransferRequest(
            transfer_id=f'{exchange_enum.name}_{withdrawal_id}',
            asset=withdrawal_status.asset,
            from_exchange=exchange_enum,
            to_exchange=None,  # Unknown at this point
            amount=withdrawal_status.amount,
            withdrawal_id=withdrawal_id,
            withdrawal_status=withdrawal_status.status,
            withdrawal_tx_id=fix_tx_id(withdrawal_status.tx_id),
            created_at=withdrawal_status.timestamp,
            deposit_address=withdrawal_status.address,
        )

        request = await self.update_deposit_status(request)

        return request

    async def update_transfer_request(self, request: TransferRequest):

        # Check withdrawal status (existing logic)
        if request.withdrawal_in_progress:
            request = await self.update_withdrawal_status(request)

        # Check deposit status (new logic)
        if request.deposit_in_progress:
            request = await self.update_deposit_status(request)

        return request

    async def update_transfer_status(self, transfer_id: str):
        """Check transfer status with dual-side validation (withdrawal + deposit).
        
        Checks both withdrawal completion and deposit arrival for complete
        end-to-end transfer validation. Only returns True when BOTH sides complete.
        
        Args:
            transfer_id: Transfer ID to check
            
        Returns:
            True if BOTH withdrawal and deposit completed, False otherwise
        """
        if transfer_id not in self.active_transfers:
            return False
        
        request = self.active_transfers[transfer_id]

        # Check withdrawal status (existing logic)
        if request.withdrawal_in_progress:
            request = await self.update_withdrawal_status(request)

        # Check deposit status (new logic)
        if request.deposit_in_progress:
            request = await self.update_deposit_status(request)

        return request.completed
        
    async def update_withdrawal_status(self, request: TransferRequest) -> TransferRequest:
        source_exchange = self.exchanges[request.from_exchange]

        try:
            withdrawal_status = await source_exchange.get_withdrawal_status(request.withdrawal_id)
            request.withdrawal_status = withdrawal_status.status
            request.last_status_check = get_current_timestamp()
            request.withdrawal_tx_id = fix_tx_id(withdrawal_status.tx_id)

            return request

        except Exception as e:
            # Log error but don't fail - might be temporary network issue
            self.logger.error(f"Error checking withdrawal status for {request.transfer_id}: {e}")
            return request


    async def update_deposit_status(self, request: TransferRequest) -> TransferRequest:
        try:
            async def update_by_exchange_enum(exchange_enum: ExchangeEnum) -> TransferRequest:
                target_exchange = self.exchanges[exchange_enum]
                deposit_history = await target_exchange.get_deposit_history(
                    asset=request.asset,
                    limit=20
                    # start_time=int(request.created_at * 1000)  # Convert to milliseconds
                )

                # Find deposits that match our transfer criteria
                for deposit in deposit_history:
                    deposit_tx_id = fix_tx_id(deposit.tx_id)
                    if deposit_tx_id == request.withdrawal_tx_id:
                        request.to_exchange = exchange_enum
                        request.deposit_id = deposit_tx_id
                        request.deposit_status = deposit.status
                        return request
                return request

            if request.withdrawal_tx_id:
                if not request.to_exchange:
                    for to_exchange_enum, target_exchange in self.exchanges.items():
                        if to_exchange_enum == request.from_exchange:
                            continue

                        request = await update_by_exchange_enum(to_exchange_enum)
                        if request.to_exchange:
                            return request
                else:
                    return await update_by_exchange_enum(request.to_exchange)

            return request

        except Exception as e:
            # Log error but don't fail - might be temporary network issue
            self.logger.error(f"Error checking deposit status for {request.transfer_id}: {e}")
            return request

    async def prune_transfer(self, transfer_id: str) -> bool:
        """Complete transfer and cleanup active tracking.
        
        Checks final status and removes from active transfers if completed.
        
        Args:
            transfer_id: Transfer ID to complete
            
        Returns:
            True if transfer completed and cleaned up, False otherwise
        """
        if transfer_id not in self.active_transfers:
            return False
        
        if await self.update_transfer_status(transfer_id):
            del self.active_transfers[transfer_id]
            return True
        
        return False

    
    def get_all_active_transfers(self) -> Dict[str, TransferRequest]:
        """Get copy of all active transfer requests.
        
        Returns:
            Dictionary copy of all active transfers
        """
        return self.active_transfers.copy()

