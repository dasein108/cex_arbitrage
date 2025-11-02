"""
Integration Example: How to Use Backtest Results in Live Trading

This shows how to integrate the backtesting framework with your existing
HFT infrastructure for live trading signals.
"""

import asyncio
import pandas as pd
from datetime import datetime, UTC, timedelta
from typing import Dict, Optional

from config import HftConfig
from exchanges.structs import Symbol
from exchanges.structs.common import AssetName
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from infrastructure.logging import get_logger
from trading.research.cross_arbitrage.multi_candles_source import MultiCandlesSource

# Import backtest framework
from advanced_backtester import AdvancedBacktester
from analysis_utils import BacktestAnalyzer


class LiveTradingSignalGenerator:
    """
    Generates live trading signals using backtest-optimized parameters
    
    Flow:
    1. Load recent historical data (last 24h)
    2. Run backtests to find best strategy
    3. Calculate current indicators
    4. Generate entry/exit signals for live trading
    """
    
    def __init__(self):
        self.config = HftConfig()
        self.logger = get_logger("LiveSignalGenerator")
        self.candles_source = MultiCandlesSource()
        self.backtester = AdvancedBacktester()
        self.analyzer = BacktestAnalyzer()
        
        self.exchanges = [
            ExchangeEnum.MEXC,
            ExchangeEnum.GATEIO,
            ExchangeEnum.GATEIO_FUTURES
        ]
        
        # Optimized parameters (updated periodically from backtests)
        self.strategy_params = {
            'mean_reversion': {
                'entry_z_threshold': 1.5,
                'exit_z_threshold': 0.5,
                'stop_loss_pct': 0.5,
            },
            'spike_capture': {
                'volatility_threshold': 1.3,
                'z_score_threshold': 2.0,
                'profit_target_pct': 0.3,
                'stop_loss_pct': 0.4,
            }
        }
        
        # Current position tracking
        self.current_position = None
    
    async def optimize_parameters(self, symbol: Symbol, hours: int = 24):
        """
        Run parameter optimization on recent data
        Call this periodically (e.g., daily) to adapt to changing conditions
        """
        
        self.logger.info(f"🔧 Optimizing parameters for {symbol}")
        
        # Load data
        df = await self._load_data(symbol, hours)
        df = self._calculate_indicators(df)
        
        # Find optimal parameters for spike capture
        optimal_spike = self.analyzer.find_optimal_parameters(
            df, 
            self.backtester,
            strategy_func='backtest_spike_capture'
        )
        
        if len(optimal_spike) > 0:
            best_params = optimal_spike.iloc[0]
            self.strategy_params['spike_capture'] = {
                'volatility_threshold': best_params['volatility_threshold'],
                'z_score_threshold': best_params['z_score_threshold'],
                'profit_target_pct': best_params['profit_target_pct'],
                'stop_loss_pct': best_params['stop_loss_pct'],
            }
            self.logger.info(f"✓ Updated spike capture params: {self.strategy_params['spike_capture']}")
        
        # Monte Carlo validation
        results = self.backtester.backtest_spike_capture(df, **self.strategy_params['spike_capture'])
        if results['total_trades'] > 0:
            mc = self.analyzer.monte_carlo_simulation(results['trades_df'])
            if mc['statistically_significant']:
                self.logger.info(f"✓ Parameters are statistically significant (p={mc['p_value_sharpe']:.3f})")
            else:
                self.logger.warning(f"⚠️ Parameters may not be robust (p={mc['p_value_sharpe']:.3f})")
    
    async def get_current_signal(self, symbol: Symbol) -> Dict:
        """
        Get current trading signal based on latest data
        
        Returns:
            {
                'action': 'ENTER_LONG' | 'ENTER_SHORT' | 'EXIT' | 'HOLD',
                'strategy': 'spike_capture' | 'mean_reversion',
                'confidence': 0.0-1.0,
                'current_spread': float,
                'z_score': float,
                'recommended_size': float,  # % of capital
            }
        """
        
        # Load recent data (last 2 hours for real-time indicators)
        df = await self._load_data(symbol, hours=2)
        df = self._calculate_indicators(df)
        
        if len(df) < 20:
            return {'action': 'HOLD', 'reason': 'Insufficient data'}
        
        # Get latest row
        latest = df.iloc[-1]
        
        # Safety checks
        if pd.isna(latest['spread_z_score']) or pd.isna(latest['rolling_corr']):
            return {'action': 'HOLD', 'reason': 'Missing indicators'}
        
        # Check correlation (critical safety check)
        if latest['rolling_corr'] < 0.6:
            return {
                'action': 'EXIT' if self.current_position else 'HOLD',
                'reason': 'Correlation breakdown',
                'current_spread': latest['mexc_vs_gateio_pct'],
            }
        
        # If in position, check exit conditions
        if self.current_position:
            exit_signal = self._check_exit_conditions(latest)
            if exit_signal:
                return exit_signal
            else:
                return {'action': 'HOLD', 'reason': 'Position active, no exit signal'}
        
        # Check entry conditions for different strategies
        spike_signal = self._check_spike_entry(latest)
        if spike_signal:
            return spike_signal
        
        mean_rev_signal = self._check_mean_reversion_entry(latest)
        if mean_rev_signal:
            return mean_rev_signal
        
        return {'action': 'HOLD', 'reason': 'No entry conditions met'}
    
    def _check_spike_entry(self, latest: pd.Series) -> Optional[Dict]:
        """Check if spike capture entry conditions are met"""
        
        params = self.strategy_params['spike_capture']
        
        entry_conditions = (
            abs(latest['spread_z_score']) > params['z_score_threshold'] and
            latest['vol_ratio'] > params['volatility_threshold'] and
            latest['mexc_static'] > 45 and
            abs(latest['spread_velocity']) > 0.08 and
            latest['rolling_corr'] > 0.7
        )
        
        if not entry_conditions:
            return None
        
        # Determine direction
        if latest['mexc_vs_gateio_pct'] > 0:
            action = 'ENTER_SHORT'  # MEXC expensive, sell MEXC
            direction = 'short_mexc'
        else:
            action = 'ENTER_LONG'  # Gate.io expensive, buy MEXC
            direction = 'long_mexc'
        
        # Calculate confidence based on Z-score magnitude
        confidence = min(1.0, abs(latest['spread_z_score']) / 3.0)
        
        # Position size: scale with confidence and inverse of volatility
        base_size = 0.1  # 10% of capital
        volatility_adjustment = 1.0 / (1.0 + latest['spread_std'])
        recommended_size = base_size * confidence * volatility_adjustment
        
        return {
            'action': action,
            'strategy': 'spike_capture',
            'direction': direction,
            'confidence': confidence,
            'current_spread': latest['mexc_vs_gateio_pct'],
            'z_score': latest['spread_z_score'],
            'volatility_ratio': latest['vol_ratio'],
            'recommended_size': recommended_size,
            'target_profit': params['profit_target_pct'],
            'stop_loss': params['stop_loss_pct'],
        }
    
    def _check_mean_reversion_entry(self, latest: pd.Series) -> Optional[Dict]:
        """Check if mean reversion entry conditions are met"""
        
        params = self.strategy_params['mean_reversion']
        
        entry_conditions = (
            abs(latest['spread_z_score']) > params['entry_z_threshold'] and
            latest['spread_velocity'] < 0 and  # Converging
            latest['rolling_corr'] > 0.75
        )
        
        if not entry_conditions:
            return None
        
        direction = 'long' if latest['mexc_vs_gateio_pct'] > 0 else 'short'
        confidence = min(1.0, abs(latest['spread_z_score']) / 2.5)
        
        return {
            'action': 'ENTER_LONG' if direction == 'long' else 'ENTER_SHORT',
            'strategy': 'mean_reversion',
            'direction': direction,
            'confidence': confidence,
            'current_spread': latest['mexc_vs_gateio_pct'],
            'z_score': latest['spread_z_score'],
            'recommended_size': 0.15 * confidence,  # More conservative
            'target_profit': params['exit_z_threshold'],
            'stop_loss': params['stop_loss_pct'],
        }
    
    def _check_exit_conditions(self, latest: pd.Series) -> Optional[Dict]:
        """Check if current position should be exited"""
        
        if not self.current_position:
            return None
        
        strategy = self.current_position['strategy']
        entry_spread = self.current_position['entry_spread']
        entry_time = self.current_position['entry_time']
        
        current_spread = latest['mexc_vs_gateio_pct']
        spread_change = current_spread - entry_spread
        hold_time = (datetime.now(UTC) - entry_time).total_seconds() / 60
        
        if strategy == 'spike_capture':
            params = self.strategy_params['spike_capture']
            
            # Profit target
            if abs(spread_change) >= params['profit_target_pct']:
                return {
                    'action': 'EXIT',
                    'reason': 'profit_target',
                    'pnl_estimate': abs(spread_change) - 0.90,  # Subtract costs
                    'hold_time_minutes': hold_time,
                }
            
            # Stop loss
            if abs(current_spread) > abs(entry_spread) + params['stop_loss_pct']:
                return {
                    'action': 'EXIT',
                    'reason': 'stop_loss',
                    'pnl_estimate': -params['stop_loss_pct'] - 0.90,
                    'hold_time_minutes': hold_time,
                }
            
            # Time stop
            if hold_time > 10:
                return {
                    'action': 'EXIT',
                    'reason': 'time_stop',
                    'pnl_estimate': abs(entry_spread) - abs(current_spread) - 0.90,
                    'hold_time_minutes': hold_time,
                }
        
        elif strategy == 'mean_reversion':
            params = self.strategy_params['mean_reversion']
            
            # Profit target
            if abs(latest['spread_z_score']) < params['exit_z_threshold']:
                return {
                    'action': 'EXIT',
                    'reason': 'profit_target',
                    'pnl_estimate': abs(spread_change) - 0.90,
                    'hold_time_minutes': hold_time,
                }
            
            # Stop loss
            if abs(spread_change) > params['stop_loss_pct']:
                return {
                    'action': 'EXIT',
                    'reason': 'stop_loss',
                    'pnl_estimate': -params['stop_loss_pct'] - 0.90,
                    'hold_time_minutes': hold_time,
                }
            
            # Time stop
            if hold_time > 120:
                return {
                    'action': 'EXIT',
                    'reason': 'time_stop',
                    'pnl_estimate': abs(entry_spread) - abs(current_spread) - 0.90,
                    'hold_time_minutes': hold_time,
                }
        
        return None
    
    async def _load_data(self, symbol: Symbol, hours: int) -> pd.DataFrame:
        """Load candle data"""
        end_time = datetime.now(UTC)
        
        df = await self.candles_source.get_multi_candles_df(
            exchanges=self.exchanges,
            symbol=symbol,
            date_to=end_time,
            hours=hours,
            timeframe=KlineInterval.MINUTE_1
        )
        
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all indicators (same as backtester)"""
        
        # Column names
        mexc_c_col = f'{ExchangeEnum.MEXC.value}_close'
        gateio_c_col = f'{ExchangeEnum.GATEIO.value}_close'
        mexc_h_col = f'{ExchangeEnum.MEXC.value}_high'
        mexc_l_col = f'{ExchangeEnum.MEXC.value}_low'
        gateio_h_col = f'{ExchangeEnum.GATEIO.value}_high'
        gateio_l_col = f'{ExchangeEnum.GATEIO.value}_low'
        
        df.attrs['mexc_c_col'] = mexc_c_col
        df.attrs['gateio_c_col'] = gateio_c_col
        
        def diff_perc(col1, col2):
            return ((df[col1] - df[col2]) / df[col2] * 100).fillna(0)
        
        # Spreads
        df['mexc_vs_gateio_pct'] = diff_perc(mexc_c_col, gateio_c_col)
        
        # Ranges
        df['mexc_range'] = (df[mexc_h_col] - df[mexc_l_col]) / df[mexc_c_col] * 100
        df['gateio_range'] = (df[gateio_h_col] - df[gateio_l_col]) / df[gateio_c_col] * 100
        
        # Volatility
        window = 20
        df['mexc_vol'] = df['mexc_range'].rolling(window).std()
        df['gateio_vol'] = df['gateio_range'].rolling(window).std()
        df['vol_ratio'] = df['mexc_vol'] / df['gateio_vol']
        
        # Liquidity
        df['mexc_static'] = ((df[mexc_h_col] == df[mexc_l_col]).rolling(window).mean() * 100)
        df['gateio_static'] = ((df[gateio_h_col] == df[gateio_l_col]).rolling(window).mean() * 100)
        
        # Spread stats
        df['spread_mean'] = df['mexc_vs_gateio_pct'].rolling(window).mean()
        df['spread_std'] = df['mexc_vs_gateio_pct'].rolling(window).std()
        df['spread_z_score'] = (df['mexc_vs_gateio_pct'] - df['spread_mean']) / df['spread_std']
        df['spread_velocity'] = df['mexc_vs_gateio_pct'].diff()
        
        # Correlation
        df['rolling_corr'] = df[mexc_c_col].rolling(window).corr(df[gateio_c_col])
        
        return df
    
    def open_position(self, signal: Dict):
        """Record position opening"""
        self.current_position = {
            'strategy': signal['strategy'],
            'direction': signal['direction'],
            'entry_spread': signal['current_spread'],
            'entry_time': datetime.now(UTC),
            'entry_z_score': signal['z_score'],
        }
        self.logger.info(f"📈 Opened {signal['direction']} position via {signal['strategy']}")
    
    def close_position(self, exit_signal: Dict):
        """Record position closing"""
        if self.current_position:
            self.logger.info(f"📉 Closed position. Reason: {exit_signal['reason']}, "
                           f"Est P&L: {exit_signal.get('pnl_estimate', 0):.3f}%")
            self.current_position = None


async def example_live_trading_loop():
    """Example of how to use signal generator in live trading"""
    
    generator = LiveTradingSignalGenerator()
    symbol = Symbol(base=AssetName("QUBIC"), quote=AssetName("USDT"))
    
    # Optimize parameters once at startup
    await generator.optimize_parameters(symbol, hours=24)
    
    # Main trading loop
    while True:
        try:
            # Get current signal
            signal = await generator.get_current_signal(symbol)
            
            print(f"\n⏰ {datetime.now(UTC)}")
            print(f"Signal: {signal['action']}")
            
            if signal['action'] == 'ENTER_LONG' or signal['action'] == 'ENTER_SHORT':
                print(f"  Strategy: {signal['strategy']}")
                print(f"  Confidence: {signal['confidence']:.2%}")
                print(f"  Current Spread: {signal['current_spread']:.3f}%")
                print(f"  Z-Score: {signal['z_score']:.2f}")
                print(f"  Recommended Size: {signal['recommended_size']:.2%}")
                
                # TODO: Execute trade via your exchange API
                # await execute_trade(signal)
                
                generator.open_position(signal)
            
            elif signal['action'] == 'EXIT':
                print(f"  Reason: {signal['reason']}")
                print(f"  Est P&L: {signal.get('pnl_estimate', 0):.3f}%")
                
                # TODO: Close position via your exchange API
                # await close_position()
                
                generator.close_position(signal)
            
            # Wait before next iteration (adjust based on your needs)
            await asyncio.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(example_live_trading_loop())
