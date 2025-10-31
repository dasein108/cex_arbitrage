from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any
from decimal import Decimal
from exchanges.structs import Order, OrderStatus
from exchanges.structs.common import Side
import msgspec
from msgspec import Struct

from utils.exchange_utils import is_order_done


class PositionError(Exception):
    """Custom exception for position-related errors."""
    pass


@dataclass
class PositionChange:
    """Records before/after state when position changes."""
    qty_before: float
    price_before: float
    qty_after: float
    price_after: float


@dataclass
class PnLTracker:
    """Tracks PnL for a position in both base asset and USDT terms."""
    pnl_base: float = 0.0
    pnl_usdt: float = 0.0
    pnl_usdt_net: float = 0.0  # After fees
    total_fees: float = 0.0

    def update(self, trade_pnl_base: float, trade_pnl_usdt: float, fee: float):
        """Update PnL with new trade results."""
        self.pnl_base += trade_pnl_base
        self.pnl_usdt += trade_pnl_usdt
        self.total_fees += fee
        self.pnl_usdt_net = self.pnl_usdt - self.total_fees

    def __str__(self) -> str:
        return f"PnL: {self.pnl_usdt_net:.4f}$ (gross: {self.pnl_usdt:.4f}$, fees: {self.total_fees:.4f}$)"


