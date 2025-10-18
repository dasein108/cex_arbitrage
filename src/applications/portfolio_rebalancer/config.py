"""
Configuration and data structures for portfolio rebalancing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class ActionType(Enum):
    """Types of rebalancing actions."""
    SELL_UPSIDE = "sell_upside"      # Sell outperforming asset
    BUY_DOWNSIDE = "buy_downside"    # Buy underperforming asset
    REDISTRIBUTE = "redistribute"     # Redistribute proceeds
    NO_ACTION = "no_action"          # No action needed


@dataclass
class RebalanceConfig:
    """Configuration for portfolio rebalancing strategy."""
    
    # Threshold parameters (optimized for volatile crypto)
    upside_threshold: float = 0.40      # 40% above mean triggers sell
    downside_threshold: float = 0.35    # 35% below mean triggers buy
    
    # Trading parameters
    sell_percentage: float = 0.20       # Sell 20% of outperforming position
    usdt_reserve: float = 0.30         # Keep 30% of proceeds as USDT
    
    # Risk management
    min_order_value: float = 15.0      # Minimum order size in USDT
    cooldown_minutes: int = 30         # Cooldown between rebalances per asset
    
    # Position limits
    max_position_pct: float = 0.40     # Max 40% in any single asset
    min_position_pct: float = 0.15     # Min 15% in any single asset
    
    # Backtesting parameters
    initial_capital: float = 10000.0   # Starting capital for backtesting
    trading_fee: float = 0.001         # 0.1% trading fee


@dataclass
class AssetState:
    """State of a single asset in the portfolio."""
    symbol: str
    quantity: float
    current_price: float
    value_usdt: float
    weight: float                      # Percentage of portfolio
    deviation: float                    # Deviation from target weight
    last_rebalance: Optional[datetime] = None
    
    @property
    def in_cooldown(self) -> bool:
        """Check if asset is in cooldown period."""
        if not self.last_rebalance:
            return False
        # Cooldown logic handled by rebalancer with config
        return False  # Let rebalancer handle timing


@dataclass
class PortfolioState:
    """Current state of the entire portfolio."""
    timestamp: datetime
    assets: Dict[str, AssetState]
    usdt_balance: float
    total_value: float
    mean_asset_value: float
    
    @property
    def asset_count(self) -> int:
        """Number of assets in portfolio."""
        return len(self.assets)
    
    @property
    def target_weight(self) -> float:
        """Target weight per asset for equal weighting."""
        if self.asset_count == 0:
            return 0.0
        return 1.0 / self.asset_count
    
    def get_deviations(self) -> Dict[str, float]:
        """Get deviation from mean for each asset."""
        deviations = {}
        for symbol, asset in self.assets.items():
            if self.mean_asset_value > 0:
                deviations[symbol] = (asset.value_usdt - self.mean_asset_value) / self.mean_asset_value
            else:
                deviations[symbol] = 0.0
        return deviations


@dataclass
class RebalanceAction:
    """A single rebalancing action to execute."""
    timestamp: datetime
    action_type: ActionType
    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: float
    price: float
    value_usdt: float
    reason: str
    
    def __str__(self) -> str:
        """String representation of the action."""
        return (f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - "
                f"{self.side} {self.quantity:.4f} {self.symbol} @ ${self.price:.4f} "
                f"(${self.value_usdt:.2f}) - {self.reason}")


@dataclass 
class RebalanceEvent:
    """A complete rebalancing event with multiple actions."""
    timestamp: datetime
    trigger_asset: str
    trigger_deviation: float
    actions: List[RebalanceAction]
    portfolio_before: PortfolioState
    portfolio_after: Optional[PortfolioState] = None
    fees_paid: float = 0.0
    
    @property
    def total_volume(self) -> float:
        """Total trading volume of the event."""
        return sum(action.value_usdt for action in self.actions)
    
    @property
    def action_count(self) -> int:
        """Number of actions in this event."""
        return len(self.actions)