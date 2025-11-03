#!/usr/bin/env python3
"""
Enhanced Entry/Exit Validation Framework

Provides comprehensive validation for arbitrage strategy signals with:
- Profit validation before entry
- Multi-factor analysis 
- Dynamic thresholds based on market conditions
- Historical context for extremeness detection
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from trading.analysis.cost_models import ArbitrageCostModel
from trading.analysis.pnl_calculator import ArbitragePnLCalculator


@dataclass
class ValidationResult:
    """Result of signal validation with detailed reasoning."""
    is_valid: bool
    signal_type: str  # 'ENTER', 'EXIT', 'HOLD'
    reason: str
    confidence: float  # 0-100
    expected_profit: Optional[float] = None
    risk_factors: Optional[list] = None
    
    def __str__(self) -> str:
        return f"{self.signal_type}: {self.reason} (confidence: {self.confidence:.1f}%)"


class RDNSignalValidator:
    """Enhanced signal validation specifically for Reverse Delta-Neutral strategy."""
    
    def __init__(self):
        self.cost_model = ArbitrageCostModel()
        self.pnl_calculator = ArbitragePnLCalculator()
        
        # Validation thresholds
        self.min_profit_margin = 0.15      # 15 basis points minimum profit
        self.min_volatility = 0.05         # 5 basis points minimum volatility
        self.min_compression_target = 30   # 30% compression target
        self.max_momentum_threshold = -0.1 # Avoid entries with negative momentum
        
        # Historical context parameters
        self.extremeness_lookback = 100    # Periods to look back for percentiles
        self.extremeness_threshold = 0.05  # Must be in bottom 5th percentile

    def validate_rdn_entry(self, df: pd.DataFrame, idx: int, position_size_usd: float = 1000,
                          context_window: int = None) -> ValidationResult:
        """
        Comprehensive validation for RDN entry signals.
        
        Validates:
        1. Profit potential after costs
        2. Market volatility and momentum
        3. Historical extremeness
        4. Risk factors
        
        Args:
            df: DataFrame with market data and indicators
            idx: Current index for validation
            position_size_usd: Position size for cost calculation
            context_window: Override for historical context window
            
        Returns:
            ValidationResult with detailed analysis
        """
        
        # Get current market data
        current_spread = df.iloc[idx][ 'rdn_combined_spread'] if 'rdn_combined_spread' in df.columns else None
        if current_spread is None or pd.isna(current_spread):
            return ValidationResult(
                is_valid=False,
                signal_type='HOLD',
                reason='Missing spread data',
                confidence=0
            )
        
        # 1. PROFIT VALIDATION
        spot_price = df.iloc[idx][ 'MEXC_ask_price'] if 'MEXC_ask_price' in df.columns else 1.0
        expected_profit, is_profitable = self.pnl_calculator.calculate_expected_rdn_profit(
            current_spread, self.min_compression_target, spot_price, df, idx, position_size_usd
        )
        
        if not is_profitable:
            return ValidationResult(
                is_valid=False,
                signal_type='HOLD',
                reason=f'Insufficient profit potential: {expected_profit:.3f}%',
                confidence=90,
                expected_profit=expected_profit
            )
        
        # 2. VOLATILITY VALIDATION
        spread_volatility = df.iloc[idx][ 'rdn_spread_volatility'] if 'rdn_spread_volatility' in df.columns else None
        if spread_volatility is not None and not pd.isna(spread_volatility):
            if spread_volatility < self.min_volatility:
                return ValidationResult(
                    is_valid=False,
                    signal_type='HOLD',
                    reason=f'Low volatility: {spread_volatility:.3f}% < {self.min_volatility:.3f}%',
                    confidence=75
                )
        
        # 3. MOMENTUM VALIDATION
        spread_momentum = df.iloc[idx][ 'rdn_spread_momentum'] if 'rdn_spread_momentum' in df.columns else None
        if spread_momentum is not None and not pd.isna(spread_momentum):
            if spread_momentum < self.max_momentum_threshold:
                return ValidationResult(
                    is_valid=False,
                    signal_type='HOLD',
                    reason=f'Negative momentum: {spread_momentum:.3f}%',
                    confidence=60,
                    risk_factors=['negative_momentum']
                )
        
        # 4. HISTORICAL EXTREMENESS VALIDATION
        lookback_window = context_window or self.extremeness_lookback
        if idx >= lookback_window:
            recent_spreads = df.iloc[max(0, idx-lookback_window):idx]['rdn_combined_spread']
            if len(recent_spreads) > 10:  # Ensure sufficient data
                percentile_5 = recent_spreads.quantile(0.05)
                
                if current_spread > percentile_5:
                    return ValidationResult(
                        is_valid=False,
                        signal_type='HOLD',
                        reason=f'Not extreme enough: {current_spread:.3f}% > {percentile_5:.3f}% (5th percentile)',
                        confidence=80
                    )
        
        # 5. RISK FACTOR ASSESSMENT
        risk_factors = []
        confidence = 100
        
        # High volatility warning
        if spread_volatility is not None and spread_volatility > 0.5:
            risk_factors.append('high_volatility')
            confidence -= 10
        
        # Spread not deeply negative enough
        if current_spread > -2.0:  # Less than 2% negative
            risk_factors.append('shallow_opportunity')
            confidence -= 15
        
        # Weekend/low liquidity periods (simplified check)
        # In real implementation, would check actual timestamp
        if 'timestamp' in df.columns:
            # Add timestamp-based liquidity checks here
            pass
        
        # Calculate final confidence
        confidence = max(50, confidence)  # Minimum 50% confidence
        
        return ValidationResult(
            is_valid=True,
            signal_type='ENTER',
            reason=f'Valid entry: {expected_profit:.3f}% expected profit, {abs(current_spread):.3f}% spread',
            confidence=confidence,
            expected_profit=expected_profit,
            risk_factors=risk_factors if risk_factors else None
        )

    def validate_rdn_exit(self, df: pd.DataFrame, idx: int, entry_spread: float,
                         entry_time: int, target_compression: float = 50) -> ValidationResult:
        """
        Comprehensive validation for RDN exit signals.
        
        Args:
            df: DataFrame with market data
            idx: Current index
            entry_spread: Spread at entry
            entry_time: Entry time/index
            target_compression: Target compression percentage
            
        Returns:
            ValidationResult for exit decision
        """
        
        current_spread = df.iloc[idx][ 'rdn_combined_spread'] if 'rdn_combined_spread' in df.columns else None
        if current_spread is None or pd.isna(current_spread):
            return ValidationResult(
                is_valid=False,
                signal_type='HOLD',
                reason='Missing spread data',
                confidence=0
            )
        
        # Calculate actual compression achieved
        spread_compression = current_spread - entry_spread
        compression_pct = (spread_compression / abs(entry_spread)) * 100 if entry_spread != 0 else 0
        
        # Calculate holding period
        holding_periods = idx - entry_time if isinstance(idx, int) and isinstance(entry_time, int) else 0
        holding_hours = holding_periods * 5 / 60  # Assuming 5-minute intervals
        
        # 1. PROFIT TARGET EXIT
        if compression_pct >= target_compression:
            return ValidationResult(
                is_valid=True,
                signal_type='EXIT',
                reason=f'Profit target achieved: {compression_pct:.1f}% compression',
                confidence=95
            )
        
        # 2. MOMENTUM REVERSAL EXIT
        spread_momentum = df.iloc[idx][ 'rdn_spread_momentum'] if 'rdn_spread_momentum' in df.columns else None
        if spread_momentum is not None and spread_momentum < -0.05:
            return ValidationResult(
                is_valid=True,
                signal_type='EXIT',
                reason=f'Momentum reversal: {spread_momentum:.3f}%',
                confidence=80,
                risk_factors=['momentum_reversal']
            )
        
        # 3. VOLATILITY COLLAPSE EXIT
        spread_volatility = df.iloc[idx][ 'rdn_spread_volatility'] if 'rdn_spread_volatility' in df.columns else None
        if spread_volatility is not None and spread_volatility < 0.02:
            return ValidationResult(
                is_valid=True,
                signal_type='EXIT',
                reason=f'Low volatility: {spread_volatility:.3f}%',
                confidence=70
            )
        
        # 4. TIME-BASED EXIT
        if holding_hours > 24:
            return ValidationResult(
                is_valid=True,
                signal_type='EXIT',
                reason=f'Max holding time: {holding_hours:.1f}h',
                confidence=60,
                risk_factors=['extended_hold']
            )
        
        # 5. EMERGENCY STOP-LOSS
        if current_spread < entry_spread * 1.5:  # 50% worse than entry
            return ValidationResult(
                is_valid=True,
                signal_type='EXIT',
                reason=f'Stop loss: {current_spread:.3f}% vs {entry_spread:.3f}% entry',
                confidence=90,
                risk_factors=['stop_loss']
            )
        
        # 6. PARTIAL PROFIT TAKING
        if compression_pct >= target_compression * 0.7:  # 70% of target achieved
            return ValidationResult(
                is_valid=False,  # Don't exit yet, but flag opportunity
                signal_type='HOLD',
                reason=f'Partial target: {compression_pct:.1f}% compression (consider partial exit)',
                confidence=60,
                risk_factors=['partial_target']
            )
        
        # Continue holding
        return ValidationResult(
            is_valid=False,
            signal_type='HOLD',
            reason=f'Continue holding: {compression_pct:.1f}% compression, {holding_hours:.1f}h held',
            confidence=70
        )


class MarketRegimeValidator:
    """Validates signals based on broader market regime."""
    
    def __init__(self):
        self.volatility_regime_thresholds = {
            'low': 0.1,
            'normal': 0.3,
            'high': 0.6,
            'extreme': 1.0
        }
    
    def classify_volatility_regime(self, df: pd.DataFrame, idx: int) -> str:
        """Classify current volatility regime."""
        spread_volatility = df.iloc[idx][ 'rdn_spread_volatility'] if 'rdn_spread_volatility' in df.columns else 0.1
        
        if pd.isna(spread_volatility):
            return 'unknown'
        
        if spread_volatility <= self.volatility_regime_thresholds['low']:
            return 'low'
        elif spread_volatility <= self.volatility_regime_thresholds['normal']:
            return 'normal'
        elif spread_volatility <= self.volatility_regime_thresholds['high']:
            return 'high'
        else:
            return 'extreme'
    
    def adjust_signal_for_regime(self, signal_result: ValidationResult, 
                                volatility_regime: str) -> ValidationResult:
        """Adjust signal confidence based on market regime."""
        
        confidence_adjustments = {
            'low': -20,      # Low vol = harder to profit
            'normal': 0,     # Normal conditions
            'high': 10,      # High vol = more opportunities
            'extreme': -10   # Too much vol = higher risk
        }
        
        adjustment = confidence_adjustments.get(volatility_regime, 0)
        adjusted_confidence = max(0, min(100, signal_result.confidence + adjustment))
        
        # Create adjusted result
        return ValidationResult(
            is_valid=signal_result.is_valid and adjusted_confidence >= 50,
            signal_type=signal_result.signal_type,
            reason=f"{signal_result.reason} [{volatility_regime} vol regime]",
            confidence=adjusted_confidence,
            expected_profit=signal_result.expected_profit,
            risk_factors=signal_result.risk_factors
        )


# Convenience functions for integration
def validate_rdn_entry_comprehensive(df: pd.DataFrame, idx: int, 
                                    position_size_usd: float = 1000) -> ValidationResult:
    """Comprehensive RDN entry validation with regime adjustment."""
    validator = RDNSignalValidator()
    regime_validator = MarketRegimeValidator()
    
    # Primary signal validation
    signal_result = validator.validate_rdn_entry(df, idx, position_size_usd)
    
    # Regime adjustment
    volatility_regime = regime_validator.classify_volatility_regime(df, idx)
    final_result = regime_validator.adjust_signal_for_regime(signal_result, volatility_regime)
    
    return final_result


def validate_rdn_exit_comprehensive(df: pd.DataFrame, idx: int, entry_spread: float,
                                  entry_time: int) -> ValidationResult:
    """Comprehensive RDN exit validation with regime adjustment."""
    validator = RDNSignalValidator()
    regime_validator = MarketRegimeValidator()
    
    # Primary exit validation
    signal_result = validator.validate_rdn_exit(df, idx, entry_spread, entry_time)
    
    # Regime adjustment
    volatility_regime = regime_validator.classify_volatility_regime(df, idx)
    final_result = regime_validator.adjust_signal_for_regime(signal_result, volatility_regime)
    
    return final_result