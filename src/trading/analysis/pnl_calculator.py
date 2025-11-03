#!/usr/bin/env python3
"""
Corrected P&L Calculation for Arbitrage Strategies

Provides accurate P&L calculations that measure what arbitrage strategies
actually capture - spread compression and convergence opportunities.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from trading.analysis.cost_models import CostBreakdown, ArbitrageCostModel


@dataclass
class TradeResult:
    """Complete trade result with detailed breakdown."""
    gross_pnl_pct: float
    net_pnl_pct: float
    spread_compression: float
    entry_spread: float
    exit_spread: float
    cost_breakdown: CostBreakdown
    holding_hours: float
    profit_margin: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for analysis."""
        result = {
            'gross_pnl_pct': self.gross_pnl_pct,
            'net_pnl_pct': self.net_pnl_pct,
            'spread_compression': self.spread_compression,
            'entry_spread': self.entry_spread,
            'exit_spread': self.exit_spread,
            'holding_hours': self.holding_hours,
            'profit_margin': self.profit_margin
        }
        result.update(self.cost_breakdown.to_dict())
        return result


class ArbitragePnLCalculator:
    """Corrected P&L calculation for arbitrage strategies."""
    
    def __init__(self):
        self.cost_model = ArbitrageCostModel()

    def calculate_rdn_pnl(self, entry_data: Dict[str, float], exit_data: Dict[str, float],
                         position_size_usd: float, holding_hours: float,
                         df: pd.DataFrame = None, entry_idx: int = None) -> TradeResult:
        """
        Calculate P&L for Reverse Delta-Neutral arbitrage based on spread compression.
        
        This is the CORRECTED calculation that measures what RDN actually captures:
        spread compression between spot and futures prices.
        
        Args:
            entry_data: Dict with 'spot_price', 'futures_price' at entry
            exit_data: Dict with 'spot_price', 'futures_price' at exit  
            position_size_usd: Position size in USD
            holding_hours: How long position was held
            df: Optional DataFrame for cost calculation context
            entry_idx: Optional index for cost calculation context
            
        Returns:
            TradeResult with complete P&L breakdown
        """
        
        # 1. Calculate spreads at entry and exit
        entry_spread = entry_data['futures_price'] - entry_data['spot_price']
        exit_spread = exit_data['futures_price'] - exit_data['spot_price']
        
        # 2. Spread compression is the core arbitrage profit
        spread_compression = exit_spread - entry_spread
        
        # 3. Calculate gross P&L as percentage of position
        # Use spot price as reference for percentage calculation
        gross_pnl_pct = (spread_compression / entry_data['spot_price']) * 100
        
        # 4. Calculate comprehensive costs
        if df is not None and entry_idx is not None:
            costs = self.cost_model.get_total_costs(
                df, entry_idx, position_size_usd, "rdn", holding_hours
            )
        else:
            # Fallback cost estimate
            costs = CostBreakdown(
                trading_fees=0.3,
                bid_ask_spreads=0.2,
                slippage=0.1,
                market_impact=0.05,
                transfer_costs=0.05,
                risk_premiums=0.07,
                total_cost=0.77
            )
        
        # 5. Net P&L after all costs
        net_pnl_pct = gross_pnl_pct - costs.total_cost
        
        # 6. Calculate profit margin
        profit_margin = (net_pnl_pct / gross_pnl_pct * 100) if gross_pnl_pct != 0 else 0
        
        return TradeResult(
            gross_pnl_pct=gross_pnl_pct,
            net_pnl_pct=net_pnl_pct,
            spread_compression=spread_compression,
            entry_spread=entry_spread,
            exit_spread=exit_spread,
            cost_breakdown=costs,
            holding_hours=holding_hours,
            profit_margin=profit_margin
        )

    def calculate_spot_arbitrage_pnl(self, mexc_entry: float, mexc_exit: float,
                                   gateio_entry: float, gateio_exit: float,
                                   position_size_usd: float, holding_hours: float) -> TradeResult:
        """
        Calculate P&L for spot arbitrage (buy on one exchange, sell on another).
        
        Args:
            mexc_entry: MEXC price at entry
            mexc_exit: MEXC price at exit
            gateio_entry: Gate.io price at entry
            gateio_exit: Gate.io price at exit
            position_size_usd: Position size
            holding_hours: Holding period
            
        Returns:
            TradeResult with spot arbitrage P&L
        """
        
        # Spot arbitrage: price convergence between exchanges
        entry_spread = mexc_entry - gateio_entry  # Price difference at entry
        exit_spread = mexc_exit - gateio_exit     # Price difference at exit
        
        # Profit from spread convergence
        spread_compression = abs(entry_spread) - abs(exit_spread)
        
        # Gross P&L as percentage
        reference_price = (mexc_entry + gateio_entry) / 2
        gross_pnl_pct = (spread_compression / reference_price) * 100
        
        # Estimate costs for spot arbitrage
        costs = CostBreakdown(
            trading_fees=0.6,   # Higher fees for spot arbitrage
            bid_ask_spreads=0.3,
            slippage=0.15,
            market_impact=0.1,
            transfer_costs=0.2,  # Higher transfer costs between exchanges
            risk_premiums=0.1,
            total_cost=1.45      # Higher total costs
        )
        
        net_pnl_pct = gross_pnl_pct - costs.total_cost
        profit_margin = (net_pnl_pct / gross_pnl_pct * 100) if gross_pnl_pct != 0 else 0
        
        return TradeResult(
            gross_pnl_pct=gross_pnl_pct,
            net_pnl_pct=net_pnl_pct,
            spread_compression=spread_compression,
            entry_spread=entry_spread,
            exit_spread=exit_spread,
            cost_breakdown=costs,
            holding_hours=holding_hours,
            profit_margin=profit_margin
        )

    def calculate_expected_rdn_profit(self, current_spread: float, target_compression_pct: float = 50,
                                    spot_price: float = 1.0, df: pd.DataFrame = None, 
                                    idx: int = None, position_size_usd: float = 1000) -> Tuple[float, bool]:
        """
        Calculate expected profit for RDN entry based on spread compression target.
        
        Args:
            current_spread: Current spread (negative for RDN opportunities)
            target_compression_pct: Target compression percentage (50 = 50% compression)
            spot_price: Current spot price for percentage calculation
            df: DataFrame for cost context
            idx: Index for cost context  
            position_size_usd: Position size for cost calculation
            
        Returns:
            Tuple of (expected_net_profit_pct, is_profitable)
        """
        
        # Calculate target exit spread
        compression_amount = abs(current_spread) * (target_compression_pct / 100)
        target_exit_spread = current_spread + compression_amount
        
        # Expected gross profit from compression
        expected_gross_profit = (compression_amount / spot_price) * 100
        
        # Get cost estimate
        if df is not None and idx is not None:
            costs = self.cost_model.get_total_costs(df, idx, position_size_usd, "rdn")
            total_cost = costs.total_cost
        else:
            total_cost = 0.77  # Default estimate
        
        # Expected net profit
        expected_net_profit = expected_gross_profit - total_cost
        
        # Check profitability (need at least 15 basis points net profit)
        is_profitable = expected_net_profit >= 0.15
        
        return expected_net_profit, is_profitable

    def validate_trade_economics(self, trade_result: TradeResult, min_profit_bps: float = 15,
                               min_profit_margin: float = 20) -> Tuple[bool, str]:
        """
        Validate that trade economics make sense.
        
        Args:
            trade_result: Completed trade result
            min_profit_bps: Minimum profit in basis points
            min_profit_margin: Minimum profit margin percentage
            
        Returns:
            Tuple of (is_valid, explanation)
        """
        
        # Check minimum profit
        if trade_result.net_pnl_pct < (min_profit_bps / 100):
            return False, f"Insufficient profit: {trade_result.net_pnl_pct:.3f}% < {min_profit_bps/100:.3f}%"
        
        # Check profit margin
        if trade_result.profit_margin < min_profit_margin:
            return False, f"Low profit margin: {trade_result.profit_margin:.1f}% < {min_profit_margin:.1f}%"
        
        # Check that spread actually compressed (for RDN)
        if trade_result.spread_compression <= 0:
            return False, f"No spread compression: {trade_result.spread_compression:.4f}"
        
        # Check reasonable holding period
        if trade_result.holding_hours > 72:  # More than 3 days
            return False, f"Excessive holding period: {trade_result.holding_hours:.1f}h"
        
        return True, f"Valid trade: {trade_result.net_pnl_pct:.3f}% profit, {trade_result.profit_margin:.1f}% margin"


