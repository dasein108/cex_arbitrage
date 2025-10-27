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


class PositionPnl(Struct):
    """Self-contained PNL calculation module."""
    entry_price: float
    exit_price: float
    quantity: float
    position_side: Side  # Position side (BUY=long, SELL=short)
    fee_rate: float = 0.0  # Fee rate for calculation
    
    # Cached calculation results
    _calculated: bool = False
    _pnl_usdt: Optional[float] = None
    _pnl_pct: Optional[float] = None
    _pnl_usdt_net: Optional[float] = None
    _pnl_pct_net: Optional[float] = None
    _entry_fee_usdt: Optional[float] = None
    _exit_fee_usdt: Optional[float] = None

    def calculate(self):
        """Perform all PNL calculations and cache results."""
        if self._calculated:
            return self
            
        # Calculate raw PNL based on position side
        if self.position_side == Side.BUY:  # Long position
            self._pnl_usdt = (self.exit_price - self.entry_price) * self.quantity
        else:  # Side.SELL - Short position
            self._pnl_usdt = (self.entry_price - self.exit_price) * self.quantity
        
        # Calculate percentage PNL (based on entry value)
        entry_value = self.entry_price * self.quantity
        self._pnl_pct = (self._pnl_usdt / entry_value) * 100 if entry_value > 1e-8 else 0.0
        
        # Calculate fees if fee_rate provided
        if self.fee_rate > 0:
            self._entry_fee_usdt = entry_value * self.fee_rate
            self._exit_fee_usdt = (self.exit_price * self.quantity) * self.fee_rate
            total_fees = self._entry_fee_usdt + self._exit_fee_usdt
            
            # Calculate net PNL after fees
            self._pnl_usdt_net = self._pnl_usdt - total_fees
            self._pnl_pct_net = (self._pnl_usdt_net / entry_value) * 100 if entry_value > 1e-8 else 0.0
        else:
            self._entry_fee_usdt = 0.0
            self._exit_fee_usdt = 0.0
            self._pnl_usdt_net = self._pnl_usdt
            self._pnl_pct_net = self._pnl_pct
        
        self._calculated = True
        return self

    @property
    def pnl_usdt(self) -> float:
        """Get raw PNL in USDT."""
        self.calculate()
        return self._pnl_usdt

    @property
    def pnl_pct(self) -> float:
        """Get raw PNL percentage."""
        self.calculate()
        return self._pnl_pct

    @property
    def pnl_usdt_net(self) -> float:
        """Get net PNL in USDT after fees."""
        self.calculate()
        return self._pnl_usdt_net

    @property
    def pnl_pct_net(self) -> float:
        """Get net PNL percentage after fees."""
        self.calculate()
        return self._pnl_pct_net

    @property
    def entry_fee_usdt(self) -> float:
        """Get entry fee in USDT."""
        self.calculate()
        return self._entry_fee_usdt

    @property
    def exit_fee_usdt(self) -> float:
        """Get exit fee in USDT."""
        self.calculate()
        return self._exit_fee_usdt

    @property
    def total_fees(self) -> float:
        """Get total fees (entry + exit)."""
        self.calculate()
        return self._entry_fee_usdt + self._exit_fee_usdt

    def __str__(self):
        return (f"PNL: {self.pnl_usdt_net:.4f} USDT ({self.pnl_pct_net:.2f}%) "
                f"[Raw: {self.pnl_usdt:.4f} USDT, Fees: {self.total_fees:.4f} USDT]")


