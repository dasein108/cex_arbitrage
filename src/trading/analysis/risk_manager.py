#!/usr/bin/env python3
"""
Advanced Risk Management System for Arbitrage Strategies

Provides comprehensive risk management including:
- Dynamic position sizing based on volatility and market conditions
- Portfolio-level risk controls and limits
- Correlation monitoring and adjustment
- Advanced stop-loss and profit-taking logic
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from trading.analysis.cost_models import ArbitrageCostModel
from trading.research.cross_arbitrage.arbitrage_analyzer import AnalyzerKeys


@dataclass
class Position:
    """Represents an active arbitrage position."""
    position_id: int
    entry_time: int
    entry_spread: float
    spot_entry_price: float
    futures_entry_price: float
    position_size_usd: float
    entry_volatility: float
    max_profit_seen: float = 0.0
    unrealized_pnl: float = 0.0
    risk_factors: List[str] = field(default_factory=list)
    
    def update_unrealized_pnl(self, current_spread: float) -> None:
        """Update unrealized P&L based on current spread."""
        spread_compression = current_spread - self.entry_spread
        self.unrealized_pnl = (spread_compression / abs(self.entry_spread)) * 100 if self.entry_spread != 0 else 0
        self.max_profit_seen = max(self.max_profit_seen, self.unrealized_pnl)


@dataclass
class RiskMetrics:
    """Portfolio risk metrics."""
    total_exposure: float
    exposure_ratio: float
    position_count: int
    total_unrealized_pnl: float
    largest_position: float
    avg_position_size: float
    risk_utilization: float
    portfolio_volatility: float
    max_drawdown: float


@dataclass
class RiskLimits:
    """Risk limits and thresholds."""
    max_portfolio_risk: float = 0.05        # 5% of portfolio
    max_single_position: float = 0.02       # 2% of portfolio per trade
    max_concurrent_positions: int = 3       # Maximum open positions
    max_sector_exposure: float = 0.10       # 10% to any single token
    correlation_limit: float = 0.7          # Exit if correlation > 70%
    max_unrealized_loss: float = 0.015      # 1.5% max unrealized loss
    trailing_stop_threshold: float = 0.005  # Start trailing at 0.5% profit
    max_holding_hours: float = 48.0         # Maximum holding period
    volatility_exit_threshold: float = 1.0  # Exit if volatility > 100bp


class AdvancedRiskManager:
    """Comprehensive risk management for arbitrage strategies."""
    
    def __init__(self, base_capital: float = 100000, risk_limits: RiskLimits = None):
        self.base_capital = base_capital
        self.risk_limits = risk_limits or RiskLimits()
        self.cost_model = ArbitrageCostModel()
        
        # Position tracking
        self.active_positions: List[Position] = []
        self.closed_positions: List[Position] = []
        self.next_position_id = 1
        
        # Performance tracking
        self.total_realized_pnl = 0.0
        self.max_drawdown_seen = 0.0
        self.peak_portfolio_value = base_capital
        
        # Risk monitoring
        self.risk_events: List[Dict[str, Any]] = []

    def calculate_position_size(self, df: pd.DataFrame, idx: int, 
                              expected_profit: float, spread_volatility: float) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate risk-adjusted position size based on multiple factors.
        
        Args:
            df: Market data DataFrame
            idx: Current index
            expected_profit: Expected profit percentage
            spread_volatility: Current spread volatility
            
        Returns:
            Tuple of (position_size_usd, sizing_details)
        """
        
        # 1. Base position size
        base_size = self.base_capital * 0.01  # 1% of capital base
        
        # 2. Volatility adjustment (Kelly-like sizing)
        if spread_volatility > 0:
            # Higher volatility = smaller positions
            vol_adjustment = min(1.5, 0.15 / spread_volatility)
        else:
            vol_adjustment = 0.5
        
        # 3. Expected profit adjustment
        # Higher expected profit = larger positions (up to limit)
        profit_adjustment = min(2.0, expected_profit / 0.5)  # Scale with expected profit
        
        # 4. Portfolio heat adjustment
        current_exposure = sum(pos.position_size_usd for pos in self.active_positions)
        portfolio_heat = current_exposure / self.base_capital
        
        # Reduce size if approaching portfolio limits
        heat_adjustment = max(0.2, 1.0 - (portfolio_heat / self.risk_limits.max_portfolio_risk))
        
        # 5. Correlation adjustment
        correlation_adjustment = self._calculate_correlation_adjustment(df, idx)
        
        # 6. Liquidity adjustment
        liquidity_adjustment = self._calculate_liquidity_adjustment(df, idx)
        
        # Calculate final size
        adjusted_size = (
            base_size * vol_adjustment * profit_adjustment * 
            heat_adjustment * correlation_adjustment * liquidity_adjustment
        )
        
        # Apply hard limits
        max_single_position = self.base_capital * self.risk_limits.max_single_position
        final_size = min(adjusted_size, max_single_position)
        
        # Minimum viable position
        final_size = max(final_size, 100) if final_size > 50 else 0
        
        sizing_details = {
            'base_size': base_size,
            'vol_adjustment': vol_adjustment,
            'profit_adjustment': profit_adjustment,
            'heat_adjustment': heat_adjustment,
            'correlation_adjustment': correlation_adjustment,
            'liquidity_adjustment': liquidity_adjustment,
            'final_size': final_size,
            'max_allowed': max_single_position
        }
        
        return final_size, sizing_details

    def _calculate_correlation_adjustment(self, df: pd.DataFrame, idx: int) -> float:
        """Calculate position size adjustment based on correlation with existing positions."""
        if len(self.active_positions) == 0:
            return 1.0
        
        # Simplified correlation estimate
        # In real implementation, would calculate actual correlation between symbols
        correlation_penalty = len(self.active_positions) * 0.1  # Reduce 10% per existing position
        return max(0.5, 1.0 - correlation_penalty)

    def _calculate_liquidity_adjustment(self, df: pd.DataFrame, idx: int) -> float:
        """Calculate position size adjustment based on market liquidity."""
        # Check available liquidity from bid/ask quantities if available
        liquidity_cols = [
            col for col in df.columns 
            if col.endswith('_bid_qty') or col.endswith('_ask_qty')
        ]
        
        if not liquidity_cols:
            return 1.0  # No liquidity data available
        
        # Simplified liquidity check
        # In real implementation, would analyze order book depth
        return 1.0  # Conservative default

    def check_entry_risk_limits(self, df: pd.DataFrame, idx: int, 
                               position_size: float) -> Tuple[bool, List[str], List[str]]:
        """
        Comprehensive risk checks before allowing entry.
        
        Returns:
            Tuple of (can_enter, warnings, blockers)
        """
        warnings = []
        blockers = []
        
        # 1. Portfolio concentration limits
        current_exposure = sum(pos.position_size_usd for pos in self.active_positions)
        new_total_exposure = current_exposure + position_size
        
        if new_total_exposure / self.base_capital > self.risk_limits.max_portfolio_risk:
            blockers.append(f"Portfolio risk limit: {new_total_exposure/self.base_capital:.1%} > {self.risk_limits.max_portfolio_risk:.1%}")
        
        # 2. Maximum concurrent positions
        if len(self.active_positions) >= self.risk_limits.max_concurrent_positions:
            blockers.append(f"Max positions: {len(self.active_positions)} >= {self.risk_limits.max_concurrent_positions}")
        
        # 3. Position size limits
        if position_size > self.base_capital * self.risk_limits.max_single_position:
            blockers.append(f"Position too large: {position_size} > {self.base_capital * self.risk_limits.max_single_position}")
        
        # 4. Volatility regime checks
        spread_volatility = df.iloc[idx]['rdn_spread_volatility'] if 'rdn_spread_volatility' in df.columns else None
        if spread_volatility is not None and spread_volatility > self.risk_limits.volatility_exit_threshold:
            warnings.append(f"High volatility: {spread_volatility:.3f}%")
        
        # 5. Market stress indicators
        spread_momentum = df.iloc[idx]['rdn_spread_momentum'] if 'rdn_spread_momentum' in df.columns else None
        if spread_momentum is not None and spread_momentum < -0.2:
            warnings.append(f"Negative momentum: {spread_momentum:.3f}%")
        
        # 6. Existing position correlation
        if len(self.active_positions) > 1:
            warnings.append(f"Multiple positions: {len(self.active_positions)} active")
        
        can_enter = len(blockers) == 0
        return can_enter, warnings, blockers

    def create_position(self, df: pd.DataFrame, idx: int, entry_spread: float,
                       position_size: float) -> Position:
        """Create new position with risk tracking."""
        
        # Get entry prices
        spot_entry = df.iloc[idx][AnalyzerKeys.mexc_ask] if AnalyzerKeys.mexc_ask in df.columns else 1.0
        futures_entry = df.iloc[idx][AnalyzerKeys.gateio_futures_bid] if AnalyzerKeys.gateio_futures_bid in df.columns else 1.0
        
        # Get entry volatility
        entry_volatility = df.iloc[idx]['rdn_spread_volatility'] if 'rdn_spread_volatility' in df.columns else 0.1
        
        # Create position
        position = Position(
            position_id=self.next_position_id,
            entry_time=idx,
            entry_spread=entry_spread,
            spot_entry_price=spot_entry,
            futures_entry_price=futures_entry,
            position_size_usd=position_size,
            entry_volatility=entry_volatility
        )
        
        self.active_positions.append(position)
        self.next_position_id += 1
        
        return position

    def check_exit_conditions(self, df: pd.DataFrame, idx: int, 
                            position: Position) -> Tuple[bool, str, str]:
        """
        Advanced exit condition checking with multiple triggers.
        
        Returns:
            Tuple of (should_exit, exit_reason, exit_details)
        """
        
        current_spread = df.iloc[idx]['rdn_combined_spread'] if 'rdn_combined_spread' in df.columns else position.entry_spread
        
        # Update position P&L
        position.update_unrealized_pnl(current_spread)
        
        # Calculate holding period
        holding_periods = idx - position.entry_time if isinstance(idx, int) else 0
        holding_hours = holding_periods * 5 / 60  # Assuming 5-minute intervals
        
        # 1. PROFIT TARGET EXIT (50% compression)
        target_compression = 50
        compression_pct = position.unrealized_pnl
        
        if compression_pct >= target_compression:
            return True, "PROFIT_TARGET", f"Target achieved: {compression_pct:.1f}% compression"
        
        # 2. TRAILING STOP-LOSS
        if position.max_profit_seen > self.risk_limits.trailing_stop_threshold * 100:
            trailing_stop_level = position.max_profit_seen * 0.6  # 60% retention
            if position.unrealized_pnl < trailing_stop_level:
                return True, "TRAILING_STOP", f"Profit dropped to {position.unrealized_pnl:.1f}% from peak {position.max_profit_seen:.1f}%"
        
        # 3. MAXIMUM LOSS LIMIT
        if position.unrealized_pnl < -self.risk_limits.max_unrealized_loss * 100:
            return True, "MAX_LOSS", f"Max loss exceeded: {position.unrealized_pnl:.1f}%"
        
        # 4. VOLATILITY SPIKE EXIT
        spread_volatility = df.iloc[idx]['rdn_spread_volatility'] if 'rdn_spread_volatility' in df.columns else None
        if spread_volatility is not None and spread_volatility > self.risk_limits.volatility_exit_threshold:
            return True, "VOLATILITY_SPIKE", f"High volatility: {spread_volatility:.3f}%"
        
        # 5. MOMENTUM REVERSAL
        spread_momentum = df.iloc[idx]['rdn_spread_momentum'] if 'rdn_spread_momentum' in df.columns else None
        if spread_momentum is not None and spread_momentum < -0.1:
            return True, "MOMENTUM_REVERSAL", f"Negative momentum: {spread_momentum:.3f}%"
        
        # 6. TIME-BASED EXIT
        if holding_hours > self.risk_limits.max_holding_hours:
            return True, "MAX_TIME", f"Max holding time: {holding_hours:.1f}h"
        
        # 7. CORRELATION BREAKDOWN
        # Simplified - in real implementation would monitor actual correlation
        if len(self.active_positions) > 2 and holding_hours > 12:
            return True, "CORRELATION_RISK", f"Portfolio correlation risk after {holding_hours:.1f}h"
        
        return False, "HOLD", f"Continue holding: {position.unrealized_pnl:.1f}% unrealized, {holding_hours:.1f}h"

    def close_position(self, df: pd.DataFrame, idx: int, position: Position,
                      exit_reason: str) -> Dict[str, Any]:
        """Close position and calculate realized P&L."""
        
        # Get exit prices
        spot_exit = df.iloc[idx][AnalyzerKeys.mexc_bid] if AnalyzerKeys.mexc_bid in df.columns else position.spot_entry_price
        futures_exit = df.iloc[idx][AnalyzerKeys.gateio_futures_ask] if AnalyzerKeys.gateio_futures_ask in df.columns else position.futures_entry_price
        
        # Calculate final P&L using corrected spread-based calculation
        current_spread = df.iloc[idx]['rdn_combined_spread'] if 'rdn_combined_spread' in df.columns else position.entry_spread
        spread_compression = current_spread - position.entry_spread
        
        # Get costs for this trade
        holding_hours = (idx - position.entry_time) * 5 / 60 if isinstance(idx, int) else 0
        costs = self.cost_model.get_total_costs(df, idx, position.position_size_usd, "rdn", holding_hours)
        
        # Gross P&L from spread compression
        gross_pnl_pct = (spread_compression / abs(position.entry_spread)) * 100 if position.entry_spread != 0 else 0
        
        # Net P&L after costs
        net_pnl_pct = gross_pnl_pct - costs.total_cost
        realized_pnl_usd = (net_pnl_pct / 100) * position.position_size_usd
        
        # Update tracking
        self.total_realized_pnl += realized_pnl_usd
        self.active_positions.remove(position)
        self.closed_positions.append(position)
        
        # Update drawdown tracking
        current_portfolio_value = self.base_capital + self.total_realized_pnl
        if current_portfolio_value > self.peak_portfolio_value:
            self.peak_portfolio_value = current_portfolio_value
        
        drawdown = (self.peak_portfolio_value - current_portfolio_value) / self.peak_portfolio_value
        self.max_drawdown_seen = max(self.max_drawdown_seen, drawdown)
        
        trade_result = {
            'position_id': position.position_id,
            'entry_time': position.entry_time,
            'exit_time': idx,
            'holding_hours': holding_hours,
            'entry_spread': position.entry_spread,
            'exit_spread': current_spread,
            'spread_compression': spread_compression,
            'gross_pnl_pct': gross_pnl_pct,
            'net_pnl_pct': net_pnl_pct,
            'realized_pnl_usd': realized_pnl_usd,
            'position_size': position.position_size_usd,
            'exit_reason': exit_reason,
            'max_profit_seen': position.max_profit_seen,
            'cost_breakdown': costs.to_dict()
        }
        
        return trade_result

    def calculate_portfolio_metrics(self) -> RiskMetrics:
        """Calculate comprehensive portfolio risk metrics."""
        
        total_exposure = sum(pos.position_size_usd for pos in self.active_positions)
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in self.active_positions)
        
        # Portfolio volatility (simplified)
        if len(self.active_positions) > 1:
            position_volatilities = [pos.entry_volatility for pos in self.active_positions]
            portfolio_volatility = np.sqrt(np.mean([vol**2 for vol in position_volatilities]))
        else:
            portfolio_volatility = self.active_positions[0].entry_volatility if self.active_positions else 0
        
        return RiskMetrics(
            total_exposure=total_exposure,
            exposure_ratio=total_exposure / self.base_capital,
            position_count=len(self.active_positions),
            total_unrealized_pnl=total_unrealized_pnl,
            largest_position=max((pos.position_size_usd for pos in self.active_positions), default=0),
            avg_position_size=total_exposure / len(self.active_positions) if self.active_positions else 0,
            risk_utilization=(total_exposure / self.base_capital) / self.risk_limits.max_portfolio_risk,
            portfolio_volatility=portfolio_volatility,
            max_drawdown=self.max_drawdown_seen
        )

    def update_all_positions(self, df: pd.DataFrame, idx: int) -> None:
        """Update P&L for all active positions."""
        current_spread = df.iloc[idx]['rdn_combined_spread'] if 'rdn_combined_spread' in df.columns else 0
        
        for position in self.active_positions:
            position.update_unrealized_pnl(current_spread)

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary."""
        metrics = self.calculate_portfolio_metrics()
        
        return {
            'base_capital': self.base_capital,
            'total_realized_pnl': self.total_realized_pnl,
            'current_portfolio_value': self.base_capital + self.total_realized_pnl,
            'active_positions': len(self.active_positions),
            'closed_positions': len(self.closed_positions),
            'total_exposure': metrics.total_exposure,
            'exposure_ratio': metrics.exposure_ratio,
            'risk_utilization': metrics.risk_utilization,
            'max_drawdown': metrics.max_drawdown,
            'portfolio_volatility': metrics.portfolio_volatility
        }