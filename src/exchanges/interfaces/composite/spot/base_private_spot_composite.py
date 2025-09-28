"""
Private SPOT exchange interface for trading operations.

This interface handles authenticated SPOT operations including order management,
balance tracking, and withdrawal operations. It extends the base private composite
with spot-specific withdrawal functionality via WithdrawalMixin.
"""

from typing import Optional
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from config.structs import ExchangeConfig
from exchanges.structs import ExchangeType
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.composite.mixins import WithdrawalMixin
from exchanges.interfaces import PrivateSpotRest
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
from infrastructure.exceptions.system import InitializationError


class CompositePrivateSpotExchange(BasePrivateComposite[PrivateSpotRest, PrivateSpotWebsocket],
                                   WithdrawalMixin):
    """
    Base interface for private SPOT exchange operations.
    
    Extends BasePrivateComposite with spot-specific withdrawal functionality:
    - All base private operations (orders, balances, WebSocket) from BasePrivateComposite
    - Withdrawal operations (withdraw, get_withdrawal_status, etc.) from WithdrawalMixin
    - Asset information management for withdrawal validation
    
    This interface requires valid API credentials and provides full spot trading
    functionality including withdrawals.
    """

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None) -> None:
        """
        Initialize private spot exchange interface.
        
        Args:
            config: Exchange configuration with API credentials
            logger: Optional injected HFT logger (auto-created if not provided)
            handlers: Optional private WebSocket handlers
        """
        super().__init__(config, ExchangeType.SPOT, logger, handlers)

    async def initialize(self, symbols_info):
        """
        Initialize spot exchange with symbols and asset information.
        
        Args:
            symbols_info: SymbolsInfo object with all exchange symbols details
        """
        # Initialize base private functionality first (sets up REST client)
        await super().initialize(symbols_info)

        try:
            # Initialize withdrawal infrastructure via mixin hook
            self.logger.info(f"{self._tag} Initializing withdrawal infrastructure...")
            await self._initialize_withdrawal_infrastructure()

            self.logger.info(f"{self._tag} spot initialization completed",
                            asset_count=len(self.assets_info))

        except Exception as e:
            self.logger.error(f"Spot exchange initialization failed: {e}")
            await self.close()  # Cleanup on failure
            raise InitializationError(f"Spot exchange initialization failed: {e}")