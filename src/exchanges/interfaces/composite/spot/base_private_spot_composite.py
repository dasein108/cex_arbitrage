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
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.composite.mixins import WithdrawalMixin
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

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None) -> None:
        """
        Initialize private spot exchange interface.
        
        Args:
            config: Exchange configuration with API credentials
            logger: Optional injected HFT logger (auto-created if not provided)
            handlers: Optional private WebSocket handlers
        """
        super().__init__(config, logger, handlers)
        
        # Update tag to indicate spot operations
        self._tag = f'{config.name}_private_spot'
        
        # Asset info for withdrawal validation (spot-specific)
        self._assets_info = {}

    # Spot-specific functionality extensions

    async def _load_assets_info(self) -> None:
        """
        Load asset information from REST API for withdrawal validation.
        Uses the get_assets_info method from WithdrawalMixin.
        """
        try:
            from infrastructure.logging import LoggingTimer

            with LoggingTimer(self.logger, "load_assets_info") as timer:
                # Use the mixin's method which delegates to REST client
                assets_info_data = await self.get_assets_info()
                self._assets_info = assets_info_data

            self.logger.info("Assets info loaded successfully",
                            asset_count=len(assets_info_data),
                            load_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to load assets info", error=str(e))
            raise InitializationError(f"Assets info loading failed: {e}")

    async def initialize(self, symbols_info):
        """
        Initialize spot exchange with symbols and asset information.
        
        Args:
            symbols_info: SymbolsInfo object with all exchange symbols details
        """
        # Initialize base private functionality first
        await super().initialize(symbols_info)

        try:
            # Load spot-specific asset information for withdrawals
            self.logger.info(f"{self._tag} Loading asset information...")
            await self._load_assets_info()

            self.logger.info(f"{self._tag} spot initialization completed",
                            asset_count=len(self._assets_info))

        except Exception as e:
            self.logger.error(f"Spot exchange initialization failed: {e}")
            await self.close()  # Cleanup on failure
            raise