"""
Portfolio state tracking and management.
"""

from typing import Dict, List, Optional
from datetime import datetime
import numpy as np

from .config import AssetState, PortfolioState, RebalanceConfig


class PortfolioTracker:
    """Tracks portfolio state and calculates metrics."""
    
    def __init__(self, assets: List[str], initial_capital: float, config: RebalanceConfig):
        """
        Initialize portfolio tracker.
        
        Args:
            assets: List of asset symbols to track
            initial_capital: Starting capital in USDT
            config: Rebalancing configuration
        """
        self.assets = assets
        self.initial_capital = initial_capital
        self.config = config
        
        # Initialize portfolio state
        self.positions: Dict[str, float] = {asset: 0.0 for asset in assets}
        self.usdt_balance = initial_capital
        self.last_rebalance: Dict[str, datetime] = {}
        
        # Performance tracking
        self.portfolio_history: List[PortfolioState] = []
        self.peak_value = initial_capital
        self.trough_value = initial_capital
        
    def update_prices(self, prices: Dict[str, float], timestamp: datetime) -> PortfolioState:
        """
        Update portfolio with new prices and return current state.
        
        Args:
            prices: Dictionary of asset prices
            timestamp: Current timestamp
            
        Returns:
            Current portfolio state
        """
        # Calculate asset states
        asset_states = {}
        total_asset_value = 0.0
        
        for symbol in self.assets:
            price = prices.get(symbol, 0.0)
            quantity = self.positions.get(symbol, 0.0)
            value = quantity * price
            total_asset_value += value
            
            asset_states[symbol] = AssetState(
                symbol=symbol,
                quantity=quantity,
                current_price=price,
                value_usdt=value,
                weight=0.0,  # Will calculate after total
                deviation=0.0,  # Will calculate after mean
                last_rebalance=self.last_rebalance.get(symbol)
            )
        
        # Calculate total portfolio value
        total_value = total_asset_value + self.usdt_balance
        
        # Calculate weights
        for asset in asset_states.values():
            if total_value > 0:
                asset.weight = asset.value_usdt / total_value
        
        # Calculate mean asset value (for equal weight portfolio)
        mean_asset_value = total_asset_value / len(self.assets) if self.assets else 0
        
        # Calculate deviations from mean
        for asset in asset_states.values():
            if mean_asset_value > 0:
                asset.deviation = (asset.value_usdt - mean_asset_value) / mean_asset_value
        
        # Create portfolio state
        state = PortfolioState(
            timestamp=timestamp,
            assets=asset_states,
            usdt_balance=self.usdt_balance,
            total_value=total_value,
            mean_asset_value=mean_asset_value
        )
        
        # Track history and performance
        self.portfolio_history.append(state)
        self.peak_value = max(self.peak_value, total_value)
        if total_value < self.trough_value:
            self.trough_value = total_value
        
        return state
    
    def execute_trade(self, symbol: str, quantity: float, price: float, 
                     side: str, timestamp: datetime) -> float:
        """
        Execute a trade and update portfolio.
        
        Args:
            symbol: Asset symbol
            quantity: Trade quantity
            price: Trade price
            side: 'BUY' or 'SELL'
            timestamp: Trade timestamp
            
        Returns:
            Trade value in USDT (including fees)
        """
        value = quantity * price
        fee = value * self.config.trading_fee
        
        if side == 'BUY':
            # Buying asset
            total_cost = value + fee
            if self.usdt_balance >= total_cost:
                self.positions[symbol] = self.positions.get(symbol, 0.0) + quantity
                self.usdt_balance -= total_cost
                self.last_rebalance[symbol] = timestamp
                return total_cost
            else:
                raise ValueError(f"Insufficient USDT balance: {self.usdt_balance} < {total_cost}")
        
        elif side == 'SELL':
            # Selling asset
            if self.positions.get(symbol, 0.0) >= quantity:
                self.positions[symbol] -= quantity
                proceeds = value - fee
                self.usdt_balance += proceeds
                self.last_rebalance[symbol] = timestamp
                return proceeds
            else:
                raise ValueError(f"Insufficient {symbol} balance: {self.positions.get(symbol, 0)} < {quantity}")
        
        else:
            raise ValueError(f"Invalid trade side: {side}")
    
    def check_cooldown(self, symbol: str, timestamp: datetime) -> bool:
        """
        Check if asset is in cooldown period.
        
        Args:
            symbol: Asset symbol
            timestamp: Current timestamp
            
        Returns:
            True if in cooldown, False otherwise
        """
        last_rebalance = self.last_rebalance.get(symbol)
        if not last_rebalance:
            return False
        
        time_since = (timestamp - last_rebalance).total_seconds()
        return time_since < (self.config.cooldown_minutes * 60)
    
    def get_portfolio_metrics(self) -> Dict:
        """
        Calculate portfolio performance metrics.
        
        Returns:
            Dictionary of performance metrics
        """
        if not self.portfolio_history:
            return {}
        
        current_state = self.portfolio_history[-1]
        
        # Calculate returns
        total_return = (current_state.total_value - self.initial_capital) / self.initial_capital
        
        # Calculate drawdown
        max_drawdown = (self.trough_value - self.peak_value) / self.peak_value if self.peak_value > 0 else 0
        
        # Calculate volatility (if enough history)
        if len(self.portfolio_history) > 2:
            values = [state.total_value for state in self.portfolio_history]
            returns = np.diff(values) / values[:-1]
            volatility = np.std(returns) if len(returns) > 0 else 0
            
            # Calculate Sharpe ratio (assuming 0 risk-free rate)
            avg_return = np.mean(returns) if len(returns) > 0 else 0
            sharpe_ratio = avg_return / volatility if volatility > 0 else 0
        else:
            volatility = 0
            sharpe_ratio = 0
        
        return {
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'current_value': current_state.total_value,
            'usdt_balance': self.usdt_balance,
            'portfolio_weight_std': self._calculate_weight_std(current_state)
        }
    
    def _calculate_weight_std(self, state: PortfolioState) -> float:
        """Calculate standard deviation of portfolio weights."""
        if not state.assets:
            return 0.0
        
        weights = [asset.weight for asset in state.assets.values()]
        target_weight = state.target_weight
        
        if target_weight > 0:
            deviations = [(w - target_weight) for w in weights]
            return np.std(deviations)
        return 0.0
    
    def initialize_equal_weights(self, prices: Dict[str, float], timestamp: datetime):
        """
        Initialize portfolio with equal weights.
        
        Args:
            prices: Current prices for all assets
            timestamp: Current timestamp
        """
        if not self.assets or not prices:
            return
        
        # Reserve for USDT
        usdt_reserve_amount = self.initial_capital * self.config.usdt_reserve
        available_capital = self.initial_capital - usdt_reserve_amount
        
        # Allocate equally to each asset
        per_asset_value = available_capital / len(self.assets)
        
        for symbol in self.assets:
            price = prices.get(symbol, 0)
            if price > 0:
                quantity = per_asset_value / price
                # Apply fee
                actual_cost = per_asset_value * (1 + self.config.trading_fee)
                
                if self.usdt_balance >= actual_cost:
                    self.positions[symbol] = quantity
                    self.usdt_balance -= actual_cost
                    self.last_rebalance[symbol] = timestamp