#!/usr/bin/env python3
"""
Arbitrage Signal Generator

Simple, configurable signal generation for arbitrage entry/exit decisions.
Returns 'enter', 'exit', or 'none' based on spread thresholds and conditions.
"""

from typing import Literal, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np


@dataclass
class SignalConfig:
    """Configuration for arbitrage signal generation."""
    
    # Entry thresholds
    entry_min_spread: float = 0.1  # Minimum spread after fees to enter (%)
    entry_percentile: int = 10     # Historical percentile threshold (10 = top 10%)
    entry_confirmation_periods: int = 2  # Consecutive profitable periods required
    
    # Exit thresholds  
    exit_spread: float = 0.05      # Exit when spread falls below this (%)
    exit_max_duration: int = 120   # Maximum position duration (periods)
    exit_stop_loss: float = -0.3   # Stop loss threshold (%)
    
    # Risk filters
    min_volume_ratio: float = 0.8  # Minimum volume vs average (0.8 = 80% of avg)
    max_spread_compression: float = 0.5  # Max spread decrease in one period (50%)


def generate_arbitrage_signal(
    current_spread: float,
    spread_history: np.ndarray,
    position_open: bool = False,
    position_duration: int = 0,
    position_pnl: float = 0.0,
    volume_ratio: float = 1.0,
    last_spread: Optional[float] = None,
    config: Optional[SignalConfig] = None
) -> Literal['enter', 'exit', 'none']:
    """
    Generate arbitrage trading signal based on current market conditions.
    
    Args:
        current_spread: Current total_arbitrage_sum_fees value (%)
        spread_history: Historical spread values for percentile calculation
        position_open: Whether a position is currently open
        position_duration: How long position has been open (periods)
        position_pnl: Current P&L of open position (%)
        volume_ratio: Current volume / average volume
        last_spread: Previous period's spread for compression check
        config: Signal configuration (uses defaults if None)
    
    Returns:
        'enter': Open new arbitrage position
        'exit': Close existing position
        'none': No action required
    
    Example:
        >>> history = np.array([0.05, 0.1, 0.15, 0.2, 0.08, 0.12])
        >>> signal = generate_arbitrage_signal(
        ...     current_spread=0.18,
        ...     spread_history=history,
        ...     position_open=False
        ... )
        >>> print(signal)  # 'enter' if conditions met
    """
    
    if config is None:
        config = SignalConfig()
    
    # Calculate historical percentile threshold
    entry_threshold = np.percentile(spread_history, 100 - config.entry_percentile)
    
    # --- EXIT SIGNALS (check first if position open) ---
    if position_open:
        
        # 1. Spread below exit threshold
        if current_spread < config.exit_spread:
            return 'exit'
        
        # 2. Maximum duration reached
        if position_duration >= config.exit_max_duration:
            return 'exit'
        
        # 3. Stop loss triggered
        if position_pnl < config.exit_stop_loss:
            return 'exit'
        
        # 4. Rapid spread compression
        if last_spread is not None:
            compression = (last_spread - current_spread) / last_spread if last_spread > 0 else 0
            if compression > config.max_spread_compression:
                return 'exit'
        
        # 5. Volume dried up
        if volume_ratio < config.min_volume_ratio * 0.5:  # 50% of minimum
            return 'exit'
        
        return 'none'
    
    # --- ENTRY SIGNALS (only if no position open) ---
    else:
        
        # 1. Spread exceeds minimum threshold
        if current_spread < config.entry_min_spread:
            return 'none'
        
        # 2. Spread exceeds historical percentile
        if current_spread < entry_threshold:
            return 'none'
        
        # 3. Sufficient volume
        if volume_ratio < config.min_volume_ratio:
            return 'none'
        
        # 4. Check confirmation periods if we have history
        if len(spread_history) >= config.entry_confirmation_periods:
            recent_spreads = spread_history[-config.entry_confirmation_periods:]
            if not all(s > config.entry_min_spread for s in recent_spreads):
                return 'none'
        
        return 'enter'


