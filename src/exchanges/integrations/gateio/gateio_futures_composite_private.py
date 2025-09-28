"""
Gate.io futures private composite exchange implementation.

This implementation follows the composite pattern for Gate.io futures
private operations with futures-specific position management, leverage
control, and futures trading functionality.
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
from exchanges.interfaces.composite.futures.base_private_futures_composite import CompositePrivateFuturesExchange
from exchanges.interfaces.rest.futures.rest_futures_private import PrivateFuturesRest
from exchanges.interfaces.ws.futures.ws_private_futures import PrivateFuturesWebsocket
from exchanges.structs.common import Symbol, Order, Position
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from exchanges.integrations.gateio.rest.gateio_rest_futures_private import GateioPrivateFuturesRest
from exchanges.integrations.gateio.ws.gateio_ws_private_futures import GateioPrivateFuturesWebsocket


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
    
    NOTE: Futures exchanges do not support withdrawals - use spot exchange for withdrawals.
    """

    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None):
        """Initialize Gate.io futures private composite exchange."""
        super().__init__(config, logger=logger, handlers=handlers)
        
        # Override tag for Gate.io futures identification
        self._tag = f'{config.name}_futures_private'

    # Composite pattern implementation - create futures-specific components

    async def _create_private_rest(self) -> PrivateFuturesRest:
        """Create Gate.io futures private REST client."""
        return GateioPrivateFuturesRest(self.config, self.logger)

    async def _create_private_websocket(self) -> PrivateFuturesWebsocket:
        """Create Gate.io futures private WebSocket client with handlers."""
        return GateioPrivateFuturesWebsocket(self.config, self._create_inner_websocket_handlers())

    # Futures-specific abstract method implementations

    # async def set_leverage(self, symbol: Symbol, leverage: int) -> bool:
    #     """Set leverage for a Gate.io futures symbol."""
    #     try:
    #         result = await self._private_rest.modify_leverage(symbol, float(leverage))
    #
    #         # Update internal leverage settings cache
    #         if result:
    #             if symbol not in self._leverage_settings:
    #                 self._leverage_settings[symbol] = {}
    #             self._leverage_settings[symbol]['leverage'] = leverage
    #             self.logger.info(f"Set leverage for {symbol} to {leverage}x")
    #
    #         return result
    #
    #     except Exception as e:
    #         self.logger.error(f"Failed to set leverage for {symbol}: {e}")
    #         return False
    #
    # async def get_leverage(self, symbol: Symbol) -> Dict:
    #     """Get current leverage for a Gate.io futures symbol."""
    #     try:
    #         # Try cached first
    #         if symbol in self._leverage_settings:
    #             return self._leverage_settings[symbol]
    #
    #         # Fetch from REST API
    #         leverage_info = await self._private_rest.get_leverage(symbol)
    #
    #         # Cache the result
    #         self._leverage_settings[symbol] = leverage_info
    #
    #         return leverage_info
    #
    #     except Exception as e:
    #         self.logger.error(f"Failed to get leverage for {symbol}: {e}")
    #         return {}

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
                order = await self.place_futures_order(
                    symbol=symbol,
                    side=close_side,
                    order_type='market',
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

    # Futures data loading implementations

    async def _load_leverage_settings(self) -> None:
        """Load leverage settings from Gate.io futures REST API."""
        try:
            for symbol in self._symbols:
                leverage_info = await self._private_rest.get_leverage(symbol)
                self._leverage_settings[symbol] = leverage_info
            
            self.logger.info(f"Loaded leverage settings for {len(self._leverage_settings)} symbols")
            
        except Exception as e:
            self.logger.error(f"Failed to load leverage settings: {e}")
            # Don't raise - this is not critical for basic operation

    async def _load_margin_info(self) -> None:
        """Load margin information from Gate.io futures REST API."""
        try:
            # Gate.io futures margin info is typically included in account balance
            balance = await self._private_rest.get_balances()
            
            # Extract margin info for each symbol
            for symbol in self._symbols:
                if symbol in balance:
                    self._margin_info[symbol] = {
                        'available_margin': balance[symbol].available,
                        'used_margin': balance[symbol].locked,
                        'total_margin': balance[symbol].total
                    }
            
            self.logger.info(f"Loaded margin info for {len(self._margin_info)} symbols")
            
        except Exception as e:
            self.logger.error(f"Failed to load margin info: {e}")
            # Don't raise - this is not critical for basic operation

    async def _load_futures_positions(self) -> None:
        """Load futures positions from Gate.io futures REST API."""
        try:
            positions = await self._private_rest.get_positions()
            
            # Update internal position tracking
            for position in positions:
                if position.quantity != 0:  # Only track active positions
                    self._positions[position.symbol] = position
            
            self.logger.debug(f"Loaded {len(self._positions)} active positions")
            
        except Exception as e:
            self.logger.error(f"Failed to load futures positions: {e}")
            # Don't raise - this is not critical for basic operation

    # Gate.io futures-specific position event handler

    async def _position_handler(self, position: Position) -> None:
        """Handle position updates from Gate.io futures WebSocket."""
        try:
            # Update internal position state
            self._update_position(position)
            
            # Log significant position changes
            if abs(position.quantity) > 0:
                self.logger.info(f"Position update for {position.symbol}: {position.quantity} @ {position.entry_price}")
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
            'leverage_symbols': len(self._leverage_settings),
            'margin_symbols': len(self._margin_info),
            'long_positions': len([p for p in self._positions.values() if p.quantity > 0]),
            'short_positions': len([p for p in self._positions.values() if p.quantity < 0])
        })
        return base_stats