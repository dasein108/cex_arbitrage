#!/usr/bin/env python3
"""
Corrected RDN Backtest Implementation

This is the FIXED version of the Reverse Delta-Neutral arbitrage strategy
that addresses all the fundamental issues found in the original implementation.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
import sys
import os

# Add the project root to Python path for imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(project_root)

from trading.analysis.signal_validators import validate_rdn_entry_comprehensive, validate_rdn_exit_comprehensive
from trading.analysis.risk_manager import AdvancedRiskManager
from trading.analysis.pnl_calculator import ArbitragePnLCalculator, calculate_rdn_trade_pnl
from trading.research.cross_arbitrage.arbitrage_analyzer import AnalyzerKeys


def add_corrected_rdn_backtest(
    df: pd.DataFrame,
    base_capital: float = 100000.0,
    use_enhanced_validation: bool = True,
    use_advanced_risk_mgmt: bool = True,
    legacy_compatibility: bool = False
) -> pd.DataFrame:
    """
    CORRECTED Reverse Delta-Neutral Arbitrage Backtest.
    
    This implementation fixes all the fundamental issues:
    1. ✅ Spread-based P&L calculation (measures actual arbitrage profit)
    2. ✅ Comprehensive cost modeling (all real costs included)
    3. ✅ Enhanced entry/exit validation (profit validation before entry)
    4. ✅ Advanced risk management (dynamic position sizing, portfolio limits)
    
    Args:
        df: DataFrame with arbitrage spread data
        base_capital: Portfolio capital for risk management
        use_enhanced_validation: Enable comprehensive entry/exit validation
        use_advanced_risk_mgmt: Enable advanced risk management
        legacy_compatibility: Maintain backward compatibility with old interface
        
    Returns:
        DataFrame with corrected RDN signals and accurate P&L
    """
    
    print("🔧 CORRECTED RDN Implementation - Fixing Fundamental Issues")
    print("=" * 60)
    
    # Initialize corrected columns
    df_corrected = df.copy()
    
    # Add corrected RDN columns
    df_corrected['rdn_signal'] = 'HOLD'
    df_corrected['rdn_position_open'] = False
    df_corrected['rdn_entry_spread'] = np.nan
    df_corrected['rdn_spot_entry'] = np.nan
    df_corrected['rdn_futures_entry'] = np.nan
    df_corrected['rdn_spot_exit'] = np.nan
    df_corrected['rdn_futures_exit'] = np.nan
    df_corrected['rdn_trade_pnl'] = 0.0
    df_corrected['rdn_cumulative_pnl'] = 0.0
    df_corrected['rdn_holding_hours'] = 0.0
    df_corrected['rdn_position_size'] = 0.0
    df_corrected['rdn_expected_profit'] = np.nan
    df_corrected['rdn_validation_reason'] = ''
    df_corrected['rdn_spread_compression'] = np.nan
    df_corrected['rdn_gross_pnl'] = np.nan
    df_corrected['rdn_total_costs'] = np.nan
    
    # Calculate required spread indicators
    mexc_spread_col = AnalyzerKeys.mexc_vs_gateio_futures_arb
    gateio_spread_col = AnalyzerKeys.gateio_spot_vs_futures_arb
    
    # Combined spread (average of both opportunities)
    df_corrected['rdn_combined_spread'] = (df_corrected[mexc_spread_col] + df_corrected[gateio_spread_col]) / 2
    
    # Rolling volatility for validation and position sizing
    df_corrected['rdn_spread_volatility'] = df_corrected['rdn_combined_spread'].rolling(window=20).std()
    
    # Spread momentum indicator
    df_corrected['rdn_spread_momentum'] = df_corrected['rdn_combined_spread'].diff(5)
    
    # Initialize analysis components
    if use_advanced_risk_mgmt:
        risk_manager = AdvancedRiskManager(base_capital=base_capital)
    else:
        risk_manager = None
        
    pnl_calculator = ArbitragePnLCalculator()
    cumulative_pnl = 0.0
    trade_count = 0
    
    print(f"📊 Processing {len(df_corrected)} periods...")
    print(f"🔍 Enhanced validation: {use_enhanced_validation}")
    print(f"🛡️ Advanced risk management: {use_advanced_risk_mgmt}")
    
    for i, idx in enumerate(df_corrected.index):
        current_spread = df_corrected.loc[idx, 'rdn_combined_spread']
        
        # Skip if data is missing
        if pd.isna(current_spread):
            continue
        
        # Update existing positions
        if risk_manager:
            risk_manager.update_all_positions(df_corrected, i)
            
            # Check exit conditions for all active positions
            positions_to_close = []
            for position in risk_manager.active_positions:
                should_exit, exit_reason, exit_details = risk_manager.check_exit_conditions(df_corrected, i, position)
                if should_exit:
                    positions_to_close.append((position, exit_reason, exit_details))
            
            # Execute exits with CORRECTED P&L calculation
            for position, exit_reason, exit_details in positions_to_close:
                
                # Get exit prices
                spot_exit_price = df_corrected.loc[idx, AnalyzerKeys.mexc_bid]
                futures_exit_price = df_corrected.loc[idx, AnalyzerKeys.gateio_futures_ask]
                
                # CORRECTED P&L calculation using spread compression
                entry_data = {
                    'spot_price': position.spot_entry_price,
                    'futures_price': position.futures_entry_price
                }
                exit_data = {
                    'spot_price': spot_exit_price,
                    'futures_price': futures_exit_price
                }
                
                # Calculate holding period
                holding_periods = idx - position.entry_time if isinstance(idx, int) else 0
                holding_hours = holding_periods * 5 / 60  # Assuming 5-minute intervals
                
                # Use corrected P&L calculator
                trade_result = pnl_calculator.calculate_rdn_pnl(
                    entry_data, exit_data, position.position_size_usd, 
                    holding_hours, df_corrected, position.entry_time
                )
                
                # Remove position from risk manager
                risk_manager.active_positions.remove(position)
                risk_manager.closed_positions.append(position)
                
                # Record corrected trade results
                df_corrected.loc[idx, 'rdn_signal'] = f'EXIT_{exit_reason}'
                df_corrected.loc[idx, 'rdn_spot_exit'] = spot_exit_price
                df_corrected.loc[idx, 'rdn_futures_exit'] = futures_exit_price
                df_corrected.loc[idx, 'rdn_trade_pnl'] = trade_result.net_pnl_pct
                df_corrected.loc[idx, 'rdn_holding_hours'] = holding_hours
                df_corrected.loc[idx, 'rdn_spread_compression'] = trade_result.spread_compression
                df_corrected.loc[idx, 'rdn_gross_pnl'] = trade_result.gross_pnl_pct
                df_corrected.loc[idx, 'rdn_total_costs'] = trade_result.cost_breakdown.total_cost
                
                cumulative_pnl += trade_result.net_pnl_pct
                trade_count += 1
                
                print(f"✅ EXIT #{trade_count} at idx {idx}: {exit_reason}")
                print(f"   📊 Spread Compression: {trade_result.spread_compression:.4f}")
                print(f"   💰 Gross P&L: {trade_result.gross_pnl_pct:.3f}%")
                print(f"   💸 Total Costs: {trade_result.cost_breakdown.total_cost:.3f}%")
                print(f"   🎯 Net P&L: {trade_result.net_pnl_pct:.3f}%")
                print(f"   ⏱️ Held: {holding_hours:.1f}h")
        
        # Check entry conditions (only if no exits on this bar)
        if not positions_to_close or not use_advanced_risk_mgmt:
            
            if use_enhanced_validation:
                # Use comprehensive validation with profit checking
                validation_result = validate_rdn_entry_comprehensive(df_corrected, i, 1000.0)
                
                if validation_result.is_valid:
                    
                    if risk_manager:
                        # Calculate risk-adjusted position size
                        position_size, sizing_details = risk_manager.calculate_position_size(
                            df_corrected, i, 
                            validation_result.expected_profit or 0.5,
                            df_corrected.loc[idx, 'rdn_spread_volatility'] or 0.1
                        )
                        
                        # Check risk limits
                        can_enter, warnings, blockers = risk_manager.check_entry_risk_limits(df_corrected, i, position_size)
                        
                        if can_enter and position_size > 100:  # Minimum $100 position
                            # Create position with risk management
                            position = risk_manager.create_position(df_corrected, i, current_spread, position_size)
                            
                            # Record entry
                            df_corrected.loc[idx, 'rdn_signal'] = 'ENTER'
                            df_corrected.loc[idx, 'rdn_position_open'] = True
                            df_corrected.loc[idx, 'rdn_entry_spread'] = current_spread
                            df_corrected.loc[idx, 'rdn_position_size'] = position_size
                            df_corrected.loc[idx, 'rdn_expected_profit'] = validation_result.expected_profit
                            df_corrected.loc[idx, 'rdn_validation_reason'] = validation_result.reason
                            
                            # Record entry prices
                            df_corrected.loc[idx, 'rdn_spot_entry'] = position.spot_entry_price
                            df_corrected.loc[idx, 'rdn_futures_entry'] = position.futures_entry_price
                            
                            print(f"🚀 ENTER at idx {idx}:")
                            print(f"   📈 Spread: {current_spread:.3f}%")
                            print(f"   💵 Size: ${position_size:.0f}")
                            print(f"   🎯 Expected: {validation_result.expected_profit:.3f}%")
                            print(f"   📝 Reason: {validation_result.reason}")
                        else:
                            # Record why entry was blocked
                            reason = f"Risk limits: {', '.join(blockers)}" if blockers else "Position size too small"
                            df_corrected.loc[idx, 'rdn_validation_reason'] = reason
                            
                    else:
                        # Simplified entry without risk management
                        df_corrected.loc[idx, 'rdn_signal'] = 'ENTER'
                        df_corrected.loc[idx, 'rdn_expected_profit'] = validation_result.expected_profit
                        df_corrected.loc[idx, 'rdn_validation_reason'] = validation_result.reason
                        
                        # Simple position tracking for legacy mode
                        df_corrected.loc[idx, 'rdn_position_open'] = True
                        df_corrected.loc[idx, 'rdn_entry_spread'] = current_spread
                        df_corrected.loc[idx, 'rdn_spot_entry'] = df_corrected.loc[idx, AnalyzerKeys.mexc_ask]
                        df_corrected.loc[idx, 'rdn_futures_entry'] = df_corrected.loc[idx, AnalyzerKeys.gateio_futures_bid]
                        
                else:
                    # Record why entry was rejected
                    df_corrected.loc[idx, 'rdn_validation_reason'] = validation_result.reason
                    
            else:
                # Legacy simple validation
                if current_spread < -2.5:  # Simple threshold
                    df_corrected.loc[idx, 'rdn_signal'] = 'ENTER'
                    df_corrected.loc[idx, 'rdn_validation_reason'] = 'Legacy threshold entry'
        
        # Update cumulative P&L and portfolio metrics
        df_corrected.loc[idx, 'rdn_cumulative_pnl'] = cumulative_pnl
        
        if risk_manager:
            portfolio_metrics = risk_manager.calculate_portfolio_metrics()
            df_corrected.loc[idx, 'portfolio_exposure'] = portfolio_metrics.exposure_ratio
            df_corrected.loc[idx, 'active_positions'] = portfolio_metrics.position_count
    
    # Final summary
    print("\n" + "=" * 60)
    print("📊 CORRECTED RDN BACKTEST RESULTS")
    print("=" * 60)
    
    total_trades = trade_count
    final_pnl = cumulative_pnl
    
    if total_trades > 0:
        winning_trades = (df_corrected['rdn_trade_pnl'] > 0).sum()
        win_rate = (winning_trades / total_trades) * 100
        avg_trade_pnl = df_corrected[df_corrected['rdn_trade_pnl'] != 0]['rdn_trade_pnl'].mean()
        
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {winning_trades}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Average Trade P&L: {avg_trade_pnl:.3f}%")
        print(f"Total P&L: {final_pnl:.3f}%")
        
        # Analyze improvements over original
        if 'rdn_spread_compression' in df_corrected.columns:
            total_compression = df_corrected[df_corrected['rdn_spread_compression'].notna()]['rdn_spread_compression'].sum()
            total_gross_pnl = df_corrected[df_corrected['rdn_gross_pnl'].notna()]['rdn_gross_pnl'].sum()
            total_costs = df_corrected[df_corrected['rdn_total_costs'].notna()]['rdn_total_costs'].sum()
            
            print(f"\n🔍 CORRECTED CALCULATION BREAKDOWN:")
            print(f"Total Spread Compression Captured: {total_compression:.3f}")
            print(f"Total Gross P&L: {total_gross_pnl:.3f}%")
            print(f"Total Costs Applied: {total_costs:.3f}%")
            print(f"Net P&L: {total_gross_pnl - total_costs:.3f}%")
            
    else:
        print("No trades executed")
        
    if risk_manager:
        final_summary = risk_manager.get_portfolio_summary()
        print(f"\n💼 PORTFOLIO SUMMARY:")
        print(f"Portfolio Value: ${final_summary['current_portfolio_value']:.2f}")
        print(f"Total Return: {(final_summary['current_portfolio_value'] / base_capital - 1) * 100:.2f}%")
        print(f"Max Drawdown: {final_summary['max_drawdown']:.2%}")
        
        # Store summary for further analysis
        df_corrected.attrs['portfolio_summary'] = final_summary
        df_corrected.attrs['corrected_rdn_metrics'] = {
            'total_trades': total_trades,
            'final_pnl': final_pnl,
            'win_rate': win_rate if total_trades > 0 else 0,
            'implementation': 'corrected_rdn_v1.0'
        }
    
    print(f"\n✅ Corrected RDN backtest completed!")
    print(f"🔧 Implementation: Fixed spread-based P&L + comprehensive cost modeling")
    
    return df_corrected


def compare_with_original_rdn(df_original: pd.DataFrame, df_corrected: pd.DataFrame) -> Dict[str, Any]:
    """
    Compare the corrected RDN implementation with the original flawed version.
    
    Args:
        df_original: DataFrame with original RDN results
        df_corrected: DataFrame with corrected RDN results
        
    Returns:
        Comparison metrics showing the improvements
    """
    
    comparison = {}
    
    # Original metrics
    original_trades = (df_original['rdn_trade_pnl'] != 0).sum() if 'rdn_trade_pnl' in df_original.columns else 0
    original_pnl = df_original['rdn_cumulative_pnl'].iloc[-1] if 'rdn_cumulative_pnl' in df_original.columns else 0
    
    # Corrected metrics  
    corrected_trades = (df_corrected['rdn_trade_pnl'] != 0).sum()
    corrected_pnl = df_corrected['rdn_cumulative_pnl'].iloc[-1]
    
    comparison['trade_count'] = {
        'original': original_trades,
        'corrected': corrected_trades,
        'change': corrected_trades - original_trades
    }
    
    comparison['total_pnl'] = {
        'original': original_pnl,
        'corrected': corrected_pnl,
        'improvement': corrected_pnl - original_pnl
    }
    
    # Calculate win rates
    if original_trades > 0:
        original_win_rate = (df_original['rdn_trade_pnl'] > 0).sum() / original_trades * 100
    else:
        original_win_rate = 0
        
    if corrected_trades > 0:
        corrected_win_rate = (df_corrected['rdn_trade_pnl'] > 0).sum() / corrected_trades * 100
    else:
        corrected_win_rate = 0
    
    comparison['win_rate'] = {
        'original': original_win_rate,
        'corrected': corrected_win_rate,
        'improvement': corrected_win_rate - original_win_rate
    }
    
    # Key improvements
    comparison['key_fixes'] = [
        'Spread-based P&L calculation',
        'Comprehensive cost modeling',
        'Profit validation before entry',
        'Advanced risk management',
        'Dynamic position sizing'
    ]
    
    return comparison


# Utility function for integration with existing demo
def apply_corrected_rdn_to_analyzer(analyzer, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Apply the corrected RDN implementation to an existing ArbitrageAnalyzer instance.
    
    This function integrates with the existing demo framework.
    """
    
    # Add the method to the analyzer instance
    analyzer.add_corrected_rdn_backtest = lambda df_input, **params: add_corrected_rdn_backtest(df_input, **params)
    
    # Execute the corrected backtest
    df_corrected = analyzer.add_corrected_rdn_backtest(df, **kwargs)
    
    return df_corrected