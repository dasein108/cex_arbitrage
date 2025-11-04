"""
Strategy Signal Backtester

Modern backtester using strategy signal architecture.
Eliminates if/else chains and provides clean strategy separation.
"""

from typing import Dict, Any, List, Optional, Union
import pandas as pd
import numpy as np
import asyncio
import logging
from datetime import datetime

from trading.strategies.base.strategy_signal_factory import create_strategy_signal, get_available_strategy_signals
from trading.strategies.base.strategy_signal_interface import StrategySignalInterface
from trading.analysis.signal_types import Signal


class StrategySignalBacktester:
    """
    Modern backtester using strategy signal architecture.
    
    Provides clean separation between strategy logic and backtesting framework.
    Eliminates if/else chains through strategy pattern implementation.
    """
    
    def __init__(self, 
                 initial_capital: float = 10000.0,
                 default_position_size: float = 1000.0,
                 total_fees: float = 0.0025):
        """
        Initialize strategy signal backtester.
        
        Args:
            initial_capital: Starting capital for backtest
            default_position_size: Default position size in USD
            total_fees: Total round-trip fees as decimal
        """
        self.initial_capital = initial_capital
        self.default_position_size = default_position_size
        self.total_fees = total_fees
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def run_strategy_backtest(self, 
                                  df: pd.DataFrame,
                                  strategy_type: str,
                                  **strategy_params) -> Dict[str, Any]:
        """
        Run backtest for a single strategy.
        
        Args:
            df: Historical market data DataFrame
            strategy_type: Strategy type to test
            **strategy_params: Parameters for strategy
            
        Returns:
            Backtest results dictionary
        """
        try:
            # Merge default parameters
            params = {
                'position_size_usd': self.default_position_size,
                'total_fees': self.total_fees,
                **strategy_params
            }
            
            # Create strategy instance
            strategy = create_strategy_signal(strategy_type, **params)
            
            # Preload strategy with historical data
            await strategy.preload(df, **params)
            
            # Apply signals to data
            df_with_signals = strategy.apply_signal_to_backtest(df, **params)
            
            # Calculate trades and P&L
            trades, positions = self._process_signals_to_trades(df_with_signals, strategy, **params)
            
            # Calculate performance metrics
            performance = self._calculate_performance_metrics(trades, positions)
            
            return {
                'strategy_type': strategy_type,
                'total_trades': len(trades),
                'total_positions': len(positions),
                'performance_metrics': performance,
                'trades': trades,
                'positions': positions,
                'signal_distribution': self._get_signal_distribution(df_with_signals),
                'success': True
            }
            
        except Exception as e:
            self.logger.error(f"Error running backtest for {strategy_type}: {e}")
            return {
                'strategy_type': strategy_type,
                'success': False,
                'error': str(e)
            }
    
    async def run_multi_strategy_backtest(self, 
                                        df: pd.DataFrame,
                                        strategy_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run backtest for multiple strategies.
        
        Args:
            df: Historical market data DataFrame
            strategy_configs: List of strategy configurations
            
        Returns:
            Multi-strategy backtest results
        """
        results = {}
        
        for config in strategy_configs:
            strategy_type = config.pop('strategy_type')
            strategy_name = config.pop('name', strategy_type)
            
            result = await self.run_strategy_backtest(df, strategy_type, **config)
            results[strategy_name] = result
        
        # Calculate comparison metrics
        comparison = self._compare_strategies(results)
        
        return {
            'individual_results': results,
            'comparison_metrics': comparison,
            'total_strategies_tested': len(strategy_configs)
        }
    
    async def run_all_strategies_backtest(self, 
                                        df: pd.DataFrame,
                                        common_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run backtest for all available strategies.
        
        Args:
            df: Historical market data DataFrame
            common_params: Common parameters for all strategies
            
        Returns:
            Results for all strategies
        """
        available_strategies = get_available_strategy_signals()
        common_params = common_params or {}
        
        results = {}
        
        for strategy_type in available_strategies:
            # Skip aliases
            if strategy_type in ['delta_neutral', 'volatility']:
                continue
            
            result = await self.run_strategy_backtest(df, strategy_type, **common_params)
            results[strategy_type] = result
        
        # Calculate comparison metrics
        comparison = self._compare_strategies(results)
        
        return {
            'individual_results': results,
            'comparison_metrics': comparison,
            'total_strategies_tested': len(results)
        }
    
    def _process_signals_to_trades(self, 
                                 df: pd.DataFrame, 
                                 strategy: StrategySignalInterface,
                                 **params) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Process signals into trades and positions.
        
        Args:
            df: DataFrame with signals
            strategy: Strategy instance
            **params: Strategy parameters
            
        Returns:
            Tuple of (trades, positions)
        """
        trades = []
        positions = []
        current_position = None
        
        for idx, row in df.iterrows():
            signal = Signal(row['signal'])
            
            # Extract market data for this row
            market_data = {
                'mexc_bid': row.get('MEXC_SPOT_bid_price', 0),
                'mexc_ask': row.get('MEXC_SPOT_ask_price', 0),
                'gateio_spot_bid': row.get('GATEIO_SPOT_bid_price', 0),
                'gateio_spot_ask': row.get('GATEIO_SPOT_ask_price', 0),
                'gateio_futures_bid': row.get('GATEIO_FUTURES_bid_price', 0),
                'gateio_futures_ask': row.get('GATEIO_FUTURES_ask_price', 0),
                'timestamp': idx
            }
            
            if signal == Signal.ENTER and current_position is None:
                # Open new position
                position = strategy.open_position(signal, market_data, **params)
                if position:
                    position['entry_index'] = idx
                    current_position = position
                    positions.append(position)
            
            elif signal == Signal.EXIT and current_position is not None:
                # Close current position
                trade = strategy.close_position(current_position, market_data, **params)
                if trade:
                    trade['exit_index'] = idx
                    trade['entry_index'] = current_position.get('entry_index')
                    trades.append(trade)
                
                current_position = None
        
        # Close any remaining position at the end
        if current_position is not None:
            final_row = df.iloc[-1]
            final_market_data = {
                'mexc_bid': final_row.get('MEXC_SPOT_bid_price', 0),
                'mexc_ask': final_row.get('MEXC_SPOT_ask_price', 0),
                'gateio_spot_bid': final_row.get('GATEIO_SPOT_bid_price', 0),
                'gateio_spot_ask': final_row.get('GATEIO_SPOT_ask_price', 0),
                'gateio_futures_bid': final_row.get('GATEIO_FUTURES_bid_price', 0),
                'gateio_futures_ask': final_row.get('GATEIO_FUTURES_ask_price', 0),
                'timestamp': df.index[-1]
            }
            
            trade = strategy.close_position(current_position, final_market_data, **params)
            if trade:
                trade['exit_index'] = df.index[-1]
                trade['entry_index'] = current_position.get('entry_index')
                trade['forced_exit'] = True
                trades.append(trade)
        
        return trades, positions
    
    def _calculate_performance_metrics(self, 
                                     trades: List[Dict[str, Any]], 
                                     positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate performance metrics from trades.
        
        Args:
            trades: List of completed trades
            positions: List of all positions
            
        Returns:
            Performance metrics dictionary
        """
        if not trades:
            return {
                'total_pnl_usd': 0.0,
                'total_pnl_pct': 0.0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'profit_factor': 0.0
            }
        
        # Extract P&L values
        pnls = [trade.get('net_pnl_usd', 0) for trade in trades]
        pnl_pcts = [trade.get('pnl_percentage', 0) for trade in trades]
        
        # Basic metrics
        total_pnl_usd = sum(pnls)
        total_pnl_pct = (total_pnl_usd / self.initial_capital) * 100
        
        # Win/loss analysis
        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]
        
        win_rate = (len(wins) / len(trades)) * 100 if trades else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        
        # Risk metrics
        cumulative_pnl = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative_pnl)
        drawdown = running_max - cumulative_pnl
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0
        
        # Sharpe ratio (simplified)
        sharpe_ratio = (np.mean(pnl_pcts) / np.std(pnl_pcts)) if len(pnl_pcts) > 1 and np.std(pnl_pcts) > 0 else 0
        
        # Profit factor
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf') if total_wins > 0 else 0
        
        return {
            'total_pnl_usd': total_pnl_usd,
            'total_pnl_pct': total_pnl_pct,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'profit_factor': profit_factor,
            'total_trades': len(trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses)
        }
    
    def _get_signal_distribution(self, df: pd.DataFrame) -> Dict[str, int]:
        """
        Get distribution of signals.
        
        Args:
            df: DataFrame with signals
            
        Returns:
            Signal distribution dictionary
        """
        signal_counts = df['signal'].value_counts().to_dict()
        
        return {
            'ENTER': signal_counts.get('enter', 0),
            'EXIT': signal_counts.get('exit', 0),
            'HOLD': signal_counts.get('hold', 0)
        }
    
    def _compare_strategies(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare performance across strategies.
        
        Args:
            results: Strategy results dictionary
            
        Returns:
            Comparison metrics
        """
        successful_results = {k: v for k, v in results.items() if v.get('success', False)}
        
        if not successful_results:
            return {'error': 'No successful strategy results to compare'}
        
        # Extract performance metrics
        performances = {}
        for name, result in successful_results.items():
            perf = result.get('performance_metrics', {})
            performances[name] = {
                'total_pnl_pct': perf.get('total_pnl_pct', 0),
                'win_rate': perf.get('win_rate', 0),
                'sharpe_ratio': perf.get('sharpe_ratio', 0),
                'max_drawdown': perf.get('max_drawdown', 0),
                'total_trades': perf.get('total_trades', 0)
            }
        
        # Find best performers
        best_pnl = max(performances.items(), key=lambda x: x[1]['total_pnl_pct'])
        best_sharpe = max(performances.items(), key=lambda x: x[1]['sharpe_ratio'])
        best_win_rate = max(performances.items(), key=lambda x: x[1]['win_rate'])
        
        # Calculate averages
        avg_pnl = np.mean([p['total_pnl_pct'] for p in performances.values()])
        avg_win_rate = np.mean([p['win_rate'] for p in performances.values()])
        avg_sharpe = np.mean([p['sharpe_ratio'] for p in performances.values()])
        
        return {
            'best_pnl_strategy': best_pnl[0],
            'best_pnl_value': best_pnl[1]['total_pnl_pct'],
            'best_sharpe_strategy': best_sharpe[0],
            'best_sharpe_value': best_sharpe[1]['sharpe_ratio'],
            'best_win_rate_strategy': best_win_rate[0],
            'best_win_rate_value': best_win_rate[1]['win_rate'],
            'average_pnl_pct': avg_pnl,
            'average_win_rate': avg_win_rate,
            'average_sharpe_ratio': avg_sharpe,
            'strategies_compared': len(performances)
        }


# Convenience functions

async def run_single_strategy_backtest(df: pd.DataFrame, 
                                     strategy_type: str,
                                     **params) -> Dict[str, Any]:
    """
    Convenience function to run a single strategy backtest.
    
    Args:
        df: Historical market data
        strategy_type: Strategy type to test
        **params: Strategy parameters
        
    Returns:
        Backtest results
    """
    backtester = StrategySignalBacktester()
    return await backtester.run_strategy_backtest(df, strategy_type, **params)


async def compare_all_strategies(df: pd.DataFrame, **common_params) -> Dict[str, Any]:
    """
    Convenience function to compare all available strategies.
    
    Args:
        df: Historical market data
        **common_params: Common parameters for all strategies
        
    Returns:
        Comparison results
    """
    backtester = StrategySignalBacktester()
    return await backtester.run_all_strategies_backtest(df, common_params)