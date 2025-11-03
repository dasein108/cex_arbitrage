#!/usr/bin/env python3
"""
Comprehensive Cost Modeling for Arbitrage Strategies

Provides accurate cost modeling for cross-exchange arbitrage including:
- Trading fees
- Bid-ask spreads
- Slippage estimation
- Market impact
- Transfer costs
- Risk premiums
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
from trading.research.cross_arbitrage.arbitrage_analyzer import AnalyzerKeys


@dataclass
class CostBreakdown:
    """Detailed breakdown of all arbitrage costs."""
    trading_fees: float
    bid_ask_spreads: float
    slippage: float
    market_impact: float
    transfer_costs: float
    risk_premiums: float
    total_cost: float
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for logging/analysis."""
        return {
            'trading_fees': self.trading_fees,
            'bid_ask_spreads': self.bid_ask_spreads,
            'slippage': self.slippage,
            'market_impact': self.market_impact,
            'transfer_costs': self.transfer_costs,
            'risk_premiums': self.risk_premiums,
            'total_cost': self.total_cost
        }


class ArbitrageCostModel:
    """Comprehensive cost modeling for cross-exchange arbitrage strategies."""
    
    def __init__(self):
        # Trading fees (realistic exchange rates)
        self.mexc_spot_fee = 0.0010      # 0.1% taker fee
        self.gateio_spot_fee = 0.0020    # 0.2% taker fee  
        self.gateio_futures_fee = 0.0005 # 0.05% taker fee
        
        # Transfer costs (conservative estimates)
        self.withdrawal_fee_pct = 0.0001  # 0.01% withdrawal fee
        self.deposit_delay_cost = 0.0002  # 0.02% for delayed execution
        
        # Market impact parameters
        self.base_slippage_bps = 1.0      # 1 basis point base slippage
        self.impact_coefficient = 0.5     # Market impact scaling
        
        # Risk premiums
        self.execution_risk_bps = 0.5     # 0.5 bps for execution timing
        self.counterparty_risk_bps = 0.2  # 0.2 bps for exchange risk
        
        # Position size thresholds for scaling
        self.small_position_threshold = 500   # USD
        self.large_position_threshold = 5000  # USD

    def calculate_trading_fees(self, strategy_type: str = "rdn") -> float:
        """Calculate round-trip trading fees based on strategy type."""
        if strategy_type == "rdn":
            # RDN: MEXC spot + Gate.io futures (both directions)
            round_trip_fees = (self.mexc_spot_fee + self.gateio_futures_fee) * 2
        elif strategy_type == "spot_arbitrage":
            # Spot arbitrage: MEXC spot + Gate.io spot
            round_trip_fees = (self.mexc_spot_fee + self.gateio_spot_fee) * 2
        else:
            # Default conservative estimate
            round_trip_fees = 0.006  # 0.6%
            
        return round_trip_fees * 100  # Convert to percentage

    def calculate_spread_costs(self, df: pd.DataFrame, idx: int, strategy_type: str = "rdn") -> float:
        """Calculate bid-ask spread costs for strategy execution."""
        if strategy_type == "rdn":
            # RDN uses MEXC spot + Gate.io futures
            mexc_spread_pct = df.iloc[idx][ 'mexc_spread_pct'] if 'mexc_spread_pct' in df.columns else 0.1
            gateio_futures_spread_pct = df.iloc[idx][ 'gateio_futures_spread_pct'] if 'gateio_futures_spread_pct' in df.columns else 0.05
            
            # Apply half-spread cost for each leg (assuming limit orders get filled)
            total_spread_cost = (mexc_spread_pct + gateio_futures_spread_pct) / 2
        else:
            # Conservative default
            total_spread_cost = 0.15  # 15 basis points
            
        return total_spread_cost

    def calculate_slippage(self, position_size_usd: float, df: pd.DataFrame, idx: int) -> float:
        """Estimate slippage based on position size and market conditions."""
        # Base slippage scales with position size
        if position_size_usd <= self.small_position_threshold:
            size_multiplier = 1.0
        elif position_size_usd >= self.large_position_threshold:
            size_multiplier = 3.0
        else:
            # Linear scaling between thresholds
            size_multiplier = 1.0 + 2.0 * (position_size_usd - self.small_position_threshold) / (self.large_position_threshold - self.small_position_threshold)
        
        # Volatility adjustment
        spread_volatility = df.iloc[idx][ 'rdn_spread_volatility'] if 'rdn_spread_volatility' in df.columns else 0.1
        if not pd.isna(spread_volatility):
            vol_multiplier = min(2.0, spread_volatility / 0.1)  # Higher vol = more slippage
        else:
            vol_multiplier = 1.0
            
        slippage_bps = self.base_slippage_bps * size_multiplier * vol_multiplier
        return slippage_bps / 100  # Convert to percentage

    def calculate_market_impact(self, position_size_usd: float, df: pd.DataFrame, idx: int) -> float:
        """Estimate market impact based on position size and volatility."""
        # Impact scales with position size and volatility
        spread_volatility = df.iloc[idx][ 'rdn_spread_volatility'] if 'rdn_spread_volatility' in df.columns else 0.1
        
        if not pd.isna(spread_volatility) and spread_volatility > 0:
            volatility_factor = min(3.0, spread_volatility / 0.05)  # Scale with volatility
        else:
            volatility_factor = 1.0
            
        # Position size factor
        size_factor = min(2.0, position_size_usd / 1000)  # Scale with size
        
        impact_bps = self.impact_coefficient * volatility_factor * size_factor
        return impact_bps / 100  # Convert to percentage

    def calculate_transfer_costs(self) -> float:
        """Calculate transfer and timing costs."""
        transfer_cost_pct = (self.withdrawal_fee_pct + self.deposit_delay_cost) * 100
        return transfer_cost_pct

    def calculate_risk_premiums(self) -> float:
        """Calculate risk premiums for execution and counterparty risk."""
        risk_premium_bps = self.execution_risk_bps + self.counterparty_risk_bps
        return risk_premium_bps / 100  # Convert to percentage

    def calculate_opportunity_cost(self, holding_hours: float, annual_risk_free_rate: float = 0.05) -> float:
        """Calculate opportunity cost for capital tied up during trade."""
        hourly_rate = annual_risk_free_rate / (365 * 24)
        opportunity_cost_pct = (hourly_rate * holding_hours) * 100
        return opportunity_cost_pct

    def get_total_costs(self, df: pd.DataFrame, idx: int, position_size_usd: float, 
                       strategy_type: str = "rdn", holding_hours: float = 0) -> CostBreakdown:
        """Calculate comprehensive cost breakdown for arbitrage trade."""
        
        # Calculate each cost component
        trading_fees = self.calculate_trading_fees(strategy_type)
        spread_costs = self.calculate_spread_costs(df, idx, strategy_type)
        slippage = self.calculate_slippage(position_size_usd, df, idx)
        market_impact = self.calculate_market_impact(position_size_usd, df, idx)
        transfer_costs = self.calculate_transfer_costs()
        risk_premiums = self.calculate_risk_premiums()
        
        # Calculate opportunity cost if holding period specified
        opportunity_cost = self.calculate_opportunity_cost(holding_hours) if holding_hours > 0 else 0
        
        # Total cost
        total_cost = (
            trading_fees + spread_costs + slippage + 
            market_impact + transfer_costs + risk_premiums + opportunity_cost
        )
        
        return CostBreakdown(
            trading_fees=trading_fees,
            bid_ask_spreads=spread_costs,
            slippage=slippage,
            market_impact=market_impact,
            transfer_costs=transfer_costs,
            risk_premiums=risk_premiums,
            total_cost=total_cost
        )

    def validate_profitability(self, expected_gross_profit: float, costs: CostBreakdown, 
                             min_profit_margin: float = 0.15) -> tuple[bool, str]:
        """Validate that expected profit exceeds costs with safety margin."""
        expected_net_profit = expected_gross_profit - costs.total_cost
        profit_margin = expected_net_profit / expected_gross_profit if expected_gross_profit > 0 else 0
        
        if expected_net_profit < min_profit_margin:
            return False, f"Insufficient profit: {expected_net_profit:.3f}% < {min_profit_margin:.3f}%"
        
        if profit_margin < 0.3:  # Less than 30% profit margin
            return False, f"Low profit margin: {profit_margin:.1%}"
            
        return True, f"Profitable: {expected_net_profit:.3f}% net profit ({profit_margin:.1%} margin)"


# Convenience functions for specific strategies
def get_rdn_costs(df: pd.DataFrame, idx: int, position_size_usd: float, holding_hours: float = 0) -> CostBreakdown:
    """Get cost breakdown specifically for Reverse Delta-Neutral strategy."""
    cost_model = ArbitrageCostModel()
    return cost_model.get_total_costs(df, idx, position_size_usd, "rdn", holding_hours)


def validate_rdn_profitability(expected_spread_compression: float, df: pd.DataFrame, idx: int, 
                              position_size_usd: float) -> tuple[bool, str, CostBreakdown]:
    """Validate RDN trade profitability before entry."""
    cost_model = ArbitrageCostModel()
    costs = cost_model.get_total_costs(df, idx, position_size_usd, "rdn")
    
    is_profitable, reason = cost_model.validate_profitability(
        expected_spread_compression, costs, min_profit_margin=0.15
    )
    
    return is_profitable, reason, costs