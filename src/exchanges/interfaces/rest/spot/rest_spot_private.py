from abc import abstractmethod
from typing import Dict, List, Optional
from exchanges.interfaces.rest.rest_base import BaseRestInterface
from exchanges.services import BaseExchangeMapper
from infrastructure.data_structures.common import (
    Symbol,
    Order,
    OrderId,
    OrderType,
    Side,
    AssetBalance,
    AssetName,
    AssetInfo,
    TimeInForce,
    WithdrawalRequest,
    WithdrawalResponse
)

from infrastructure.config.structs import ExchangeConfig

# HFT Logger Integration
from infrastructure.logging import HFTLoggerInterface


class PrivateSpotRest(BaseRestInterface):
    """Abstract interface for private exchange operations (trading, account management)"""
    CAN_MODIFY_ORDERS = False  # Default capability flag for modifying orders

    def __init__(self, config: ExchangeConfig, mapper: BaseExchangeMapper, logger: Optional[HFTLoggerInterface] = None):
        """Initialize private interface with transport manager and mapper."""
        if not config.has_credentials():
            raise ValueError(f"{config.name} API credentials must be provided")
            
        super().__init__(
            config=config,
            mapper=mapper,
            is_private=True,  # Private API operations with authentication
            logger=logger  # Pass logger to parent for specialized private.spot logging
        )

    @abstractmethod
    async def get_account_balance(self) -> List[AssetBalance]:
        """Get account balance for all assets"""
        pass
    
    @abstractmethod
    async def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """Get balance for a specific asset"""
        pass

    @abstractmethod
    async def modify_order(
        self,
        symbol: Symbol,
        order_id: OrderId,
        amount: Optional[float] = None,
        price: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        stop_price: Optional[float] = None
    ) -> Order:

        """Modify an existing order (if supported)"""
        pass
    
    @abstractmethod
    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        order_type: OrderType,
        amount: Optional[float] = None,
        price: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        stop_price: Optional[float] = None,
        iceberg_qty: Optional[float] = None,
        new_order_resp_type: Optional[str] = None
    ) -> Order:
        """Place a new order with comprehensive parameters"""
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Cancel an active order"""
        pass
    
    @abstractmethod
    async def cancel_all_orders(self, symbol: Symbol) -> List[Order]:
        """Cancel all open orders for a symbol"""
        pass
    
    @abstractmethod
    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Query order status"""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """Get all open orders for account or symbol"""
        pass
    
    @abstractmethod
    async def create_listen_key(self) -> str:
        """
        Create a new listen key for user data stream.
        
        Returns:
            Listen key string for WebSocket user data stream
        """
        pass
    
    @abstractmethod
    async def get_all_listen_keys(self) -> Dict:
        """
        Get all active listen keys.
        
        Returns:
            Dictionary containing active listen keys and their metadata
        """
        pass
    
    @abstractmethod
    async def keep_alive_listen_key(self, listen_key: str) -> None:
        """
        Keep a listen key alive to prevent expiration.
        
        Args:
            listen_key: The listen key to keep alive
        """
        pass
    
    @abstractmethod
    async def delete_listen_key(self, listen_key: str) -> None:
        """
        Delete/close a listen key.

        Args:
            listen_key: The listen key to delete
        """
        pass

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

    # Withdrawal operations

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
    
    # @abstractmethod
    # async def get_order_history(
    #     self,
    #     symbol: Symbol,
    #     limit: int = 500,
    #     start_time: Optional[int] = None,
    #     end_time: Optional[int] = None
    # ) -> List[Order]:
    #     """Get order history"""
    #     pass
    #
    # @abstractmethod
    # async def get_trade_history(
    #     self,
    #     symbol: Symbol,
    #     limit: int = 500,
    #     start_time: Optional[int] = None,
    #     end_time: Optional[int] = None
    # ) -> List[Trade]:
    #     """Get account trade history"""
    #     pass
    