class PositionChange(Struct):
    qty_before: float
    price_before: float
    qty_after: float
    price_after: float
    pnl: Optional[PositionPnl] = None  # PNL module for this change

    @property
    def has_pnl(self) -> bool:
        """Check if this position change includes PNL calculation."""
        return self.pnl is not None

    @property
    def pnl_usdt(self) -> Optional[float]:
        """Get raw PNL in USDT."""
        return self.pnl.pnl_usdt if self.pnl else None

    @property
    def pnl_pct(self) -> Optional[float]:
        """Get raw PNL percentage."""
        return self.pnl.pnl_pct if self.pnl else None

    @property
    def pnl_usdt_net(self) -> Optional[float]:
        """Get net PNL in USDT after fees."""
        return self.pnl.pnl_usdt_net if self.pnl else None

    @property
    def pnl_pct_net(self) -> Optional[float]:
        """Get net PNL percentage after fees."""
        return self.pnl.pnl_pct_net if self.pnl else None

    @property
    def entry_fee_usdt(self) -> Optional[float]:
        """Get entry fee in USDT."""
        return self.pnl.entry_fee_usdt if self.pnl else None

    @property
    def exit_fee_usdt(self) -> Optional[float]:
        """Get exit fee in USDT."""
        return self.pnl.exit_fee_usdt if self.pnl else None

    @property
    def total_fees(self) -> float:
        """Get total fees (entry + exit)."""
        return self.pnl.total_fees if self.pnl else 0.0

    @property
    def close_quantity(self) -> Optional[float]:
        """Get close quantity for backward compatibility."""
        return self.pnl.quantity if self.pnl else None

    @property
    def entry_price(self) -> Optional[float]:
        """Get entry price for backward compatibility."""
        return self.pnl.entry_price if self.pnl else None

    @property
    def exit_price(self) -> Optional[float]:
        """Get exit price for backward compatibility."""
        return self.pnl.exit_price if self.pnl else None

    def get_pnl_summary(self) -> str:
        """Get PNL summary string."""
        return str(self.pnl) if self.pnl else ""

    def __str__(self):
        if abs(self.qty_after - self.qty_before) < 1e-8:
            return f"[No Change] {self.qty_before:.4f} @ {self.price_before:.8f}"

        result = (f"Change: {self.qty_before:.4f} @ {self.price_before:.8f} -> "
                  f"{self.qty_after:.4f} @ {self.price_after:.8f}")
        if self.has_pnl:
            result += f" | {self.get_pnl_summary()}"
        return result


