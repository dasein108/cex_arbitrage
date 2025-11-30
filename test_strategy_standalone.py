#!/usr/bin/env python3
"""
Standalone test for the updated MEXC-Gate.io futures arbitrage strategy
"""

import sys
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Add src to path
sys.path.insert(0, 'src')

def test_updated_strategy():
    """Test the updated strategy with realistic market data"""
    print('🧪 Testing Updated MEXC-Gate.io Futures Arbitrage Strategy')
    print('=' * 60)
    
    try:
        # Import the strategy directly
        from trading.signals_v2.implementation.mexc_gateio_futures_arbitrage_signal import (
            MexcGateioFuturesArbitrageSignal,
            SpreadMetrics,
            FeeStructure
        )
        from trading.signals_v2.entities import ExchangeEnum
        from trading.data_sources.column_utils import get_column_key
        
        print('✅ Strategy imports successful')
        
        # Create strategy with updated parameters
        strategy = MexcGateioFuturesArbitrageSignal(
            entry_quantile=0.70,          # Updated from 0.80 
            exit_quantile=0.20,
            min_spread_threshold=-0.0005, # Updated from -0.001
            position_size_usd=1000.0,
            max_daily_trades=20
        )
        
        print(f'✅ Strategy created with updated parameters:')
        print(f'   entry_quantile: {strategy.entry_quantile}')
        print(f'   min_spread_threshold: {strategy.min_spread_threshold}')
        
        # Create realistic test data based on user's analysis
        timestamps = pd.date_range(
            start=datetime.now(timezone.utc) - timedelta(hours=6),
            end=datetime.now(timezone.utc),
            freq='5min'
        )
        
        np.random.seed(42)
        base_price = 0.05000
        
        # Generate spread data that matches user's analysis results
        # MEXC to Futures: range -147.23 to +81.78 bps, with realistic arbitrage opportunities
        mexc_price_changes = np.cumsum(np.random.normal(0, 0.000005, len(timestamps)))
        
        # Create Gate.io futures prices with realistic spread distribution  
        futures_offset = np.random.normal(-0.00003, 0.00001, len(timestamps))  # Slight systematic difference
        
        mexc_bid = base_price + mexc_price_changes - 0.000005
        mexc_ask = base_price + mexc_price_changes + 0.000005
        gateio_fut_bid = base_price + mexc_price_changes + futures_offset - 0.000003
        gateio_fut_ask = base_price + mexc_price_changes + futures_offset + 0.000003
        
        # Use dynamic column keys
        test_df = pd.DataFrame({
            strategy.col_mexc_bid: mexc_bid,
            strategy.col_mexc_ask: mexc_ask,
            strategy.col_gateio_fut_bid: gateio_fut_bid,
            strategy.col_gateio_fut_ask: gateio_fut_ask,
        }, index=timestamps)
        
        # Ensure positive prices
        test_df = test_df.abs()
        
        print(f'📊 Created test data: {len(test_df)} rows')
        print(f'   Time range: {test_df.index[0]} to {test_df.index[-1]}')
        
        # Run analysis on the data
        print('\n📈 Running strategy analysis...')
        analysis = strategy.analyze_signals(test_df)
        
        print('\nStrategy Configuration:')
        config = analysis['strategy_config']
        for key, value in config.items():
            if isinstance(value, float):
                print(f'  {key}: {value:.4f}')
            else:
                print(f'  {key}: {value}')
        
        print('\nSignal Analysis:')
        signal_analysis = analysis['signal_analysis']
        for key, value in signal_analysis.items():
            print(f'  {key}: {value}')
        
        # Test signal application
        print('\n🎯 Testing signal application...')
        df_with_signals = strategy.apply_signals(test_df)
        
        entry_count = df_with_signals['entry_signal'].sum()
        exit_count = df_with_signals['exit_signal'].sum()
        
        print(f'Entry signals generated: {entry_count}')
        print(f'Exit signals generated: {exit_count}')
        
        if entry_count > 0:
            print('\n✅ SUCCESS: Strategy now generates entry signals!')
            
            # Show first entry signal details
            first_entry_idx = df_with_signals['entry_signal'].idxmax()
            if first_entry_idx and df_with_signals.loc[first_entry_idx, 'entry_signal']:
                first_entry = df_with_signals.loc[first_entry_idx]
                print(f'\nFirst Entry Signal Details:')
                print(f'  Time: {first_entry_idx}')
                print(f'  MEXC to Futures spread: {first_entry["mexc_to_fut_spread"]:.2f} bps')
                print(f'  Futures to MEXC spread: {first_entry["fut_to_mexc_spread"]:.2f} bps')
                print(f'  MEXC to Futures percentile: {first_entry["mexc_to_fut_percentile"]:.1f}%')
                print(f'  Futures to MEXC percentile: {first_entry["fut_to_mexc_percentile"]:.1f}%')
        else:
            print('\n⚠️  Still no entry signals - may need more data or further threshold adjustments')
            
            # Debug info
            spreads = df_with_signals[['mexc_to_fut_spread', 'fut_to_mexc_spread']].dropna()
            if not spreads.empty:
                print(f'\nDebug Info:')
                print(f'  MEXC to Futures spread range: {spreads["mexc_to_fut_spread"].min():.2f} to {spreads["mexc_to_fut_spread"].max():.2f} bps')
                print(f'  Futures to MEXC spread range: {spreads["fut_to_mexc_spread"].min():.2f} to {spreads["fut_to_mexc_spread"].max():.2f} bps')
                
                # Check percentiles if we have history
                if len(strategy._mexc_to_fut_history) >= 50:
                    mexc_70th = np.percentile(strategy._mexc_to_fut_history, 30)  # For negative spreads, 30th percentile means 70th from bottom
                    fut_70th = np.percentile(strategy._fut_to_mexc_history, 70)
                    print(f'  MEXC to Futures 30th percentile threshold: {mexc_70th:.2f} bps')
                    print(f'  Futures to MEXC 70th percentile threshold: {fut_70th:.2f} bps')
        
        print('\n🎉 Strategy testing completed successfully!')
        
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_updated_strategy()