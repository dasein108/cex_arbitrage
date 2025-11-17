"""
Position Manager - Service layer for single position management.

This module provides a service layer that operates on a single PositionData while 
handling all exchange interactions. It replaces the hybrid ExchangePosition approach
with clean separation of data (PositionData) and services (PositionManager).
Each PositionManager handles exactly one position on one exchange.
"""

import asyncio
from typing import Optional, Callable, Awaitable

from exchanges.dual_exchange import DualExchange
from exchanges.structs import Order, SymbolInfo, Fees, AssetName, AssetBalance
from exchanges.structs.common import Side
from infrastructure.exceptions.exchange import OrderNotFoundError, InsufficientBalanceError
from infrastructure.logging import HFTLoggerInterface
from utils.exchange_utils import is_order_done

from .position_data import PositionData
from .pnl_tracker import PositionChange


class PositionManager:
    """Service layer for single position management.
    
    This class handles all exchange operations for a single position while keeping the actual
    position data pure and serializable. Each PositionManager instance manages exactly one
    position on one exchange, similar to the original ExchangePosition pattern.
    """

    def __init__(self,
                 position_data: PositionData,
                 exchange: DualExchange,
                 logger: HFTLoggerInterface,
                 save_context: Optional[Callable[[PositionData], None]] = None,
                 on_order_filled_callback: Optional[Callable[[Order, PositionChange], Awaitable[None]]] = None):
        self._position = position_data
        self._exchange = exchange
        self._logger = logger
        self._save_context = save_context

        # Exchange-specific data
        self._symbol_info: Optional[SymbolInfo] = None
        self._fees: Optional[Fees] = None
        self._last_order: Optional[Order] = None
        self._on_order_filled_callback = on_order_filled_callback

    @property
    def symbol(self):
        return self._position.symbol

    @property
    def position(self) -> PositionData:
        """Get the position data."""
        return self._position

    @property
    def qty(self) -> float:
        """Get the position quantity."""
        return self._position.qty

    @property
    def exchange(self) -> DualExchange:
        """Get the exchange."""
        return self._exchange

    @property
    def tag(self) -> str:
        """Generate logging tag for position manager."""
        exchange_name = self._exchange.exchange_enum.value if self._exchange else "Unknown"
        return f"{exchange_name}_{self.symbol}" if self.symbol else f"{exchange_name}_Position"

    @property
    def is_futures(self) -> bool:
        """Check if exchange is futures."""
        return self._exchange.is_futures if self._exchange else False

    @property
    def book_ticker(self):
        """Get book ticker for the symbol."""
        if self._exchange and self.symbol:
            return self._exchange.public.book_ticker.get(self.symbol)
        return None

    @property
    def has_order(self):
        return self._last_order is not None

    @property
    def balance_usdt(self):
        return self._exchange.private.balances[AssetName('USDT')].available

    @property
    def balance_base(self):
        return self._exchange.private.balances.get(self.symbol.base,
                                                   AssetBalance(self.symbol.base, 0, 0)).available

    async def initialize(self, target_qty: float = 0.0) -> bool:
        """Initialize position with exchange data."""
        try:
            if not self.symbol:
                raise ValueError("Symbol not set for position")

            # Load symbol info and fees
            symbols_info = await self._exchange.public.load_symbols_info()
            self._symbol_info = symbols_info.get(self.symbol)
            self._fees = self._exchange.private.get_fees(self.symbol)

            # Set target quantity
            self._position.target_qty = target_qty

            # Initialize position state from exchange
            await asyncio.gather(
                self.load_position_from_exchange(),
                self._force_book_ticker_refresh(),
                self._force_last_order_refresh()
            )

            self._logger.info(f"✅ {self.tag} Position initialized")
            return True

        except Exception as e:
            self._logger.error(f"❌ {self.tag} Failed to initialize position: {e}")
            return False

    async def load_position_from_exchange(self) -> None:
        """Load current position from exchange and update local data."""
        if self.is_futures:
            await self._load_futures_position()
        else:
            await self._load_spot_position()

    async def _load_futures_position(self) -> None:
        """Load futures position from exchange."""
        exchange_position = await self._exchange.private.get_position(self.symbol, force=True)

        if exchange_position:
            self._position.qty = exchange_position.qty_base
            self._position.price = exchange_position.entry_price
            self._logger.info(f"🔄 {self.tag} Loaded initial futures position: {self._position}")
        else:
            self._logger.info(f"ℹ️ {self.tag} No existing futures position")
            self._position.reset(reset_pnl=False)

    async def _load_spot_position(self) -> None:
        """Load spot position from exchange."""
        min_qty = self.get_min_base_qty()
        book_ticker = self.book_ticker
        balance = await self._exchange.private.get_asset_balance(self.symbol.base)

        if balance.available > min_qty:
            self._position.qty = balance.available
        else:
            self._position.qty = 0.0

        # Fix price if not set
        if self._position.qty > 0 and self._position.price == 0:
            self._logger.info(f"⚠️ {self.tag} Price was not set for spot position, guessing from order book")
            self._position.price = book_ticker.bid_price

        self._logger.info(f"🔄 {self.tag} Loaded initial spot position: {self._position}")

    async def _force_book_ticker_refresh(self) -> None:
        """Force reload book ticker via REST API."""
        await self._exchange.public.get_book_ticker(self.symbol, force=True)


    async def _force_last_order_refresh(self) -> None:
        """Refresh the last order status for the position."""
        if not self._last_order:
            return

        order = None

        try:
            order = await self._exchange.private.fetch_order(self.symbol, self._last_order.order_id)
        except OrderNotFoundError as e:
            self._logger.warning(f"⚠️ {self.tag} Could not find existing order '{self._last_order}' during reload: {e}")
            self._last_order = None

        if self._last_order is None and order:
            self._logger.info(f"Lag detected: SKIPPING {order} update as no last_order is set")

        await self._track_order_execution(order)

    def get_min_base_qty(self) -> float:
        """Get minimum base quantity for the exchange."""
        book_ticker = self.book_ticker

        if not book_ticker or not self._symbol_info:
            return 0.0

        price = book_ticker.bid_price if self._position.side == Side.BUY else book_ticker.ask_price
        return self._symbol_info.get_abs_min_quantity(price)

    async def _track_order_execution(self, order: Optional[Order] = None) -> bool:
        """Process filled order and update position data."""
        if not order:
            self._last_order = None
            return False

        try:
            # Check for out-of-order updates
            if self._last_order:
                # self._last_order.timestamp > order.timestamp or
                if (self._last_order.filled_quantity > order.filled_quantity or
                        (self._last_order.is_done and not order.is_done)):
                    self._logger.warning(f"⚠️ {self.tag} Received out-of-order update for order "
                                         f"{order.order_id}: last_order timestamp {self._last_order.timestamp} > "
                                         f"order timestamp {order.timestamp}. Skipping update.")

                return False

            pos_change = self.update_position_with_order(order)
            if pos_change.is_changed:
                self._save()
                self._on_order_filled_callback and await self._on_order_filled_callback(order, pos_change)
                self._logger.info(f"📊 {self.tag} Updated position",
                                  side=order.side.name,
                                  qty_before=pos_change.qty_before,
                                  price_before=pos_change.price_before,
                                  qty_after=pos_change.qty_after,
                                  price_after=pos_change.price_after)

        except Exception as pe:
            self._logger.error(f"🚫 {self.tag} Position update error after order fill",
                               error=str(pe))

        finally:
            return True

    def _save(self):
        self._save_context and self._save_context(self._position)

    def update_position_with_order(self, order: Optional[Order] = None) -> PositionChange:
        """Update position based on an order object."""
        if not order:
            self._last_order = None
            return PositionChange(self._position.qty, self._position.price, self._position.qty, self._position.price)

        filled_qty = order.filled_quantity - (self._last_order.filled_quantity if self._last_order else 0)

        self._last_order = order if not is_order_done(order) else None

        fee_rate = self._fees.taker_fee if self._fees else 0.0
        return self._position.update(order.side, filled_qty, order.price, fee_rate)

    async def place_market_order(self, side: Side, quantity: float) -> Optional[Order]:
        """Place market order for the position."""
        price = self.book_ticker.ask_price if side == Side.BUY else self.book_ticker.bid_price
        return await self.place_order(side, quantity, price, is_market=True)

    async def place_order(self, side: Side, quantity: float, price: float, is_market: bool = False) -> Optional[Order]:
        """Place order for the position."""

        try:
            if is_market:
                order = await self._exchange.private.place_market_order(
                    symbol=self.symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                )
            else:
                order = await self._exchange.private.place_limit_order(
                    symbol=self.symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                )

            await self._track_order_execution(order)

            self._logger.info(f"📈 {self.tag} placed order",
                              order_id=order.order_id,
                              order=str(order))

            return order

        except InsufficientBalanceError as ife:
            # Mark position as fulfilled if we can't place more orders due to balance
            # self._position.qty = self._position.target_qty

            await self.exchange.private.load_balances()
            self._position.qty = self.balance_base  # Adjust position qty to balance

            self._logger.error(f"🚫 {self.tag} Insufficient balance to place order "
                               f"| pos: {self._position}, order: {quantity} @ {price}  adjust position amount",
                               error=str(ife))
            return None
        except Exception as e:
            self._logger.error(f"🚫 {self.tag} Failed to place order", error=str(e))
            return None
        finally:
            self._save()

    async def cancel_order(self) -> Optional[Order]:
        """Cancel active order for the position."""
        if self._last_order is None:
            # self._logger.warning(f"⚠️ {self.tag} No active order to cancel")
            return None

        order_id = self._last_order.order_id

        try:
            order = await self._exchange.private.cancel_order(self.symbol, order_id)
            self._logger.info(f"🛑 {self.tag} Cancelled order", order=str(order), order_id=order_id)
        except Exception as e:
            self._logger.error(f"🚫 {self.tag} Failed to cancel order", error=str(e))
            # Try to fetch order status instead
        finally:
            order = await self._exchange.private.fetch_order(self.symbol, order_id)

        await self._track_order_execution(order)
        return order

    async def sync_with_exchange(self) -> Optional[Order]:
        """Get current order from exchange and track updates."""
        if not self._last_order:
            return None

        updated_order = await self._exchange.private.get_active_order(self.symbol, self._last_order.order_id)

        if await self._track_order_execution(updated_order):
            return updated_order

        return None

    @property
    def min_base_qty(self):
        return self._exchange.public.get_min_base_quantity(self.symbol)

    def is_fulfilled(self) -> bool:
        """Check if position has reached its target quantity."""
        return self._position.is_fulfilled(self.min_base_qty)

    def get_remaining_qty(self) -> float:
        """Calculate remaining quantity to reach target."""
        return self._position.get_remaining_qty(self.min_base_qty)

    def _should_cancel_trailing_order(self, current_price: float, trail_pct: float) -> float:
        """Return percent change between current_price and order_price from the perspective of the side.

        For SELL: positive when current_price > order_price.
        For BUY: positive when current_price < order_price.
        Returned value is in percent (e.g. 1.5 means 1.5%).
        """
        order = self._last_order
        if not order or order.price == 0:
            return 0.0

        if order.side == Side.SELL:
            return (current_price / order.price - 1.0) * 100.0 < -trail_pct
        else:
            return (1.0 - current_price / order.price) * 100.0 > trail_pct

    def _adjust_price_by_pct(self, price: float, price_pct: float, side: Side) -> float:
        """Adjust price by price_pct depending on side.

        For SELL: increases price by price_pct percent.
        For BUY: decreases price by price_pct percent.
        """
        factor = 1.0 + (price_pct / 100.0) if side == Side.SELL else 1.0 - (price_pct / 100.0)
        return self._symbol_info.round_quote(price * factor)

    async def place_trailing_limit_order(self, side: Side, quantity: float,
                                         top_offset_pct: float = 0, trail_pct: float = 0) -> Optional[Order]:
        order = self._last_order

        price = self.book_ticker.ask_price if side == Side.SELL else self.book_ticker.bid_price

        if self._should_cancel_trailing_order(price, trail_pct):
            self._logger.info(f"🔻 {self.tag} Updating trailing limit order from {order.price} to {price}")
            o = await self.cancel_order()
            if o and o.is_filled:
                return o  # Filled during cancel handle hedge outside
        elif order:
            if order.is_done:
                return order

            return None

        price_with_offset = self._adjust_price_by_pct(price, top_offset_pct, side)

        new_order = await self.place_order(side, quantity, price_with_offset, is_market=False)

        if new_order:
            self._logger.info(f"🔺 {self.tag} Placed trailing limit order {new_order}")
            if new_order.is_filled:
                return new_order

        return None
