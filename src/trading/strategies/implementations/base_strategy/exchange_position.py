import asyncio

from msgspec import Struct, field
from typing import Optional, Callable

from exchanges.dual_exchange import DualExchange
from exchanges.structs import Order, Symbol
from exchanges.structs.common import Side
from infrastructure.exceptions.exchange import OrderNotFoundError, InsufficientBalanceError
from infrastructure.logging import HFTLoggerInterface
from trading.strategies.implementations.base_strategy.pnl_tracker import PnlTracker, PositionChange
from utils.math_utils import calculate_weighted_price
from utils.exchange_utils import is_order_done


class PositionError(Exception):
    """Custom exception for position management errors."""
    pass


class ExchangePosition(Struct):
    """Simplified position with integrated PNL tracking."""
    qty: float = 0.0
    price: float = 0.0
    target_qty: float = 0.0
    symbol: Symbol = None

    side: Optional[Side] = None
    last_order: Optional[Order] = None

    # Integrated PNL tracker with avg entry/exit prices
    pnl_tracker: PnlTracker = field(default_factory=PnlTracker)

    @property
    def quote_qty(self) -> float:
        """Calculate position value in USDT."""
        return self.qty * self.price if self.price > 1e-8 else 0.0

    @property
    def has_position(self):
        return self.qty > 1e-8

    def __str__(self):
        return f"[{self.side.name}: {self.qty} @ {self.price}]" if self.side else "[No Position]"

    def _is_closing_operation(self, side: Side) -> bool:
        """Check if this side operation would close/reduce the current position."""
        if not self.has_position or not self.side:
            return False
        # Closing happens when order side is opposite to position side
        return (self.side == Side.BUY and side == Side.SELL) or (self.side == Side.SELL and side == Side.BUY)

    def update(self, side: Side, quantity: float, price: float, fee: float = 0.0) -> PositionChange:
        """Update position with simplified entry/exit logic based on order side.

        Args:
            side: Order side (BUY/SELL) for position direction
            quantity: Order quantity to update position with
            price: Order price for weighted average calculation
            fee: Fee rate for PNL calculation (e.g., 0.001 for 0.1%)

        Returns:
            New PositionChange with before/after qty and price and optional PNL

        Note:
            - When order.side == position.side: Add to position (entry)
            - When order.side != position.side: Reduce position (exit)
            - Maintains weighted average price for accurate P&L calculation
        """

        if quantity <= 0:
            return PositionChange(self.qty, self.price, self.qty, self.price)

        # No existing position - always entry
        if not self.has_position:
            self.qty = quantity
            self.price = price
            self.side = side

            # Track entry in PNL tracker
            self.pnl_tracker.add_entry(price, quantity, side, fee)

            return PositionChange(0, 0, quantity, price)

        # Same side as position = add to position (entry)
        if self.side == side:
            new_qty, new_price = calculate_weighted_price(self.price, self.qty, price, quantity)
            pos_change = PositionChange(self.qty, self.price, new_qty, new_price)
            self.qty = new_qty
            self.price = new_price

            # Always track entry when adding to position
            self.pnl_tracker.add_entry(price, quantity, side, fee)

            return pos_change

        # Opposite side = close/reduce position (exit)
        else:
            old_qty = self.qty
            old_price = self.price

            # Determine the quantity being closed
            close_qty = min(quantity, self.qty)

            # Calculate PNL for this exit
            realized_pnl = 0.0
            realized_pnl_net = 0.0
            if self.side and old_price > 1e-8:
                if self.side == Side.BUY:
                    realized_pnl = (price - old_price) * close_qty
                else:
                    realized_pnl = (old_price - price) * close_qty

                # Calculate fees
                total_fees = 0.0
                if fee > 0:
                    total_fees = (old_price * close_qty * fee) + (price * close_qty * fee)

                realized_pnl_net = realized_pnl - total_fees

            # Track exit in PNL tracker
            self.pnl_tracker.add_exit(price, close_qty, fee)

            if quantity < self.qty:
                # Reducing position - keep original price, reduce quantity
                new_qty = self.qty - quantity
                pos_change = PositionChange(old_qty, old_price, new_qty, old_price,
                                            realized_pnl=realized_pnl, realized_pnl_net=realized_pnl_net)
                self.qty = new_qty
                # price stays the same
            elif abs(quantity - self.qty) < 1e-8:  # Use epsilon comparison for floating point
                # Closing position completely
                pos_change = PositionChange(old_qty, old_price, 0, 0,
                                            realized_pnl=realized_pnl, realized_pnl_net=realized_pnl_net)
                self.qty = 0
                self.price = 0
                self.side = None
            else:
                # Reversing position (quantity > self.qty)
                remaining_qty = quantity - self.qty
                pos_change = PositionChange(old_qty, old_price, remaining_qty, price,
                                            realized_pnl=realized_pnl, realized_pnl_net=realized_pnl_net)
                self.qty = remaining_qty
                self.price = price
                self.side = side

                # Track the new position entry for the remaining quantity
                if remaining_qty > 0:
                    self.pnl_tracker.add_entry(price, remaining_qty, side, fee)

            return pos_change

    def update_position_with_order(self, order: Optional[Order] = None, fee: float = 0.0) -> PositionChange:
        """Update position based on an order object.

        Args:
            order: Order object with side, quantity, and price attributes
            fee: Fee rate for PNL calculation (e.g., 0.001 for 0.1%)

        Returns:
            New PositionChange with before/after qty and price and optional PNL
        """

        if not order:
            self.last_order = None
            return PositionChange(self.qty, self.price, self.qty, self.price)

        filled_qty = order.filled_quantity - (self.last_order.filled_quantity if self.last_order else 0)

        self.last_order = order if not is_order_done(order) else None

        return self.update(order.side, filled_qty, order.price, fee)

    def is_fulfilled(self, min_base_amount: float) -> bool:
        """Check if position has reached its target quantity."""
        return abs(self.qty - self.target_qty) < min_base_amount and self.target_qty > 1e-8

    def get_remaining_qty(self, min_base_amount: float) -> float:
        """Calculate remaining quantity to reach target."""
        if self.target_qty <= 1e-8:
            return 0.0
            
        remaining = abs(self.target_qty - self.qty)
        
        if remaining < min_base_amount:
            return 0.0

        return remaining

    def reset(self, target_qty=0.0, reset_pnl: bool = True):
        """Reset position and optionally reset PNL tracking."""
        self.target_qty = target_qty
        self.qty = 0.0
        self.price = 0.0
        self.last_order = None
        self.side = None

        if reset_pnl:
            self.pnl_tracker.reset()

        return self
    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self._ex: Optional[DualExchange] = None
    #     self._si: Optional[SymbolInfo] = None
    #     self._logger: Optional[HFTLoggerInterface] = None
    #     self._fees: Optional[Fees] = None
    #
    @property
    def is_futures(self):
        return self._ex.is_futures

    @property
    def tag(self):
        return f'{self._ex.exchange_enum.value}_{self.symbol}'

    @property
    def book_ticker(self):
        return self._ex.public.book_ticker[self.symbol]

    async def initialize(self, logger: HFTLoggerInterface, exchange: DualExchange, target_qty: float = 0.0,
                         save_context: Optional[Callable] = None):
        """Dynamically initialize private runtime-only attributes."""
        self._logger = logger
        self._ex = exchange
        symbols_info = await exchange.public.load_symbols_info()
        self._si = symbols_info.get(self.symbol)
        self._fees = self._ex.private.get_fees(self.symbol)
        self.target_qty = target_qty
        self._save_context = save_context
        await asyncio.gather(self.load_position_from_exchange(),
                             self.force_book_ticker_refresh(),
                             self.force_last_order_refresh())

    async def force_book_ticker_refresh(self):
        # force reload book ticker via REST API
        await self._ex.public.get_book_ticker(self.symbol, force=True)

    async def force_last_order_refresh(self):
        if not self.last_order:
            return

        order = None
        try:
            order = await self._ex.private.fetch_order(self.symbol, self.last_order.order_id)
        except OrderNotFoundError as e:
            self._logger.warning(f"⚠️ {self.tag} Could not find existing order '{self.last_order}' during reload: {e}")
            self.last_order = None

        if self.last_order is None and order:
            self._logger.info(f"Lag detected: SKIPPING {order} update as no last_order is set", )

        return self._track_order_execution(order)

    def _get_min_base_qty(self) -> float:
        price = self.book_ticker.bid_price
        return self._si.get_abs_min_quantity(price)

    def _track_order_execution(self, order: Optional[Order] = None) -> bool:
        """Process filled order and update context for specific market."""
        if not order:
            self.last_order = None
            return False

        try:
            if self.last_order.timestamp > order.timestamp:
                self._logger.warning(f"⚠️ {self.tag} Received out-of-order update for order "
                                     f"{order.order_id}: last_order timestamp {self.last_order.timestamp} > "
                                     f"order timestamp {order.timestamp}. Skipping update.")
                return False

            pos_change = self.update_position_with_order(order, fee=self._fees.taker_fee)
            if pos_change.is_changed:
                self._save_context and self._save_context()
                self._logger.info(f"📊 {self.tag} Updated position",
                                  side=order.side.name,
                                  qty_before=pos_change.qty_before,
                                  price_before=pos_change.price_before,
                                  qty_after=pos_change.qty_after,
                                  price_after=pos_change.price_after)

        except PositionError as pe:
            self._logger.error(f"🚫 {self.tag} Position update error after order fill",
                               error=str(pe))

        finally:
            return True

    async def sync_with_exchange(self) -> Order | None:
        """Get current order from exchange, track updates."""

        if not self.last_order:
            return None

        updated_order = await self._ex.private.get_active_order(self.symbol, self.last_order.order_id)

        if self._track_order_execution(updated_order):
            return updated_order

        return None

    async def _load_futures_position(self):
        position = await self._ex.private.get_position(self.symbol, force=True)

        if position:
            self.qty = position.qty_base
            self.price = position.entry_price
            self._logger.info(f"🔄 {self.tag} Loaded initial futures position {self}")
        else:
            self._logger.info(f"ℹ️ {self.tag} No existing futures position")
            self.reset(reset_pnl=False)

    async def _load_spot_position(self):
        min_qty = self._get_min_base_qty()
        book_ticker = self.book_ticker
        balance = await self._ex.private.get_asset_balance(self.symbol.base)

        if balance.available > min_qty:
            self.qty = balance.available

        # Fix price if not set
        if self.qty > 0 and self.price == 0:
            self._logger.info(f"⚠️{self.tag} Price was not set for spot position, guessing from order book")
            self.price = book_ticker.bid_price

        self._logger.info(f"🔄 {self.tag} Loaded initial spot position")

    async def load_position_from_exchange(self):
        """Load current position from exchange and reset local tracking."""
        if self.is_futures:
            await self._load_futures_position()
        else:
            await self._load_spot_position()

    async def cancel_order(self) -> Optional[Order]:
        """Safely cancel order with consistent error handling."""
        if self.last_order is None:
            self._logger.warning(f"⚠️ {self.tag} No active order to cancel")
            return None

        order_id = self.last_order.order_id

        try:
            order = await self._ex.private.cancel_order(self.symbol, order_id)
            self._logger.info(f"🛑 {self.tag} Cancelled", order=str(order), order_id=order_id)
        except Exception as e:
            self._logger.error(f"🚫 {self.tag} Failed to cancel order", error=str(e))
            # Try to fetch order status instead
        finally:
            order = await self._ex.private.fetch_order(self.symbol, order_id)

        self._track_order_execution(order)

        return order

    async def place_order(
            self,
            side: Side,
            quantity: float,
            price: float,
            is_market: bool = False,
            tag: str = ""
    ) -> Optional[Order]:
        """Place limit order with validation and error handling."""

        try:
            if is_market:
                order = await self._ex.private.place_market_order(
                    symbol=self.symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                )
            else:
                order = await self._ex.private.place_limit_order(
                    symbol=self.symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                )

            self._track_order_execution(order)

            self._logger.info(f"📈 {self.tag} placed order",
                             order_id=order.order_id,
                             order=str(order))

            return order

        except InsufficientBalanceError as ife:
            # Mark position as fulfilled if we can't place more orders due to balance
            self.qty = self.target_qty

            self._logger.error(f"🚫 {self.tag} Insufficient balance to place order "
                              f"| pos: {self}, order: {quantity} @ {price}  adjust position amount",
                              error=str(ife))
            return None
        except Exception as e:
            self._logger.error(f"🚫 {self.tag} Failed to place order", error=str(e))
            return None
        finally:
            self._save_context and self._save_context()