def generate_signal_with_stats(
    current_spread: float,
    spread_history: np.ndarray,
    position_open: bool = False,
    config: Optional[SignalConfig] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate signal with additional statistics for debugging/monitoring.
    
    Returns dict with:
        - signal: 'enter', 'exit', or 'none'
        - entry_threshold: Calculated percentile threshold
        - spread_percentile: Where current spread sits in historical distribution
        - conditions_met: List of conditions that were checked
    """
    
    if config is None:
        config = SignalConfig()
    
    # Get base signal
    signal = generate_arbitrage_signal(
        current_spread=current_spread,
        spread_history=spread_history,
        position_open=position_open,
        config=config,
        **kwargs
    )
    
    # Calculate statistics
    entry_threshold = np.percentile(spread_history, 100 - config.entry_percentile)
    spread_percentile = (spread_history < current_spread).sum() / len(spread_history) * 100
    
    # Build conditions summary
    conditions = []
    if position_open:
        conditions.append(f"Position open, duration: {kwargs.get('position_duration', 0)}")
        conditions.append(f"Current P&L: {kwargs.get('position_pnl', 0):.3f}%")
    else:
        conditions.append(f"Spread vs minimum: {current_spread:.3f}% vs {config.entry_min_spread}%")
        conditions.append(f"Spread vs percentile: {current_spread:.3f}% vs {entry_threshold:.3f}%")
    
    return {
        'signal': signal,
        'entry_threshold': entry_threshold,
        'spread_percentile': spread_percentile,
        'current_spread': current_spread,
        'conditions_met': conditions,
        'config': config
    }


# Convenience functions for common use cases
def simple_entry_signal(
    current_spread: float,
    spread_history: np.ndarray,
    percentile: int = 10
) -> bool:
    """Simple entry signal based on percentile threshold only."""
    threshold = np.percentile(spread_history, 100 - percentile)
    return current_spread > threshold


def simple_exit_signal(
    current_spread: float,
    exit_threshold: float = 0.05
) -> bool:
    """Simple exit signal based on spread threshold only."""
    return current_spread < exit_threshold


if __name__ == "__main__":
    # Example usage
    import pandas as pd
    
    # Simulate some historical spread data
    np.random.seed(42)
    historical_spreads = np.random.normal(0.15, 0.05, 1000)  # Mean 0.15%, std 0.05%
    historical_spreads = np.maximum(historical_spreads, -0.1)  # Floor at -0.1%
    
    print("📊 ARBITRAGE SIGNAL GENERATOR EXAMPLE")
    print("="*50)
    
    # Test scenarios
    scenarios = [
        {
            'name': 'Good Entry Opportunity',
            'current_spread': 0.25,
            'position_open': False,
            'volume_ratio': 1.2
        },
        {
            'name': 'Below Threshold',
            'current_spread': 0.08,
            'position_open': False,
            'volume_ratio': 1.0
        },
        {
            'name': 'Exit on Low Spread',
            'current_spread': 0.04,
            'position_open': True,
            'position_duration': 50,
            'position_pnl': 0.1
        },
        {
            'name': 'Exit on Max Duration',
            'current_spread': 0.12,
            'position_open': True,
            'position_duration': 125,
            'position_pnl': 0.15
        },
        {
            'name': 'Exit on Stop Loss',
            'current_spread': 0.10,
            'position_open': True,
            'position_duration': 30,
            'position_pnl': -0.35
        }
    ]
    
    # Custom config for testing
    config = SignalConfig(
        entry_min_spread=0.1,
        entry_percentile=10,
        exit_spread=0.05,
        exit_max_duration=120
    )
    
    for scenario in scenarios:
        print(f"\n🎯 {scenario['name']}:")
        print(f"   Current spread: {scenario['current_spread']:.3f}%")
        
        result = generate_signal_with_stats(
            current_spread=scenario['current_spread'],
            spread_history=historical_spreads,
            config=config,
            **{k: v for k, v in scenario.items() if k not in ['name', 'current_spread']}
        )
        
        print(f"   Signal: {result['signal'].upper()}")
        print(f"   Entry threshold (90th percentile): {result['entry_threshold']:.3f}%")
        print(f"   Current spread percentile: {result['spread_percentile']:.1f}%")
        
        for condition in result['conditions_met']:
            print(f"   • {condition}")
    
    print("\n" + "="*50)
    print("✅ Signal generator ready for use!")
    print("\nUsage in your code:")
    print("  signal = generate_arbitrage_signal(")
    print("      current_spread=0.18,")
    print("      spread_history=historical_data,")
    print("      position_open=False")
    print("  )")