from msgspec import Struct
from typing import Optional

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
            return f"[No Change] {self.qty_before}:.4f @ {self.price_before}:.8f"

        return (f"Change: {self.qty_before}:.4f @ {self.price_before}:.8f -> "
                f"{self.qty_after}:.4f @ {self.price_after}:.8f")

class Position(Struct):
    """Individual position information with float-only policy."""
    qty: float = 0.0
    price: float = 0.0
    acc_quote_qty: float = 0.0 # in case of SELL accumulated quote qty
    side: Optional[Side] = None
    last_order: Optional[Order] = None

    def _str__(self):
        return f"{self.side.name} {self.qty}:.4f @{self.price}:.8f"

    @property
    def qty_usdt(self) -> float:
        """Calculate position value in USDT."""
        return self.qty / self.price if self.price > 1e-8 else 0.0

    @property
    def has_position(self):
        return self.qty > 1e-8

    def __str__(self):
        return f"[{self.side.name}: {self.qty} @ {self.price}]" if self.side else "[No Position]"

    def update_position(self,  side: Side, quantity: float, price: float) -> PositionChange:
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

        # No existing position
        if not self.has_position:
            self.qty = quantity
            self.price = price
            self.side = side

            if self.side == Side.SELL:
                self.acc_quote_qty += quantity * price

            return PositionChange(0,0,quantity,price)
        else:
            multiplier = 1 if self.side == side else -1
            signed_quantity = quantity * multiplier

            self.acc_quote_qty += signed_quantity * price

            new_price, new_qty = calculate_weighted_price(self.qty, self.price,signed_quantity, price)
            pos_change =  PositionChange(self.qty, self.price, new_price, new_qty)

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