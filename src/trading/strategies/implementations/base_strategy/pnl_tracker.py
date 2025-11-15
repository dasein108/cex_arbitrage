from typing import Optional

from msgspec import Struct

from exchanges.structs import Side
from utils.math_utils import calculate_weighted_price


class PnlTracker(Struct):
    """Unified PNL tracking with weighted average entry/exit prices."""
    # Weighted average prices for all trades
    avg_entry_price: float = 0.0
    avg_exit_price: float = 0.0
    total_entry_qty: float = 0.0  # Total quantity entered
    total_exit_qty: float = 0.0  # Total quantity exited

    # Cumulative PNL tracking
    total_pnl_usdt: float = 0.0
    total_fees: float = 0.0

    # Position side for PNL calculation
    position_side: Optional[Side] = None

    # Cached calculations for performance
    _pnl_usdt_net_cached: Optional[float] = None
    _pnl_pct_cached: Optional[float] = None
    _pnl_pct_net_cached: Optional[float] = None
    _cache_valid: bool = False

    def add_entry(self, price: float, quantity: float, side: Side, fee_rate: float = 0.0):
        """Record a position entry (buy for long, sell for short)."""
        if not self.position_side:
            self.position_side = side

        # Update weighted average entry price
        if self.total_entry_qty > 0:
            self.total_entry_qty, self.avg_entry_price = calculate_weighted_price(
                self.avg_entry_price, self.total_entry_qty, price, quantity
            )
        else:
            self.avg_entry_price = price
            self.total_entry_qty = quantity

        # Track entry fees
        if fee_rate > 0:
            self.total_fees += (price * quantity * fee_rate)

        self._cache_valid = False

    def add_exit(self, price: float, quantity: float, fee_rate: float = 0.0):
        """Record a position exit and calculate realized PNL."""
        if not self.position_side or self.avg_entry_price <= 0:
            return

        # Calculate PNL for this exit
        if self.position_side == Side.BUY:  # Long position
            pnl = (price - self.avg_entry_price) * quantity
        else:  # Short position
            pnl = (self.avg_entry_price - price) * quantity

        self.total_pnl_usdt += pnl

        # Update weighted average exit price
        if self.total_exit_qty > 0:
            self.total_exit_qty, self.avg_exit_price = calculate_weighted_price(
                self.avg_exit_price, self.total_exit_qty, price, quantity
            )
        else:
            self.avg_exit_price = price
            self.total_exit_qty = quantity

        # Track exit fees
        if fee_rate > 0:
            self.total_fees += (price * quantity * fee_rate)

        self._cache_valid = False

    def _recalculate_cache(self):
        """Recalculate cached values."""
        self._pnl_usdt_net_cached = self.total_pnl_usdt - self.total_fees

        # Calculate percentages based on total entry value
        if self.total_entry_qty > 0 and self.avg_entry_price > 0:
            entry_value = self.avg_entry_price * self.total_entry_qty
            self._pnl_pct_cached = (self.total_pnl_usdt / entry_value) * 100
            self._pnl_pct_net_cached = (self._pnl_usdt_net_cached / entry_value) * 100
        else:
            self._pnl_pct_cached = 0.0
            self._pnl_pct_net_cached = 0.0

        self._cache_valid = True

    @property
    def pnl_usdt(self) -> float:
        """Get total raw PNL in USDT."""
        return self.total_pnl_usdt

    @property
    def pnl_usdt_net(self) -> float:
        """Get total net PNL after fees."""
        if not self._cache_valid:
            self._recalculate_cache()
        return self._pnl_usdt_net_cached or 0.0

    @property
    def pnl_pct(self) -> float:
        """Get total PNL percentage."""
        if not self._cache_valid:
            self._recalculate_cache()
        return self._pnl_pct_cached or 0.0

    @property
    def pnl_pct_net(self) -> float:
        """Get total net PNL percentage."""
        if not self._cache_valid:
            self._recalculate_cache()
        return self._pnl_pct_net_cached or 0.0

    @property
    def position_closed_percent(self) -> float:
        """Calculate what percentage of entered position has been exited."""
        if self.total_entry_qty > 0:
            return (self.total_exit_qty / self.total_entry_qty) * 100
        return 0.0

    @property
    def unrealized_qty(self) -> float:
        """Get quantity that hasn't been exited yet."""
        return max(0.0, self.total_entry_qty - self.total_exit_qty)

    @property
    def unrealized_qty_quote(self) -> float:
        """Get quote currency value of unrealized quantity."""
        return self.unrealized_qty * self.avg_entry_price

    def calculate_unrealized_pnl(self, current_price: float, fee_rate: float = 0.0) -> Optional[float]:
        """Calculate unrealized PNL for remaining position."""
        remaining = self.unrealized_qty
        if remaining <= 0 or not self.position_side:
            return None

        if self.position_side == Side.BUY:
            pnl = (current_price - self.avg_entry_price) * remaining
        else:
            pnl = (self.avg_entry_price - current_price) * remaining

        # Subtract estimated exit fees
        if fee_rate > 0:
            pnl -= (current_price * remaining * fee_rate)
            pnl -= (self.avg_entry_price * remaining * fee_rate)  # Entry fee for unrealized portion

        return pnl

    def reset(self):
        """Reset all PNL tracking."""
        self.avg_entry_price = 0.0
        self.avg_exit_price = 0.0
        self.total_entry_qty = 0.0
        self.total_exit_qty = 0.0
        self.total_pnl_usdt = 0.0
        self.total_fees = 0.0
        self.position_side = None
        self._pnl_usdt_net_cached = None
        self._pnl_pct_cached = None
        self._pnl_pct_net_cached = None
        self._cache_valid = False

    def __str__(self):
        return (f"PNL: {self.total_pnl_usdt:.4f}$ net: {self.pnl_usdt_net:.4f}$ |"
                f" {self.avg_entry_price:.4f} -> {self.avg_exit_price:.4f} ({self.total_exit_qty:.4f})")


class PositionChange(Struct):
    """Simplified position change tracking."""
    qty_before: float
    price_before: float
    qty_after: float
    price_after: float
    realized_pnl: float = 0.0  # Direct PNL value instead of object
    realized_pnl_net: float = 0.0  # Net PNL after fees

    @property
    def is_changed(self):
        return self.qty_after > self.qty_before + 1e-8 or self.qty_after < self.qty_before - 1e-8

    @property
    def has_pnl(self) -> bool:
        """Check if this position change includes PNL calculation."""
        return abs(self.realized_pnl) > 1e-8

    def __str__(self):
        if abs(self.qty_after - self.qty_before) < 1e-8:
            return f"[No Change] {self.qty_before:.4f} @ {self.price_before:.8f}"

        result = (f"Change: {self.qty_before:.4f} @ {self.price_before:.8f} -> "
                  f"{self.qty_after:.4f} @ {self.price_after:.8f}")
        if self.has_pnl:
            result += f" | PNL: {self.realized_pnl_net:.4f} USDT"
        return result
