"""
Base Arbitrage Strategy Framework

Unified strategy framework that composes data provider, indicators, and signal engine
for both backtesting and live trading. Provides consistent interface for all arbitrage strategies.

Key Features:
- Dual-mode operation (backtesting and live trading)
- Composable architecture with dependency injection
- Performance monitoring and optimization
- Strategy-agnostic base implementation
"""

import asyncio
import pandas as pd
from datetime import datetime, UTC
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from db import get_database_manager
from exchanges.structs import Symbol, ExchangeEnum
from exchanges.structs.enums import KlineInterval
from trading.research.cross_arbitrage.book_ticker_source import BookTickerSourceProtocol, BookTickerDbSource, CandlesBookTickerSource
from trading.analysis.arbitrage_data_provider import ArbitrageDataProvider, DataProviderConfig
from trading.analysis.arbitrage_indicators import ArbitrageIndicators, IndicatorConfig
from trading.analysis.arbitrage_signal_engine import ArbitrageSignalEngine, SignalEngineConfig


@dataclass
class StrategyConfig:
    """Configuration for arbitrage strategy behavior."""
    # Core strategy settings
    strategy_type: str = 'generic'  # 'reverse_delta_neutral', 'inventory_spot', etc.
    mode: str = 'backtest'  # 'backtest' or 'live'
    
    # Data settings
    symbol: Optional[Symbol] = None
    exchanges: List[ExchangeEnum] = field(default_factory=lambda: [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES])
    timeframe: KlineInterval = KlineInterval.MINUTE_5
    use_db_source: bool = False
    
    # Analysis settings
    backtest_days: int = 7
    min_history: int = 50
    lookback_periods: int = 500
    
    # Strategy-specific parameters
    entry_threshold: float = 0.3
    exit_threshold: float = 0.1
    min_profit_threshold: float = 0.05
    position_size_usd: float = 1000.0
    total_fees: float = 0.0025


