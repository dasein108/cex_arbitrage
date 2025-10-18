"""
Core rebalancing logic implementation.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .config import (
    RebalanceConfig, PortfolioState, RebalanceAction, 
    RebalanceEvent, ActionType
)
from .portfolio_tracker import PortfolioTracker


class ThresholdCascadeRebalancer:
    """
    Simple threshold-based cascade rebalancer for volatile crypto assets.
    """
    
    def __init__(self, assets: List[str], config: RebalanceConfig, tracker: PortfolioTracker):
        """
        Initialize rebalancer.
        
        Args:
            assets: List of asset symbols to manage
            config: Rebalancing configuration
            tracker: Portfolio state tracker
        """
        self.assets = assets
        self.config = config
        self.tracker = tracker
        
        # Track rebalancing history
        self.rebalance_history: List[RebalanceEvent] = []
        
    def check_rebalance_needed(self, state: PortfolioState) -> Optional[Tuple[str, float, str]]:
        """
        Check if rebalancing is needed based on current state.
        
        Args:
            state: Current portfolio state
            
        Returns:
            Tuple of (symbol, deviation, action) if rebalancing needed, None otherwise
        """
        deviations = state.get_deviations()
        
        for symbol, deviation in deviations.items():
            # Skip if in cooldown
            if self.tracker.check_cooldown(symbol, state.timestamp):
                continue
            
            # Check upside threshold
            if deviation > self.config.upside_threshold:
                return (symbol, deviation, 'upside')
            
            # Check downside threshold  
            elif deviation < -self.config.downside_threshold:
                return (symbol, deviation, 'downside')
        
        return None
    
    def calculate_rebalance_actions(self, state: PortfolioState, 
                                   trigger: Tuple[str, float, str]) -> List[RebalanceAction]:
        """
        Calculate rebalancing actions for the triggered asset.
        
        Args:
            state: Current portfolio state
            trigger: Tuple of (symbol, deviation, direction)
            
        Returns:
            List of rebalancing actions to execute
        """
        symbol, deviation, direction = trigger
        actions = []
        
        if direction == 'upside':
            actions = self._handle_upside_rebalance(state, symbol, deviation)
        elif direction == 'downside':
            actions = self._handle_downside_rebalance(state, symbol, deviation)
        
        return actions
    
    def _handle_upside_rebalance(self, state: PortfolioState, 
                                 symbol: str, deviation: float) -> List[RebalanceAction]:
        """
        Handle rebalancing for an outperforming asset.
        
        Args:
            state: Current portfolio state
            symbol: Outperforming asset symbol
            deviation: Deviation from mean
            
        Returns:
            List of actions to execute
        """
        actions = []
        asset = state.assets[symbol]
        
        # Calculate sell quantity (20% of position)
        sell_quantity = asset.quantity * self.config.sell_percentage
        sell_value = sell_quantity * asset.current_price
        
        # Check minimum order value
        if sell_value < self.config.min_order_value:
            return []
        
        # Create sell action
        actions.append(RebalanceAction(
            timestamp=state.timestamp,
            action_type=ActionType.SELL_UPSIDE,
            symbol=symbol,
            side='SELL',
            quantity=sell_quantity,
            price=asset.current_price,
            value_usdt=sell_value,
            reason=f"Outperforming by {deviation:.1%}, selling {self.config.sell_percentage:.0%}"
        ))
        
        # Calculate redistribution (after fees)
        fee = sell_value * self.config.trading_fee
        proceeds = sell_value - fee
        usdt_reserve = proceeds * self.config.usdt_reserve
        to_redistribute = proceeds - usdt_reserve
        
        # Redistribute to other assets
        other_assets = [a for a in self.assets if a != symbol]
        if other_assets and to_redistribute > 0:
            per_asset_value = to_redistribute / len(other_assets)
            
            for target_symbol in other_assets:
                target_asset = state.assets.get(target_symbol)
                if not target_asset or target_asset.current_price <= 0:
                    continue
                
                # Skip if amount too small
                if per_asset_value < self.config.min_order_value:
                    continue
                
                buy_quantity = per_asset_value / target_asset.current_price
                
                actions.append(RebalanceAction(
                    timestamp=state.timestamp,
                    action_type=ActionType.REDISTRIBUTE,
                    symbol=target_symbol,
                    side='BUY',
                    quantity=buy_quantity,
                    price=target_asset.current_price,
                    value_usdt=per_asset_value,
                    reason=f"Redistribution from {symbol} outperformance"
                ))
        
        return actions
    
    def _handle_downside_rebalance(self, state: PortfolioState,
                                   symbol: str, deviation: float) -> List[RebalanceAction]:
        """
        Handle rebalancing for an underperforming asset.
        
        Args:
            state: Current portfolio state
            symbol: Underperforming asset symbol
            deviation: Deviation from mean
            
        Returns:
            List of actions to execute
        """
        actions = []
        asset = state.assets[symbol]
        
        # Calculate target value and deficit
        target_value = state.mean_asset_value
        current_value = asset.value_usdt
        deficit = target_value - current_value
        
        # Check minimum order value
        if deficit < self.config.min_order_value:
            return []
        
        # First check if we have enough USDT
        if state.usdt_balance >= deficit:
            # Buy with available USDT
            buy_quantity = deficit / asset.current_price
            
            actions.append(RebalanceAction(
                timestamp=state.timestamp,
                action_type=ActionType.BUY_DOWNSIDE,
                symbol=symbol,
                side='BUY',
                quantity=buy_quantity,
                price=asset.current_price,
                value_usdt=deficit,
                reason=f"Underperforming by {deviation:.1%}, buying to rebalance"
            ))
        else:
            # Need to sell from outperforming assets
            outperformers = []
            for other_symbol, other_asset in state.assets.items():
                if other_symbol == symbol:
                    continue
                if other_asset.value_usdt > state.mean_asset_value:
                    outperformers.append((other_symbol, other_asset))
            
            if not outperformers:
                return []  # No assets to sell from
            
            # Calculate how much to sell from each outperformer
            total_excess = sum(asset.value_usdt - state.mean_asset_value 
                             for _, asset in outperformers)
            
            if total_excess <= 0:
                return []
            
            for source_symbol, source_asset in outperformers:
                # Calculate proportional sell amount
                asset_excess = source_asset.value_usdt - state.mean_asset_value
                sell_ratio = min(asset_excess / total_excess, 1.0)
                sell_value = deficit * sell_ratio
                
                # Apply max sell limit (25% of position)
                max_sell_value = source_asset.value_usdt * 0.25
                sell_value = min(sell_value, max_sell_value)
                
                if sell_value < self.config.min_order_value:
                    continue
                
                sell_quantity = sell_value / source_asset.current_price
                
                actions.append(RebalanceAction(
                    timestamp=state.timestamp,
                    action_type=ActionType.REDISTRIBUTE,
                    symbol=source_symbol,
                    side='SELL',
                    quantity=sell_quantity,
                    price=source_asset.current_price,
                    value_usdt=sell_value,
                    reason=f"Selling to support {symbol} rebalance"
                ))
            
            # Now add the buy action for the underperformer
            # Calculate total proceeds from sells
            total_proceeds = sum(a.value_usdt for a in actions) * (1 - self.config.trading_fee)
            
            if total_proceeds > self.config.min_order_value:
                buy_quantity = total_proceeds / asset.current_price
                
                actions.append(RebalanceAction(
                    timestamp=state.timestamp,
                    action_type=ActionType.BUY_DOWNSIDE,
                    symbol=symbol,
                    side='BUY',
                    quantity=buy_quantity,
                    price=asset.current_price,
                    value_usdt=total_proceeds,
                    reason=f"Underperforming by {deviation:.1%}, buying to rebalance"
                ))
        
        return actions
    
    def execute_rebalance(self, state: PortfolioState, 
                         prices: Dict[str, float]) -> Optional[RebalanceEvent]:
        """
        Check and execute rebalancing if needed.
        
        Args:
            state: Current portfolio state
            prices: Current asset prices
            
        Returns:
            RebalanceEvent if rebalancing occurred, None otherwise
        """
        # Check if rebalancing is needed
        trigger = self.check_rebalance_needed(state)
        
        if not trigger:
            return None
        
        symbol, deviation, direction = trigger
        
        # Calculate rebalancing actions
        actions = self.calculate_rebalance_actions(state, trigger)
        
        if not actions:
            return None
        
        # Create rebalance event
        event = RebalanceEvent(
            timestamp=state.timestamp,
            trigger_asset=symbol,
            trigger_deviation=deviation,
            actions=actions,
            portfolio_before=state
        )
        
        # Execute actions in portfolio tracker
        total_fees = 0
        for action in actions:
            try:
                if action.side in ['BUY', 'SELL']:
                    self.tracker.execute_trade(
                        symbol=action.symbol,
                        quantity=action.quantity,
                        price=action.price,
                        side=action.side,
                        timestamp=action.timestamp
                    )
                    total_fees += action.value_usdt * self.config.trading_fee
            except ValueError as e:
                print(f"Trade execution failed: {e}")
                continue
        
        event.fees_paid = total_fees
        
        # Get updated portfolio state
        event.portfolio_after = self.tracker.update_prices(prices, state.timestamp)
        
        # Store event
        self.rebalance_history.append(event)
        
        return event
    
    def get_statistics(self) -> Dict:
        """
        Get rebalancing statistics.
        
        Returns:
            Dictionary of statistics
        """
        if not self.rebalance_history:
            return {
                'total_events': 0,
                'total_actions': 0,
                'total_volume': 0,
                'total_fees': 0,
                'upside_triggers': 0,
                'downside_triggers': 0
            }
        
        upside_triggers = sum(1 for e in self.rebalance_history 
                            if any(a.action_type == ActionType.SELL_UPSIDE for a in e.actions))
        downside_triggers = sum(1 for e in self.rebalance_history 
                              if any(a.action_type == ActionType.BUY_DOWNSIDE for a in e.actions))
        
        return {
            'total_events': len(self.rebalance_history),
            'total_actions': sum(e.action_count for e in self.rebalance_history),
            'total_volume': sum(e.total_volume for e in self.rebalance_history),
            'total_fees': sum(e.fees_paid for e in self.rebalance_history),
            'upside_triggers': upside_triggers,
            'downside_triggers': downside_triggers,
            'avg_actions_per_event': sum(e.action_count for e in self.rebalance_history) / len(self.rebalance_history)
        }