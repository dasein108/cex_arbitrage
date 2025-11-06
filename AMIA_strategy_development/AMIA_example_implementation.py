"""
AMIA (Aggregated Market Inefficiency Arbitrage) Strategy Implementation

This module provides a complete working implementation of the AMIA strategy,
integrating with the existing CEX arbitrage engine architecture.

Author: Claude Code
Version: 1.0
Date: October 2025
"""

import asyncio
import datetime
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging
from decimal import Decimal

# Import from existing codebase
from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data


class PositionStatus(Enum):
    """Position status enumeration"""
    OPEN = "open"
    CLOSED = "closed"
    FORCE_CLOSED = "force_closed"


@dataclass
class AMIAPosition:
    """AMIA position data structure"""
    position_id: str
    entry_time: pd.Timestamp
    spot_entry_price: float
    futures_entry_price: float
    position_size: float
    spot_exchange: str
    futures_exchange: str
    
    # Exit data
    exit_time: Optional[pd.Timestamp] = None
    spot_exit_price: Optional[float] = None
    futures_exit_price: Optional[float] = None
    status: PositionStatus = PositionStatus.OPEN
    
    # P&L tracking
    spot_pnl: Optional[float] = None
    futures_pnl: Optional[float] = None
    total_pnl: Optional[float] = None
    
    # Strategy metrics
    entry_opportunity_score: Optional[float] = None
    exit_opportunity_score: Optional[float] = None
    hold_duration_hours: Optional[float] = None


@dataclass
class AMIAConfig:
    """AMIA strategy configuration"""
    # Signal generation parameters
    entry_threshold: float = -0.001  # -0.1% aggregated opportunity
    exit_threshold: float = -0.0005  # -0.05% aggregated opportunity
    min_individual_deviation: float = -0.0002  # -0.02% minimum per leg
    
    # Risk management parameters
    max_hold_hours: float = 6.0
    max_positions: int = 1
    position_size_base: float = 1000.0  # Base position size in USD
    
    # Data quality parameters
    max_spread_pct: float = 0.05  # 5% maximum spread
    min_volume_threshold: float = 10000.0  # Minimum volume
    max_latency_seconds: float = 5.0  # Maximum data age
    
    # Performance parameters
    outlier_threshold: float = 3.0  # Z-score threshold for outliers
    signal_min_gap_seconds: float = 30.0  # Minimum time between signals_v2


