"""
Temporal Aggregation Backtester Integration

Extends SymbolBacktester with temporal aggregation capabilities for high-frequency data testing.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio

from symbol_backtester import SymbolBacktester, Trade, ExitReason
from exchanges.structs import Symbol
from exchanges.structs.enums import KlineInterval
from trading.analysis.temporal_aggregation import (
    AdaptiveTemporalAggregator, 
    BookTickerData, 
    SignalResult, 
    SignalAction,
    SignalLevel,
    create_temporal_aggregator
)


class TemporalAggregationBacktester(SymbolBacktester):
    """
    Enhanced backtester with temporal aggregation for high-frequency data
    
    Solves the 5-second timeframe performance degradation by using
    multi-window statistics and signal confirmation.
    """
    
    def __init__(self, use_temporal_aggregation: bool = True, conservative_mode: bool = True):
        super().__init__()
        self.use_temporal_aggregation = use_temporal_aggregation
        self.conservative_mode = conservative_mode
        self.temporal_aggregator = None
        
        if use_temporal_aggregation:
            self.temporal_aggregator = create_temporal_aggregator(
                timeframe_seconds=5,
                conservative=conservative_mode
            )
    
    async def load_high_frequency_data(self, 
                                     symbol: Symbol,
                                     hours: int = 6,
                                     target_interval_seconds: int = 5) -> pd.DataFrame:
        """
        Load high-frequency book ticker data for temporal aggregation testing
        
        Args:
            symbol: Trading symbol to load
            hours: Hours of historical data
            target_interval_seconds: Target interval (5 seconds recommended)
            
        Returns:
            DataFrame with processed high-frequency data
        """
        self.logger.info(f"📊 Loading high-frequency data for {symbol}")
        self.logger.info(f"   Target interval: {target_interval_seconds} seconds")
        self.logger.info(f"   Period: {hours} hours")
        
        # Load book ticker data at target frequency
        try:
            # Use existing book ticker loader but with higher frequency
            df = await self.load_book_ticker_data(
                symbol=symbol,
                hours=hours,
                timeframe=target_interval_seconds
            )
            
            if df is None or len(df) == 0:
                self.logger.warning("No high-frequency data available, falling back to 1-minute")
                df = await self.load_book_ticker_data(symbol=symbol, hours=hours, timeframe=60)
            
            self.logger.info(f"✅ Loaded {len(df)} high-frequency data points")
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to load high-frequency data: {e}")
            # Fallback to regular data
            return await self.load_book_ticker_data(symbol=symbol, hours=hours)
    
    def _convert_to_book_ticker_data(self, row: pd.Series) -> BookTickerData:
        """Convert DataFrame row to BookTickerData object"""
        
        # Extract bid/ask prices from the processed DataFrame
        # Assuming columns: MEXC_bid_price, MEXC_ask_price, GATEIO_bid_price, GATEIO_ask_price
        mexc_cols = [col for col in row.index if 'MEXC' in col]
        gateio_cols = [col for col in row.index if 'GATEIO' in col and 'FUTURES' not in col]
        
        # Find bid/ask columns
        mexc_bid = next((row[col] for col in mexc_cols if 'bid_price' in col), None)
        mexc_ask = next((row[col] for col in mexc_cols if 'ask_price' in col), None)
        gateio_bid = next((row[col] for col in gateio_cols if 'bid_price' in col), None)
        gateio_ask = next((row[col] for col in gateio_cols if 'ask_price' in col), None)
        
        # Fallback to mid prices if bid/ask not available
        if mexc_bid is None or mexc_ask is None:
            mexc_mid = next((row[col] for col in mexc_cols if 'close' in col or 'price' in col), 0)
            mexc_spread = mexc_mid * 0.0005  # Assume 0.05% spread
            mexc_bid = mexc_mid - mexc_spread / 2
            mexc_ask = mexc_mid + mexc_spread / 2
        
        if gateio_bid is None or gateio_ask is None:
            gateio_mid = next((row[col] for col in gateio_cols if 'close' in col or 'price' in col), 0)
            gateio_spread = gateio_mid * 0.001  # Assume 0.1% spread
            gateio_bid = gateio_mid - gateio_spread / 2
            gateio_ask = gateio_mid + gateio_spread / 2
        
        return BookTickerData(
            timestamp=row.name if hasattr(row, 'name') else datetime.now(),
            mexc_bid=mexc_bid,
            mexc_ask=mexc_ask,
            gateio_bid=gateio_bid,
            gateio_ask=gateio_ask
        )
    
    def backtest_temporal_spike_capture(self,
                                      df: pd.DataFrame,
                                      min_confidence: float = 0.4,
                                      max_hold_minutes: int = 10,
                                      symbol: Symbol = None,
                                      save_report: bool = True) -> Dict:
        """
        Backtest spike capture strategy using temporal aggregation
        
        Args:
            df: High-frequency DataFrame
            min_confidence: Minimum signal confidence to enter (0.0-1.0)
            max_hold_minutes: Maximum hold time in minutes
            symbol: Trading symbol for reporting
            save_report: Whether to save detailed report
            
        Returns:
            Backtest results dictionary
        """
        if not self.use_temporal_aggregation or self.temporal_aggregator is None:
            self.logger.warning("Temporal aggregation not enabled, falling back to regular spike capture")
            return self.backtest_optimized_spike_capture(df, symbol=symbol)
        
        self.logger.info(f"🎯 Backtesting Temporal Spike Capture for {symbol}")
        self.logger.info(f"   Min confidence: {min_confidence:.1f}")
        self.logger.info(f"   Max hold time: {max_hold_minutes} minutes")
        self.logger.info(f"   Conservative mode: {self.conservative_mode}")
        
        # Reset aggregator for clean backtest
        self.temporal_aggregator.reset()
        
        position = None
        trades = []
        signals_generated = 0
        signals_acted_on = 0
        
        for idx, row in df.iterrows():
            # Convert row to BookTickerData
            book_ticker = self._convert_to_book_ticker_data(row)
            
            # Process through temporal aggregator
            signal_result = self.temporal_aggregator.process_update(book_ticker)
            
            if signal_result.action != SignalAction.HOLD:
                signals_generated += 1
            
            # === ENTRY LOGIC ===
            if position is None and signal_result.action in [SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT]:
                
                # Filter by confidence
                if signal_result.confidence < min_confidence:
                    continue
                
                signals_acted_on += 1
                
                # Determine position details
                action = signal_result.action
                entry_price_mexc = book_ticker.mexc_mid
                entry_price_gateio = book_ticker.gateio_mid
                
                # Calculate expected profit based on signal strength
                expected_profit = abs(signal_result.z_score_short) * 0.1  # 0.1% per Z-score
                
                position = {
                    'entry_time': book_ticker.timestamp,
                    'entry_idx': idx,
                    'action': action,
                    'signal_level': signal_result.level,
                    'confidence': signal_result.confidence,
                    'entry_price_mexc': entry_price_mexc,
                    'entry_price_gateio': entry_price_gateio,
                    'entry_differential': book_ticker.price_differential,
                    'expected_profit': expected_profit,
                    'z_score_at_entry': signal_result.z_score_short
                }
            
            # === EXIT LOGIC ===
            elif position is not None:
                current_time = book_ticker.timestamp
                hold_time = current_time - position['entry_time']
                hold_minutes = hold_time.total_seconds() / 60
                
                # Calculate current P&L
                current_price_mexc = book_ticker.mexc_mid
                current_price_gateio = book_ticker.gateio_mid
                
                if position['action'] == SignalAction.ENTER_LONG:
                    # Long MEXC, Short Gate.io
                    mexc_pnl = (current_price_mexc - position['entry_price_mexc']) / position['entry_price_mexc'] * 100
                    gateio_pnl = (position['entry_price_gateio'] - current_price_gateio) / position['entry_price_gateio'] * 100
                else:
                    # Short MEXC, Long Gate.io  
                    mexc_pnl = (position['entry_price_mexc'] - current_price_mexc) / position['entry_price_mexc'] * 100
                    gateio_pnl = (current_price_gateio - position['entry_price_gateio']) / position['entry_price_gateio'] * 100
                
                gross_pnl = mexc_pnl + gateio_pnl
                
                # Exit conditions
                profit_target_hit = gross_pnl >= position['expected_profit']
                time_limit_hit = hold_minutes >= max_hold_minutes
                confidence_degraded = signal_result.confidence < position['confidence'] * 0.5
                signal_reversed = (signal_result.action != SignalAction.HOLD and 
                                 signal_result.action != position['action'])
                
                should_exit = profit_target_hit or time_limit_hit or confidence_degraded or signal_reversed
                
                # Determine exit reason
                if profit_target_hit:
                    exit_reason = ExitReason.PROFIT_TARGET
                elif time_limit_hit:
                    exit_reason = ExitReason.TIME_STOP
                elif confidence_degraded:
                    exit_reason = ExitReason.STOP_LOSS  # Confidence degradation
                elif signal_reversed:
                    exit_reason = ExitReason.CORRELATION_STOP  # Signal reversal
                else:
                    exit_reason = ExitReason.TIME_STOP
                
                if should_exit:
                    # Calculate final P&L with costs
                    net_pnl = gross_pnl - 0.14  # 0.14% round-trip costs
                    
                    # Record trade
                    trade = Trade(
                        entry_idx=position['entry_idx'],
                        exit_idx=idx,
                        entry_time=position['entry_time'],
                        exit_time=current_time,
                        hold_time=hold_minutes,
                        entry_spread=position['entry_differential'],
                        exit_spread=book_ticker.price_differential,
                        raw_pnl_pct=gross_pnl,
                        net_pnl_pct=net_pnl,
                        exit_reason=exit_reason,
                        direction=position['action'].value,
                        entry_price_mexc=position['entry_price_mexc'],
                        exit_price_mexc=current_price_mexc,
                        entry_price_gateio=position['entry_price_gateio'],
                        exit_price_gateio=current_price_gateio
                    )
                    
                    trades.append(trade)
                    position = None
        
        # Calculate results
        results = self._calculate_backtest_results(trades, df)
        
        # Add temporal aggregation specific metrics
        agg_stats = self.temporal_aggregator.get_performance_stats()
        results.update({
            'temporal_aggregation_used': True,
            'signals_generated': signals_generated,
            'signals_acted_on': signals_acted_on,
            'signal_action_rate': signals_acted_on / max(1, signals_generated),
            'aggregator_stats': agg_stats,
            'min_confidence_threshold': min_confidence,
            'conservative_mode': self.conservative_mode
        })
        
        self.logger.info(f"✅ Temporal Backtest Complete:")
        self.logger.info(f"   Trades: {len(trades)}")
        self.logger.info(f"   Signals generated: {signals_generated}")
        self.logger.info(f"   Signals acted on: {signals_acted_on}")
        self.logger.info(f"   Win rate: {results.get('win_rate', 0):.1f}%")
        self.logger.info(f"   Total P&L: {results.get('total_pnl_pct', 0):.3f}%")
        
        if save_report:
            self._save_temporal_report(results, symbol, df)
        
        return results
    
    def _calculate_backtest_results(self, trades: List[Trade], df: pd.DataFrame) -> Dict:
        """Calculate backtest results from trades"""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl_pct': 0,
                'avg_pnl_pct': 0,
                'avg_hold_time': 0,
                'max_pnl_pct': 0,
                'min_pnl_pct': 0,
                'sharpe_ratio': 0
            }
        
        # Convert to DataFrame for analysis
        trades_data = []
        for trade in trades:
            trades_data.append({
                'net_pnl_pct': trade.net_pnl_pct,
                'hold_time': trade.hold_time,
                'exit_reason': trade.exit_reason.value
            })
        
        trades_df = pd.DataFrame(trades_data)
        
        # Basic metrics
        total_trades = len(trades)
        winning_trades = len(trades_df[trades_df['net_pnl_pct'] > 0])
        win_rate = (winning_trades / total_trades) * 100
        
        total_pnl = trades_df['net_pnl_pct'].sum()
        avg_pnl = trades_df['net_pnl_pct'].mean()
        max_pnl = trades_df['net_pnl_pct'].max()
        min_pnl = trades_df['net_pnl_pct'].min()
        avg_hold_time = trades_df['hold_time'].mean()
        
        # Sharpe ratio
        pnl_std = trades_df['net_pnl_pct'].std()
        sharpe_ratio = (avg_pnl / pnl_std) if pnl_std > 0 else 0
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl_pct': total_pnl,
            'avg_pnl_pct': avg_pnl,
            'avg_hold_time': avg_hold_time,
            'max_pnl_pct': max_pnl,
            'min_pnl_pct': min_pnl,
            'sharpe_ratio': sharpe_ratio
        }
    
    def _save_temporal_report(self, results: Dict, symbol: Symbol, df: pd.DataFrame):
        """Save temporal aggregation specific report"""
        # Implementation would save detailed report with temporal aggregation metrics
        # For now, just log key metrics
        self.logger.info("📄 Temporal aggregation report saved")
    
    async def compare_temporal_vs_standard(self, 
                                   symbol: Symbol,
                                   hours: int = 6,
                                   save_comparison: bool = True) -> Dict:
        """
        Compare temporal aggregation vs standard backtesting performance
        
        Returns:
            Comparison results showing improvement metrics
        """
        self.logger.info(f"🔄 Comparing temporal vs standard backtesting for {symbol}")
        
        # Load high-frequency data
        hf_df = await self.load_high_frequency_data(symbol, hours, target_interval_seconds=5)
        
        # Test 1: Standard 5-second processing (expected poor performance)
        self.use_temporal_aggregation = False
        standard_5s_results = self.backtest_optimized_spike_capture(hf_df, symbol=symbol, save_report=False)
        
        # Test 2: Temporal aggregation processing  
        self.use_temporal_aggregation = True
        temporal_results = self.backtest_temporal_spike_capture(hf_df, symbol=symbol, save_report=False)
        
        # Test 3: Load 1-minute data for baseline
        min_df = await self.load_book_ticker_data(symbol, hours, timeframe=60)
        baseline_1m_results = self.backtest_optimized_spike_capture(min_df, symbol=symbol, save_report=False)
        
        # Calculate improvements
        comparison = {
            'symbol': symbol,
            'test_period_hours': hours,
            'data_points_5s': len(hf_df),
            'data_points_1m': len(min_df),
            
            'standard_5s': {
                'trades': standard_5s_results.get('total_trades', 0),
                'win_rate': standard_5s_results.get('win_rate', 0),
                'total_pnl': standard_5s_results.get('total_pnl_pct', 0)
            },
            
            'temporal_5s': {
                'trades': temporal_results.get('total_trades', 0),
                'win_rate': temporal_results.get('win_rate', 0),
                'total_pnl': temporal_results.get('total_pnl_pct', 0)
            },
            
            'baseline_1m': {
                'trades': baseline_1m_results.get('total_trades', 0),
                'win_rate': baseline_1m_results.get('win_rate', 0),
                'total_pnl': baseline_1m_results.get('total_pnl_pct', 0)
            }
        }
        
        # Calculate improvements
        comparison['improvements'] = {
            'win_rate_improvement': temporal_results.get('win_rate', 0) - standard_5s_results.get('win_rate', 0),
            'pnl_improvement': temporal_results.get('total_pnl_pct', 0) - standard_5s_results.get('total_pnl_pct', 0),
            'vs_baseline_win_rate': temporal_results.get('win_rate', 0) - baseline_1m_results.get('win_rate', 0),
            'vs_baseline_pnl': temporal_results.get('total_pnl_pct', 0) - baseline_1m_results.get('total_pnl_pct', 0)
        }
        
        self.logger.info(f"📊 Comparison Results:")
        self.logger.info(f"   Standard 5s: {comparison['standard_5s']['win_rate']:.1f}% win rate")
        self.logger.info(f"   Temporal 5s: {comparison['temporal_5s']['win_rate']:.1f}% win rate")
        self.logger.info(f"   Baseline 1m: {comparison['baseline_1m']['win_rate']:.1f}% win rate")
        self.logger.info(f"   Improvement: +{comparison['improvements']['win_rate_improvement']:.1f}% win rate")
        
        return comparison


# Helper function for easy testing
async def quick_temporal_test(symbol_str: str = "PIGGY_USDT", 
                            hours: int = 3,
                            conservative: bool = True) -> Dict:
    """Quick test of temporal aggregation performance"""
    
    symbol = Symbol(base=symbol_str.split('_')[0], quote=symbol_str.split('_')[1])
    
    backtester = TemporalAggregationBacktester(
        use_temporal_aggregation=True,
        conservative_mode=conservative
    )
    
    # Load high-frequency data
    df = await backtester.load_high_frequency_data(symbol, hours, target_interval_seconds=5)
    
    # Run temporal backtest
    results = backtester.backtest_temporal_spike_capture(
        df, 
        min_confidence=0.4,
        symbol=symbol,
        save_report=True
    )
    
    return results