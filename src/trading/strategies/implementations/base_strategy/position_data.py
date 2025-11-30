"""
Pure data structures for position tracking - serializable and exchange-agnostic.

This module provides clean separation between position data (serializable in contexts)
and position services (exchange operations). The data structures here can be safely
stored in msgspec.Struct contexts without any runtime dependencies.
"""

from msgspec import Struct, field
from typing import Optional, Dict

from exchanges.structs import Symbol, ExchangeEnum
from exchanges.structs.common import Side
from .pnl_tracker import PnlTracker, PositionChange


class PositionData(Struct):
    """Pure data structure for position state - serializable and exchange-agnostic.
    
    This class contains only position data and can be safely serialized/deserialized
    in task contexts. All exchange operations are handled by PositionManager.
    """
    qty: float = 0.0
    price: float = 0.0
    target_qty: float = 0.0
    symbol: Optional[Symbol] = None  # String representation for serialization
    exchange: Optional[ExchangeEnum] = None
    side: Optional[Side] = None
    filled_amount: Dict[Side, float] = field(default_factory=lambda: {Side.BUY: 0.0, Side.SELL: 0.0})

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
        from utils.math_utils import calculate_weighted_price
        self.filled_amount[side] += quantity

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

    def is_fulfilled(self, min_base_amount: float) -> bool:
        """Check if position has reached its target quantity."""
        delta = self.target_qty - self.qty
        return delta < min_base_amount and self.target_qty > 1e-8

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
        self.side = None
        self.filled_amount[Side.BUY] = 0.0
        self.filled_amount[Side.SELL] = 0.0

        if reset_pnl:
            self.pnl_tracker.reset()

        return self