class AMIADataProcessor:
    """AMIA data processing and validation"""
    
    def __init__(self, config: AMIAConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def validate_market_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate and clean market data
        
        Args:
            df: Raw market data DataFrame
            
        Returns:
            Cleaned DataFrame
        """
        if df.empty:
            return df
        
        original_length = len(df)
        
        # Basic price validation
        df = df[(df['bid_price'] > 0) & (df['ask_price'] > 0)]
        df = df[df['bid_price'] <= df['ask_price']]
        
        # Volume validation
        if 'bid_qty' in df.columns and 'ask_qty' in df.columns:
            df = df[(df['bid_qty'] > 0) & (df['ask_qty'] > 0)]
        
        # Calculate spreads
        df = self._calculate_spreads(df)
        
        # Filter wide spreads
        df = df[df['spread_pct'] <= self.config.max_spread_pct]
        
        # Remove statistical outliers
        df = self._remove_outliers(df)
        
        filtered_count = original_length - len(df)
        if filtered_count > 0:
            self.logger.info(f"Filtered {filtered_count} invalid data points")
        
        return df
    
    def _calculate_spreads(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate bid-ask spreads and mid prices"""
        df = df.copy()
        df['mid_price'] = (df['bid_price'] + df['ask_price']) / 2
        df['spread'] = df['ask_price'] - df['bid_price']
        df['spread_pct'] = df['spread'] / df['mid_price']
        return df
    
    def _remove_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove statistical outliers based on Z-score"""
        if len(df) < 10:  # Need minimum data for statistics
            return df
        
        # Calculate Z-scores for spread percentages
        spread_mean = df['spread_pct'].mean()
        spread_std = df['spread_pct'].std()
        
        if spread_std > 0:
            z_scores = np.abs((df['spread_pct'] - spread_mean) / spread_std)
            df = df[z_scores <= self.config.outlier_threshold]
        
        return df


class AMIASignalGenerator:
    """AMIA signal generation engine"""
    
    def __init__(self, config: AMIAConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.last_signal_time = None
    
    def calculate_deviations(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate mid-price deviations for AMIA scoring
        
        Args:
            df: Market data with mid_price, bid_price, ask_price
            
        Returns:
            DataFrame with deviation calculations
        """
        result = df.copy()
        
        # Calculate deviations from mid-price (normalized)
        result['bid_deviation'] = (result['bid_price'] - result['mid_price']) / result['mid_price']
        result['ask_deviation'] = (result['ask_price'] - result['mid_price']) / result['mid_price']
        
        # Clip to reasonable ranges (bid_deviation should be negative, ask_deviation positive)
        result['bid_deviation'] = np.clip(result['bid_deviation'], -0.1, 0)
        result['ask_deviation'] = np.clip(result['ask_deviation'], 0, 0.1)
        
        return result
    
    def calculate_opportunity_scores(self, spot_df: pd.DataFrame, 
                                   futures_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate aggregated opportunity scores for AMIA strategy
        
        Args:
            spot_df: Spot exchange data with deviations
            futures_df: Futures exchange data with deviations
            
        Returns:
            Merged DataFrame with opportunity scores
        """
        # Ensure both DataFrames have deviations calculated
        spot_with_dev = self.calculate_deviations(spot_df)
        futures_with_dev = self.calculate_deviations(futures_df)
        
        # Merge on timestamp with tolerance
        merged = pd.merge_asof(
            spot_with_dev.sort_values('timestamp'),
            futures_with_dev.sort_values('timestamp'),
            on='timestamp',
            suffixes=('_spot', '_futures'),
            tolerance=pd.Timedelta(seconds=self.config.max_latency_seconds)
        )
        
        if merged.empty:
            self.logger.warning("No synchronized data found between exchanges")
            return merged
        
        # Calculate AMIA opportunity scores
        # Entry: Buy spot (pay ask) + Sell futures (receive bid)
        merged['entry_opportunity'] = (
            merged['ask_deviation_spot'] + merged['bid_deviation_futures']
        )
        
        # Exit: Sell spot (receive bid) + Buy futures (pay ask)
        merged['exit_opportunity'] = (
            merged['bid_deviation_spot'] + merged['ask_deviation_futures']
        )
        
        return merged
    
    def generate_signals(self, df_with_opportunities: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Generate AMIA entry and exit signals_v2
        
        Args:
            df_with_opportunities: DataFrame with opportunity scores
            
        Returns:
            Tuple of (entry_signals, exit_signals)
        """
        if df_with_opportunities.empty:
            return pd.Series(dtype=bool), pd.Series(dtype=bool)
        
        df = df_with_opportunities
        
        # Entry signal conditions
        entry_conditions = [
            df['entry_opportunity'] < self.config.entry_threshold,
            df['ask_deviation_spot'] < self.config.min_individual_deviation,
            df['bid_deviation_futures'] < self.config.min_individual_deviation
        ]
        entry_signals = np.all(entry_conditions, axis=0)
        
        # Exit signal conditions
        exit_conditions = [
            df['exit_opportunity'] < self.config.exit_threshold,
            df['bid_deviation_spot'] < self.config.min_individual_deviation,
            df['ask_deviation_futures'] < self.config.min_individual_deviation
        ]
        exit_signals = np.all(exit_conditions, axis=0)
        
        # Apply timing filters to prevent signal oscillation
        entry_series = pd.Series(entry_signals, index=df.index)
        exit_series = pd.Series(exit_signals, index=df.index)
        
        entry_filtered, exit_filtered = self._apply_timing_filters(
            entry_series, exit_series, df
        )
        
        return entry_filtered, exit_filtered
    
    def _apply_timing_filters(self, entry_signals: pd.Series, exit_signals: pd.Series,
                            df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Apply timing filters to prevent rapid signal oscillation"""
        if 'timestamp' not in df.columns:
            return entry_signals, exit_signals
        
        min_gap = pd.Timedelta(seconds=self.config.signal_min_gap_seconds)
        filtered_entry = entry_signals.copy()
        filtered_exit = exit_signals.copy()
        
        last_signal_time = self.last_signal_time
        
        for idx, timestamp in enumerate(df['timestamp']):
            if last_signal_time and (timestamp - last_signal_time) < min_gap:
                filtered_entry.iloc[idx] = False
                filtered_exit.iloc[idx] = False
            elif filtered_entry.iloc[idx] or filtered_exit.iloc[idx]:
                last_signal_time = timestamp
                self.last_signal_time = timestamp
        
        return filtered_entry, filtered_exit


class AMIAPositionManager:
    """AMIA position management and tracking"""
    
    def __init__(self, config: AMIAConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.active_positions: List[AMIAPosition] = []
        self.closed_positions: List[AMIAPosition] = []
        self.position_counter = 0
    
    def can_open_position(self) -> bool:
        """Check if new position can be opened"""
        return len(self.active_positions) < self.config.max_positions
    
    def open_position(self, timestamp: pd.Timestamp, spot_data: Dict, 
                     futures_data: Dict, opportunity_score: float) -> Optional[AMIAPosition]:
        """
        Open new AMIA position
        
        Args:
            timestamp: Entry timestamp
            spot_data: Spot market data dict
            futures_data: Futures market data dict
            opportunity_score: Entry opportunity score
            
        Returns:
            Created position or None if failed
        """
        if not self.can_open_position():
            self.logger.warning("Cannot open position: maximum positions reached")
            return None
        
        self.position_counter += 1
        position_id = f"AMIA_{timestamp.strftime('%Y%m%d_%H%M%S')}_{self.position_counter}"
        
        position = AMIAPosition(
            position_id=position_id,
            entry_time=timestamp,
            spot_entry_price=spot_data['ask_price'],  # Buy spot at ask
            futures_entry_price=futures_data['bid_price'],  # Sell futures at bid
            position_size=self.config.position_size_base,
            spot_exchange=spot_data.get('exchange', 'SPOT'),
            futures_exchange=futures_data.get('exchange', 'FUTURES'),
            entry_opportunity_score=opportunity_score
        )
        
        self.active_positions.append(position)
        
        self.logger.info(f"Opened position {position_id}: "
                        f"Spot@{position.spot_entry_price:.6f}, "
                        f"Futures@{position.futures_entry_price:.6f}, "
                        f"Opportunity={opportunity_score:.6f}")
        
        return position
    
    def close_position(self, position: AMIAPosition, timestamp: pd.Timestamp,
                      spot_data: Dict, futures_data: Dict,
                      opportunity_score: float, force_close: bool = False) -> float:
        """
        Close existing position and calculate P&L
        
        Args:
            position: Position to close
            timestamp: Exit timestamp
            spot_data: Current spot market data
            futures_data: Current futures market data
            opportunity_score: Exit opportunity score
            force_close: Whether this is a forced close
            
        Returns:
            Total P&L
        """
        if position not in self.active_positions:
            self.logger.error(f"Position {position.position_id} not found in active positions")
            return 0.0
        
        # Calculate P&L for each leg
        spot_exit_price = spot_data['bid_price']  # Sell spot at bid
        futures_exit_price = futures_data['ask_price']  # Buy futures at ask
        
        # Spot leg P&L: bought at ask, selling at bid
        spot_pnl = (spot_exit_price - position.spot_entry_price) * position.position_size / position.spot_entry_price
        
        # Futures leg P&L: sold at bid, buying at ask
        futures_pnl = (position.futures_entry_price - futures_exit_price) * position.position_size / position.futures_entry_price
        
        total_pnl = spot_pnl + futures_pnl
        
        # Update position
        position.exit_time = timestamp
        position.spot_exit_price = spot_exit_price
        position.futures_exit_price = futures_exit_price
        position.spot_pnl = spot_pnl
        position.futures_pnl = futures_pnl
        position.total_pnl = total_pnl
        position.exit_opportunity_score = opportunity_score
        position.hold_duration_hours = (timestamp - position.entry_time).total_seconds() / 3600
        position.status = PositionStatus.FORCE_CLOSED if force_close else PositionStatus.CLOSED
        
        # Move to closed positions
        self.active_positions.remove(position)
        self.closed_positions.append(position)
        
        status_str = "FORCE CLOSED" if force_close else "CLOSED"
        self.logger.info(f"{status_str} position {position.position_id}: "
                        f"Spot P&L={spot_pnl:.4f}, Futures P&L={futures_pnl:.4f}, "
                        f"Total P&L={total_pnl:.4f}, Duration={position.hold_duration_hours:.2f}h")
        
        return total_pnl
    
    def check_force_close_positions(self, current_time: pd.Timestamp) -> List[AMIAPosition]:
        """Check for positions that need force closing due to max hold time"""
        positions_to_close = []
        for position in self.active_positions:
            hold_hours = (current_time - position.entry_time).total_seconds() / 3600
            if hold_hours >= self.config.max_hold_hours:
                positions_to_close.append(position)
        return positions_to_close
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary of closed positions"""
        if not self.closed_positions:
            return {'total_trades': 0}
        
        pnls = [pos.total_pnl for pos in self.closed_positions if pos.total_pnl is not None]
        winning_trades = [pnl for pnl in pnls if pnl > 0]
        losing_trades = [pnl for pnl in pnls if pnl <= 0]
        
        return {
            'total_trades': len(self.closed_positions),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'hit_rate': len(winning_trades) / len(pnls) if pnls else 0,
            'total_pnl': sum(pnls),
            'average_pnl': np.mean(pnls) if pnls else 0,
            'average_win': np.mean(winning_trades) if winning_trades else 0,
            'average_loss': np.mean(losing_trades) if losing_trades else 0,
            'profit_factor': abs(sum(winning_trades) / sum(losing_trades)) if losing_trades else float('inf'),
            'max_win': max(pnls) if pnls else 0,
            'max_loss': min(pnls) if pnls else 0
        }


class AMIAStrategy:
    """Main AMIA strategy implementation"""
    
    def __init__(self, config: Optional[AMIAConfig] = None):
        self.config = config or AMIAConfig()
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.data_processor = AMIADataProcessor(self.config)
        self.signal_generator = AMIASignalGenerator(self.config)
        self.position_manager = AMIAPositionManager(self.config)
        
        # Strategy state
        self.is_running = False
        self.performance_metrics = {}
    
    async def run_backtest(self, symbol: Symbol, start_date: datetime.datetime, 
                          end_date: datetime.datetime) -> Dict[str, Any]:
        """
        Run AMIA strategy backtest
        
        Args:
            symbol: Trading symbol
            start_date: Backtest start date
            end_date: Backtest end date
            
        Returns:
            Backtest results dictionary
        """
        self.logger.info(f"Starting AMIA backtest for {symbol.base}/{symbol.quote} "
                        f"from {start_date} to {end_date}")
        
        # Load market data
        market_data = await load_market_data(symbol, start_date, end_date)
        
        if market_data.empty:
            self.logger.error("No market data loaded")
            return {'error': 'No market data available'}
        
        # Process data
        processed_data = self.data_processor.validate_market_data(market_data)
        
        if processed_data.empty:
            self.logger.error("No valid data after processing")
            return {'error': 'No valid data after processing'}
        
        # Split into spot and futures data (assuming data contains both)
        # This is a simplified version - in practice you'd have separate data sources
        spot_data = processed_data.copy()
        futures_data = processed_data.copy()
        
        # Add some synthetic spread for demonstration
        np.random.seed(42)  # For reproducible results
        futures_data['bid_price'] *= (1 + np.random.normal(0, 0.0001, len(futures_data)))
        futures_data['ask_price'] *= (1 + np.random.normal(0, 0.0001, len(futures_data)))
        
        # Calculate opportunities and signals_v2
        opportunities_df = self.signal_generator.calculate_opportunity_scores(spot_data, futures_data)
        
        if opportunities_df.empty:
            self.logger.error("No opportunity data calculated")
            return {'error': 'No opportunity data calculated'}
        
        entry_signals, exit_signals = self.signal_generator.generate_signals(opportunities_df)
        
        # Run trading simulation
        trades = self._simulate_trading(opportunities_df, entry_signals, exit_signals)
        
        # Calculate performance metrics
        performance = self._calculate_performance_metrics(trades)
        
        self.logger.info(f"Backtest completed: {len(trades)} trades, "
                        f"Total P&L: {performance.get('total_pnl', 0):.4f}")
        
        return {
            'trades': trades,
            'performance': performance,
            'signals_summary': {
                'total_entry_signals': entry_signals.sum(),
                'total_exit_signals': exit_signals.sum(),
                'signal_rate': entry_signals.sum() / len(opportunities_df) if len(opportunities_df) > 0 else 0
            },
            'config': self.config.__dict__
        }
    
    def _simulate_trading(self, opportunities_df: pd.DataFrame, 
                         entry_signals: pd.Series, exit_signals: pd.Series) -> List[AMIAPosition]:
        """Simulate trading based on signals_v2"""
        trades = []
        
        # Combine signals_v2 with data
        signal_data = opportunities_df.copy()
        signal_data['entry_signal'] = entry_signals
        signal_data['exit_signal'] = exit_signals
        
        for idx, row in signal_data.iterrows():
            current_time = row['timestamp']
            
            # Check for force close conditions
            positions_to_force_close = self.position_manager.check_force_close_positions(current_time)
            for position in positions_to_force_close:
                spot_data = {
                    'bid_price': row['bid_price_spot'],
                    'ask_price': row['ask_price_spot'],
                    'exchange': 'SPOT'
                }
                futures_data = {
                    'bid_price': row['bid_price_futures'],
                    'ask_price': row['ask_price_futures'],
                    'exchange': 'FUTURES'
                }
                self.position_manager.close_position(
                    position, current_time, spot_data, futures_data,
                    row['exit_opportunity'], force_close=True
                )
            
            # Check for entry signals_v2
            if row['entry_signal'] and self.position_manager.can_open_position():
                spot_data = {
                    'bid_price': row['bid_price_spot'],
                    'ask_price': row['ask_price_spot'],
                    'exchange': 'SPOT'
                }
                futures_data = {
                    'bid_price': row['bid_price_futures'],
                    'ask_price': row['ask_price_futures'],
                    'exchange': 'FUTURES'
                }
                position = self.position_manager.open_position(
                    current_time, spot_data, futures_data, row['entry_opportunity']
                )
                if position:
                    trades.append(position)
            
            # Check for exit signals_v2
            elif row['exit_signal'] and self.position_manager.active_positions:
                for position in list(self.position_manager.active_positions):
                    spot_data = {
                        'bid_price': row['bid_price_spot'],
                        'ask_price': row['ask_price_spot'],
                        'exchange': 'SPOT'
                    }
                    futures_data = {
                        'bid_price': row['bid_price_futures'],
                        'ask_price': row['ask_price_futures'],
                        'exchange': 'FUTURES'
                    }
                    self.position_manager.close_position(
                        position, current_time, spot_data, futures_data,
                        row['exit_opportunity']
                    )
        
        return self.position_manager.closed_positions
    
    def _calculate_performance_metrics(self, trades: List[AMIAPosition]) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        if not trades:
            return {'total_trades': 0, 'total_pnl': 0}
        
        # Basic metrics
        pnls = [trade.total_pnl for trade in trades if trade.total_pnl is not None]
        durations = [trade.hold_duration_hours for trade in trades if trade.hold_duration_hours is not None]
        
        if not pnls:
            return {'total_trades': len(trades), 'total_pnl': 0}
        
        winning_trades = [pnl for pnl in pnls if pnl > 0]
        losing_trades = [pnl for pnl in pnls if pnl <= 0]
        
        # Calculate returns assuming starting capital
        starting_capital = self.config.position_size_base
        returns = [pnl / starting_capital for pnl in pnls]
        cumulative_returns = np.cumprod(np.array(returns) + 1)
        
        # Risk metrics
        if len(returns) > 1:
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
            max_drawdown = self._calculate_max_drawdown(cumulative_returns)
        else:
            sharpe_ratio = 0
            max_drawdown = 0
        
        return {
            'total_trades': len(trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'hit_rate': len(winning_trades) / len(pnls),
            'total_pnl': sum(pnls),
            'average_pnl': np.mean(pnls),
            'average_win': np.mean(winning_trades) if winning_trades else 0,
            'average_loss': np.mean(losing_trades) if losing_trades else 0,
            'profit_factor': abs(sum(winning_trades) / sum(losing_trades)) if losing_trades else float('inf'),
            'max_win': max(pnls),
            'max_loss': min(pnls),
            'average_duration_hours': np.mean(durations) if durations else 0,
            'total_return': cumulative_returns[-1] - 1 if len(cumulative_returns) > 0 else 0,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'calmar_ratio': (cumulative_returns[-1] - 1) / abs(max_drawdown) if max_drawdown != 0 else 0
        }
    
    def _calculate_max_drawdown(self, cumulative_returns: np.array) -> float:
        """Calculate maximum drawdown"""
        peak = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - peak) / peak
        return np.min(drawdown)


# Example usage and testing functions
async def run_amia_example():
    """Run AMIA strategy example"""
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Create strategy configuration
    config = AMIAConfig(
        entry_threshold=-0.001,
        exit_threshold=-0.0005,
        min_individual_deviation=-0.0002,
        max_hold_hours=6.0,
        position_size_base=1000.0
    )
    
    # Initialize strategy
    strategy = AMIAStrategy(config)
    
    # Define test parameters
    symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    end_date = datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(hours=24)  # 24 hours of data
    
    try:
        # Run backtest
        results = await strategy.run_backtest(symbol, start_date, end_date)
        
        # Print results
        print("=" * 80)
        print("AMIA STRATEGY BACKTEST RESULTS")
        print("=" * 80)
        
        if 'error' in results:
            print(f"Error: {results['error']}")
            return
        
        performance = results['performance']
        print(f"Total Trades: {performance['total_trades']}")
        print(f"Winning Trades: {performance['winning_trades']}")
        print(f"Hit Rate: {performance['hit_rate']:.2%}")
        print(f"Total P&L: {performance['total_pnl']:.4f}")
        print(f"Average P&L per Trade: {performance['average_pnl']:.4f}")
        print(f"Profit Factor: {performance['profit_factor']:.2f}")
        print(f"Sharpe Ratio: {performance['sharpe_ratio']:.2f}")
        print(f"Maximum Drawdown: {performance['max_drawdown']:.2%}")
        print(f"Average Duration: {performance['average_duration_hours']:.2f} hours")
        
        # Print individual trades
        trades = results['trades']
        if trades:
            print("\n" + "=" * 80)
            print("TRADE DETAILS")
            print("=" * 80)
            print(f"{'Trade':<8} {'Entry Time':<20} {'Duration':<10} {'Spot P&L':<10} {'Fut P&L':<10} {'Total P&L':<10}")
            print("-" * 80)
            
            for i, trade in enumerate(trades[:10], 1):  # Show first 10 trades
                entry_time = trade.entry_time.strftime('%Y-%m-%d %H:%M:%S')
                duration = f"{trade.hold_duration_hours:.2f}h" if trade.hold_duration_hours else "N/A"
                spot_pnl = f"{trade.spot_pnl:.4f}" if trade.spot_pnl else "N/A"
                fut_pnl = f"{trade.futures_pnl:.4f}" if trade.futures_pnl else "N/A"
                total_pnl = f"{trade.total_pnl:.4f}" if trade.total_pnl else "N/A"
                
                print(f"{i:<8} {entry_time:<20} {duration:<10} {spot_pnl:<10} {fut_pnl:<10} {total_pnl:<10}")
        
        print("\n" + "=" * 80)
        print("CONFIGURATION USED")
        print("=" * 80)
        for key, value in config.__dict__.items():
            print(f"{key}: {value}")
        
    except Exception as e:
        logger.error(f"Error running AMIA example: {e}")
        raise


def create_sample_config() -> AMIAConfig:
    """Create sample AMIA configuration for testing"""
    return AMIAConfig(
        # Aggressive parameters for testing
        entry_threshold=-0.0008,
        exit_threshold=-0.0004,
        min_individual_deviation=-0.0001,
        max_hold_hours=4.0,
        max_positions=2,
        position_size_base=500.0,
        
        # Quality filters
        max_spread_pct=0.03,
        min_volume_threshold=5000.0,
        max_latency_seconds=3.0,
        outlier_threshold=2.5,
        signal_min_gap_seconds=15.0
    )


if __name__ == "__main__":
    # Run the example
    asyncio.run(run_amia_example())