class BaseArbitrageStrategy:
    """
    Base arbitrage strategy that composes data provider, indicators, and signal engine.
    
    Provides unified interface for both backtesting and live trading across all arbitrage types.
    Can be used directly for simple strategies or inherited for complex implementations.
    """
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        
        # Initialize composed components
        self.data_source = self._create_data_source()
        self.data_provider = self._create_data_provider()
        self.indicators = self._create_indicators()
        self.signal_engine = self._create_signal_engine()
        
        # Performance tracking
        self._performance_stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'avg_execution_time_ms': 0.0,
            'last_run_time': None
        }
    
    async def run_analysis(self, **override_params) -> pd.DataFrame:
        """
        Run complete arbitrage analysis with automatic mode optimization.
        
        Args:
            **override_params: Parameters to override from config
            
        Returns:
            DataFrame with prices, indicators, signals, and P&L
        """
        import time
        start_time = time.perf_counter()
        
        try:
            if self.config.use_db_source:
                await get_database_manager()
            # Merge override parameters with config
            run_params = {**self.config.__dict__, **override_params}
            
            # Load historical data
            df = await self._load_data(run_params)
            
            # Calculate indicators
            df = self._calculate_indicators(df, run_params)
            
            # Generate signals
            df = self._generate_signals(df, run_params)
            
            # Calculate P&L (if backtesting)
            if self.config.mode == 'backtest':
                df = self._calculate_pnl(df, run_params)
            
            # Update performance stats
            execution_time = (time.perf_counter() - start_time) * 1000
            self._update_performance_stats(execution_time, success=True)
            
            print(f"✅ Analysis completed in {execution_time:.2f}ms ({len(df)} rows processed)")
            return df
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            self._update_performance_stats(execution_time, success=False)
            print(f"❌ Analysis failed after {execution_time:.2f}ms: {e}")
            raise
    
    async def update_live(self, new_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Process live data update and return trading signal.
        
        Optimized for sub-millisecond performance in live trading.
        
        Args:
            new_data: Latest market data from exchange
            **params: Optional parameter overrides
            
        Returns:
            Dictionary with signal and metadata
        """
        if self.config.mode != 'live':
            raise ValueError("update_live only available in live mode")
        
        import time
        start_time = time.perf_counter()
        
        try:
            # Update data provider with new data
            context_df = await self.data_provider.update_realtime(new_data)
            
            # Calculate indicators for context window
            context_df = self.indicators.calculate_all_indicators(context_df, force_mode='single_row')
            
            # Generate signal for latest data
            signal_df = self.signal_engine.generate_signals(
                context_df.tail(1), 
                self.config.strategy_type, 
                **{**self.config.__dict__, **params}
            )
            
            # Extract signal result
            if not signal_df.empty:
                latest_signal = signal_df.iloc[-1]
                result = {
                    'signal': latest_signal.get('signal', 'HOLD'),
                    'confidence': latest_signal.get('confidence', 0.0),
                    'direction': latest_signal.get('direction', 'NONE'),
                    'timestamp': datetime.now(UTC),
                    'processing_time_ms': (time.perf_counter() - start_time) * 1000
                }
            else:
                result = {
                    'signal': 'HOLD',
                    'confidence': 0.0,
                    'direction': 'NONE',
                    'timestamp': datetime.now(UTC),
                    'processing_time_ms': (time.perf_counter() - start_time) * 1000,
                    'error': 'No signal generated'
                }
            
            return result
            
        except Exception as e:
            return {
                'signal': 'HOLD',
                'confidence': 0.0,
                'direction': 'NONE',
                'timestamp': datetime.now(UTC),
                'processing_time_ms': (time.perf_counter() - start_time) * 1000,
                'error': str(e)
            }
    
    def switch_mode(self, new_mode: str):
        """
        Switch between backtesting and live trading modes.
        
        Updates all components to optimize for the new mode.
        """
        if new_mode not in ['backtest', 'live']:
            raise ValueError("Mode must be 'backtest' or 'live'")
        
        old_mode = self.config.mode
        self.config.mode = new_mode
        
        # Update all components
        self.data_provider.mode = new_mode
        self.signal_engine.mode = new_mode
        
        print(f"🔄 Strategy mode switched: {old_mode} → {new_mode}")
    
    async def _load_data(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Load data based on current mode and parameters."""
        symbol = params.get('symbol') or self.config.symbol
        if not symbol:
            raise ValueError("Symbol must be specified in config or parameters")
        
        days = params.get('backtest_days', self.config.backtest_days)
        exchanges = params.get('exchanges', self.config.exchanges)
        
        df = await self.data_provider.get_historical_data(symbol, days, exchanges)
        
        if df.empty:
            raise ValueError(f"No data loaded for {symbol}")
        
        print(f"📊 Loaded {len(df)} periods for {symbol}")
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Calculate all technical indicators."""
        return self.indicators.calculate_all_indicators(df)
    
    def _generate_signals(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Generate trading signals."""
        strategy_type = params.get('strategy_type', self.config.strategy_type)
        
        # Filter parameters relevant to signal generation
        signal_params = {
            k: v for k, v in params.items() 
            if k in ['entry_threshold', 'exit_threshold', 'min_profit_threshold', 
                    'min_history', 'lookback_periods', 'max_exit_threshold']
        }
        
        return self.signal_engine.generate_signals(df, strategy_type, **signal_params)
    
    def _calculate_pnl(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Calculate P&L for backtesting (can be overridden in subclasses)."""
        # Basic P&L calculation - can be enhanced in strategy subclasses
        if 'signal' in df.columns:
            df['position'] = (df['signal'] == 'ENTER').astype(int)
            df['position'] = df['position'].diff().fillna(0)  # Position changes
            
            # Simple P&L calculation based on spread capture
            spread_col = 'mexc_vs_gateio_futures_net'
            if spread_col in df.columns:
                df['trade_pnl'] = df['position'] * df[spread_col] * params.get('position_size_usd', 1000.0) / 100
                df['cumulative_pnl'] = df['trade_pnl'].cumsum()
            else:
                df['trade_pnl'] = 0.0
                df['cumulative_pnl'] = 0.0
        
        return df
    
    def _create_data_source(self) -> BookTickerSourceProtocol:
        """Create appropriate data source based on configuration."""
        if self.config.use_db_source:
            return BookTickerDbSource()
        else:
            return CandlesBookTickerSource()
    
    def _create_data_provider(self) -> ArbitrageDataProvider:
        """Create data provider with optimized configuration."""
        provider_config = DataProviderConfig(
            mode=self.config.mode,
            live_buffer_size=max(1000, self.config.lookback_periods),
            context_window_size=max(100, self.config.min_history)
        )
        return ArbitrageDataProvider(self.data_source, provider_config)
    
    def _create_indicators(self) -> ArbitrageIndicators:
        """Create indicators engine with optimized configuration."""
        indicator_config = IndicatorConfig(
            single_row_threshold=5 if self.config.mode == 'live' else 1
        )
        return ArbitrageIndicators(indicator_config)
    
    def _create_signal_engine(self) -> ArbitrageSignalEngine:
        """Create signal engine with optimized configuration."""
        signal_config = SignalEngineConfig(
            mode=self.config.mode,
            lookback_periods=self.config.lookback_periods,
            min_history=self.config.min_history,
            cache_signals=self.config.mode == 'live'
        )
        return ArbitrageSignalEngine(signal_config)
    
    def _update_performance_stats(self, execution_time_ms: float, success: bool):
        """Update performance tracking."""
        self._performance_stats['total_runs'] += 1
        if success:
            self._performance_stats['successful_runs'] += 1
        
        # Update rolling average
        total_runs = self._performance_stats['total_runs']
        current_avg = self._performance_stats['avg_execution_time_ms']
        self._performance_stats['avg_execution_time_ms'] = (
            (current_avg * (total_runs - 1) + execution_time_ms) / total_runs
        )
        self._performance_stats['last_run_time'] = datetime.now(UTC)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        return {
            'strategy_config': {
                'type': self.config.strategy_type,
                'mode': self.config.mode,
                'symbol': str(self.config.symbol) if self.config.symbol else None
            },
            'execution_stats': self._performance_stats,
            'component_stats': {
                'data_provider': self.data_provider.get_buffer_status(),
                'indicators': self.indicators.get_performance_stats(),
                'signal_engine': self.signal_engine.get_performance_stats()
            }
        }
    
    def reset_performance_stats(self):
        """Reset all performance tracking."""
        self._performance_stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'avg_execution_time_ms': 0.0,
            'last_run_time': None
        }
        self.data_provider._metrics = {
            'cache_hits': 0, 'cache_misses': 0, 'live_updates': 0, 'avg_update_time_ms': 0.0
        }
        self.indicators.reset_performance_stats()


# Convenience factory functions
def create_strategy(strategy_type: str, symbol: Symbol, mode: str = 'backtest', **kwargs) -> BaseArbitrageStrategy:
    """
    Factory function to create pre-configured strategy instances.
    
    Args:
        strategy_type: Type of strategy ('reverse_delta_neutral', 'inventory_spot', etc.)
        symbol: Trading symbol
        mode: Operation mode ('backtest' or 'live')
        **kwargs: Additional configuration parameters
        
    Returns:
        Configured BaseArbitrageStrategy instance
    """
    config = StrategyConfig(
        strategy_type=strategy_type,
        symbol=symbol,
        mode=mode,
        **kwargs
    )
    return BaseArbitrageStrategy(config)


def create_backtesting_strategy(strategy_type: str, symbol: Symbol, days: int = 7, **kwargs) -> BaseArbitrageStrategy:
    """Create strategy optimized for backtesting."""
    return create_strategy(
        strategy_type=strategy_type,
        symbol=symbol,
        mode='backtest',
        backtest_days=days,
        # use_db_source=kwargs.get('use_db_source', True),  # Default to DB for backtesting
        **kwargs
    )


def create_live_trading_strategy(strategy_type: str, symbol: Symbol, **kwargs) -> BaseArbitrageStrategy:
    """Create strategy optimized for live trading."""
    return create_strategy(
        strategy_type=strategy_type,
        symbol=symbol,
        mode='live',
        # use_db_source=kwargs.get('use_db_source', False),  # Default to candles for live
        **kwargs
    )