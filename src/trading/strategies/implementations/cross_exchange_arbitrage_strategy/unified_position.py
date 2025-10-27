from itertools import accumulate

from msgspec import Struct, field
from typing import Optional, Literal

from exchanges.structs import Order
from exchanges.structs.common import Side
from utils import calculate_weighted_price
from utils.exchange_utils import is_order_done


class PositionError(Exception):
    """Custom exception for position management errors."""
    pass


class PnlTracker(Struct):
    """Unified PNL tracking with weighted average entry/exit prices."""
    # Weighted average prices for all trades
    avg_entry_price: float = 0.0
    avg_exit_price: float = 0.0
    total_entry_qty: float = 0.0  # Total quantity entered
    total_exit_qty: float = 0.0   # Total quantity exited
    
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


class Position(Struct):
    """Simplified position with integrated PNL tracking."""
    qty: float = 0.0
    price: float = 0.0
    acc_qty: float = 0.0  # in case of SELL accumulated base qty
    target_qty: float = 0.0

    mode: Literal['accumulate', 'release', 'hedge'] = 'accumulate'  # Position management mode

    side: Optional[Side] = None
    last_order: Optional[Order] = None
    
    # Integrated PNL tracker with avg entry/exit prices
    pnl_tracker: PnlTracker = field(default_factory=PnlTracker)

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
            
            # Track entry in PNL tracker
            self.pnl_tracker.add_entry(price, quantity, side, fee)
            
            return PositionChange(0, 0, quantity, price)
        
        # Same side - add to position with weighted average
        if self.side == side:
            new_qty, new_price = calculate_weighted_price(self.price, self.qty, price, quantity)
            pos_change = PositionChange(self.qty, self.price, new_qty, new_price)
            self.qty = new_qty
            self.price = new_price
            
            # Track additional entry in PNL tracker
            self.pnl_tracker.add_entry(price, quantity, side, fee)
            
            return pos_change
        
        # Opposite side - reducing or reversing position
        else:
            old_qty = self.qty
            old_price = self.price
            
            # Track exit in PNL tracker if in release or hedge mode
            realized_pnl = 0.0
            realized_pnl_net = 0.0
            if self.mode in ('release', 'hedge') and self.side and old_price > 1e-8:
                # Determine the quantity being closed
                close_qty = min(quantity, self.qty)
                
                # Calculate PNL for this exit
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
        """Reset position and optionally reset PNL tracking."""
        self.target_qty = target_qty
        self.acc_qty = 0.0
        self.qty = 0.0
        self.price = 0.0
        self.last_order = None
        # self.side = None

        if reset_pnl:
            self.pnl_tracker.reset()

        return self
    

    
