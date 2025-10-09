"""
Private SPOT exchange interface for trading operations.

This interface handles authenticated SPOT operations including order management,
balance tracking, and withdrawal operations. It extends the base private composite
with spot-specific withdrawal functionality via WithdrawalMixin.
"""

from typing import Optional
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.composite.mixins import WithdrawalMixin
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebsocketType
from infrastructure.exceptions.system import InitializationError


class CompositePrivateSpotExchange(BasePrivateComposite, WithdrawalMixin):
    """
    Base interface for private SPOT exchange operations.
    
    Extends BasePrivateComposite with spot-specific withdrawal functionality:
    - All base private operations (orders, balances, WebSocket) from BasePrivateComposite
    - Withdrawal operations (withdraw, get_withdrawal_status, etc.) from WithdrawalMixin
    - Asset information management for withdrawal validation
    
    This interface requires valid API credentials and provides full spot trading
    functionality including withdrawals.
    """

    def __init__(self,
                 config: ExchangeConfig,
                 rest_client: PrivateRestType,
                 websocket_client: Optional[PrivateWebsocketType] = None,
                 logger: Optional[HFTLoggerInterface] = None,
                 balance_sync_interval: Optional[float] = None):
        """
        Initialize private spot exchange interface with dependency injection.
        
        Args:
            config: Exchange configuration with API credentials
            rest_client: Injected private REST client instance
            websocket_client: Injected private WebSocket client instance (optional)
            logger: Optional injected HFT logger (auto-created if not provided)
            balance_sync_interval: Optional interval in seconds for automatic balance syncing
        """
        super().__init__(config, rest_client, websocket_client, logger, balance_sync_interval)
        
        # Update tag to indicate spot operations

        # Asset info for withdrawal validation (spot-specific)
        self._assets_info = {}

    # Spot-specific functionality extensions

    async def initialize(self, *args, **kwargs):
        """
        Initialize spot exchange with symbols and asset information.
        """
        # Initialize base private functionality first
        await super().initialize(*args, **kwargs)
        await self._load_assets_info()