# Convenience functions for backward compatibility
def calculate_rdn_trade_pnl(spot_entry: float, futures_entry: float,
                           spot_exit: float, futures_exit: float,
                           position_size_usd: float = 1000, holding_hours: float = 0,
                           df: pd.DataFrame = None, entry_idx: int = None) -> Dict[str, Any]:
    """
    Simplified interface for RDN P&L calculation.
    
    Returns dictionary with key metrics for backward compatibility.
    """
    calculator = ArbitragePnLCalculator()
    
    entry_data = {'spot_price': spot_entry, 'futures_price': futures_entry}
    exit_data = {'spot_price': spot_exit, 'futures_price': futures_exit}
    
    result = calculator.calculate_rdn_pnl(
        entry_data, exit_data, position_size_usd, holding_hours, df, entry_idx
    )
    
    return result.to_dict()


def estimate_rdn_profit_potential(current_spread: float, spot_price: float,
                                 compression_scenarios: list = [30, 50, 70]) -> Dict[str, float]:
    """
    Estimate profit potential for different compression scenarios.
    
    Returns dictionary with profit estimates for each scenario.
    """
    calculator = ArbitragePnLCalculator()
    scenarios = {}
    
    for compression_pct in compression_scenarios:
        expected_profit, is_profitable = calculator.calculate_expected_rdn_profit(
            current_spread, compression_pct, spot_price
        )
        scenarios[f'compression_{compression_pct}pct'] = {
            'expected_profit': expected_profit,
            'is_profitable': is_profitable
        }
    
    return scenarios