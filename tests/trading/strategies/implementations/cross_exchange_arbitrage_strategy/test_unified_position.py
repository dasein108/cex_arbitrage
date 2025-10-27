"""Essential unit tests for unified_position.py with PNL tracking.

Test Coverage:
- Fill and release position with weighted average pricing
- PNL calculation with fees in release mode
- Hedge mode PNL tracking and calculations
- Cumulative PNL tracking from max position to zero
- Position mode behavior (accumulate vs release vs hedge)
- Position reset functionality
- Short position PNL calculations
"""

import pytest
from unittest.mock import MagicMock, patch
from exchanges.structs.common import Side
from exchanges.structs import Order
from trading.strategies.implementations.cross_exchange_arbitrage_strategy.unified_position import (
    Position, PositionChange, PositionPnl
)


def create_mock_order(side: Side, price: float, qty: float, filled_qty: float) -> Order:
    """Create a mock order with minimal required fields."""
    order = MagicMock(spec=Order)
    order.side = side
    order.price = price
    order.quantity = qty
    order.filled_quantity = filled_qty
    order.status = "filled" if filled_qty == qty else "partial"
    return order


@patch('trading.strategies.implementations.cross_exchange_arbitrage_strategy.unified_position.is_order_done')
class TestPosition:
    """Essential tests for Position class with PNL tracking."""
    
    def test_fill_and_release_with_weighted_average(self, mock_is_order_done):
        """Test filling position with weighted average pricing and complete release."""
        mock_is_order_done.return_value = True
        position = Position()
        
        # Fill position with two orders at different prices
        position.update(Side.BUY, 100.0, 50.0)  # 100 @ $50.00
        position.update(Side.BUY, 50.0, 60.0)   # 50 @ $60.00
        
        # Weighted average: (100*50 + 50*60) / 150 = 8000 / 150 = $53.33
        assert position.qty == 150.0
        assert abs(position.price - 53.333333) < 0.01
        assert position.side == Side.BUY
        assert position.max_position_qty == 150.0
        
        # Release position completely with two sell orders
        position.mode = 'release'  # Enable PNL tracking
        change1 = position.update(Side.SELL, 80.0, 55.0, 0.001)
        assert position.qty == 70.0
        assert change1.has_pnl is True
        
        change2 = position.update(Side.SELL, 70.0, 56.0, 0.001)
        assert position.qty == 0.0
        assert position.side is None
        assert change2.has_pnl is True
    
    def test_pnl_calculation_with_fees_release_mode(self, mock_is_order_done):
        """Test detailed PNL calculation with fees in release mode."""
        position = Position()
        position.mode = 'release'
        fee_rate = 0.001  # 0.1% fee
        
        # Open position: 100 @ $50.00
        position.update(Side.BUY, 100.0, 50.0)
        
        # Close with profit: sell 100 @ $55.00
        change = position.update(Side.SELL, 100.0, 55.0, fee_rate)
        
        # Verify PNL calculations
        assert change.has_pnl is True
        assert abs(change.pnl_usdt - 500.0) < 1e-6  # (55-50)*100
        assert abs(change.pnl_pct - 10.0) < 1e-6    # 10% profit
        
        # Verify fees: entry (50*100*0.001) + exit (55*100*0.001) = 5 + 5.5 = 10.5
        assert abs(change.total_fees - 10.5) < 1e-6
        assert abs(change.pnl_usdt_net - 489.5) < 1e-6  # 500 - 10.5
        assert abs(change.pnl_pct_net - 9.79) < 0.01    # Net percentage
        
        # Position should be closed
        assert position.qty == 0.0
        assert position.side is None
    
    def test_hedge_mode_pnl_tracking(self, mock_is_order_done):
        """Test PNL tracking in hedge mode with multiple trades."""
        position = Position()
        position.mode = 'hedge'
        fee_rate = 0.0015  # 0.15% fee
        
        # Open initial hedge position
        position.update(Side.BUY, 200.0, 45.0)
        assert position.qty == 200.0
        assert position.acc_qty == 0.0  # No accumulation in hedge mode
        assert position.max_position_qty == 200.0
        
        # First hedge trade with profit
        change1 = position.update(Side.SELL, 80.0, 48.0, fee_rate)
        assert change1.has_pnl is True
        assert position.qty == 120.0  # 200 - 80 = 120 remaining
        
        # Verify first hedge PNL: (48-45)*80 = 240 USDT
        assert abs(change1.pnl_usdt - 240.0) < 1e-6
        # Fees: (45*80*0.0015) + (48*80*0.0015) = 5.4 + 5.76 = 11.16
        assert abs(change1.total_fees - 11.16) < 1e-6
        assert abs(change1.pnl_usdt_net - 228.84) < 1e-6  # 240 - 11.16
        
        # Verify cumulative tracking in hedge mode
        assert abs(position.cumulative_pnl_usdt - 240.0) < 1e-6
        assert abs(position.cumulative_pnl_usdt_net - 228.84) < 1e-6
        assert position.position_closed_percent == 40.0  # 80/200 = 40%
        
        # Second hedge trade with loss
        change2 = position.update(Side.SELL, 60.0, 42.0, fee_rate)
        assert change2.has_pnl is True
        assert position.qty == 60.0  # 120 - 60 = 60 remaining
        
        # Verify second hedge PNL: (42-45)*60 = -180 USDT
        assert abs(change2.pnl_usdt - (-180.0)) < 1e-6
        # Fees: (45*60*0.0015) + (42*60*0.0015) = 4.05 + 3.78 = 7.83
        assert abs(change2.total_fees - 7.83) < 1e-6
        assert abs(change2.pnl_usdt_net - (-187.83)) < 1e-6  # -180 - 7.83
        
        # Verify final cumulative in hedge mode
        # Total PNL: 240 + (-180) = 60 USDT
        # Total fees: 11.16 + 7.83 = 18.99 USDT
        # Net PNL: 228.84 + (-187.83) = 41.01 USDT
        assert abs(position.cumulative_pnl_usdt - 60.0) < 1e-6
        assert abs(position.cumulative_pnl_usdt_net - 41.01) < 1e-6
        assert abs(position.cumulative_fees - 18.99) < 1e-6
        assert position.position_closed_percent == 70.0  # 140/200 = 70%
    
    def test_cumulative_pnl_tracking_full_lifecycle(self, mock_is_order_done):
        """Test cumulative PNL tracking from position build to complete closure."""
        position = Position()
        position.mode = 'release'
        fee_rate = 0.001
        
        # Build position in stages
        position.update(Side.BUY, 100.0, 50.0)  # 100 @ $50
        position.update(Side.BUY, 50.0, 52.0)   # 50 @ $52 (weighted avg: $50.67)
        assert position.max_position_qty == 150.0
        assert abs(position.price - 50.666667) < 0.01
        
        # Close in stages with different PNL outcomes
        # First close: profit
        change1 = position.update(Side.SELL, 60.0, 55.0, fee_rate)
        assert change1.has_pnl is True
        assert position.cumulative_pnl_usdt > 0
        assert position.position_closed_percent == 40.0  # 60/150
        
        # Second close: loss
        change2 = position.update(Side.SELL, 50.0, 48.0, fee_rate)
        assert change2.has_pnl is True
        assert abs(position.position_closed_percent - 73.33) < 0.1  # 110/150 ≈ 73.33%
        
        # Final close: profit
        change3 = position.update(Side.SELL, 40.0, 53.0, fee_rate)
        assert change3.has_pnl is True
        assert position.qty == 0.0
        assert position.position_closed_percent == 100.0
        
        # Verify cumulative summary
        summary = position.get_cumulative_pnl_summary()
        assert "Cumulative PNL:" in summary
        assert "Closed: 100.0%" in summary
        assert "Fees:" in summary
        assert position.cumulative_fees > 0
    
    def test_position_mode_behavior(self, mock_is_order_done):
        """Test different behaviors across position modes."""
        
        # Test accumulate mode (no PNL tracking)
        position_acc = Position()
        position_acc.mode = 'accumulate'
        position_acc.update(Side.BUY, 100.0, 50.0)
        change_acc = position_acc.update(Side.SELL, 50.0, 55.0, 0.001)
        assert change_acc.has_pnl is False
        assert position_acc.cumulative_pnl_usdt == 0.0
        
        # Test release mode (PNL tracking)
        position_rel = Position()
        position_rel.mode = 'release'
        position_rel.update(Side.BUY, 100.0, 50.0)
        change_rel = position_rel.update(Side.SELL, 50.0, 55.0, 0.001)
        assert change_rel.has_pnl is True
        assert position_rel.cumulative_pnl_usdt > 0
        
        # Test hedge mode (PNL tracking, no accumulation)
        position_hedge = Position()
        position_hedge.mode = 'hedge'
        position_hedge.update(Side.BUY, 100.0, 50.0)
        assert position_hedge.acc_qty == 0.0  # No accumulation
        change_hedge = position_hedge.update(Side.SELL, 50.0, 55.0, 0.001)
        assert change_hedge.has_pnl is True
        assert position_hedge.cumulative_pnl_usdt > 0
    
    def test_position_reset_functionality(self, mock_is_order_done):
        """Test that position reset clears all tracking data."""
        position = Position()
        position.mode = 'release'
        
        # Build position and create PNL
        position.update(Side.BUY, 100.0, 50.0)
        position.update(Side.SELL, 50.0, 55.0, 0.001)
        
        # Verify data exists
        assert position.max_position_qty > 0
        assert position.cumulative_pnl_usdt_net != 0
        assert position.cumulative_fees > 0
        
        # Reset and verify cleanup
        position.reset()
        assert position.qty == 0.0
        assert position.price == 0.0
        assert position.max_position_qty == 0.0
        assert position.max_position_price == 0.0
        assert position.cumulative_pnl_usdt == 0.0
        assert position.cumulative_pnl_usdt_net == 0.0
        assert position.cumulative_fees == 0.0
        assert position.get_cumulative_pnl_summary() == "No cumulative PNL (no position history)"
    
    def test_short_position_pnl_calculations(self, mock_is_order_done):
        """Test PNL calculations for short positions."""
        position = Position()
        position.mode = 'release'
        fee_rate = 0.0015
        
        # Open short position: Sell 100 @ $60.00
        position.update(Side.SELL, 100.0, 60.0)
        assert position.side == Side.SELL
        assert position.max_position_qty == 100.0
        
        # Close part with profit: Buy 40 @ $55.00
        change1 = position.update(Side.BUY, 40.0, 55.0, fee_rate)
        
        # Short PNL: (entry_price - exit_price) * quantity = (60-55)*40 = 200 USDT
        assert abs(change1.pnl_usdt - 200.0) < 1e-6
        # Fees: (60*40*0.0015) + (55*40*0.0015) = 3.6 + 3.3 = 6.9
        assert abs(change1.total_fees - 6.9) < 1e-6
        assert abs(change1.pnl_usdt_net - 193.1) < 1e-6
        
        # Verify cumulative tracking
        assert abs(position.cumulative_pnl_usdt - 200.0) < 1e-6
        assert abs(position.cumulative_pnl_usdt_net - 193.1) < 1e-6
        assert position.position_closed_percent == 40.0
        
        # Close remaining with loss: Buy 60 @ $65.00
        change2 = position.update(Side.BUY, 60.0, 65.0, fee_rate)
        
        # Short PNL: (60-65)*60 = -300 USDT
        assert abs(change2.pnl_usdt - (-300.0)) < 1e-6
        assert position.qty == 0.0
        assert position.position_closed_percent == 100.0
        
        # Final cumulative: 200 + (-300) = -100 USDT net
        assert abs(position.cumulative_pnl_usdt - (-100.0)) < 1e-6