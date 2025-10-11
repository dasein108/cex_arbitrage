"""
Optimal Threshold Calculator for Spot-Futures Arbitrage

This module provides utilities to calculate optimal entry and exit thresholds for 
spot-futures arbitrage trading using historical order book data. It performs grid 
search optimization to maximize profit after accounting for all trading fees.

Key Concepts:
- FTS (Futures-to-Spot): Buy futures, sell spot (when futures are underpriced)
- STF (Spot-to-Futures): Buy spot, sell futures (when spot is underpriced)

The optimizer finds thresholds that maximize total profit after all fees and costs.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ThresholdResult:
    """
    Result of optimal threshold calculation for spot-futures arbitrage.
    
    Threshold Variables Explained:
    
    optimal_fts_entry: float
        Entry threshold for Futures-to-Spot arbitrage (in percentage)
        - When |futures_to_spot_spread| >= this threshold AND spread is negative
        - Action: BUY futures (at ask), SELL spot (at bid)
        - Example: 0.08 means enter when spread is <= -0.08%
        
    optimal_stf_entry: float  
        Entry threshold for Spot-to-Futures arbitrage (in percentage)
        - When spot_to_futures_spread >= this threshold AND spread is positive
        - Action: BUY spot (at ask), SELL futures (at bid) 
        - Example: 0.02 means enter when spread is >= +0.02%
        
    optimal_fts_exit: float
        Exit threshold for Futures-to-Spot positions (in percentage)
        - Close FTS position when |futures_to_spot_spread| < this threshold
        - Action: SELL futures (at bid), BUY spot (at ask)
        - Example: 0.05 means exit when spread compresses to > -0.05%
        
    optimal_stf_exit: float
        Exit threshold for Spot-to-Futures positions (in percentage)  
        - Close STF position when spot_to_futures_spread <= this threshold
        - Action: SELL spot (at bid), BUY futures (at ask)
        - Example: 0.00 means exit at break-even or when spread turns negative
    
    Trading Flow Example:
    1. FTS Entry: Futures@100, Spot@101 → spread = -0.99% → if >= 0.08%, BUY futures, SELL spot
    2. FTS Exit: Futures@100.5, Spot@100.4 → spread = -0.10% → if < 0.05%, close position
    """
    # Optimal thresholds (in percentage points)
    optimal_fts_entry: float
    optimal_stf_entry: float  
    optimal_fts_exit: float
    optimal_stf_exit: float
    
    # Performance metrics
    expected_profit: float          # Total expected profit after all fees
    trade_count: int               # Number of trades executed with optimal thresholds
    win_rate: float               # Percentage of profitable trades
    avg_holding_time_hours: float # Average time positions are held
    
    # Risk metrics
    max_drawdown: float           # Maximum portfolio drawdown
    profit_factor: float          # Gross profit / Gross loss
    sharpe_ratio: float          # Risk-adjusted return
    
    # Detailed analysis
    fts_trades: int              # Count of FTS trades
    stf_trades: int              # Count of STF trades
    total_fees_paid: float       # Total fees across all trades
    optimization_details: Dict   # Full grid search results for analysis
    
    # Market statistics
    market_statistics: Dict      # Bid/ask statistics for each exchange


@dataclass
class FeeConfiguration:
    """
    Trading fee configuration for spot and futures markets using maker/taker structure.
    
    All fees are in percentage (e.g., 0.1 = 0.1% = 10 basis points).
    
    Maker fees: For limit orders that add liquidity to the order book
    Taker fees: For market orders that remove liquidity from the order book
    """
    # Spot market fees
    spot_maker_fee: float   # Fee for spot limit orders (adding liquidity)
    spot_taker_fee: float   # Fee for spot market orders (removing liquidity)
    
    # Futures market fees
    futures_maker_fee: float   # Fee for futures limit orders (adding liquidity)
    futures_taker_fee: float   # Fee for futures market orders (removing liquidity)
    
    # Optional additional costs
    slippage_factor: float = 0.02  # Market impact/slippage per trade (default 0.02%)
    
    @classmethod
    def create_uniform(cls, maker_fee: float, taker_fee: float = None, slippage: float = 0.02) -> 'FeeConfiguration':
        """
        Create uniform fee configuration.
        
        Args:
            maker_fee: Fee rate for limit orders (adding liquidity)
            taker_fee: Fee rate for market orders (removing liquidity). If None, uses maker_fee
            slippage: Slippage factor for all trades
        """
        if taker_fee is None:
            taker_fee = maker_fee
            
        return cls(
            spot_maker_fee=maker_fee,
            spot_taker_fee=taker_fee,
            futures_maker_fee=maker_fee,
            futures_taker_fee=taker_fee,
            slippage_factor=slippage
        )
    
    @classmethod
    def create_realistic(cls, slippage: float = 0.02) -> 'FeeConfiguration':
        """
        Create realistic fee configuration based on actual exchange rates.
        
        MEXC Spot: 0% maker, 0.05% taker
        Gate.io Futures: 0.02% maker, 0.05% taker
        """
        return cls(
            spot_maker_fee=0.0,     # MEXC spot maker
            spot_taker_fee=0.05,    # MEXC spot taker
            futures_maker_fee=0.02, # Gate.io futures maker
            futures_taker_fee=0.05, # Gate.io futures taker
            slippage_factor=slippage
        )


def align_market_data(
    spot_df: pd.DataFrame, 
    futures_df: pd.DataFrame,
    tolerance_seconds: int = 1
) -> pd.DataFrame:
    """
    Align spot and futures data by timestamp with tolerance.
    
    Args:
        spot_df: Spot market orderbook data
        futures_df: Futures market orderbook data  
        tolerance_seconds: Timestamp alignment tolerance
        
    Returns:
        Aligned DataFrame with both spot and futures data
        
    Expected DataFrame columns:
        - timestamp, bid_price, ask_price, bid_qty, ask_qty
        OR timestamp as index with bid_price, ask_price, bid_qty, ask_qty columns
    """
    if spot_df.empty or futures_df.empty:
        return pd.DataFrame()
    
    # Ensure timestamp is datetime
    spot_df = spot_df.copy()
    futures_df = futures_df.copy()
    
    # Handle timestamp as column or index
    if 'timestamp' not in spot_df.columns:
        if spot_df.index.name == 'timestamp' or isinstance(spot_df.index, pd.DatetimeIndex):
            spot_df = spot_df.reset_index()
            if spot_df.columns[0] != 'timestamp':
                spot_df = spot_df.rename(columns={spot_df.columns[0]: 'timestamp'})
        else:
            raise ValueError("Spot DataFrame must have 'timestamp' column or datetime index")
    
    if 'timestamp' not in futures_df.columns:
        if futures_df.index.name == 'timestamp' or isinstance(futures_df.index, pd.DatetimeIndex):
            futures_df = futures_df.reset_index()
            if futures_df.columns[0] != 'timestamp':
                futures_df = futures_df.rename(columns={futures_df.columns[0]: 'timestamp'})
        else:
            raise ValueError("Futures DataFrame must have 'timestamp' column or datetime index")
    
    # Round timestamps to nearest second for alignment
    spot_df['time_bucket'] = pd.to_datetime(spot_df['timestamp']).dt.floor(f'{tolerance_seconds}s')
    futures_df['time_bucket'] = pd.to_datetime(futures_df['timestamp']).dt.floor(f'{tolerance_seconds}s')
    
    # Take latest data within each time bucket
    spot_latest = spot_df.groupby('time_bucket').last().reset_index()
    futures_latest = futures_df.groupby('time_bucket').last().reset_index()
    
    # Merge on time bucket
    merged = pd.merge(
        spot_latest,
        futures_latest,
        on='time_bucket',
        how='inner',
        suffixes=('_spot', '_futures')
    )
    
    if merged.empty:
        return pd.DataFrame()
    
    # Rename columns for clarity
    merged = merged.rename(columns={
        'time_bucket': 'timestamp',
        'bid_price_spot': 'spot_bid',
        'ask_price_spot': 'spot_ask', 
        'bid_qty_spot': 'spot_bid_qty',
        'ask_qty_spot': 'spot_ask_qty',
        'bid_price_futures': 'fut_bid',
        'ask_price_futures': 'fut_ask',
        'bid_qty_futures': 'fut_bid_qty', 
        'ask_qty_futures': 'fut_ask_qty'
    })
    
    # Calculate spreads
    merged['spot_to_futures_spread_pct'] = ((merged['fut_bid'] - merged['spot_ask']) / merged['spot_ask']) * 100.0
    merged['futures_to_spot_spread_pct'] = ((merged['spot_bid'] - merged['fut_ask']) / merged['fut_ask']) * 100.0
    
    # Calculate liquidity
    merged['spot_liquidity'] = merged['spot_bid_qty'] * merged['spot_bid'] + merged['spot_ask_qty'] * merged['spot_ask']
    merged['fut_liquidity'] = merged['fut_bid_qty'] * merged['fut_bid'] + merged['fut_ask_qty'] * merged['fut_ask']
    
    return merged.set_index('timestamp').sort_index()


def calculate_market_statistics(
    spot_df: pd.DataFrame,
    futures_df: pd.DataFrame,
    aligned_df: pd.DataFrame
) -> Dict:
    """
    Calculate comprehensive market statistics for bid/ask prices.
    
    Args:
        spot_df: Original spot market data
        futures_df: Original futures market data
        aligned_df: Aligned market data
        
    Returns:
        Dictionary with detailed market statistics for each exchange
    """
    statistics = {
        'spot_exchange': {},
        'futures_exchange': {},
        'aligned_data': {},
        'spread_statistics': {}
    }
    
    # Spot exchange statistics
    if not spot_df.empty:
        spot_stats = {}
        
        # Handle timestamp as column or index for spot data
        spot_data = spot_df.copy()
        if 'timestamp' not in spot_data.columns:
            if spot_data.index.name == 'timestamp' or isinstance(spot_data.index, pd.DatetimeIndex):
                spot_data = spot_data.reset_index()
        
        # Calculate bid price statistics
        if 'bid_price' in spot_data.columns:
            spot_stats['bid_price'] = {
                'mean': float(spot_data['bid_price'].mean()),
                'median': float(spot_data['bid_price'].median()),
                'min': float(spot_data['bid_price'].min()),
                'max': float(spot_data['bid_price'].max()),
                'std': float(spot_data['bid_price'].std()),
                'count': int(len(spot_data['bid_price'].dropna()))
            }
        
        # Calculate ask price statistics
        if 'ask_price' in spot_data.columns:
            spot_stats['ask_price'] = {
                'mean': float(spot_data['ask_price'].mean()),
                'median': float(spot_data['ask_price'].median()),
                'min': float(spot_data['ask_price'].min()),
                'max': float(spot_data['ask_price'].max()),
                'std': float(spot_data['ask_price'].std()),
                'count': int(len(spot_data['ask_price'].dropna()))
            }
        
        # Calculate mid price and spread statistics
        if 'bid_price' in spot_data.columns and 'ask_price' in spot_data.columns:
            spot_mid = (spot_data['bid_price'] + spot_data['ask_price']) / 2
            spot_spread = spot_data['ask_price'] - spot_data['bid_price']
            spot_spread_pct = (spot_spread / spot_mid) * 100
            
            spot_stats['mid_price'] = {
                'mean': float(spot_mid.mean()),
                'median': float(spot_mid.median()),
                'min': float(spot_mid.min()),
                'max': float(spot_mid.max()),
                'std': float(spot_mid.std())
            }
            
            spot_stats['bid_ask_spread'] = {
                'mean_absolute': float(spot_spread.mean()),
                'mean_percentage': float(spot_spread_pct.mean()),
                'median_percentage': float(spot_spread_pct.median()),
                'min_percentage': float(spot_spread_pct.min()),
                'max_percentage': float(spot_spread_pct.max())
            }
        
        # Calculate quantity statistics
        if 'bid_qty' in spot_data.columns and 'ask_qty' in spot_data.columns:
            spot_stats['liquidity'] = {
                'avg_bid_qty': float(spot_data['bid_qty'].mean()),
                'avg_ask_qty': float(spot_data['ask_qty'].mean()),
                'total_bid_qty': float(spot_data['bid_qty'].sum()),
                'total_ask_qty': float(spot_data['ask_qty'].sum())
            }
        
        statistics['spot_exchange'] = spot_stats
    
    # Futures exchange statistics
    if not futures_df.empty:
        futures_stats = {}
        
        # Handle timestamp as column or index for futures data
        futures_data = futures_df.copy()
        if 'timestamp' not in futures_data.columns:
            if futures_data.index.name == 'timestamp' or isinstance(futures_data.index, pd.DatetimeIndex):
                futures_data = futures_data.reset_index()
        
        # Calculate bid price statistics
        if 'bid_price' in futures_data.columns:
            futures_stats['bid_price'] = {
                'mean': float(futures_data['bid_price'].mean()),
                'median': float(futures_data['bid_price'].median()),
                'min': float(futures_data['bid_price'].min()),
                'max': float(futures_data['bid_price'].max()),
                'std': float(futures_data['bid_price'].std()),
                'count': int(len(futures_data['bid_price'].dropna()))
            }
        
        # Calculate ask price statistics
        if 'ask_price' in futures_data.columns:
            futures_stats['ask_price'] = {
                'mean': float(futures_data['ask_price'].mean()),
                'median': float(futures_data['ask_price'].median()),
                'min': float(futures_data['ask_price'].min()),
                'max': float(futures_data['ask_price'].max()),
                'std': float(futures_data['ask_price'].std()),
                'count': int(len(futures_data['ask_price'].dropna()))
            }
        
        # Calculate mid price and spread statistics
        if 'bid_price' in futures_data.columns and 'ask_price' in futures_data.columns:
            futures_mid = (futures_data['bid_price'] + futures_data['ask_price']) / 2
            futures_spread = futures_data['ask_price'] - futures_data['bid_price']
            futures_spread_pct = (futures_spread / futures_mid) * 100
            
            futures_stats['mid_price'] = {
                'mean': float(futures_mid.mean()),
                'median': float(futures_mid.median()),
                'min': float(futures_mid.min()),
                'max': float(futures_mid.max()),
                'std': float(futures_mid.std())
            }
            
            futures_stats['bid_ask_spread'] = {
                'mean_absolute': float(futures_spread.mean()),
                'mean_percentage': float(futures_spread_pct.mean()),
                'median_percentage': float(futures_spread_pct.median()),
                'min_percentage': float(futures_spread_pct.min()),
                'max_percentage': float(futures_spread_pct.max())
            }
        
        # Calculate quantity statistics
        if 'bid_qty' in futures_data.columns and 'ask_qty' in futures_data.columns:
            futures_stats['liquidity'] = {
                'avg_bid_qty': float(futures_data['bid_qty'].mean()),
                'avg_ask_qty': float(futures_data['ask_qty'].mean()),
                'total_bid_qty': float(futures_data['bid_qty'].sum()),
                'total_ask_qty': float(futures_data['ask_qty'].sum())
            }
        
        statistics['futures_exchange'] = futures_stats
    
    # Aligned data statistics (arbitrage spreads)
    if not aligned_df.empty:
        aligned_stats = {}
        
        # Cross-exchange spread statistics
        if 'spot_to_futures_spread_pct' in aligned_df.columns:
            stf_spreads = aligned_df['spot_to_futures_spread_pct']
            aligned_stats['spot_to_futures_spread'] = {
                'mean': float(stf_spreads.mean()),
                'median': float(stf_spreads.median()),
                'min': float(stf_spreads.min()),
                'max': float(stf_spreads.max()),
                'std': float(stf_spreads.std()),
                'positive_count': int((stf_spreads > 0).sum()),
                'negative_count': int((stf_spreads < 0).sum()),
                'positive_percentage': float((stf_spreads > 0).mean() * 100)
            }
        
        if 'futures_to_spot_spread_pct' in aligned_df.columns:
            fts_spreads = aligned_df['futures_to_spot_spread_pct']
            aligned_stats['futures_to_spot_spread'] = {
                'mean': float(fts_spreads.mean()),
                'median': float(fts_spreads.median()),
                'min': float(fts_spreads.min()),
                'max': float(fts_spreads.max()),
                'std': float(fts_spreads.std()),
                'positive_count': int((fts_spreads > 0).sum()),
                'negative_count': int((fts_spreads < 0).sum()),
                'negative_percentage': float((fts_spreads < 0).mean() * 100)
            }
        
        # Price correlation statistics
        if all(col in aligned_df.columns for col in ['spot_bid', 'spot_ask', 'fut_bid', 'fut_ask']):
            spot_mid_aligned = (aligned_df['spot_bid'] + aligned_df['spot_ask']) / 2
            fut_mid_aligned = (aligned_df['fut_bid'] + aligned_df['fut_ask']) / 2
            
            aligned_stats['price_correlation'] = {
                'spot_futures_correlation': float(spot_mid_aligned.corr(fut_mid_aligned)),
                'spot_mid_mean': float(spot_mid_aligned.mean()),
                'futures_mid_mean': float(fut_mid_aligned.mean()),
                'price_difference_mean': float((spot_mid_aligned - fut_mid_aligned).mean()),
                'price_difference_std': float((spot_mid_aligned - fut_mid_aligned).std())
            }
        
        # Liquidity statistics
        if all(col in aligned_df.columns for col in ['spot_liquidity', 'fut_liquidity']):
            aligned_stats['liquidity_comparison'] = {
                'spot_avg_liquidity': float(aligned_df['spot_liquidity'].mean()),
                'futures_avg_liquidity': float(aligned_df['fut_liquidity'].mean()),
                'min_liquidity_mean': float(aligned_df[['spot_liquidity', 'fut_liquidity']].min(axis=1).mean()),
                'liquidity_ratio_mean': float((aligned_df['spot_liquidity'] / aligned_df['fut_liquidity']).mean())
            }
        
        # Data quality statistics
        aligned_stats['data_quality'] = {
            'total_aligned_points': int(len(aligned_df)),
            'timestamp_range_hours': float((aligned_df.index.max() - aligned_df.index.min()).total_seconds() / 3600),
            'avg_time_gap_seconds': float(aligned_df.index.to_series().diff().dt.total_seconds().mean())
        }
        
        statistics['aligned_data'] = aligned_stats
    
    return statistics


def simulate_arbitrage_trades(
    df: pd.DataFrame,
    fts_entry_threshold: float,
    stf_entry_threshold: float, 
    fts_exit_threshold: float,
    stf_exit_threshold: float,
    fees: FeeConfiguration,
    max_positions: int = 5,
    min_liquidity: float = 1000.0
) -> Dict:
    """
    Simulate arbitrage trading with given thresholds.
    
    Args:
        df: Aligned market data with spreads calculated
        fts_entry_threshold: Entry threshold for futures-to-spot trades (%)
        stf_entry_threshold: Entry threshold for spot-to-futures trades (%)
        fts_exit_threshold: Exit threshold for futures-to-spot trades (%)
        stf_exit_threshold: Exit threshold for spot-to-futures trades (%)
        fees: Fee configuration
        max_positions: Maximum concurrent positions
        min_liquidity: Minimum liquidity required for trade (USD)
        
    Returns:
        Dictionary with simulation results
    """
    if df.empty:
        return _empty_simulation_result()
    
    active_positions = []
    closed_trades = []
    portfolio_value = 100000.0  # Starting portfolio value
    
    for timestamp, row in df.iterrows():
        # Check data quality
        if not _is_valid_market_data(row):
            continue
            
        # Check liquidity
        min_liquidity_available = min(row['spot_liquidity'], row['fut_liquidity'])
        if min_liquidity_available < min_liquidity:
            continue
        
        # Update existing positions and check exits
        positions_to_close = []
        for i, pos in enumerate(active_positions):
            if _should_close_position(pos, row, fts_exit_threshold, stf_exit_threshold):
                positions_to_close.append(i)
        
        # Close positions (reverse order to maintain indices)
        for i in reversed(positions_to_close):
            closed_trade = _close_position(active_positions[i], row, fees, timestamp)
            closed_trades.append(closed_trade)
            del active_positions[i]
        
        # Check for new entry signals
        if len(active_positions) < max_positions:
            # Check FTS entry (futures-to-spot)
            if (abs(row['futures_to_spot_spread_pct']) >= fts_entry_threshold and 
                row['futures_to_spot_spread_pct'] < 0):
                
                position = _enter_fts_position(row, fees, timestamp)
                if position:
                    active_positions.append(position)
            
            # Check STF entry (spot-to-futures) 
            elif (row['spot_to_futures_spread_pct'] >= stf_entry_threshold and
                  row['spot_to_futures_spread_pct'] > 0):
                
                position = _enter_stf_position(row, fees, timestamp)
                if position:
                    active_positions.append(position)
    
    # Close any remaining positions at final price
    if active_positions and not df.empty:
        final_row = df.iloc[-1]
        final_timestamp = df.index[-1]
        for pos in active_positions:
            closed_trade = _close_position(pos, final_row, fees, final_timestamp)
            closed_trades.append(closed_trade)
    
    return _calculate_simulation_metrics(closed_trades)


def _is_valid_market_data(row: pd.Series) -> bool:
    """Validate market data quality."""
    required_fields = ['spot_bid', 'spot_ask', 'fut_bid', 'fut_ask']
    
    # Check all fields exist and are positive
    for field in required_fields:
        if field not in row or row[field] <= 0 or pd.isna(row[field]):
            return False
    
    # Check bid < ask ordering
    if row['spot_bid'] >= row['spot_ask'] or row['fut_bid'] >= row['fut_ask']:
        return False
        
    return True


def _should_close_position(position: Dict, row: pd.Series, fts_exit: float, stf_exit: float) -> bool:
    """Check if position should be closed based on exit thresholds."""
    if position['type'] == 'fts':
        # Close FTS when spread compresses above exit threshold
        current_spread = abs(row['futures_to_spot_spread_pct'])
        return current_spread < fts_exit
    else:  # stf
        # Close STF when spread falls to exit threshold or below
        current_spread = row['spot_to_futures_spread_pct']
        return current_spread <= stf_exit


def _enter_fts_position(row: pd.Series, fees: FeeConfiguration, timestamp) -> Optional[Dict]:
    """Enter futures-to-spot position: buy futures, sell spot."""
    position_size = 1000.0  # Fixed position size for simulation
    
    # Calculate entry prices with slippage
    futures_entry_price = row['fut_ask'] * (1 + fees.slippage_factor / 100)  # Buy futures at ask + slippage
    spot_entry_price = row['spot_bid'] * (1 - fees.slippage_factor / 100)   # Sell spot at bid - slippage
    
    # Calculate fees for entry (use taker fees for market orders in arbitrage)
    futures_entry_fee = position_size * fees.futures_taker_fee / 100  # Buy futures (taker)
    spot_entry_fee = position_size * fees.spot_taker_fee / 100        # Sell spot (taker)
    
    return {
        'type': 'fts',
        'entry_time': timestamp,
        'position_size': position_size,
        'futures_entry_price': futures_entry_price,
        'spot_entry_price': spot_entry_price, 
        'entry_fees': futures_entry_fee + spot_entry_fee,
        'entry_spread_pct': row['futures_to_spot_spread_pct']
    }


def _enter_stf_position(row: pd.Series, fees: FeeConfiguration, timestamp) -> Optional[Dict]:
    """Enter spot-to-futures position: buy spot, sell futures."""
    position_size = 1000.0  # Fixed position size for simulation
    
    # Calculate entry prices with slippage  
    spot_entry_price = row['spot_ask'] * (1 + fees.slippage_factor / 100)     # Buy spot at ask + slippage
    futures_entry_price = row['fut_bid'] * (1 - fees.slippage_factor / 100)  # Sell futures at bid - slippage
    
    # Calculate fees for entry (use taker fees for market orders in arbitrage)
    spot_entry_fee = position_size * fees.spot_taker_fee / 100     # Buy spot (taker)
    futures_entry_fee = position_size * fees.futures_taker_fee / 100  # Sell futures (taker)
    
    return {
        'type': 'stf', 
        'entry_time': timestamp,
        'position_size': position_size,
        'spot_entry_price': spot_entry_price,
        'futures_entry_price': futures_entry_price,
        'entry_fees': spot_entry_fee + futures_entry_fee,
        'entry_spread_pct': row['spot_to_futures_spread_pct']
    }


def _close_position(position: Dict, row: pd.Series, fees: FeeConfiguration, timestamp) -> Dict:
    """Close position and calculate P&L."""
    position_size = position['position_size']
    
    if position['type'] == 'fts':
        # Close FTS: sell futures, buy spot
        futures_exit_price = row['fut_bid'] * (1 - fees.slippage_factor / 100)  # Sell futures at bid - slippage
        spot_exit_price = row['spot_ask'] * (1 + fees.slippage_factor / 100)    # Buy spot at ask + slippage
        
        # Calculate P&L
        futures_pnl = (futures_exit_price - position['futures_entry_price']) * position_size / position['futures_entry_price']
        spot_pnl = (position['spot_entry_price'] - spot_exit_price) * position_size / position['spot_entry_price']
        
        # Calculate exit fees (use taker fees for market orders)
        exit_fees = position_size * (fees.futures_taker_fee + fees.spot_taker_fee) / 100
        
    else:  # stf
        # Close STF: sell spot, buy futures
        spot_exit_price = row['spot_bid'] * (1 - fees.slippage_factor / 100)    # Sell spot at bid - slippage  
        futures_exit_price = row['fut_ask'] * (1 + fees.slippage_factor / 100)  # Buy futures at ask + slippage
        
        # Calculate P&L
        spot_pnl = (spot_exit_price - position['spot_entry_price']) * position_size / position['spot_entry_price']
        futures_pnl = (position['futures_entry_price'] - futures_exit_price) * position_size / position['futures_entry_price']
        
        # Calculate exit fees (use taker fees for market orders)
        exit_fees = position_size * (fees.spot_taker_fee + fees.futures_taker_fee) / 100
    
    gross_pnl = futures_pnl + spot_pnl
    total_fees = position['entry_fees'] + exit_fees
    net_pnl = gross_pnl - total_fees
    
    # Calculate holding time
    holding_time = (timestamp - position['entry_time']).total_seconds() / 3600  # hours
    
    return {
        'type': position['type'],
        'entry_time': position['entry_time'],
        'exit_time': timestamp,
        'holding_time_hours': holding_time,
        'position_size': position_size,
        'entry_spread_pct': position['entry_spread_pct'],
        'gross_pnl': gross_pnl,
        'total_fees': total_fees,
        'net_pnl': net_pnl,
        'is_profitable': net_pnl > 0
    }


def _calculate_simulation_metrics(trades: List[Dict]) -> Dict:
    """Calculate performance metrics from closed trades."""
    if not trades:
        return _empty_simulation_result()
    
    trades_df = pd.DataFrame(trades)
    
    total_profit = trades_df['net_pnl'].sum()
    trade_count = len(trades)
    win_rate = (trades_df['net_pnl'] > 0).mean() * 100
    avg_holding_time = trades_df['holding_time_hours'].mean()
    
    # Risk metrics
    returns = trades_df['net_pnl'] / 1000.0  # Assuming 1000 position size
    max_drawdown = (returns.cumsum().cummax() - returns.cumsum()).max()
    
    profitable_trades = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum()
    losing_trades = abs(trades_df[trades_df['net_pnl'] < 0]['net_pnl'].sum())
    profit_factor = profitable_trades / losing_trades if losing_trades > 0 else float('inf')
    
    sharpe_ratio = returns.mean() / returns.std() if returns.std() > 0 else 0
    
    # Trade type breakdown
    fts_trades = len(trades_df[trades_df['type'] == 'fts'])
    stf_trades = len(trades_df[trades_df['type'] == 'stf'])
    total_fees = trades_df['total_fees'].sum()
    
    return {
        'total_profit': total_profit,
        'trade_count': trade_count,
        'win_rate': win_rate,
        'avg_holding_time_hours': avg_holding_time,
        'max_drawdown': max_drawdown,
        'profit_factor': profit_factor,
        'sharpe_ratio': sharpe_ratio,
        'fts_trades': fts_trades,
        'stf_trades': stf_trades,
        'total_fees': total_fees
    }


def _empty_simulation_result() -> Dict:
    """Return empty simulation result."""
    return {
        'total_profit': 0.0,
        'trade_count': 0,
        'win_rate': 0.0,
        'avg_holding_time_hours': 0.0,
        'max_drawdown': 0.0,
        'profit_factor': 0.0,
        'sharpe_ratio': 0.0,
        'fts_trades': 0,
        'stf_trades': 0,
        'total_fees': 0.0
    }


async def calculate_optimal_thresholds(
    spot_df: pd.DataFrame,
    futures_df: pd.DataFrame,
    fees: FeeConfiguration,
    optimization_target: str = 'total_profit',
    threshold_ranges: Optional[Dict] = None,
    max_positions: int = 5,
    min_liquidity: float = 1000.0,
    alignment_tolerance: int = 1
) -> ThresholdResult:
    """
    Calculate optimal entry/exit thresholds for spot-futures arbitrage.
    
    Args:
        spot_df: Spot market orderbook data with columns [timestamp, bid_price, ask_price, bid_qty, ask_qty]
        futures_df: Futures market orderbook data with same column structure
        fees: Fee configuration for all trading operations
        optimization_target: Target metric to optimize ('total_profit', 'sharpe_ratio', 'profit_per_trade')
        threshold_ranges: Custom threshold ranges, auto-detected if None
        max_positions: Maximum concurrent positions 
        min_liquidity: Minimum liquidity required for trades (USD)
        alignment_tolerance: Timestamp alignment tolerance in seconds
        
    Returns:
        ThresholdResult with optimal thresholds and performance metrics
        
    Example:
        ```python
        # Configure fees with realistic rates
        fees = FeeConfiguration.create_realistic()  # MEXC spot + Gate.io futures
        
        # Or create custom fees
        fees = FeeConfiguration(
            spot_maker_fee=0.0, spot_taker_fee=0.05,
            futures_maker_fee=0.02, futures_taker_fee=0.05,
            slippage_factor=0.02
        )
        
        # Calculate optimal thresholds
        result = await calculate_optimal_thresholds(
            spot_df=spot_data,
            futures_df=futures_data, 
            fees=fees,
            optimization_target='total_profit'
        )
        
        print(f"Optimal FTS entry: {result.optimal_fts_entry:.3f}%")
        print(f"Expected profit: ${result.expected_profit:.2f}")
        ```
    """
    start_time = time.time()
    logger.info("🚀 Starting optimal threshold calculation...")
    
    # Align market data
    logger.info("📊 Aligning spot and futures data...")
    aligned_df = align_market_data(spot_df, futures_df, alignment_tolerance)
    
    if aligned_df.empty:
        logger.warning("❌ No aligned data available")
        return _create_empty_threshold_result()
    
    logger.info(f"✅ Aligned {len(aligned_df)} data points")
    
    # Calculate market statistics
    logger.info("📊 Calculating market statistics...")
    market_stats = calculate_market_statistics(spot_df, futures_df, aligned_df)
    
    # Auto-detect threshold ranges if not provided
    if threshold_ranges is None:
        threshold_ranges = _detect_threshold_ranges(aligned_df)
        logger.info(f"📈 Auto-detected threshold ranges: {threshold_ranges}")
    
    # Generate threshold combinations
    threshold_combinations = _generate_threshold_grid(threshold_ranges)
    logger.info(f"🔍 Testing {len(threshold_combinations)} threshold combinations...")
    
    best_result = None
    best_score = float('-inf')
    all_results = []
    
    # Test each threshold combination
    for i, (fts_entry, stf_entry, fts_exit, stf_exit) in enumerate(threshold_combinations):
        if i % 100 == 0:
            logger.info(f"⚡ Progress: {i}/{len(threshold_combinations)} ({i/len(threshold_combinations)*100:.1f}%)")
        
        # Simulate trading with these thresholds
        sim_result = simulate_arbitrage_trades(
            aligned_df, fts_entry, stf_entry, fts_exit, stf_exit,
            fees, max_positions, min_liquidity
        )
        
        # Calculate optimization score
        score = _calculate_optimization_score(sim_result, optimization_target)
        
        # Store result
        result_record = {
            'fts_entry': fts_entry,
            'stf_entry': stf_entry,
            'fts_exit': fts_exit,
            'stf_exit': stf_exit,
            'score': score,
            **sim_result
        }
        all_results.append(result_record)
        
        # Track best result
        if score > best_score:
            best_score = score
            best_result = result_record
    
    # Create final result
    if best_result is None:
        logger.warning("❌ No profitable threshold combination found")
        return _create_empty_threshold_result()
    
    execution_time = time.time() - start_time
    logger.info(f"✅ Optimization completed in {execution_time:.2f}s")
    logger.info(f"🎯 Best thresholds - FTS Entry: {best_result['fts_entry']:.3f}%, STF Entry: {best_result['stf_entry']:.3f}%")
    logger.info(f"💰 Expected profit: ${best_result['total_profit']:.2f} from {best_result['trade_count']} trades")
    
    return ThresholdResult(
        optimal_fts_entry=best_result['fts_entry'],
        optimal_stf_entry=best_result['stf_entry'],
        optimal_fts_exit=best_result['fts_exit'],
        optimal_stf_exit=best_result['stf_exit'],
        expected_profit=best_result['total_profit'],
        trade_count=best_result['trade_count'],
        win_rate=best_result['win_rate'],
        avg_holding_time_hours=best_result['avg_holding_time_hours'],
        max_drawdown=best_result['max_drawdown'],
        profit_factor=best_result['profit_factor'],
        sharpe_ratio=best_result['sharpe_ratio'],
        fts_trades=best_result['fts_trades'],
        stf_trades=best_result['stf_trades'],
        total_fees_paid=best_result['total_fees'],
        optimization_details={'all_results': all_results, 'optimization_target': optimization_target},
        market_statistics=market_stats
    )


def _detect_threshold_ranges(df: pd.DataFrame) -> Dict:
    """Auto-detect reasonable threshold ranges from data."""
    fts_spreads = df['futures_to_spot_spread_pct'].abs()
    stf_spreads = df['spot_to_futures_spread_pct']
    
    # FTS thresholds based on negative spread distribution
    fts_min = max(0.02, fts_spreads.quantile(0.25))  # 25th percentile, min 0.02%
    fts_max = min(0.20, fts_spreads.quantile(0.95))  # 95th percentile, max 0.20%
    
    # STF thresholds based on positive spread distribution
    stf_positive = stf_spreads[stf_spreads > 0]
    if len(stf_positive) > 10:
        stf_min = max(0.005, stf_positive.quantile(0.10))  # 10th percentile, min 0.005%
        stf_max = min(0.10, stf_positive.quantile(0.90))   # 90th percentile, max 0.10%
    else:
        stf_min, stf_max = 0.01, 0.05  # Fallback ranges
    
    return {
        'fts_entry': (fts_min, fts_max, 0.01),  # (min, max, step)
        'stf_entry': (stf_min, stf_max, 0.005),
        'fts_exit': (fts_min * 0.5, fts_max * 0.8, 0.01),  # Exit thresholds smaller than entry
        'stf_exit': (0.0, stf_max * 0.5, 0.005)
    }


def _generate_threshold_grid(ranges: Dict) -> List[Tuple[float, float, float, float]]:
    """Generate grid of threshold combinations."""
    combinations = []
    
    # Generate ranges
    fts_entry_range = np.arange(ranges['fts_entry'][0], ranges['fts_entry'][1], ranges['fts_entry'][2])
    stf_entry_range = np.arange(ranges['stf_entry'][0], ranges['stf_entry'][1], ranges['stf_entry'][2])
    fts_exit_range = np.arange(ranges['fts_exit'][0], ranges['fts_exit'][1], ranges['fts_exit'][2])
    stf_exit_range = np.arange(ranges['stf_exit'][0], ranges['stf_exit'][1], ranges['stf_exit'][2])
    
    for fts_entry in fts_entry_range:
        for stf_entry in stf_entry_range:
            for fts_exit in fts_exit_range:
                for stf_exit in stf_exit_range:
                    # Ensure exit thresholds are smaller than entry thresholds
                    if fts_exit < fts_entry and stf_exit <= stf_entry:
                        combinations.append((fts_entry, stf_entry, fts_exit, stf_exit))
    
    return combinations


def _calculate_optimization_score(sim_result: Dict, target: str) -> float:
    """Calculate optimization score based on target metric."""
    if sim_result['trade_count'] == 0:
        return float('-inf')
    
    if target == 'total_profit':
        return sim_result['total_profit']
    elif target == 'sharpe_ratio':
        return sim_result['sharpe_ratio']
    elif target == 'profit_per_trade':
        return sim_result['total_profit'] / sim_result['trade_count']
    else:
        raise ValueError(f"Unknown optimization target: {target}")


def _create_empty_threshold_result() -> ThresholdResult:
    """Create empty threshold result for failed optimization."""
    return ThresholdResult(
        optimal_fts_entry=0.0,
        optimal_stf_entry=0.0,
        optimal_fts_exit=0.0,
        optimal_stf_exit=0.0,
        expected_profit=0.0,
        trade_count=0,
        win_rate=0.0,
        avg_holding_time_hours=0.0,
        max_drawdown=0.0,
        profit_factor=0.0,
        sharpe_ratio=0.0,
        fts_trades=0,
        stf_trades=0,
        total_fees_paid=0.0,
        optimization_details={'all_results': [], 'optimization_target': 'none'},
        market_statistics={}
    )


# Example usage and testing
if __name__ == "__main__":
    async def example_usage():
        """Example of how to use the threshold optimizer."""
        
        # Create sample data (in real usage, load from database)
        dates = pd.date_range('2024-01-01', periods=1000, freq='1min')
        
        # Sample spot data
        spot_data = pd.DataFrame({
            'timestamp': dates,
            'bid_price': 100.0 + np.random.randn(1000) * 0.1,
            'ask_price': 100.05 + np.random.randn(1000) * 0.1,
            'bid_qty': 1000 + np.random.randn(1000) * 100,
            'ask_qty': 1000 + np.random.randn(1000) * 100
        })
        
        # Sample futures data (slightly different prices to create spreads)
        futures_data = pd.DataFrame({
            'timestamp': dates,
            'bid_price': 99.98 + np.random.randn(1000) * 0.1,  # Slightly lower than spot
            'ask_price': 100.03 + np.random.randn(1000) * 0.1,
            'bid_qty': 1000 + np.random.randn(1000) * 100,
            'ask_qty': 1000 + np.random.randn(1000) * 100
        })
        
        # Configure fees (0.05% maker, 0.1% taker, 0.02% slippage)
        fees = FeeConfiguration.create_uniform(maker_fee=0.05, taker_fee=0.1, slippage=0.02)
        
        # Calculate optimal thresholds
        result = await calculate_optimal_thresholds(
            spot_df=spot_data,
            futures_df=futures_data,
            fees=fees,
            optimization_target='total_profit'
        )
        
        # Print results
        print("\n" + "="*60)
        print("OPTIMAL THRESHOLD CALCULATION RESULTS")
        print("="*60)
        print(f"Optimal FTS Entry Threshold: {result.optimal_fts_entry:.3f}%")
        print(f"Optimal STF Entry Threshold: {result.optimal_stf_entry:.3f}%")
        print(f"Optimal FTS Exit Threshold:  {result.optimal_fts_exit:.3f}%")
        print(f"Optimal STF Exit Threshold:  {result.optimal_stf_exit:.3f}%")
        print()
        print(f"Expected Profit: ${result.expected_profit:.2f}")
        print(f"Total Trades: {result.trade_count}")
        print(f"Win Rate: {result.win_rate:.1f}%")
        print(f"Average Holding Time: {result.avg_holding_time_hours:.2f} hours")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print()
        print(f"FTS Trades: {result.fts_trades}")
        print(f"STF Trades: {result.stf_trades}")
        print(f"Total Fees Paid: ${result.total_fees_paid:.2f}")
        print("="*60)
    
    # Run example
    asyncio.run(example_usage())