class Position(Struct):
    """Individual position information with float-only policy."""
    qty: float = 0.0
    price: float = 0.0
    acc_qty: float = 0.0  # in case of SELL accumulated base qty
    target_qty: float = 0.0

    mode: Literal['accumulate', 'release', 'hedge'] = 'accumulate'  # Position management mode

    side: Side = None
    last_order: Optional[Order] = None
    
    # Cumulative PNL tracking from max position to zero
    max_position_qty: float = 0.0  # Track maximum position size achieved
    max_position_price: float = 0.0  # Track price when max position was achieved
    cumulative_pnl_usdt: float = 0.0  # Total realized PNL from max position to current
    cumulative_pnl_usdt_net: float = 0.0  # Total realized PNL after fees
    cumulative_fees: float = 0.0  # Total fees paid during position lifecycle

    @property
    def acc_quote_qty(self) -> float:
        return self.acc_qty * self.price if self.price > 1e-8 else 0.0

    @property
    def quote_qty(self) -> float:
        """Calculate position value in USDT."""
        return self.qty * self.price if self.price > 1e-8 else 0.0

    @property
    def has_position(self):
        return self.qty > 1e-8

    @property
    def remaining_qty(self) -> float:
        remaining = self.qty - self.acc_qty
        if remaining < 1e-8:
            return 0.0
        return remaining

    def __str__(self):
        return f"[{self.side.name}: {self.qty} @ {self.price}]" if self.side else "[No Position]"

    def update(self, side: Side, quantity: float, price: float, fee: float = 0.0) -> PositionChange:
        """Update position for specified exchange with automatic profit calculation.

        Args:
            side: Order side (BUY/SELL) for position direction
            quantity: Order quantity to update position with
            price: Order price for weighted average calculation
            fee: Fee rate for PNL calculation (e.g., 0.001 for 0.1%)

        Returns:
            New PositionChange with before/after qty and price and optional PNL

        Note:
            - Maintains position weighted average price for accurate P&L calculation
            - PNL calculated when mode is 'release' or 'hedge' and fee > 0
        """

        if quantity <= 0:
            return PositionChange(self.qty, self.price, self.qty, self.price)

        if self.mode != 'hedge':
            self.acc_qty += quantity

        # No existing position - simple case
        if not self.has_position:
            self.qty = quantity
            self.price = price
            self.side = side
            
            # Initialize max position tracking
            if quantity > self.max_position_qty:
                self.max_position_qty = quantity
                self.max_position_price = price
            
            return PositionChange(0, 0, quantity, price)
        
        # Same side - add to position with weighted average
        if self.side == side:
            new_qty, new_price = calculate_weighted_price(self.price, self.qty, price, quantity)
            pos_change = PositionChange(self.qty, self.price, new_qty, new_price)
            self.qty = new_qty
            self.price = new_price
            
            # Update max position tracking when adding to position
            if new_qty > self.max_position_qty:
                self.max_position_qty = new_qty
                self.max_position_price = new_price
            
            return pos_change
        
        # Opposite side - reducing or reversing position
        else:
            old_qty = self.qty
            old_price = self.price
            
            # Create PNL module if in release or hedge mode
            pnl_module = None
            if self.mode in ('release', 'hedge') and self.side and old_price > 1e-8:
                # Determine the quantity being closed
                close_qty = min(quantity, self.qty)
                
                # Create PNL module for calculation
                pnl_module = PositionPnl(
                    entry_price=old_price,
                    exit_price=price,
                    quantity=close_qty,
                    position_side=self.side,
                    fee_rate=fee
                )
                
                # Update cumulative PNL tracking when closing position
                self._update_cumulative_pnl(pnl_module)
            
            if quantity < self.qty:
                # Reducing position - keep original price, reduce quantity
                new_qty = self.qty - quantity
                pos_change = PositionChange(old_qty, old_price, new_qty, old_price, pnl=pnl_module)
                self.qty = new_qty
                # price stays the same
            elif abs(quantity - self.qty) < 1e-8:  # Use epsilon comparison for floating point
                # Closing position completely
                pos_change = PositionChange(old_qty, old_price, 0, 0, pnl=pnl_module)
                self.qty = 0
                self.price = 0
                self.side = None
            else:
                # Reversing position (quantity > self.qty)
                remaining_qty = quantity - self.qty
                pos_change = PositionChange(old_qty, old_price, remaining_qty, price, pnl=pnl_module)
                self.qty = remaining_qty
                self.price = price
                self.side = side
            
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
        if self.mode == 'hedge':
            return False
        else:
            return self.get_remaining_qty(min_base_amount) <= 1e-8 and self.target_qty > 1e-8

    def get_remaining_qty(self, min_base_amount: float) -> float:
        """Calculate remaining quantity to reach target."""
        if self.mode == 'release':
            qty = self.target_qty - self.acc_qty
        elif self.mode == 'accumulate':
            qty = self.target_qty - self.acc_qty
        else:  # hedge
            qty = self.qty

        if qty < min_base_amount:
            return 0.0

        return qty

    def reset(self, target_qty=0.0, reset_pnl: bool = True):
        self.target_qty = target_qty
        self.acc_qty = 0.0
        self.qty = 0.0
        self.price = 0.0
        self.last_order = None

        if reset_pnl:
            # Reset cumulative PNL tracking
            self.max_position_qty = 0.0
            self.max_position_price = 0.0
            self.cumulative_pnl_usdt = 0.0
            self.cumulative_pnl_usdt_net = 0.0
            self.cumulative_fees = 0.0
    
    def _update_cumulative_pnl(self, pnl_module: PositionPnl):
        """Update cumulative PNL tracking when position is reduced."""
        self.cumulative_pnl_usdt += pnl_module.pnl_usdt
        self.cumulative_pnl_usdt_net += pnl_module.pnl_usdt_net
        self.cumulative_fees += pnl_module.total_fees
    
    @property
    def cumulative_pnl_pct(self) -> float:
        """Calculate cumulative PNL percentage based on max position value."""
        if self.max_position_qty > 1e-8 and self.max_position_price > 1e-8:
            max_position_value = self.max_position_qty * self.max_position_price
            return (self.cumulative_pnl_usdt / max_position_value) * 100
        return 0.0
    
    @property
    def cumulative_pnl_pct_net(self) -> float:
        """Calculate cumulative net PNL percentage based on max position value."""
        if self.max_position_qty > 1e-8 and self.max_position_price > 1e-8:
            max_position_value = self.max_position_qty * self.max_position_price
            return (self.cumulative_pnl_usdt_net / max_position_value) * 100
        return 0.0
    
    @property
    def position_closed_percent(self) -> float:
        """Calculate what percentage of max position has been closed."""
        if self.max_position_qty > 1e-8:
            closed_qty = self.max_position_qty - self.qty
            return (closed_qty / self.max_position_qty) * 100
        return 0.0
    
    def get_cumulative_pnl_summary(self) -> str:
        """Get cumulative PNL summary string."""
        if self.max_position_qty > 1e-8:
            return (f"Cumulative PNL: {self.cumulative_pnl_usdt_net:.4f} USDT "
                   f"({self.cumulative_pnl_pct_net:.2f}%) | "
                   f"Closed: {self.position_closed_percent:.1f}% | "
                   f"Fees: {self.cumulative_fees:.4f} USDT")
        return "No cumulative PNL (no position history)"
    