class Position(Struct):
    """
    Unified position tracker for spot-futures arbitrage.
    
    Handles both spot and futures positions with proper PnL tracking
    and order management.
    """
    side: Side
    mode: Literal['accumulate', 'release', 'hedge'] = 'accumulate'
    
    # Position data
    qty: float = 0.0
    price: float = 0.0
    target_qty: float = 0.0
    acc_qty: float = 0.0  # Accumulated quantity (filled orders)
    acc_quote_qty: float = 0.0  # Accumulated quote quantity (for selling)
    entry_price: float = 0.0  # Initial entry price for PnL calculations
    # Order tracking
    last_order: Optional[Order] = None
    
    # PnL tracking
    pnl_tracker: PnLTracker = msgspec.field(default_factory=PnLTracker)

    def reset(self, new_target_qty: float = 0.0, reset_pnl: bool = True) -> 'Position':
        """Reset position to initial state."""
        self.qty = 0.0
        self.price = 0.0
        self.target_qty = new_target_qty
        self.acc_qty = 0.0
        self.acc_quote_qty = 0.0
        self.last_order = None
        self.entry_price = 0.0
        
        if reset_pnl:
            self.pnl_tracker = PnLTracker()
        
        return self

    @property
    def actual_qty(self) -> float:
        return self.qty - self.acc_qty

    def update(self, side: Side, filled_qty: float, filled_price: float, fee: float) -> 'Position':
        """Update position with a new fill."""
        if filled_qty <= 0:
            raise PositionError(f"Invalid filled quantity: {filled_qty}")
        
        if self.mode == 'accumulate':
            if side == Side.SELL:
                raise PositionError(f"Cannot SELL in accumulate mode")
            self._accumulate_position(filled_qty, filled_price, fee)
        
        elif self.mode == 'release':
            if side == Side.BUY:
                raise PositionError(f"Cannot BUY in release mode")
            self._release_position(filled_qty, filled_price, fee)
        
        elif self.mode == 'hedge':
            self._hedge_position(side, filled_qty, filled_price, fee)
        
        else:
            raise PositionError(f"Unknown position mode: {self.mode}")
        
        return self

    def _accumulate_position(self, filled_qty: float, filled_price: float, fee: float):
        """Handle accumulation (buying) logic."""
        # Calculate new average price
        total_cost = (self.qty * self.price) + (filled_qty * filled_price)
        new_qty = self.qty + filled_qty
        
        self.price = total_cost / new_qty if new_qty > 0 else filled_price
        self.qty = new_qty
        self.acc_qty += filled_qty

        
        # Update PnL (for accumulate, PnL is unrealized until release)
        self.pnl_tracker.update(0.0, 0.0, fee * filled_qty * filled_price)

    def _release_position(self, filled_qty: float, filled_price: float, fee: float):
        """Handle release (selling) logic."""
        if filled_qty > self.qty:
            raise PositionError(f"Cannot sell {filled_qty}, only have {self.qty}")
        
        # Calculate realized PnL
        cost_basis = self.price * filled_qty
        sale_proceeds = filled_price * filled_qty
        trade_pnl_usdt = sale_proceeds - cost_basis
        
        # Update position
        self.qty -= filled_qty
        self.acc_quote_qty += sale_proceeds
        
        # Update PnL
        self.pnl_tracker.update(0.0, trade_pnl_usdt, fee * filled_qty * filled_price)

    def _hedge_position(self, side: Side, filled_qty: float, filled_price: float, fee: float):
        """Handle hedge (futures) position logic."""
        # For hedge positions, we track signed quantities (negative for short)
        signed_qty = filled_qty if side == Side.BUY else -filled_qty
        
        if self.qty == 0:
            # New position
            self.qty = signed_qty
            self.price = filled_price
        else:
            # Existing position - calculate new average or close
            if (self.qty > 0 and side == Side.SELL) or (self.qty < 0 and side == Side.BUY):
                # Reducing position or reversing
                if abs(signed_qty) >= abs(self.qty):
                    # Position reversal or close
                    closed_qty = abs(self.qty)
                    remaining_qty = abs(signed_qty) - closed_qty
                    
                    # Calculate PnL for closed portion
                    if self.qty > 0:  # Was long, now selling
                        trade_pnl_usdt = (filled_price - self.price) * closed_qty
                    else:  # Was short, now buying
                        trade_pnl_usdt = (self.price - filled_price) * closed_qty
                    
                    # Update position
                    if remaining_qty > 0:
                        self.qty = remaining_qty if side == Side.BUY else -remaining_qty
                        self.price = filled_price
                    else:
                        self.qty = 0.0
                        self.price = 0.0
                    
                    self.pnl_tracker.update(0.0, trade_pnl_usdt, fee * filled_qty * filled_price)
                else:
                    # Partial reduction
                    trade_pnl_usdt = 0.0  # Unrealized until position is closed
                    self.qty += signed_qty
                    self.pnl_tracker.update(0.0, trade_pnl_usdt, fee * filled_qty * filled_price)
            else:
                # Adding to position - calculate new average price
                total_cost = (abs(self.qty) * self.price) + (filled_qty * filled_price)
                new_qty = abs(self.qty) + filled_qty
                
                self.price = total_cost / new_qty if new_qty > 0 else filled_price
                self.qty = new_qty if side == Side.BUY else -new_qty
                
                self.pnl_tracker.update(0.0, 0.0, fee * filled_qty * filled_price)

    def update_position_with_order(self, order: Order, fee: float) -> PositionChange:
        """Update position based on order fill and return change summary."""
        if not order or order.status not in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
            # Store order reference for tracking
            self.last_order = order
            return PositionChange(self.qty, self.price, self.qty, self.price)
        
        # Record before state
        qty_before = self.qty
        price_before = self.price
        
        # Update position with filled amount
        filled_qty = order.filled_quantity or 0.0
        avg_price = order.average_price or order.price
        
        if filled_qty > 0:
            self.update(order.side, filled_qty, avg_price, fee)

        if is_order_done(order):
            self.last_order = None
        else:
            # Store order reference
            self.last_order = order

        
        return PositionChange(qty_before, price_before, self.qty, self.price)

    def set_mode(self, mode: Literal['accumulate', 'release', 'hedge']) -> 'Position':
        """Set position mode."""
        if mode not in ['accumulate', 'release', 'hedge']:
            raise PositionError(f"Invalid mode: {mode}")
        self.mode = mode
        return self

    def get_remaining_qty(self, min_quantity: float = 0.0) -> float:
        """Get remaining quantity to reach target."""
        if self.mode == 'accumulate':
            remaining = max(0.0, self.target_qty - self.acc_qty)
        elif self.mode == 'release':
            remaining = max(0.0, self.qty)
        else:  # hedge
            remaining = max(0.0, abs(self.target_qty) - abs(self.qty))
        
        return remaining if remaining >= min_quantity else 0.0

    def is_fulfilled(self, min_quantity: float = 0.0) -> bool:
        """Check if position target is fulfilled."""
        remaining = self.get_remaining_qty(min_quantity)
        return remaining == 0.0

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized PnL based on current market price."""
        if self.qty == 0:
            return 0.0
        
        if self.mode == 'hedge':
            # For futures positions
            if self.qty > 0:  # Long position
                return (current_price - self.price) * self.qty
            else:  # Short position
                return (self.price - current_price) * abs(self.qty)
        else:
            # For spot positions
            return (current_price - self.price) * self.qty

    def __str__(self) -> str:
        side_str = "LONG" if self.qty >= 0 else "SHORT"
        return (f"{self.mode.upper()} {side_str} {abs(self.qty):.8f} @ {self.price:.8f} "
                f"(target: {self.target_qty:.8f}, acc: {self.acc_qty:.8f}) | {self.pnl_tracker}")