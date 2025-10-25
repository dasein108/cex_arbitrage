from itertools import accumulate

from msgspec import Struct
from typing import Optional, Literal

from exchanges.structs import Order
from exchanges.structs.common import Side
from utils import calculate_weighted_price
from utils.exchange_utils import is_order_done


class PositionError(Exception):
    """Custom exception for position management errors."""
    pass


class PositionChange(Struct):
    qty_before: float
    price_before: float
    qty_after: float
    price_after: float

    def __str__(self):
        if abs(self.qty_after - self.qty_before) < 1e-8:
            return f"[No Change] {self.qty_before:.4f} @ {self.price_before:.8f}"

        return (f"Change: {self.qty_before:.4f} @ {self.price_before:.8f} -> "
                f"{self.qty_after:.4f} @ {self.price_after:.8f}")


class Position(Struct):
    """Individual position information with float-only policy."""
    qty: float = 0.0
    price: float = 0.0
    acc_qty: float = 0.0  # in case of SELL accumulated base qty
    target_qty: float = 0.0

    mode: Literal['accumulate', 'release', 'hedge'] = 'accumulate'  # Position management mode

    side: Side = None
    last_order: Optional[Order] = None

    @property
    def acc_quote_qty(self) -> float:
        return self.acc_qty / self.price if self.price > 1e-8 else 0.0

    @property
    def qty_usdt(self) -> float:
        """Calculate position value in USDT."""
        return self.qty * self.price if self.price > 1e-8 else 0.0

    @property
    def has_position(self):
        return self.qty > 1e-8

    def __str__(self):
        return f"[{self.side.name}: {self.qty} @ {self.price}]" if self.side else "[No Position]"

    def update_position(self, side: Side, quantity: float, price: float) -> PositionChange:
        """Update position for specified exchange with automatic profit calculation.

        Args:
            side: Order side (BUY/SELL) for position direction

            quantity: Order quantity to update position with
            price: Order price for weighted average calculation

        Returns:
            New PositionChange with before/after qty and price

        Note:
            - Maintains position weighted average price for accurate P&L calculation
        """

        if quantity <= 0:
            return PositionChange(self.qty, self.price, self.qty, self.price)

        if self.mode != 'hedge':
            self.acc_qty += quantity

        # No existing position
        if not self.has_position:
            self.qty = quantity
            self.price = price
            self.side = side

            if self.side == Side.SELL:
                self.acc_quote_qty += quantity / price
                # self.acc_qty += quantity

            # self.target_qty -= quantity
            return PositionChange(0, 0, quantity, price)
        else:
            multiplier = 1 if self.side == side else -1
            signed_quantity = quantity * multiplier

            # Only accumulate quote qty from actual SELL operations (USDT received)
            if side == Side.SELL:
                self.acc_quote_qty += quantity / price
                # self.acc_qty += quantity

            # self.target_qty -= quantity

            new_qty, new_price = calculate_weighted_price(self.price, self.qty, price, signed_quantity)
            pos_change = PositionChange(self.qty, self.price, new_qty, new_price)

            self.qty = new_qty
            self.price = new_price

            return pos_change

    def update_position_with_order(self, order: Optional[Order] = None) -> PositionChange:
        """Update position based on an order object.

        Args:
            order: Order object with side, quantity, and price attributes

        Returns:
            New PositionChange with before/after qty and price
        """

        if not order:
            self.last_order = None
            return PositionChange(self.qty, self.price, self.qty, self.price)

        filled_qty = order.filled_quantity - (self.last_order.filled_quantity if self.last_order else 0)

        self.last_order = order if not is_order_done(order) else None

        return self.update_position(order.side, filled_qty, order.price)

    def is_fulfilled(self, min_base_amount: float) -> bool:
        """Check if position has reached its target quantity."""
        if self.mode == 'hedge':
            return False
        else:
            return self.get_remaining_qty(min_base_amount) <= 1e-8 and self.target_qty > 1e-8

    def get_remaining_qty(self, min_base_amount: float) -> float:
        """Calculate remaining quantity to reach target."""
        if self.mode == 'release':
            qty = self.target_qty - self.acc_qty
        elif self.mode == 'accumulate':  # accumulate
            qty = self.target_qty - self.acc_qty
        else:  # hedge
            qty = self.qty

        if qty < min_base_amount:
            return 0.0

        return qty

    def reset(self, target_qty=0.0):
        self.target_qty = target_qty
        self.acc_qty = 0.0
        self.qty = 0.0
        self.price = 0.0
        self.last_order = None
