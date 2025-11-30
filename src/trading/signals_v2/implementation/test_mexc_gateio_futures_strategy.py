"""
Test Suite for MexcGateioFuturesArbitrageSignal Strategy

Comprehensive testing of the MEXC-Gate.io futures arbitrage strategy including:
- Unit tests for core functionality
- Integration tests with realistic market data
- Performance benchmarking
- Edge case validation
"""

import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from mexc_gateio_futures_arbitrage_signal import (
    MexcGateioFuturesArbitrageSignal,
    SpreadMetrics,
    FeeStructure,
    create_mexc_gateio_futures_strategy
)
from trading.signals_v2.entities import PerformanceMetrics, ExchangeEnum
from trading.data_sources.column_utils import get_column_key


class TestMexcGateioFuturesArbitrageSignal(unittest.TestCase):
    """Test suite for MEXC-Gate.io futures arbitrage strategy."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.strategy = MexcGateioFuturesArbitrageSignal(
            entry_quantile=0.80,
            exit_quantile=0.20,
            position_size_usd=1000.0,
            historical_window_hours=2  # Shorter for testing
        )
        
        # Create synthetic market data for testing
        self.test_df = self._create_test_market_data()
    
    def _create_test_market_data(self) -> pd.DataFrame:
        """Create realistic synthetic market data for testing."""
        timestamps = pd.date_range(
            start=datetime.now(timezone.utc) - timedelta(hours=3),
            end=datetime.now(timezone.utc),
            freq='5min'
        )
        
        np.random.seed(42)  # For reproducible tests
        base_price = 0.05000  # Example: 5 cents base price
        
        # Generate correlated but slightly different prices
        mexc_spot_mid = base_price + np.cumsum(np.random.normal(0, 0.00001, len(timestamps)))
        gateio_fut_mid = mexc_spot_mid + np.random.normal(0, 0.00005, len(timestamps))
        
        # Add bid-ask spreads
        mexc_spread = np.random.uniform(0.00001, 0.00003, len(timestamps))
        gateio_spread = np.random.uniform(0.00001, 0.00002, len(timestamps))
        
        # Use dynamic column keys for consistency
        df = pd.DataFrame({
            get_column_key(ExchangeEnum.MEXC, 'bid_price'): mexc_spot_mid - mexc_spread / 2,
            get_column_key(ExchangeEnum.MEXC, 'ask_price'): mexc_spot_mid + mexc_spread / 2,
            get_column_key(ExchangeEnum.GATEIO_FUTURES, 'bid_price'): gateio_fut_mid - gateio_spread / 2,
            get_column_key(ExchangeEnum.GATEIO_FUTURES, 'ask_price'): gateio_fut_mid + gateio_spread / 2,
        }, index=timestamps)
        
        # Ensure positive prices
        df = df.abs()
        
        return df
    
    def test_strategy_initialization(self):
        """Test strategy initialization with various parameters."""
        # Test default initialization
        strategy = MexcGateioFuturesArbitrageSignal()
        self.assertEqual(strategy.entry_quantile, 0.80)
        self.assertEqual(strategy.exit_quantile, 0.20)
        self.assertEqual(strategy.position_size_usd, 1000.0)
        
        # Test custom initialization
        custom_fees = FeeStructure(
            mexc_spot_maker_fee=0.0008,
            gateio_futures_taker_fee=0.0005
        )
        
        strategy = MexcGateioFuturesArbitrageSignal(
            entry_quantile=0.75,
            exit_quantile=0.25,
            position_size_usd=500.0,
            fee_structure=custom_fees
        )
        
        self.assertEqual(strategy.entry_quantile, 0.75)
        self.assertEqual(strategy.exit_quantile, 0.25)
        self.assertEqual(strategy.position_size_usd, 500.0)
        self.assertEqual(strategy.fee_structure.mexc_spot_maker_fee, 0.0008)
    
    def test_spread_calculation(self):
        """Test spread calculation logic."""
        # Test with first timestamp
        timestamp = self.test_df.index[20]  # Use middle timestamp with history
        
        # Manually add some history to arrays for realistic test
        self.strategy._mexc_to_fut_history = np.random.normal(-0.001, 0.0005, 50)
        self.strategy._fut_to_mexc_history = np.random.normal(-0.001, 0.0005, 50)
        
        spread_metrics = self.strategy.calculate_spread_metrics(self.test_df, timestamp)
        
        # Validate spread metrics structure
        self.assertIsInstance(spread_metrics, SpreadMetrics)
        self.assertIsInstance(spread_metrics.mexc_to_gateio_fut, float)
        self.assertIsInstance(spread_metrics.gateio_fut_to_mexc, float)
        self.assertTrue(0 <= spread_metrics.mexc_to_gateio_fut_percentile <= 100)
        self.assertTrue(0 <= spread_metrics.gateio_fut_to_mexc_percentile <= 100)
        self.assertIn(spread_metrics.favorable_direction, ['mexc_to_fut', 'fut_to_mexc'])
        
        # Test edge case with missing data
        empty_df = pd.DataFrame(columns=self.test_df.columns)
        empty_timestamp = datetime.now(timezone.utc)
        neutral_metrics = self.strategy.calculate_spread_metrics(empty_df, empty_timestamp)
        
        self.assertEqual(neutral_metrics.mexc_to_gateio_fut, 0)
        self.assertEqual(neutral_metrics.gateio_fut_to_mexc, 0)
        self.assertFalse(neutral_metrics.entry_signal)
        self.assertFalse(neutral_metrics.exit_signal)
    
    def test_daily_trade_limit(self):
        """Test daily trade limit functionality."""
        test_timestamp = datetime.now(timezone.utc)
        
        # Initially should allow trades
        self.assertTrue(self.strategy._check_daily_trade_limit(test_timestamp))
        
        # Simulate reaching daily limit
        for _ in range(self.strategy.max_daily_trades):
            self.strategy._increment_daily_trade_count(test_timestamp)
        
        # Should now block trades
        self.assertFalse(self.strategy._check_daily_trade_limit(test_timestamp))
        
        # Next day should reset
        next_day = test_timestamp + timedelta(days=1)
        self.assertTrue(self.strategy._check_daily_trade_limit(next_day))
    
    def test_arbitrage_trade_execution(self):
        """Test arbitrage trade execution logic."""
        timestamp = self.test_df.index[25]
        
        # Create favorable spread metrics for testing
        spread_metrics = SpreadMetrics(
            mexc_to_gateio_fut=-0.0008,
            gateio_fut_to_mexc=-0.0012,
            mexc_to_gateio_fut_percentile=85.0,  # High percentile = favorable
            gateio_fut_to_mexc_percentile=40.0,
            volatility=0.0002,
            favorable_direction='mexc_to_fut',
            entry_signal=True,
            exit_signal=False
        )
        
        position = self.strategy._execute_arbitrage_trade(
            timestamp, spread_metrics, self.test_df
        )
        
        self.assertIsNotNone(position)
        self.assertEqual(len(position.arbitrage_trades), 1)
        
        # Verify trades were created correctly
        trades = list(position.arbitrage_trades.values())[0]
        self.assertEqual(len(trades), 2)  # Should have both MEXC and Gate.io trades
        
        # Find buy and sell trades
        buy_trade = next(t for t in trades if t.side.value == 'BUY')
        sell_trade = next(t for t in trades if t.side.value == 'SELL')
        
        self.assertEqual(buy_trade.exchange, ExchangeEnum.MEXC_SPOT)
        self.assertEqual(sell_trade.exchange, ExchangeEnum.GATEIO_FUTURES)
        
        # Test daily limit enforcement
        # Fill up daily limit
        for _ in range(self.strategy.max_daily_trades):
            self.strategy._increment_daily_trade_count(timestamp)
        
        # Should not execute when limit reached
        position_blocked = self.strategy._execute_arbitrage_trade(
            timestamp, spread_metrics, self.test_df
        )
        self.assertIsNone(position_blocked)
    
    def test_backtest_execution(self):
        """Test comprehensive backtesting functionality."""
        # Run backtest
        performance = self.strategy.backtest(self.test_df)
        
        # Validate performance metrics
        self.assertIsInstance(performance, PerformanceMetrics)
        self.assertIsInstance(performance.total_pnl_usd, float)
        self.assertIsInstance(performance.total_pnl_pct, float)
        self.assertIsInstance(performance.win_rate, float)
        self.assertTrue(0 <= performance.win_rate <= 100)
        
        # Test with empty DataFrame
        empty_df = pd.DataFrame()
        empty_performance = self.strategy.backtest(empty_df)
        self.assertEqual(empty_performance.total_trades, 0)
        
        # Test with malformed data
        invalid_df = pd.DataFrame({
            'invalid_column': [1, 2, 3]
        })
        
        with self.assertRaises(ValueError):
            self.strategy.backtest(invalid_df)
    
    def test_signal_generation(self):
        """Test live signal generation functionality."""
        timestamp = self.test_df.index[30]
        
        # Add some history for realistic signal generation
        self.strategy._mexc_to_fut_history = np.random.normal(-0.001, 0.0005, 100)
        self.strategy._fut_to_mexc_history = np.random.normal(-0.001, 0.0005, 100)
        
        signal = self.strategy.get_current_signal(self.test_df, timestamp)
        
        # Validate signal structure
        required_keys = [
            'timestamp', 'entry_signal', 'exit_signal', 'favorable_direction',
            'mexc_to_fut_spread', 'fut_to_mexc_spread', 'mexc_to_fut_percentile',
            'fut_to_mexc_percentile', 'spread_volatility', 'daily_trades_remaining'
        ]
        
        for key in required_keys:
            self.assertIn(key, signal)
        
        self.assertEqual(signal['timestamp'], timestamp)
        self.assertIn(signal['favorable_direction'], ['mexc_to_fut', 'fut_to_mexc'])
        self.assertTrue(isinstance(signal['entry_signal'], bool))
        self.assertTrue(isinstance(signal['exit_signal'], bool))
        self.assertTrue(isinstance(signal['spread_volatility'], float))
    
    def test_fee_structure(self):
        """Test fee structure functionality."""
        # Test default fees
        default_fees = FeeStructure()
        self.assertEqual(default_fees.mexc_spot_maker_fee, 0.001)
        self.assertEqual(default_fees.gateio_futures_taker_fee, 0.0006)
        
        # Test custom fees
        custom_fees = FeeStructure(
            mexc_spot_maker_fee=0.0005,
            mexc_spot_taker_fee=0.0008,
            gateio_futures_maker_fee=0.0001,
            gateio_futures_taker_fee=0.0004,
            funding_rate_daily=0.0002,
            transfer_fee_usd=2.0
        )
        
        strategy = MexcGateioFuturesArbitrageSignal(fee_structure=custom_fees)
        self.assertEqual(strategy.fee_structure.mexc_spot_maker_fee, 0.0005)
        self.assertEqual(strategy.fee_structure.transfer_fee_usd, 2.0)
    
    def test_factory_function(self):
        """Test convenience factory function."""
        strategy = create_mexc_gateio_futures_strategy(
            entry_quantile=0.75,
            exit_quantile=0.30,
            position_size_usd=500.0,
            max_daily_trades=25
        )
        
        self.assertIsInstance(strategy, MexcGateioFuturesArbitrageSignal)
        self.assertEqual(strategy.entry_quantile, 0.75)
        self.assertEqual(strategy.exit_quantile, 0.30)
        self.assertEqual(strategy.position_size_usd, 500.0)
        self.assertEqual(strategy.max_daily_trades, 25)
    
    def test_volatility_adjustment(self):
        """Test volatility-based threshold adjustment."""
        # Test with volatility adjustment enabled
        strategy_adaptive = MexcGateioFuturesArbitrageSignal(
            volatility_adjustment=True,
            entry_quantile=0.80
        )
        
        # Test with volatility adjustment disabled
        strategy_fixed = MexcGateioFuturesArbitrageSignal(
            volatility_adjustment=False,
            entry_quantile=0.80
        )
        
        # Add artificial volatility to test adaptive behavior
        strategy_adaptive._mexc_to_fut_history = np.array([
            -0.001, -0.002, -0.0005, -0.003, -0.0008  # High volatility
        ])
        strategy_adaptive._fut_to_mexc_history = np.array([
            -0.0015, -0.0025, -0.0007, -0.0035, -0.0012
        ])
        
        strategy_fixed._mexc_to_fut_history = strategy_adaptive._mexc_to_fut_history.copy()
        strategy_fixed._fut_to_mexc_history = strategy_adaptive._fut_to_mexc_history.copy()
        
        timestamp = self.test_df.index[20]
        
        # Calculate metrics with both strategies
        metrics_adaptive = strategy_adaptive.calculate_spread_metrics(self.test_df, timestamp)
        metrics_fixed = strategy_fixed.calculate_spread_metrics(self.test_df, timestamp)
        
        # Volatility adjustment should affect signal generation in high volatility
        # (though the exact behavior depends on the current spread values)
        self.assertIsInstance(metrics_adaptive.volatility, float)
        self.assertIsInstance(metrics_fixed.volatility, float)


class TestPerformanceBenchmarks(unittest.TestCase):
    """Performance benchmarking tests for the strategy."""
    
    def test_large_dataset_performance(self):
        """Test strategy performance with large datasets."""
        # Create large dataset (24 hours at 5-minute intervals)
        timestamps = pd.date_range(
            start=datetime.now(timezone.utc) - timedelta(hours=24),
            end=datetime.now(timezone.utc),
            freq='5min'
        )
        
        # Generate 288 data points (24h * 12 intervals/hour)
        np.random.seed(123)
        base_price = 0.05000
        price_changes = np.cumsum(np.random.normal(0, 0.000005, len(timestamps)))
        
        # Use dynamic column keys for consistency
        large_df = pd.DataFrame({
            get_column_key(ExchangeEnum.MEXC, 'bid_price'): base_price + price_changes - 0.000005,
            get_column_key(ExchangeEnum.MEXC, 'ask_price'): base_price + price_changes + 0.000005,
            get_column_key(ExchangeEnum.GATEIO_FUTURES, 'bid_price'): base_price + price_changes - 0.000003 + np.random.normal(0, 0.000002, len(timestamps)),
            get_column_key(ExchangeEnum.GATEIO_FUTURES, 'ask_price'): base_price + price_changes + 0.000003 + np.random.normal(0, 0.000002, len(timestamps)),
        }, index=timestamps)
        
        # Ensure positive prices
        large_df = large_df.abs()
        
        strategy = MexcGateioFuturesArbitrageSignal(
            entry_quantile=0.75,
            exit_quantile=0.25,
            max_daily_trades=100  # Allow more trades for large dataset
        )
        
        # Measure execution time
        import time
        start_time = time.time()
        
        performance = strategy.backtest(large_df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Performance requirements (should complete in reasonable time)
        self.assertLess(execution_time, 5.0, "Backtest should complete within 5 seconds")
        self.assertIsInstance(performance, PerformanceMetrics)
        
        # Print performance summary for manual review
        print(f"\n--- Performance Benchmark Results ---")
        print(f"Dataset size: {len(large_df)} rows (24 hours)")
        print(f"Execution time: {execution_time:.3f} seconds")
        print(f"Total trades: {performance.total_trades}")
        print(f"Total P&L: ${performance.total_pnl_usd:.2f} ({performance.total_pnl_pct:.2f}%)")
        print(f"Win rate: {performance.win_rate:.1f}%")
        print(f"Sharpe ratio: {performance.sharpe_ratio:.2f}")
        print(f"Max drawdown: {performance.max_drawdown:.2f}%")


if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)