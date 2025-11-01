"""
Volatility indicators for spot-spot arbitrage strategy.

This module implements three key volatility indicators:
1. Intraday Range Breakout Indicator (IRBI)
2. Volatility Ratio Divergence (VRD) 
3. Spike Persistence Score (SPS)
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class VolatilitySignal:
    """Signal structure for volatility arbitrage opportunities"""
    timestamp: datetime
    action: str  # 'hold', 'switch', 'exit'
    from_pair: Optional[str]
    to_pair: Optional[str]
    strength: float  # 0.0 to 2.0
    irbi_score: float
    vrd_score: float
    sps_score: float
    confidence: float


class VolatilityIndicators:
    """Volatility indicators for cross-pair arbitrage opportunities"""
    
    def __init__(self, irbi_threshold: float = 0.15, vrd_threshold: float = 1.3, sps_threshold: float = 0.6):
        self.irbi_threshold = irbi_threshold
        self.vrd_threshold = vrd_threshold
        self.sps_threshold = sps_threshold
    
    def calculate_irbi(self, df: pd.DataFrame, lookback: int = 20) -> pd.Series:
        """
        Intraday Range Breakout Indicator (IRBI)
        
        Detects when current high/low exceeds normal range by N%
        Signal: (current_range - avg_range) / avg_range > threshold
        
        Args:
            df: OHLCV DataFrame
            lookback: Periods for rolling average calculation
            
        Returns:
            Series of range breakout values
        """
        if len(df) < lookback:
            return pd.Series(index=df.index, dtype=float)
        
        # Calculate intraday ranges as percentage of low
        ranges = (df['high'] - df['low']) / df['low']
        
        # Rolling average of ranges
        avg_range = ranges.rolling(window=lookback, min_periods=lookback//2).mean()
        
        # Breakout calculation
        range_breakout = (ranges - avg_range) / avg_range
        
        return range_breakout.fillna(0.0)
    
    def calculate_vrd(self, df1: pd.DataFrame, df2: pd.DataFrame, window: int = 14) -> pd.Series:
        """
        Volatility Ratio Divergence (VRD)
        
        Compares realized volatility between two pairs
        Signal: When vol_ratio deviates significantly from historical mean
        
        Args:
            df1: First pair OHLCV data
            df2: Second pair OHLCV data
            window: Rolling window for volatility calculation
            
        Returns:
            Series of volatility ratios
        """
        min_len = min(len(df1), len(df2))
        if min_len < window:
            return pd.Series(dtype=float)
        
        # Align dataframes by taking last min_len periods
        df1_aligned = df1.tail(min_len).copy()
        df2_aligned = df2.tail(min_len).copy()
        
        # Calculate returns
        returns1 = df1_aligned['close'].pct_change()
        returns2 = df2_aligned['close'].pct_change()
        
        # Calculate rolling volatility (annualized to daily)
        vol1 = returns1.rolling(window=window, min_periods=window//2).std() * np.sqrt(1440)  # 1min to daily
        vol2 = returns2.rolling(window=window, min_periods=window//2).std() * np.sqrt(1440)
        
        # Avoid division by zero
        vol_ratio = vol1 / vol2.replace(0, np.nan)
        
        return vol_ratio.fillna(1.0)
    
    def calculate_sps(self, df: pd.DataFrame, spike_threshold: float = 0.15, persistence_window: int = 5) -> pd.Series:
        """
        Spike Persistence Score (SPS)
        
        Measures if volatility spikes have follow-through
        Signal: High current spike + low mean reversion tendency
        
        Args:
            df: OHLCV DataFrame
            spike_threshold: Minimum price change to be considered a spike
            persistence_window: Window to measure spike persistence
            
        Returns:
            Series of persistence scores (0.0 to 1.0)
        """
        if len(df) < persistence_window:
            return pd.Series(index=df.index, dtype=float)
        
        # Calculate absolute price changes
        price_changes = df['close'].pct_change().abs()
        
        # Identify spikes
        spikes = (price_changes > spike_threshold).astype(int)
        
        # Calculate persistence as rolling percentage of spike periods
        persistence = spikes.rolling(window=persistence_window, min_periods=1).mean()
        
        return persistence.fillna(0.0)
    
    def generate_signal(self, pair1_data: pd.DataFrame, pair2_data: pd.DataFrame, 
                       pair1_name: str, pair2_name: str) -> VolatilitySignal:
        """
        Generate trading signal based on volatility indicators
        
        Args:
            pair1_data: First pair OHLCV data
            pair2_data: Second pair OHLCV data
            pair1_name: Name of first pair
            pair2_name: Name of second pair
            
        Returns:
            VolatilitySignal with action and metadata
        """
        # Calculate indicators
        irbi1 = self.calculate_irbi(pair1_data)
        irbi2 = self.calculate_irbi(pair2_data)
        vrd = self.calculate_vrd(pair1_data, pair2_data)
        sps1 = self.calculate_sps(pair1_data)
        sps2 = self.calculate_sps(pair2_data)
        
        # Get latest values
        current_irbi1 = irbi1.iloc[-1] if len(irbi1) > 0 else 0.0
        current_irbi2 = irbi2.iloc[-1] if len(irbi2) > 0 else 0.0
        current_vrd = vrd.iloc[-1] if len(vrd) > 0 else 1.0
        current_sps1 = sps1.iloc[-1] if len(sps1) > 0 else 0.0
        current_sps2 = sps2.iloc[-1] if len(sps2) > 0 else 0.0
        
        # Signal generation logic
        signal = VolatilitySignal(
            timestamp=datetime.now(),
            action='hold',
            from_pair=None,
            to_pair=None,
            strength=0.0,
            irbi_score=max(current_irbi1, current_irbi2),
            vrd_score=current_vrd,
            sps_score=max(current_sps1, current_sps2),
            confidence=0.0
        )
        
        # Check for switch from pair1 to pair2 (pair2 more volatile)
        if (current_vrd > self.vrd_threshold and 
            current_irbi2 > self.irbi_threshold and 
            current_sps2 > self.sps_threshold):
            
            signal.action = 'switch'
            signal.from_pair = pair1_name
            signal.to_pair = pair2_name
            signal.strength = min(current_vrd, 2.0)  # Cap at 2x
            signal.confidence = (current_irbi2 + current_sps2 + (current_vrd - 1.0)) / 3.0
            
        # Check for switch from pair2 to pair1 (pair1 more volatile)
        elif (current_vrd < (1.0 / self.vrd_threshold) and 
              current_irbi1 > self.irbi_threshold and 
              current_sps1 > self.sps_threshold):
            
            signal.action = 'switch'
            signal.from_pair = pair2_name
            signal.to_pair = pair1_name
            signal.strength = min(1.0 / current_vrd, 2.0)  # Inverse for pair1 dominance
            signal.confidence = (current_irbi1 + current_sps1 + (1.0/current_vrd - 1.0)) / 3.0
        
        return signal
    
    def scan_opportunities(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[Tuple[str, str], VolatilitySignal]:
        """
        Scan all pair combinations for volatility arbitrage opportunities
        
        Args:
            data_dict: Dictionary of {symbol: OHLCV_dataframe}
            
        Returns:
            Dictionary of {(pair1, pair2): signal} for all combinations
        """
        opportunities = {}
        symbols = list(data_dict.keys())
        
        # Check all pair combinations
        for i, symbol1 in enumerate(symbols):
            for symbol2 in symbols[i+1:]:
                if len(data_dict[symbol1]) > 20 and len(data_dict[symbol2]) > 20:
                    signal = self.generate_signal(
                        data_dict[symbol1], 
                        data_dict[symbol2],
                        symbol1,
                        symbol2
                    )
                    
                    # Only store signals with action
                    if signal.action != 'hold':
                        opportunities[(symbol1, symbol2)] = signal
        
        return opportunities
    
    def rank_opportunities(self, opportunities: Dict[Tuple[str, str], VolatilitySignal]) -> list:
        """
        Rank opportunities by quality (strength * confidence)
        
        Args:
            opportunities: Dictionary of opportunities from scan_opportunities
            
        Returns:
            List of (pair_tuple, signal) sorted by quality desc
        """
        ranked = []
        
        for pair_tuple, signal in opportunities.items():
            quality_score = signal.strength * signal.confidence
            ranked.append((pair_tuple, signal, quality_score))
        
        # Sort by quality score descending
        ranked.sort(key=lambda x: x[2], reverse=True)
        
        return [(pair, signal) for pair, signal, _ in ranked]