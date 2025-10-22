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
from exchanges.structs.common import AssetName, AssetInfo, WithdrawalRequest, DepositResponse
from exchanges.structs.enums import ExchangeEnum, WithdrawalStatus, DepositStatus

class TransferRequest(Struct):
    """Enhanced transfer request with comprehensive deposit and withdrawal tracking."""
    transfer_id: str
    asset: AssetName
    from_exchange: ExchangeEnum
    to_exchange: ExchangeEnum
    amount: float
    fees: float = 0
    
    # Withdrawal tracking (existing)
    initiated: bool = False
    transfer_tx_id: str = ""
    current_status: Optional[WithdrawalStatus] = None
    
    # NEW: Deposit tracking
    deposit_tx_id: Optional[str] = None
    deposit_detected: bool = False
    deposit_status: Optional[DepositStatus] = None
    deposit_address_used: str = ""
    memo_used: Optional[str] = None
    last_deposit_check: Optional[datetime] = None
    
    # Enhanced completion tracking
    completed: bool = False              # True only when BOTH withdrawal and deposit complete
    withdrawal_completed: bool = False   # Withdrawal side complete
    deposit_completed: bool = False      # Deposit side complete
    
    # Timestamps
    created_at: Optional[datetime] = None
    last_status_check: Optional[datetime] = None

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
    
    def __init__(self, exchanges: Dict[ExchangeEnum, CompositePrivateSpotExchange]):
        """Initialize asset transfer module with exchange interfaces.
        
        Args:
            exchanges: Dictionary mapping exchange enums to private spot interfaces
        """
        self.exchanges = exchanges
        self.active_transfers: Dict[str, TransferRequest] = {}

    async def initialize(self):
        """Initialize all exchanges in the module."""
        for exchange in self.exchanges.values():
            await exchange.initialize()

    async def start_transfer_asset(self, asset: AssetName, from_exchange: ExchangeEnum, 
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
        transfer_id = f"{asset}_{from_exchange.name}_{to_exchange.name}_{int(datetime.now().timestamp())}"
        request = TransferRequest(
            transfer_id=transfer_id,
            asset=asset,
            from_exchange=from_exchange,
            to_exchange=to_exchange,
            amount=amount,
            fees=validation.estimated_fee,
            created_at=datetime.now()
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
    
    async def _get_transfer_address(self, asset: AssetName, network: str, 
                                   target_exchange: CompositePrivateSpotExchange) -> AddressInfo:
        """Get validated deposit address for transfer.
        
        Retrieves deposit address from target exchange and validates it for security.
        Separated from network selection for better responsibility separation.
        
        Args:
            asset: Asset to transfer
            network: Selected network name
            target_exchange: Target exchange interface
            
        Returns:
            AddressInfo with validated address and memo
            
        Raises:
            ValueError: If address retrieval or validation fails
        """
        try:
            # Get real deposit address from target exchange API
            deposit_info = await target_exchange.get_deposit_address(asset, network)
            
            # Validate we got a valid address
            if not deposit_info.address:
                raise ValueError(f"No valid deposit address for {asset} on {target_exchange.config.exchange_enum.name}")
            
            return AddressInfo(
                address=deposit_info.address,
                memo=deposit_info.memo,
                network=network
            )
            
        except Exception as e:
            raise ValueError(f"Failed to get or validate deposit address for {asset}: {e}")
    
    async def _execute_transfer(self, request: TransferRequest, validation: TransferValidation) -> None:
        """Execute transfer using existing withdrawal infrastructure.
        
        Gets deposit address just-in-time for optimal HFT performance.
        Separated address retrieval ensures minimal latency during execution.
        """
        source_exchange = self.exchanges[request.from_exchange]
        target_exchange = self.exchanges[request.to_exchange]
        
        # Get validated deposit address just-in-time
        address_info = await self._get_transfer_address(
            request.asset, 
            validation.optimal_network, 
            target_exchange
        )
        
        # Submit withdrawal using validated address
        withdrawal_request = WithdrawalRequest(
            asset=request.asset,
            amount=request.amount,
            address=address_info.address,
            network=address_info.network,
            memo=address_info.memo
        )
        
        response = await source_exchange.submit_withdrawal(withdrawal_request)
        
        # Update the stored transfer request with transaction ID, address used, and initiated status
        self._update_transfer_request(
            request.transfer_id,
            initiated=True,
            transfer_tx_id=response.withdrawal_id,
            deposit_address_used=address_info.address,
            memo_used=address_info.memo
        )

    async def check_transfer_status(self, transfer_id: str) -> bool:
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
        if not request.initiated:
            return False
        
        # Check withdrawal status (existing logic)
        withdrawal_completed = await self._check_withdrawal_status(transfer_id)
        
        # Check deposit status (new logic)
        deposit_completed = await self._check_deposit_status(transfer_id)
        
        # Update completion tracking
        self._update_transfer_request(
            transfer_id,
            withdrawal_completed=withdrawal_completed,
            deposit_completed=deposit_completed,
            completed=withdrawal_completed and deposit_completed,
            last_status_check=datetime.now()
        )
        
        return withdrawal_completed and deposit_completed

    async def _check_withdrawal_status(self, transfer_id: str) -> bool:
        """Check withdrawal status on source exchange.
        
        Args:
            transfer_id: Transfer ID to check
            
        Returns:
            True if withdrawal completed, False otherwise
        """
        request = self.active_transfers[transfer_id]
        source_exchange = self.exchanges[request.from_exchange]
        
        try:
            withdrawal_status = await source_exchange.get_withdrawal_status(request.transfer_tx_id)
            
            # Update withdrawal status in request
            self._update_transfer_request(
                transfer_id,
                current_status=withdrawal_status.status
            )
            
            return withdrawal_status.status == WithdrawalStatus.COMPLETED
            
        except Exception as e:
            # Log error but don't fail - might be temporary network issue
            print(f"Error checking withdrawal status for {transfer_id}: {e}")
            return False

    async def _check_deposit_status(self, transfer_id: str) -> bool:
        """Check deposit status on target exchange using deposit history.
        
        Searches deposit history for matching deposits and validates completion.
        
        Args:
            transfer_id: Transfer ID to check
            
        Returns:
            True if matching deposit completed, False otherwise
        """
        request = self.active_transfers[transfer_id]
        target_exchange = self.exchanges[request.to_exchange]
        
        try:
            # Check if we already detected this deposit
            if request.deposit_completed:
                return True
            
            # Look for new deposits since transfer initiated
            new_deposit = await self._detect_new_deposit(transfer_id)
            
            if new_deposit:
                # Update request with deposit information
                self._update_transfer_request(
                    transfer_id,
                    deposit_tx_id=new_deposit.tx_id,
                    deposit_detected=True,
                    deposit_status=new_deposit.status,
                    last_deposit_check=datetime.now()
                )
                
                # Check if deposit is completed
                return new_deposit.status == DepositStatus.COMPLETED
            
            # Update last check time even if no deposit found
            self._update_transfer_request(
                transfer_id,
                last_deposit_check=datetime.now()
            )
            
            return False
            
        except Exception as e:
            # Log error but don't fail - might be temporary network issue
            print(f"Error checking deposit status for {transfer_id}: {e}")
            return False

    async def _detect_new_deposit(self, transfer_id: str) -> Optional[DepositResponse]:
        """Detect new deposits matching the transfer criteria.
        
        Searches deposit history for deposits that match the transfer asset,
        amount, and timeframe to identify the incoming transfer.
        
        Args:
            transfer_id: Transfer ID to match
            
        Returns:
            DepositResponse if matching deposit found, None otherwise
        """
        request = self.active_transfers[transfer_id]
        target_exchange = self.exchanges[request.to_exchange]
        
        try:
            # Check if transfer has been pending too long (48 hours timeout)
            if request.created_at:
                time_elapsed = datetime.now() - request.created_at
                if time_elapsed.total_seconds() > (48 * 3600):  # 48 hours in seconds
                    print(f"Transfer {transfer_id} has been pending for {time_elapsed}, may be stuck")
                    return None
            
            # Get deposit history since transfer was initiated
            # Add buffer time to account for blockchain delays
            since_time = request.created_at - timedelta(minutes=5) if request.created_at else datetime.now() - timedelta(hours=1)
            
            # Limit history search to reasonable timeframe (24 hours max)
            max_lookback = datetime.now() - timedelta(hours=24)
            if since_time < max_lookback:
                since_time = max_lookback
            
            deposit_history = await target_exchange.get_deposit_history(
                asset=request.asset,
                start_time=int(since_time.timestamp() * 1000)  # Convert to milliseconds
            )
            
            # Find deposits that match our transfer criteria
            for deposit in deposit_history:
                if self._validate_deposit_match(request, deposit):
                    return deposit
            
            return None
            
        except Exception as e:
            print(f"Error detecting new deposit for {transfer_id}: {e}")
            return None

    def _validate_deposit_match(self, request: TransferRequest, deposit: DepositResponse) -> bool:
        """Validate if a deposit matches the transfer request.
        
        Checks asset, amount, address, and timing to determine if this deposit
        corresponds to our outgoing transfer.
        
        Args:
            request: Transfer request to match
            deposit: Deposit response to validate
            
        Returns:
            True if deposit matches transfer, False otherwise
        """
        try:
            # Check asset match
            if deposit.asset != request.asset:
                return False
            
            # Check amount match (allow small tolerance for fees/precision)
            amount_tolerance = 0.001  # 0.1% tolerance
            if abs(deposit.amount - request.amount) > (request.amount * amount_tolerance):
                return False
            
            # Check if deposit arrived after transfer initiated (with safety buffer)
            if request.created_at and deposit.timestamp:
                # Convert timestamp appropriately (handle both seconds and milliseconds)
                if deposit.timestamp > 1e12:  # Looks like milliseconds
                    deposit_time = datetime.fromtimestamp(deposit.timestamp / 1000)
                else:  # Looks like seconds
                    deposit_time = datetime.fromtimestamp(deposit.timestamp)
                
                # Allow 5 minute buffer before transfer creation (blockchain delays)
                buffer_time = request.created_at - timedelta(minutes=5)
                if deposit_time < buffer_time:
                    return False
            
            # Check address match if we stored the deposit address used
            if request.deposit_address_used and deposit.address:
                if deposit.address.lower() != request.deposit_address_used.lower():
                    return False
            
            # Check memo match if applicable (case-insensitive for safety)
            if request.memo_used and deposit.memo:
                if deposit.memo.strip().lower() != request.memo_used.strip().lower():
                    return False
            
            # Avoid matching the same deposit twice
            if request.deposit_tx_id and deposit.tx_id:
                if deposit.tx_id == request.deposit_tx_id:
                    return True  # This is the same deposit we already matched
            
            return True
            
        except Exception as e:
            print(f"Error validating deposit match: {e}")
            return False

    async def complete_transfer(self, transfer_id: str) -> bool:
        """Complete transfer and cleanup active tracking.
        
        Checks final status and removes from active transfers if completed.
        
        Args:
            transfer_id: Transfer ID to complete
            
        Returns:
            True if transfer completed and cleaned up, False otherwise
        """
        if transfer_id not in self.active_transfers:
            return False
        
        if await self.check_transfer_status(transfer_id):
            del self.active_transfers[transfer_id]
            return True
        
        return False
    
    def _update_transfer_request(self, transfer_id: str, **updates) -> None:
        """Update transfer request with new field values.
        
        Creates new immutable TransferRequest struct with updated values.
        Uses msgspec.Struct pattern for thread-safe updates.
        
        Args:
            transfer_id: Transfer ID to update
            **updates: Field values to update
        """
        if transfer_id not in self.active_transfers:
            return
        
        current_request = self.active_transfers[transfer_id]
        
        # Create updated request with new values (msgspec.Struct pattern)
        updated_request = TransferRequest(
            transfer_id=current_request.transfer_id,
            asset=current_request.asset,
            from_exchange=current_request.from_exchange,
            to_exchange=current_request.to_exchange,
            amount=current_request.amount,
            fees=current_request.fees,
            # Withdrawal tracking
            initiated=updates.get('initiated', current_request.initiated),
            transfer_tx_id=updates.get('transfer_tx_id', current_request.transfer_tx_id),
            current_status=updates.get('current_status', current_request.current_status),
            # Deposit tracking
            deposit_tx_id=updates.get('deposit_tx_id', current_request.deposit_tx_id),
            deposit_detected=updates.get('deposit_detected', current_request.deposit_detected),
            deposit_status=updates.get('deposit_status', current_request.deposit_status),
            deposit_address_used=updates.get('deposit_address_used', current_request.deposit_address_used),
            memo_used=updates.get('memo_used', current_request.memo_used),
            last_deposit_check=updates.get('last_deposit_check', current_request.last_deposit_check),
            # Enhanced completion tracking
            completed=updates.get('completed', current_request.completed),
            withdrawal_completed=updates.get('withdrawal_completed', current_request.withdrawal_completed),
            deposit_completed=updates.get('deposit_completed', current_request.deposit_completed),
            # Timestamps
            created_at=current_request.created_at,
            last_status_check=updates.get('last_status_check', current_request.last_status_check)
        )
        
        self.active_transfers[transfer_id] = updated_request
    
    def get_transfer_request(self, transfer_id: str) -> Optional[TransferRequest]:
        """Get current transfer request by ID.
        
        Args:
            transfer_id: Transfer ID to retrieve
            
        Returns:
            TransferRequest if found, None otherwise
        """
        return self.active_transfers.get(transfer_id)
    
    def get_all_active_transfers(self) -> Dict[str, TransferRequest]:
        """Get copy of all active transfer requests.
        
        Returns:
            Dictionary copy of all active transfers
        """
        return self.active_transfers.copy()
    
    def get_transfers_by_status(self, initiated: Optional[bool] = None, 
                               completed: Optional[bool] = None) -> Dict[str, TransferRequest]:
        """Get transfers filtered by status criteria.
        
        Args:
            initiated: Filter by initiated status (None for no filter)
            completed: Filter by completed status (None for no filter)
            
        Returns:
            Dictionary of transfers matching criteria
        """
        filtered_transfers = {}
        
        for transfer_id, request in self.active_transfers.items():
            if initiated is not None and request.initiated != initiated:
                continue
            if completed is not None and request.completed != completed:
                continue
            filtered_transfers[transfer_id] = request
        
        return filtered_transfers
    
    def get_stalled_transfers(self, timeout_hours: int = 24) -> Dict[str, TransferRequest]:
        """Get transfers that may be stalled or stuck.
        
        Identifies transfers that have been active for too long without completion.
        
        Args:
            timeout_hours: Hours after which a transfer is considered stalled
            
        Returns:
            Dictionary of potentially stalled transfers
        """
        stalled_transfers = {}
        timeout_threshold = datetime.now() - timedelta(hours=timeout_hours)
        
        for transfer_id, request in self.active_transfers.items():
            if request.initiated and not request.completed:
                if request.created_at and request.created_at < timeout_threshold:
                    stalled_transfers[transfer_id] = request
        
        return stalled_transfers
    
    def get_transfers_pending_deposit(self) -> Dict[str, TransferRequest]:
        """Get transfers where withdrawal completed but deposit not yet detected.
        
        Returns:
            Dictionary of transfers pending deposit detection
        """
        pending_deposits = {}
        
        for transfer_id, request in self.active_transfers.items():
            if (request.withdrawal_completed and 
                not request.deposit_completed and 
                not request.completed):
                pending_deposits[transfer_id] = request
        
        return pending_deposits
    
    def get_transfer_summary(self, transfer_id: str) -> Optional[Dict]:
        """Get comprehensive summary of transfer status.
        
        Args:
            transfer_id: Transfer ID to summarize
            
        Returns:
            Dictionary with detailed transfer information
        """
        if transfer_id not in self.active_transfers:
            return None
        
        request = self.active_transfers[transfer_id]
        
        # Calculate time elapsed
        time_elapsed = None
        if request.created_at:
            time_elapsed = datetime.now() - request.created_at
        
        return {
            'transfer_id': transfer_id,
            'asset': request.asset,
            'amount': request.amount,
            'from_exchange': request.from_exchange.name,
            'to_exchange': request.to_exchange.name,
            'status': {
                'initiated': request.initiated,
                'withdrawal_completed': request.withdrawal_completed,
                'deposit_detected': request.deposit_detected,
                'deposit_completed': request.deposit_completed,
                'overall_completed': request.completed
            },
            'transaction_ids': {
                'withdrawal_tx_id': request.transfer_tx_id,
                'deposit_tx_id': request.deposit_tx_id
            },
            'addresses': {
                'deposit_address_used': request.deposit_address_used,
                'memo_used': request.memo_used
            },
            'timing': {
                'created_at': request.created_at.isoformat() if request.created_at else None,
                'time_elapsed_seconds': time_elapsed.total_seconds() if time_elapsed else None,
                'last_status_check': request.last_status_check.isoformat() if request.last_status_check else None,
                'last_deposit_check': request.last_deposit_check.isoformat() if request.last_deposit_check else None
            },
            'fees': request.fees
        }


