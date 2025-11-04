"""
Arbitrage Signal Strategy - Dependency-free signal generation for backtesting and live trading.

Focuses only on data loading, indicators, and signal generation without external dependencies.
Can be used both for backtesting and integrated with MultiSpotFuturesArbitrageTask.
"""

import pandas as pd
from typing import Dict, Optional

from exchanges.structs import Symbol, BookTicker
from .signal_types import Signal
from .arbitrage_data_loader import ArbitrageDataLoader
from .arbitrage_indicators import ArbitrageIndicators, IndicatorConfig
from .arbitrage_signal_generator import ArbitrageSignalGenerator


class ArbitrageSignalStrategy:
    """
    Dual-mode arbitrage strategy focused on signals generation.
    Works for both backtesting and live trading with MultiSpotFuturesArbitrageTask.
    
    No external dependencies - all data passed as parameters.
    """
    
    def __init__(self, symbol: Symbol, strategy_type: str, is_live_mode: bool = False):
        """
        Initialize strategy with symbol and type.
        
        Args:
            symbol: Trading symbol
            strategy_type: 'reverse_delta_neutral', 'inventory_spot', 'volatility_harvesting'
            is_live_mode: True for live trading, False for backtesting
        """
        self.symbol = symbol
        self.strategy_type = strategy_type
        self.is_live_mode = is_live_mode
        
        # Pure components with no external dependencies
        self.data_loader = ArbitrageDataLoader(symbol, is_live_mode)
        self.indicators = ArbitrageIndicators(IndicatorConfig())
        self.signal_generator = ArbitrageSignalGenerator(strategy_type)
        
        # Historical context (rolling buffer for live mode)
        self.historical_df = pd.DataFrame()
        self.context_ready = False
        
        # Performance tracking
        self.total_signals = 0
        self.signal_counts = {'ENTER': 0, 'EXIT': 0, 'HOLD': 0}
    
    async def initialize(self, days: int = 7) -> None:
        """
        Load initial historical data and prepare indicators.
        
        Args:
            days: Number of days of historical data to load
        """
        # Load historical data from database
        self.historical_df = await self.data_loader.load_initial_data(days)
        
        if self.historical_df.empty:
            raise ValueError(f"No historical data found for {self.symbol}")
        
        # Calculate initial indicators based on strategy type
        if self.strategy_type == 'reverse_delta_neutral':
            self.historical_df = self.indicators.calculate_reverse_delta_neutral_indicators(self.historical_df)
        elif self.strategy_type == 'inventory_spot':
            self.historical_df = self.indicators.calculate_inventory_spot_indicators(self.historical_df)
        elif self.strategy_type == 'volatility_harvesting':
            self.historical_df = self.indicators.calculate_volatility_harvesting_indicators(self.historical_df)
        else:
            raise ValueError(f"Unknown strategy type: {self.strategy_type}")
        
        self.context_ready = True
        print(f"✅ Strategy initialized with {len(self.historical_df)} historical data points")
    
    def update_with_live_data(self,
                             spot_book_tickers: Dict[str, BookTicker],
                             futures_book_ticker: BookTicker,
                             current_positions: Optional[Dict[str, float]] = None,
                             current_balances: Optional[Dict[str, float]] = None) -> Signal:
        """
        Update strategy with live market data and generate signal.
        
        Args:
            spot_book_tickers: Dict of exchange_name -> BookTicker  
            futures_book_ticker: Futures exchange BookTicker
            current_positions: Optional position data
            current_balances: Optional balance data
            
        Returns:
            Trading signal based on current market conditions
        """
        if not self.context_ready:
            return Signal.HOLD  # No signal until initialized
        
        # Process live data
        current_data = self.data_loader.update_live_data(
            spot_book_tickers=spot_book_tickers,
            futures_book_ticker=futures_book_ticker,
            current_positions=current_positions or {},
            current_balances=current_balances or {}
        )
        
        # Update indicators with single row
        current_indicators = self.indicators.calculate_single_row_indicators(
            current_data, self.strategy_type
        )
        
        # Generate signal
        signal = self.signal_generator.generate_signal(
            strategy_type=self.strategy_type,
            current_indicators=current_indicators,
            historical_context=self.historical_df.tail(100)  # Last 100 rows for context
        )
        
        # Update rolling buffer for live mode
        if self.is_live_mode:
            self._update_rolling_buffer(current_data, current_indicators)
        
        # Track signal statistics
        self.total_signals += 1
        self.signal_counts[signal.value.upper()] += 1
        
        return signal
    
    def _update_rolling_buffer(self, current_data: dict, current_indicators: pd.Series):
        """Update rolling historical buffer with new data point."""
        try:
            # Flatten current_data for easier Series creation
            flattened_data = {}
            for key, value in current_data.items():
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        flattened_data[f"{key}_{subkey}"] = subvalue
                else:
                    flattened_data[key] = value
            
            # Create new row combining raw data and indicators
            new_row = pd.concat([
                pd.Series(flattened_data),
                current_indicators
            ])
            
            # Add to historical data and maintain rolling window
            self.historical_df = pd.concat([
                self.historical_df,
                new_row.to_frame().T
            ]).tail(1000)  # Keep last 1000 rows
            
        except Exception as e:
            print(f"⚠️ Error updating rolling buffer: {e}")
    
    def get_strategy_metrics(self) -> dict:
        """Get current strategy state and performance metrics."""
        return {
            'strategy_type': self.strategy_type,
            'symbol': str(self.symbol),
            'is_live_mode': self.is_live_mode,
            'context_ready': self.context_ready,
            'historical_data_points': len(self.historical_df),
            'total_signals': self.total_signals,
            'signal_distribution': self.signal_counts.copy(),
            'last_update': pd.Timestamp.now().isoformat() if self.context_ready else None
        }
    
    def get_historical_data(self) -> pd.DataFrame:
        """Get copy of historical data for analysis."""
        return self.historical_df.copy()
    
    def reset_signal_stats(self):
        """Reset signal statistics counters."""
        self.total_signals = 0
        self.signal_counts = {'ENTER': 0, 'EXIT': 0, 'HOLD': 0}