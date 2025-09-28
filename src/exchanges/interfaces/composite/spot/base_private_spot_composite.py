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
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebSocketType
from infrastructure.exceptions.system import InitializationError


class BasePrivateSpotComposite(BasePrivateComposite, WithdrawalMixin):
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
                 websocket_client: Optional[PrivateWebSocketType] = None,
                 logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None) -> None:
        """
        Initialize private spot exchange interface with dependency injection.
        
        Args:
            config: Exchange configuration with API credentials
            rest_client: Injected private REST client instance
            websocket_client: Injected private WebSocket client instance (optional)
            logger: Optional injected HFT logger (auto-created if not provided)
            handlers: Optional private WebSocket handlers
        """
        super().__init__(config, rest_client, websocket_client, logger, handlers)
        
        # Update tag to indicate spot operations
        self._tag = f'{config.name}_private_spot'
        
        # Asset info for withdrawal validation (spot-specific)
        self._assets_info = {}

    # Spot-specific functionality extensions

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
            raise InitializationError(f"Spot initialization failed: {e}")

    def _create_inner_websocket_handlers(self) -> PrivateWebsocketHandlers:
        """Get private WebSocket handlers for Gate.io."""
        return PrivateWebsocketHandlers(
            order_handler=self._order_handler,
            balance_handler=self._balance_handler,
            execution_handler=self._execution_handler,
        )

# Alias for backward compatibility with existing imports
CompositePrivateSpotExchange = BasePrivateSpotComposite