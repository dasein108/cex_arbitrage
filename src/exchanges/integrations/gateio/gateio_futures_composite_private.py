"""
Gate.io futures private composite exchange implementation.

This implementation follows the composite pattern for Gate.io futures
private operations with futures-specific position management, leverage
control, and futures trading functionality.
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
from exchanges.interfaces.composite.futures.base_private_futures_composite import CompositePrivateFuturesExchange
from exchanges.integrations.gateio.rest.gateio_rest_futures_private import GateioPrivateFuturesRest
from exchanges.integrations.gateio.ws.gateio_ws_private_futures import GateioPrivateFuturesWebsocket
from exchanges.structs import AssetName, OrderType
from exchanges.structs.common import Symbol, Order, Position, WithdrawalRequest, WithdrawalResponse
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers


class GateioFuturesCompositePrivateExchange(CompositePrivateFuturesExchange):
    """
    Gate.io futures private composite exchange.
    
    Provides futures trading operations including:
    - Futures order management
    - Position control (long/short)
    - Leverage management
    - Margin management
    - Futures account operations
    
    Extends base futures composite with Gate.io-specific implementations
    for futures trading and position management.
    """

    #TODO: separate withdrawal interface from futures interface if needed
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        pass

    async def get_withdrawal_history(self, asset: Optional[AssetName] = None, limit: int = 100) -> List[
        WithdrawalResponse]:
        pass

    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        pass


    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None, 
                 handlers: Optional[PrivateWebsocketHandlers] = None):
        """Initialize Gate.io futures private composite exchange."""
        super().__init__(config, logger=logger, handlers=handlers)
        
        # Override tag for Gate.io futures identification
        self._tag = f'{config.name}_futures_private'

    # Composite pattern implementation - create futures-specific components

    async def _create_private_rest(self) -> GateioPrivateFuturesRest:
        """Create Gate.io futures private REST client."""
        return GateioPrivateFuturesRest(self.config, self.logger)

    async def _create_private_ws_with_handlers(self, handlers: PrivateWebsocketHandlers) -> GateioPrivateFuturesWebsocket:
        """Create Gate.io futures private WebSocket client with handlers."""
        return GateioPrivateFuturesWebsocket(self.config, handlers)

    async def close_position(
        self, 
        symbol: Symbol, 
        quantity: Optional[Decimal] = None
    ) -> List[Order]:
        """Close position (partially or completely) for Gate.io futures."""
        try:
            # Get current position
            positions = await self._private_rest.get_positions(symbol)
            if not positions:
                self.logger.warning(f"No position found for {symbol}")
                return []
            
            orders = []
            for position in positions:
                if position.quantity == 0:
                    continue
                
                # Determine close quantity
                close_qty = quantity if quantity else abs(position.quantity)
                
                # Determine side (opposite of position)
                close_side = 'sell' if position.quantity > 0 else 'buy'
                
                # Place market order to close position
                order = await self.place_market_order(
                    symbol=symbol,
                    side=close_side,
                    order_type=OrderType.MARKET,
                    quantity=close_qty,
                    reduce_only=True,
                    close_position=(quantity is None)  # Full close if no quantity specified
                )
                
                orders.append(order)
            
            self.logger.info(f"Closed position for {symbol}, orders: {[o.order_id for o in orders]}")
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to close position for {symbol}: {e}")
            raise


    async def _position_handler(self, position: Position) -> None:
        """Handle position updates from Gate.io futures WebSocket."""
        try:
            # Update internal position state
            self._update_futures_position(position)
            
            # Log significant position changes
            if abs(position.size) > 0:
                self.logger.info(f"Position update for {position.symbol}: {position.size} @ {position.entry_price}")
            else:
                self.logger.info(f"Position closed for {position.symbol}")
            
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}")

    # Enhanced trading stats with Gate.io futures metrics

    def get_trading_stats(self) -> Dict[str, Any]:
        """Get trading stats including Gate.io futures-specific metrics."""
        base_stats = super().get_trading_stats()
        base_stats.update({
            'exchange_type': 'futures',
            'exchange_name': 'gateio',
            'long_positions': len([p for p in self._positions.values() if p.size > 0]),
            'short_positions': len([p for p in self._positions.values() if p.size < 0])
        })
        return base_stats