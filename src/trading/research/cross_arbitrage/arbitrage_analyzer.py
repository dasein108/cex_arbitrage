#!/usr/bin/env python3
"""
Arbitrage Analysis Tool

Analyzes arbitrage opportunities between MEXC spot, Gate.io spot, and Gate.io futures
using 5-minute candle data. Calculates optimal entry/exit points for delta-neutral 
arbitrage strategies.

Usage:
    analyzer = ArbitrageAnalyzer()
    df, results = await analyzer.run_analysis("BTC_USDT", days=7)
    print(analyzer.format_report(results))
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Union
import sys
import os

from db import initialize_database_manager

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from trading.research.cross_arbitrage.book_ticker_source import CandlesBookTickerSource, BookTickerDbSource
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from exchanges.structs import Symbol, AssetName
from trading.analysis.arbitrage_signals import calculate_arb_signals


class AnalyzerKeys:
    """Static keys for column names and arbitrage calculations."""
    
    # Exchange column keys
    mexc_bid = f'{ExchangeEnum.MEXC.value}_bid_price'
    mexc_ask = f'{ExchangeEnum.MEXC.value}_ask_price'
    gateio_spot_bid = f'{ExchangeEnum.GATEIO.value}_bid_price'
    gateio_spot_ask = f'{ExchangeEnum.GATEIO.value}_ask_price'
    gateio_futures_bid = f'{ExchangeEnum.GATEIO_FUTURES.value}_bid_price'
    gateio_futures_ask = f'{ExchangeEnum.GATEIO_FUTURES.value}_ask_price'
    
    # Arbitrage calculation keys
    mexc_vs_gateio_futures_arb = f'{ExchangeEnum.MEXC.value}_vs_{ExchangeEnum.GATEIO_FUTURES.value}_arb'
    gateio_spot_vs_futures_arb = f'{ExchangeEnum.GATEIO.value}_vs_{ExchangeEnum.GATEIO_FUTURES.value}_arb'


class ArbitrageAnalyzer:
    """
    Simple arbitrage analyzer for MEXC → Gate.io delta-neutral strategies.
    
    Calculates 4 arbitrage opportunities and finds optimal entry/exit points
    accounting for trading fees and market spreads.
    """
    
    # Remove SPREAD_BPS - now handled by BookTickerSource
    TOTAL_FEES = 0.25  # 0.1% + 0.05% + 0.05% total fees
    
    def __init__(self, exchanges: Optional[List[ExchangeEnum]] = None, use_db_book_tickers = False,
                 tf: Union[KlineInterval, int] = KlineInterval.MINUTE_5):
        """Initialize analyzer with modern BookTickerSource."""
        self.tf = tf
        self.exchanges = exchanges or [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
        self.book_ticker_source = BookTickerDbSource() if use_db_book_tickers else  CandlesBookTickerSource()
    
    async def run_analysis(self, symbol: Symbol, days: int = 7,
                           df_data: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Run complete arbitrage analysis for given symbol and time period.
        
        Args:
            symbol: Trading symbol (e.g., "BTC_USDT")
            days: Number of days to analyze
            
        Returns:
            Tuple of (dataframe with all calculations, analysis results dict)
        """
        print(f"🚀 Starting arbitrage analysis for {symbol} ({days} days)")
        
        # Load data using BookTickerSource (includes bid/ask prices)
        if df_data is not None:
            df = df_data
            print(f"💾 Using provided dataframe with {len(df)} periods")
        else:
            df = await self._download_and_merge_data(symbol, days)

        # Calculate arbitrage opportunities
        df = self._calculate_arbitrage_metrics(df)
        
        # Perform statistical analysis

        # Analysis completed
        print(f"💾 Analysis completed: {len(df)} periods analyzed")
        
        return df, {}
    
    async def _download_and_merge_data(self, symbol: Symbol, days: int) -> pd.DataFrame:
        """Download book ticker data using modern BookTickerSource architecture."""
        print(f"📥 Loading {symbol} book ticker data from 3 exchanges...")
        

        # Use BookTickerSource for data loading
        df = await self.book_ticker_source.get_multi_exchange_data(
            exchanges=self.exchanges,
            symbol=symbol,
            hours=round(days * 24),
            timeframe=self.tf
        )

        len_before = len(df)
        # df.fillna(method='ffill', inplace=True)

        df.dropna(inplace=True)

        print(f"🔀 Loaded data: {len(df)}(with nan: {len_before}) aligned periods")



        return df
    
    def _validate_required_columns(self, df: pd.DataFrame) -> None:
        """Validate that all required columns exist in the dataframe."""
        required_columns = [
            AnalyzerKeys.mexc_ask,
            AnalyzerKeys.mexc_bid,
            AnalyzerKeys.gateio_spot_bid,
            AnalyzerKeys.gateio_spot_ask,
            AnalyzerKeys.gateio_futures_bid,
            AnalyzerKeys.gateio_futures_ask
        ]
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
    
    def _calculate_arbitrage_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate arbitrage opportunities with proper cost modeling.
        
        Fixed calculation considers:
        1. Proper execution prices (buy at ask, sell at bid)
        2. Mid-price denominators for accurate percentage calculations
        3. Realistic cost structure including fees and spreads
        """
        
        # Validate required columns exist
        self._validate_required_columns(df)
        
        # Calculate mid prices for proper percentage calculation
        df['mexc_mid'] = (df[AnalyzerKeys.mexc_bid] + df[AnalyzerKeys.mexc_ask]) / 2
        df['gateio_spot_mid'] = (df[AnalyzerKeys.gateio_spot_bid] + df[AnalyzerKeys.gateio_spot_ask]) / 2
        df['gateio_futures_mid'] = (df[AnalyzerKeys.gateio_futures_bid] + df[AnalyzerKeys.gateio_futures_ask]) / 2

        # Calculate internal spreads (bid/ask spreads) for cost modeling - using percentages
        df['mexc_spread_pct'] = ((df[AnalyzerKeys.mexc_ask] - df[AnalyzerKeys.mexc_bid]) / df['mexc_mid']) * 100
        df['gateio_spot_spread_pct'] = ((df[AnalyzerKeys.gateio_spot_ask] - df[AnalyzerKeys.gateio_spot_bid]) / df['gateio_spot_mid']) * 100
        df['gateio_futures_spread_pct'] = ((df[AnalyzerKeys.gateio_futures_ask] - df[AnalyzerKeys.gateio_futures_bid]) / df['gateio_futures_mid']) * 100
        
        # 1. MEXC vs Gate.io Futures arbitrage (ORIGINAL)
        # Buy MEXC spot (at ask), Sell Gate.io futures (at bid)
        df[AnalyzerKeys.mexc_vs_gateio_futures_arb] = (
            (df[AnalyzerKeys.gateio_futures_bid] - df[AnalyzerKeys.mexc_ask]) / 
            df[AnalyzerKeys.gateio_futures_bid] * 100
        )
        
        # 2. Gate.io Spot vs Futures arbitrage (ORIGINAL)
        # Buy Gate.io spot (at ask), Sell Gate.io futures (at bid) 
        df[AnalyzerKeys.gateio_spot_vs_futures_arb] = (
            (df[AnalyzerKeys.gateio_futures_bid] - df[AnalyzerKeys.gateio_spot_ask]) / 
            df[AnalyzerKeys.gateio_futures_bid] * 100
        )
        
        # Calculate net arbitrage after transaction costs - all in percentages
        # Total cost = trading fees + bid/ask spreads + transfer costs
        df['total_cost_pct'] = (
            0.25 +  # Trading fees (0.25%)
            (df['mexc_spread_pct'] + df['gateio_futures_spread_pct']) / 2 +  # Avg spread cost
            0.0    # Transfer/withdrawal costs (0.1%)
        )
        
        # Net arbitrage = gross arbitrage - total costs (all in percentages)
        df['mexc_vs_gateio_futures_net'] = df[AnalyzerKeys.mexc_vs_gateio_futures_arb] - df['total_cost_pct']
        df['gateio_spot_vs_futures_net'] = df[AnalyzerKeys.gateio_spot_vs_futures_arb] - df['total_cost_pct']

        print(f'{AnalyzerKeys.gateio_spot_vs_futures_arb}: min {df[AnalyzerKeys.gateio_spot_vs_futures_arb].min()}, '
              f'max {df[AnalyzerKeys.gateio_spot_vs_futures_arb].max()}')
        print(f'{AnalyzerKeys.mexc_vs_gateio_futures_arb}: min {df[AnalyzerKeys.mexc_vs_gateio_futures_arb].min()}, '
              f'max {df[AnalyzerKeys.mexc_vs_gateio_futures_arb].max()}')
        print(f"mexc_spread_pct: {df['mexc_spread_pct'].min()}, max {df['mexc_spread_pct'].max()}")
        print(f"gateio_spot_spread_pct: {df['gateio_spot_spread_pct'].min()}, max {df['gateio_spot_spread_pct'].max()}")
        print(f"gateio_futures_spread_pct: {df['gateio_futures_spread_pct'].min()}, max {df['gateio_futures_spread_pct'].max()}")
        print(f"Total Cost %: min {df['total_cost_pct'].min()}, max {df['total_cost_pct'].max()}")
        df = self.add_arb_signals_with_pnl(df)
        return df

    def add_arb_signals_with_pnl(
            self,
            df: pd.DataFrame,
            window_size: int = 10,
            total_fees: float = 0.0025,  # 0.25% total fees
            lookback_periods: int = 500,  # Fixed lookback like hedged backtest
            min_history: int = 50,  # Minimum periods before trading
    ) -> pd.DataFrame:
        """
        Add arbitrage signals with bidirectional position tracking and P&L calculation.
        Uses unified logic for both MEXC_TO_GATEIO and GATEIO_TO_MEXC directions.

        Args:
            df: DataFrame with price and arb columns
            window_size: Rolling window size for statistics (default: 10)
            total_fees: Total trading fees (default: 0.25%)
            lookback_periods: Fixed lookback period for percentile calculation (default: 500)
            min_history: Minimum periods before generating signals (default: 50)

        Returns:
            DataFrame with signals, positions, and P&L for both directions
        """
        mexc_col = AnalyzerKeys.mexc_vs_gateio_futures_arb
        gateio_col = AnalyzerKeys.gateio_spot_vs_futures_arb

        # Initialize unified signal columns for bidirectional trading
        df['signal'] = 'HOLD'
        df['direction'] = 'NONE'
        df['mexc_gateio_min_25pct'] = np.nan
        df['gateio_spot_max_25pct'] = np.nan
        df['mexc_gateio_mean'] = np.nan
        df['gateio_spot_mean'] = np.nan

        # Calculate signals using unified methodology from hedged backtest
        for i in range(len(df)):
            # Skip if insufficient history
            if i < min_history:
                continue
                
            # Get historical data (fixed lookback period like hedged backtest)
            start_idx = max(0, i - lookback_periods)
            mexc_history = df[mexc_col].iloc[start_idx:i+1].values
            gateio_history = df[gateio_col].iloc[start_idx:i+1].values
            
            # Use unified signal detection like hedged backtest
            if len(mexc_history) >= min_history:
                signal_result = calculate_arb_signals(
                    mexc_vs_gateio_futures_history=mexc_history,
                    gateio_spot_vs_futures_history=gateio_history,
                    current_mexc_vs_gateio_futures=df.iloc[i][mexc_col],
                    current_gateio_spot_vs_futures=df.iloc[i][gateio_col],
                    window_size=window_size
                )
                
                # Store statistics
                df.iloc[i, df.columns.get_loc('mexc_gateio_min_25pct')] = signal_result.mexc_vs_gateio_futures.min_25pct
                df.iloc[i, df.columns.get_loc('gateio_spot_max_25pct')] = signal_result.gateio_spot_vs_futures.max_25pct
                df.iloc[i, df.columns.get_loc('mexc_gateio_mean')] = signal_result.mexc_vs_gateio_futures.mean
                df.iloc[i, df.columns.get_loc('gateio_spot_mean')] = signal_result.gateio_spot_vs_futures.mean
                
                # IMPROVED SIGNAL LOGIC WITH PROFITABILITY VALIDATION
                if signal_result.signal.value == 'ENTER':
                    # Get current net spreads (after costs) for profitability check
                    current_mexc_net = df.iloc[i]['mexc_vs_gateio_futures_net']
                    current_gateio_net = df.iloc[i]['gateio_spot_vs_futures_net']
                    
                    # Only enter if net spread is positive and significant
                    min_profit_threshold = 0.05  # Minimum 0.05% profit after all costs
                    
                    # Choose best direction based on net profitability
                    mexc_profitable = current_mexc_net > min_profit_threshold
                    gateio_profitable = current_gateio_net > min_profit_threshold
                    
                    if mexc_profitable and current_mexc_net >= current_gateio_net:
                        # MEXC direction is most profitable
                        df.iloc[i, df.columns.get_loc('signal')] = 'ENTER'
                        df.iloc[i, df.columns.get_loc('direction')] = 'MEXC_TO_GATEIO'
                    elif gateio_profitable and current_gateio_net > current_mexc_net:
                        # Gate.io direction is most profitable
                        df.iloc[i, df.columns.get_loc('signal')] = 'ENTER'
                        df.iloc[i, df.columns.get_loc('direction')] = 'GATEIO_TO_MEXC'
                    else:
                        # No profitable opportunity, stay in HOLD
                        df.iloc[i, df.columns.get_loc('signal')] = 'HOLD'
                        df.iloc[i, df.columns.get_loc('direction')] = 'NONE'
                        
                elif signal_result.signal.value == 'EXIT':
                    # Additional exit validation: only exit if spread has normalized
                    current_mexc_net = df.iloc[i]['mexc_vs_gateio_futures_net']
                    current_gateio_net = df.iloc[i]['gateio_spot_vs_futures_net']
                    
                    # Exit if spreads are no longer profitable or have reversed
                    max_exit_threshold = 0.02  # Exit if spread < 0.02%
                    if abs(current_mexc_net) < max_exit_threshold and abs(current_gateio_net) < max_exit_threshold:
                        df.iloc[i, df.columns.get_loc('signal')] = 'EXIT'
                    else:
                        # Don't exit yet, wait for better conditions
                        df.iloc[i, df.columns.get_loc('signal')] = 'HOLD'

        # --- Unified Bidirectional Position Tracking and P&L Calculation ---
        df['position_open'] = False
        df['source_spot_entry'] = np.nan
        df['hedge_futures_entry'] = np.nan
        df['dest_spot_exit'] = np.nan
        df['hedge_futures_exit'] = np.nan
        df['trade_pnl'] = 0.0
        df['cumulative_pnl'] = 0.0

        position_open = False
        position_direction = None
        source_spot_entry = 0.0
        hedge_futures_entry = 0.0
        cumulative_pnl = 0.0

        for idx in df.index:
            signal = df.loc[idx, 'signal']
            direction = df.loc[idx, 'direction']

            if signal == 'ENTER' and not position_open:
                # Open unified position based on direction
                position_direction = direction
                
                if direction == 'MEXC_TO_GATEIO':
                    # Buy MEXC spot, Sell Gate.io futures
                    source_spot_entry = df.loc[idx, AnalyzerKeys.mexc_ask]
                    hedge_futures_entry = df.loc[idx, AnalyzerKeys.gateio_futures_bid]
                elif direction == 'GATEIO_TO_MEXC':
                    # Buy Gate.io spot, Sell Gate.io futures
                    source_spot_entry = df.loc[idx, AnalyzerKeys.gateio_spot_ask]
                    hedge_futures_entry = df.loc[idx, AnalyzerKeys.gateio_futures_bid]

                df.loc[idx, 'position_open'] = True
                df.loc[idx, 'source_spot_entry'] = source_spot_entry
                df.loc[idx, 'hedge_futures_entry'] = hedge_futures_entry
                position_open = True

            elif signal == 'EXIT' and position_open:
                # Close unified position based on current direction
                if position_direction == 'MEXC_TO_GATEIO':
                    # Transfer complete: Sell Gate.io spot, Buy Gate.io futures
                    dest_spot_exit = df.loc[idx, AnalyzerKeys.gateio_spot_bid]
                    hedge_futures_exit = df.loc[idx, AnalyzerKeys.gateio_futures_ask]
                elif position_direction == 'GATEIO_TO_MEXC':
                    # Transfer complete: Sell MEXC spot, Buy Gate.io futures
                    dest_spot_exit = df.loc[idx, AnalyzerKeys.mexc_bid]
                    hedge_futures_exit = df.loc[idx, AnalyzerKeys.gateio_futures_ask]

                # CORRECTED DELTA-NEUTRAL P&L CALCULATION
                # Properly account for actual execution costs and position sizing
                
                # Get entry and exit costs for this trade
                entry_cost_pct = df.loc[idx, 'total_cost_pct']
                
                # Calculate actual USD values to ensure proper P&L calculation
                position_size_usd = 1000.0  # Standard position size
                
                # Entry positions (negative for buys, positive for sells)
                spot_entry_usd = -position_size_usd  # Bought spot (cash outflow)
                futures_entry_usd = position_size_usd * (hedge_futures_entry / source_spot_entry)  # Sold futures (cash inflow)
                
                # Exit positions (positive for sells, negative for buys)
                spot_exit_usd = position_size_usd * (dest_spot_exit / source_spot_entry)  # Sold spot (cash inflow)
                futures_exit_usd = -position_size_usd * (hedge_futures_exit / source_spot_entry)  # Bought futures (cash outflow)
                
                # Net cash flow = Exit flows - Entry flows
                total_cash_flow = (spot_exit_usd + futures_exit_usd) - (spot_entry_usd + futures_entry_usd)
                
                # Apply transaction costs
                total_transaction_cost = position_size_usd * (entry_cost_pct / 100)
                
                # Net P&L as percentage of position size
                net_pnl_usd = total_cash_flow - total_transaction_cost
                trade_pnl = (net_pnl_usd / position_size_usd) * 100  # Convert to percentage

                df.loc[idx, 'dest_spot_exit'] = dest_spot_exit
                df.loc[idx, 'hedge_futures_exit'] = hedge_futures_exit
                df.loc[idx, 'trade_pnl'] = trade_pnl  # Already in percentage
                cumulative_pnl += trade_pnl
                df.loc[idx, 'cumulative_pnl'] = cumulative_pnl

                position_open = False
                position_direction = None

            # Forward fill position state
            if position_open:
                df.loc[idx, 'position_open'] = True
                df.loc[idx, 'direction'] = position_direction
                df.loc[idx, 'source_spot_entry'] = source_spot_entry
                df.loc[idx, 'hedge_futures_entry'] = hedge_futures_entry

            # Forward fill cumulative P&L
            df.loc[idx, 'cumulative_pnl'] = cumulative_pnl

        return df

    def add_reverse_delta_neutral_backtest(
        self,
        df: pd.DataFrame,
        entry_spread_threshold: float = -2.5,  # Enter when spread < -2.5%
        exit_spread_threshold: float = -0.3,   # Exit when spread > -0.3%
        stop_loss_threshold: float = -6.0,     # Emergency exit at -6%
        max_holding_hours: int = 24,           # Force close after 24 hours
        position_size_usd: float = 1000.0,     # Position size
        total_fees: float = 0.0067,            # 0.67% round-trip fees
    ) -> pd.DataFrame:
        """
        Backtest reverse delta-neutral arbitrage strategy.
        
        Strategy: Enter LONG spot + SHORT futures when spread is deeply negative,
        exit when spread compresses (normalizes toward zero).
        
        Args:
            df: DataFrame with arbitrage spread data
            entry_spread_threshold: Spread threshold for entry (negative value)
            exit_spread_threshold: Spread threshold for exit (negative value)
            stop_loss_threshold: Emergency exit threshold (negative value)
            max_holding_hours: Maximum holding period in hours
            position_size_usd: Position size in USD
            total_fees: Total round-trip trading fees as decimal
            
        Returns:
            DataFrame with reverse delta-neutral signals and P&L
        """
        # Initialize columns for reverse delta-neutral strategy
        df['rdn_signal'] = 'HOLD'
        df['rdn_position_open'] = False
        df['rdn_entry_time'] = pd.NaT
        df['rdn_entry_spread'] = np.nan
        df['rdn_spot_entry'] = np.nan
        df['rdn_futures_entry'] = np.nan
        df['rdn_spot_exit'] = np.nan
        df['rdn_futures_exit'] = np.nan
        df['rdn_trade_pnl'] = 0.0
        df['rdn_cumulative_pnl'] = 0.0
        df['rdn_holding_hours'] = 0.0
        
        # Add spread indicators
        mexc_spread_col = AnalyzerKeys.mexc_vs_gateio_futures_arb
        gateio_spread_col = AnalyzerKeys.gateio_spot_vs_futures_arb
        
        # Calculate combined spread (average of both opportunities)
        df['rdn_combined_spread'] = (df[mexc_spread_col] + df[gateio_spread_col]) / 2
        
        # Add rolling volatility for position sizing
        df['rdn_spread_volatility'] = df['rdn_combined_spread'].rolling(window=20).std()
        
        # Add spread momentum indicator
        df['rdn_spread_momentum'] = df['rdn_combined_spread'].diff(5)  # 5-period momentum
        
        # State tracking variables
        position_open = False
        entry_time = None
        entry_spread = 0.0
        spot_entry_price = 0.0
        futures_entry_price = 0.0
        cumulative_pnl = 0.0
        
        for idx in df.index:
            current_spread = df.loc[idx, 'rdn_combined_spread']
            current_time = df.loc[idx, 'timestamp'] if 'timestamp' in df.columns else idx
            
            # Skip if data is missing
            if pd.isna(current_spread):
                continue
                
            if not position_open:
                # Entry logic: Enter when spread is deeply negative
                if (current_spread < entry_spread_threshold and 
                    not pd.isna(df.loc[idx, 'rdn_spread_volatility']) and
                    df.loc[idx, 'rdn_spread_volatility'] > 0.1):  # Require minimum volatility
                    
                    # Enter reverse delta-neutral position
                    df.loc[idx, 'rdn_signal'] = 'ENTER'
                    df.loc[idx, 'rdn_position_open'] = True
                    df.loc[idx, 'rdn_entry_time'] = current_time
                    df.loc[idx, 'rdn_entry_spread'] = current_spread
                    
                    # Use MEXC for spot and Gate.io futures (most liquid combination)
                    spot_entry_price = df.loc[idx, AnalyzerKeys.mexc_ask]  # Buy MEXC spot
                    futures_entry_price = df.loc[idx, AnalyzerKeys.gateio_futures_bid]  # Sell Gate.io futures
                    
                    df.loc[idx, 'rdn_spot_entry'] = spot_entry_price
                    df.loc[idx, 'rdn_futures_entry'] = futures_entry_price
                    
                    # Update state
                    position_open = True
                    entry_time = current_time
                    entry_spread = current_spread
                    
            else:
                # Exit logic
                time_held = (current_time - entry_time).total_seconds() / 3600 if hasattr(current_time - entry_time, 'total_seconds') else 0
                df.loc[idx, 'rdn_holding_hours'] = time_held
                
                should_exit = False
                exit_reason = ""
                
                # Exit conditions
                if current_spread > exit_spread_threshold:
                    should_exit = True
                    exit_reason = "SPREAD_COMPRESSION"
                elif current_spread < stop_loss_threshold:
                    should_exit = True
                    exit_reason = "STOP_LOSS"
                elif time_held > max_holding_hours:
                    should_exit = True
                    exit_reason = "MAX_TIME"
                
                if should_exit:
                    # Exit position
                    df.loc[idx, 'rdn_signal'] = f'EXIT_{exit_reason}'
                    
                    # Exit prices
                    spot_exit_price = df.loc[idx, AnalyzerKeys.mexc_bid]  # Sell MEXC spot
                    futures_exit_price = df.loc[idx, AnalyzerKeys.gateio_futures_ask]  # Buy Gate.io futures
                    
                    df.loc[idx, 'rdn_spot_exit'] = spot_exit_price
                    df.loc[idx, 'rdn_futures_exit'] = futures_exit_price
                    
                    # Calculate P&L for reverse delta-neutral
                    # Long spot: profit = (exit_price - entry_price) / entry_price
                    # Short futures: profit = (entry_price - exit_price) / entry_price
                    spot_pnl = (spot_exit_price - spot_entry_price) / spot_entry_price
                    futures_pnl = (futures_entry_price - futures_exit_price) / futures_entry_price
                    gross_pnl = (spot_pnl + futures_pnl) * 100  # Convert to percentage
                    
                    # Apply fees
                    net_pnl = gross_pnl - (total_fees * 100)  # Subtract fees
                    
                    df.loc[idx, 'rdn_trade_pnl'] = net_pnl
                    cumulative_pnl += net_pnl
                    df.loc[idx, 'rdn_cumulative_pnl'] = cumulative_pnl
                    
                    # Reset position
                    position_open = False
                    entry_time = None
                
                # Forward fill position state
                if position_open:
                    df.loc[idx, 'rdn_position_open'] = True
                    df.loc[idx, 'rdn_entry_time'] = entry_time
                    df.loc[idx, 'rdn_entry_spread'] = entry_spread
                    df.loc[idx, 'rdn_spot_entry'] = spot_entry_price
                    df.loc[idx, 'rdn_futures_entry'] = futures_entry_price
            
            # Forward fill cumulative P&L
            df.loc[idx, 'rdn_cumulative_pnl'] = cumulative_pnl
            
        return df

    def add_inventory_spot_arbitrage_backtest(
        self,
        df: pd.DataFrame,
        min_spread_threshold: float = 0.30,     # Minimum 0.30% spread for profitability
        max_spread_threshold: float = 2.0,      # Maximum 2.0% spread (avoid anomalies)
        initial_mexc_balance_usd: float = 5000.0,  # Starting MEXC balance
        initial_gateio_balance_usd: float = 5000.0,  # Starting Gate.io balance
        min_trade_size_usd: float = 500.0,      # Minimum trade size
        max_trade_size_usd: float = 2000.0,     # Maximum trade size
        target_balance_ratio: float = 0.5,      # Target 50/50 balance
        rebalance_threshold: float = 0.3,       # Rebalance when 30% off target
        total_fees: float = 0.0025,            # 0.25% round-trip fees
    ) -> pd.DataFrame:
        """
        Backtest inventory-based spot arbitrage strategy.
        
        Strategy: Use existing balances to trade spot-to-spot arbitrage without transfers,
        gradually rebalance inventory through profitable trades.
        
        Args:
            df: DataFrame with price data
            min_spread_threshold: Minimum spread to enter trade (percentage)
            max_spread_threshold: Maximum spread to avoid anomalies
            initial_mexc_balance_usd: Starting balance on MEXC
            initial_gateio_balance_usd: Starting balance on Gate.io
            min_trade_size_usd: Minimum trade size
            max_trade_size_usd: Maximum trade size
            target_balance_ratio: Target balance ratio (0.5 = 50/50)
            rebalance_threshold: Rebalance trigger threshold
            total_fees: Total round-trip trading fees
            
        Returns:
            DataFrame with inventory arbitrage signals and P&L
        """
        # Initialize columns
        df['inv_signal'] = 'HOLD'
        df['inv_trade_direction'] = 'NONE'  # 'MEXC_TO_GATEIO' or 'GATEIO_TO_MEXC'
        df['inv_trade_size_usd'] = 0.0
        df['inv_spread_captured'] = 0.0
        df['inv_trade_pnl'] = 0.0
        df['inv_cumulative_pnl'] = 0.0
        df['inv_mexc_balance'] = initial_mexc_balance_usd
        df['inv_gateio_balance'] = initial_gateio_balance_usd
        df['inv_total_balance'] = initial_mexc_balance_usd + initial_gateio_balance_usd
        df['inv_balance_ratio'] = 0.5  # Start balanced
        df['inv_imbalance_penalty'] = 0.0
        
        # Calculate spot-to-spot spreads
        df['inv_mexc_to_gateio_spread'] = ((df[AnalyzerKeys.gateio_spot_bid] - df[AnalyzerKeys.mexc_ask]) / 
                                           df[AnalyzerKeys.mexc_ask] * 100)
        df['inv_gateio_to_mexc_spread'] = ((df[AnalyzerKeys.mexc_bid] - df[AnalyzerKeys.gateio_spot_ask]) / 
                                           df[AnalyzerKeys.gateio_spot_ask] * 100)
        
        # Add rolling spread statistics for filtering
        df['inv_spread_volatility'] = df['inv_mexc_to_gateio_spread'].rolling(window=10).std()
        df['inv_spread_mean'] = df['inv_mexc_to_gateio_spread'].rolling(window=20).mean()
        
        # State tracking
        mexc_balance = initial_mexc_balance_usd
        gateio_balance = initial_gateio_balance_usd
        cumulative_pnl = 0.0
        
        for idx in df.index:
            # Update balance tracking
            total_balance = mexc_balance + gateio_balance
            balance_ratio = mexc_balance / total_balance if total_balance > 0 else 0.5
            
            df.loc[idx, 'inv_mexc_balance'] = mexc_balance
            df.loc[idx, 'inv_gateio_balance'] = gateio_balance
            df.loc[idx, 'inv_total_balance'] = total_balance
            df.loc[idx, 'inv_balance_ratio'] = balance_ratio
            
            # Calculate imbalance penalty (reduces trade size when very imbalanced)
            imbalance = abs(balance_ratio - target_balance_ratio)
            imbalance_penalty = min(imbalance * 2, 0.5)  # Max 50% penalty
            df.loc[idx, 'inv_imbalance_penalty'] = imbalance_penalty
            
            # Get current spreads
            mexc_to_gateio_spread = df.loc[idx, 'inv_mexc_to_gateio_spread']
            gateio_to_mexc_spread = df.loc[idx, 'inv_gateio_to_mexc_spread']
            
            # Skip if data is missing
            if pd.isna(mexc_to_gateio_spread) or pd.isna(gateio_to_mexc_spread):
                continue
            
            # Trade logic
            trade_executed = False
            
            # Option 1: MEXC to Gate.io (buy MEXC, sell Gate.io)
            if (mexc_to_gateio_spread > min_spread_threshold and 
                mexc_to_gateio_spread < max_spread_threshold and
                mexc_balance >= min_trade_size_usd):
                
                # Calculate trade size based on balance and imbalance
                max_possible = min(mexc_balance * 0.8, max_trade_size_usd)  # Use max 80% of balance
                base_trade_size = min(max_possible, min_trade_size_usd * 2)
                trade_size = base_trade_size * (1 - imbalance_penalty)
                
                if trade_size >= min_trade_size_usd:
                    # Execute MEXC to Gate.io arbitrage
                    buy_price = df.loc[idx, AnalyzerKeys.mexc_ask]
                    sell_price = df.loc[idx, AnalyzerKeys.gateio_spot_bid]
                    
                    # Calculate quantities and costs
                    quantity = trade_size / buy_price
                    buy_cost = trade_size
                    sell_proceeds = quantity * sell_price
                    fees = (buy_cost + sell_proceeds) * (total_fees / 2)  # Fees on both sides
                    
                    net_pnl = sell_proceeds - buy_cost - fees
                    pnl_percentage = (net_pnl / trade_size) * 100
                    
                    # Update balances
                    mexc_balance -= buy_cost + (buy_cost * total_fees / 2)
                    gateio_balance += sell_proceeds - (sell_proceeds * total_fees / 2)
                    
                    # Record trade
                    df.loc[idx, 'inv_signal'] = 'TRADE'
                    df.loc[idx, 'inv_trade_direction'] = 'MEXC_TO_GATEIO'
                    df.loc[idx, 'inv_trade_size_usd'] = trade_size
                    df.loc[idx, 'inv_spread_captured'] = mexc_to_gateio_spread
                    df.loc[idx, 'inv_trade_pnl'] = pnl_percentage
                    
                    cumulative_pnl += pnl_percentage
                    trade_executed = True
            
            # Option 2: Gate.io to MEXC (buy Gate.io, sell MEXC)
            elif (gateio_to_mexc_spread > min_spread_threshold and 
                  gateio_to_mexc_spread < max_spread_threshold and
                  gateio_balance >= min_trade_size_usd and
                  not trade_executed):  # Don't trade both directions same period
                
                # Calculate trade size
                max_possible = min(gateio_balance * 0.8, max_trade_size_usd)
                base_trade_size = min(max_possible, min_trade_size_usd * 2)
                trade_size = base_trade_size * (1 - imbalance_penalty)
                
                if trade_size >= min_trade_size_usd:
                    # Execute Gate.io to MEXC arbitrage
                    buy_price = df.loc[idx, AnalyzerKeys.gateio_spot_ask]
                    sell_price = df.loc[idx, AnalyzerKeys.mexc_bid]
                    
                    # Calculate quantities and costs
                    quantity = trade_size / buy_price
                    buy_cost = trade_size
                    sell_proceeds = quantity * sell_price
                    fees = (buy_cost + sell_proceeds) * (total_fees / 2)
                    
                    net_pnl = sell_proceeds - buy_cost - fees
                    pnl_percentage = (net_pnl / trade_size) * 100
                    
                    # Update balances
                    gateio_balance -= buy_cost + (buy_cost * total_fees / 2)
                    mexc_balance += sell_proceeds - (sell_proceeds * total_fees / 2)
                    
                    # Record trade
                    df.loc[idx, 'inv_signal'] = 'TRADE'
                    df.loc[idx, 'inv_trade_direction'] = 'GATEIO_TO_MEXC'
                    df.loc[idx, 'inv_trade_size_usd'] = trade_size
                    df.loc[idx, 'inv_spread_captured'] = gateio_to_mexc_spread
                    df.loc[idx, 'inv_trade_pnl'] = pnl_percentage
                    
                    cumulative_pnl += pnl_percentage
                    trade_executed = True
            
            # Update cumulative P&L
            df.loc[idx, 'inv_cumulative_pnl'] = cumulative_pnl
        
        return df

    def add_spread_volatility_harvesting_backtest(
        self,
        df: pd.DataFrame,
        volatility_window: int = 20,            # Window for volatility calculation
        volatility_threshold: float = 1.0,      # Minimum volatility for entry
        extreme_negative_threshold: float = -5.0,  # Extreme negative spread threshold
        moderate_negative_threshold: float = -2.0,  # Moderate negative spread threshold
        exit_compression_threshold: float = -0.5,   # Exit when spread compresses to this level
        position_size_base_usd: float = 1000.0,    # Base position size
        max_positions: int = 3,                     # Maximum concurrent positions
        tail_hedge_cost: float = 0.01,             # 1% monthly cost for tail hedging
        total_fees: float = 0.0067,                # 0.67% total fees
    ) -> pd.DataFrame:
        """
        Backtest spread volatility harvesting strategy.
        
        Strategy: Multi-tier approach that trades spread volatility across different regimes,
        with tail hedging for extreme events.
        
        Args:
            df: DataFrame with spread data
            volatility_window: Window for volatility calculation
            volatility_threshold: Minimum volatility required for entry
            extreme_negative_threshold: Threshold for extreme negative spreads
            moderate_negative_threshold: Threshold for moderate negative spreads
            exit_compression_threshold: Exit threshold for spread compression
            position_size_base_usd: Base position size
            max_positions: Maximum concurrent positions
            tail_hedge_cost: Monthly cost of tail hedging (percentage)
            total_fees: Total trading fees
            
        Returns:
            DataFrame with volatility harvesting signals and P&L
        """
        # Initialize columns
        df['svh_signal'] = 'HOLD'
        df['svh_position_tier'] = 'NONE'  # 'EXTREME', 'MODERATE', 'HEDGE'
        df['svh_position_id'] = np.nan
        df['svh_position_size'] = 0.0
        df['svh_entry_spread'] = np.nan
        df['svh_trade_pnl'] = 0.0
        df['svh_cumulative_pnl'] = 0.0
        df['svh_active_positions'] = 0
        df['svh_tail_hedge_cost'] = 0.0
        
        # Calculate spread volatility and regime indicators
        mexc_spread = df[AnalyzerKeys.mexc_vs_gateio_futures_arb]
        gateio_spread = df[AnalyzerKeys.gateio_spot_vs_futures_arb]
        
        # Combined spread for strategy
        df['svh_combined_spread'] = (mexc_spread + gateio_spread) / 2
        
        # Volatility indicators
        df['svh_spread_volatility'] = df['svh_combined_spread'].rolling(window=volatility_window).std()
        df['svh_spread_zscore'] = ((df['svh_combined_spread'] - 
                                   df['svh_combined_spread'].rolling(window=volatility_window).mean()) /
                                  df['svh_spread_volatility'])
        
        # Regime classification
        df['svh_spread_regime'] = 'NORMAL'
        df.loc[df['svh_combined_spread'] < extreme_negative_threshold, 'svh_spread_regime'] = 'EXTREME_NEGATIVE'
        df.loc[(df['svh_combined_spread'] >= extreme_negative_threshold) & 
               (df['svh_combined_spread'] < moderate_negative_threshold), 'svh_spread_regime'] = 'MODERATE_NEGATIVE'
        df.loc[df['svh_combined_spread'] >= -0.5, 'svh_spread_regime'] = 'NORMAL_TO_POSITIVE'
        
        # Position weights by regime
        regime_weights = {
            'EXTREME_NEGATIVE': 0.5,    # Reduce size in tail events
            'MODERATE_NEGATIVE': 1.0,   # Full size
            'NORMAL_TO_POSITIVE': 0.25  # Small positions
        }
        
        # State tracking
        active_positions = []  # List of active positions
        cumulative_pnl = 0.0
        next_position_id = 1
        
        for idx in df.index:
            current_spread = df.loc[idx, 'svh_combined_spread']
            current_volatility = df.loc[idx, 'svh_spread_volatility']
            current_regime = df.loc[idx, 'svh_spread_regime']
            current_time = df.loc[idx, 'timestamp'] if 'timestamp' in df.columns else idx
            
            # Skip if insufficient data
            if pd.isna(current_spread) or pd.isna(current_volatility):
                continue
            
            # Remove expired positions and calculate exit P&L
            positions_to_remove = []
            period_pnl = 0.0
            
            for pos in active_positions:
                should_exit = False
                exit_reason = ""
                
                # Exit conditions
                if current_spread > exit_compression_threshold:
                    should_exit = True
                    exit_reason = "COMPRESSION"
                elif (hasattr(current_time, '__sub__') and 
                      (current_time - pos['entry_time']).total_seconds() > 24 * 3600):  # 24 hours max
                    should_exit = True
                    exit_reason = "MAX_TIME"
                elif current_spread < -7.0:  # Emergency exit for extreme moves
                    should_exit = True
                    exit_reason = "EMERGENCY"
                
                if should_exit:
                    # Calculate position P&L
                    spread_change = current_spread - pos['entry_spread']
                    gross_pnl = spread_change * pos['position_weight']
                    net_pnl = gross_pnl - (total_fees * 100)  # Apply fees
                    
                    period_pnl += net_pnl
                    positions_to_remove.append(pos)
                    
                    # Record exit
                    df.loc[idx, 'svh_signal'] = f'EXIT_{exit_reason}'
            
            # Remove closed positions
            for pos in positions_to_remove:
                active_positions.remove(pos)
            
            # Entry logic: Enter new positions if conditions are met
            if (len(active_positions) < max_positions and
                current_volatility > volatility_threshold and
                current_regime in ['EXTREME_NEGATIVE', 'MODERATE_NEGATIVE']):
                
                # Calculate position size based on regime
                regime_weight = regime_weights.get(current_regime, 0.5)
                position_size = position_size_base_usd * regime_weight
                
                # Additional sizing based on volatility (higher vol = smaller size)
                volatility_adjustment = min(1.0, 2.0 / current_volatility) if current_volatility > 0 else 0.5
                adjusted_size = position_size * volatility_adjustment
                
                # Create new position
                new_position = {
                    'id': next_position_id,
                    'entry_time': current_time,
                    'entry_spread': current_spread,
                    'tier': current_regime,
                    'position_size': adjusted_size,
                    'position_weight': regime_weight
                }
                
                active_positions.append(new_position)
                next_position_id += 1
                
                # Record entry
                df.loc[idx, 'svh_signal'] = 'ENTER'
                df.loc[idx, 'svh_position_tier'] = current_regime
                df.loc[idx, 'svh_position_id'] = new_position['id']
                df.loc[idx, 'svh_position_size'] = adjusted_size
                df.loc[idx, 'svh_entry_spread'] = current_spread
            
            # Apply tail hedge cost (monthly) - use position in index instead of timestamp
            period_number = list(df.index).index(idx) if idx in df.index else 0
            if period_number > 0 and period_number % 8640 == 0:  # Approximately monthly (assuming 5-min intervals)
                tail_hedge_monthly_cost = tail_hedge_cost
                period_pnl -= tail_hedge_monthly_cost
                df.loc[idx, 'svh_tail_hedge_cost'] = tail_hedge_monthly_cost
            
            # Update tracking columns
            df.loc[idx, 'svh_active_positions'] = len(active_positions)
            df.loc[idx, 'svh_trade_pnl'] = period_pnl
            cumulative_pnl += period_pnl
            df.loc[idx, 'svh_cumulative_pnl'] = cumulative_pnl
        
        return df

    def add_comprehensive_reverse_arbitrage_analysis(
        self,
        df: pd.DataFrame,
        include_all_strategies: bool = True,
        rdn_params: Optional[Dict] = None,
        inv_params: Optional[Dict] = None, 
        svh_params: Optional[Dict] = None,
    ) -> pd.DataFrame:
        """
        Add all three reverse arbitrage strategies with comprehensive indicators.
        
        Args:
            df: DataFrame with price data
            include_all_strategies: Whether to include all three strategies
            rdn_params: Parameters for reverse delta-neutral strategy
            inv_params: Parameters for inventory arbitrage strategy
            svh_params: Parameters for spread volatility harvesting strategy
            
        Returns:
            DataFrame with all strategies and comprehensive analysis
        """
        print("🚀 Adding Comprehensive Reverse Arbitrage Analysis")
        
        # Add market regime indicators
        df = self._add_market_regime_indicators(df)
        
        # Add volatility and momentum indicators
        df = self._add_volatility_momentum_indicators(df)
        
        # Add correlation indicators
        df = self._add_correlation_indicators(df)
        
        if include_all_strategies:
            # Strategy 1: Reverse Delta-Neutral
            print("📊 Adding Reverse Delta-Neutral Backtest...")
            rdn_params = rdn_params or {}
            df = self.add_reverse_delta_neutral_backtest(df, **rdn_params)
            
            # Strategy 2: Inventory Spot Arbitrage
            print("📊 Adding Inventory Spot Arbitrage Backtest...")
            inv_params = inv_params or {}
            df = self.add_inventory_spot_arbitrage_backtest(df, **inv_params)
            
            # Strategy 3: Spread Volatility Harvesting
            print("📊 Adding Spread Volatility Harvesting Backtest...")
            svh_params = svh_params or {}
            df = self.add_spread_volatility_harvesting_backtest(df, **svh_params)
            
            # Add combined strategy analysis
            df = self._add_combined_strategy_analysis(df)
        
        print("✅ Comprehensive reverse arbitrage analysis completed")
        return df

    def _add_market_regime_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add market regime classification indicators."""
        mexc_spread = df[AnalyzerKeys.mexc_vs_gateio_futures_arb]
        gateio_spread = df[AnalyzerKeys.gateio_spot_vs_futures_arb]
        
        # Combined spread for regime analysis
        df['combined_spread'] = (mexc_spread + gateio_spread) / 2
        
        # Rolling statistics for regime detection
        df['spread_mean_20'] = df['combined_spread'].rolling(window=20).mean()
        df['spread_std_20'] = df['combined_spread'].rolling(window=20).std()
        df['spread_min_20'] = df['combined_spread'].rolling(window=20).min()
        df['spread_max_20'] = df['combined_spread'].rolling(window=20).max()
        
        # Z-score for regime detection
        df['spread_zscore'] = (df['combined_spread'] - df['spread_mean_20']) / df['spread_std_20']
        
        # Market regime classification
        df['market_regime'] = 'NORMAL'
        df.loc[df['combined_spread'] < -5.0, 'market_regime'] = 'EXTREME_NEGATIVE'
        df.loc[(df['combined_spread'] >= -5.0) & (df['combined_spread'] < -2.0), 'market_regime'] = 'DEEP_NEGATIVE'
        df.loc[(df['combined_spread'] >= -2.0) & (df['combined_spread'] < -0.5), 'market_regime'] = 'MODERATE_NEGATIVE'
        df.loc[(df['combined_spread'] >= -0.5) & (df['combined_spread'] < 0.5), 'market_regime'] = 'NORMAL'
        df.loc[df['combined_spread'] >= 0.5, 'market_regime'] = 'POSITIVE'
        
        # Regime persistence indicator
        df['regime_persistence'] = (df['market_regime'] == df['market_regime'].shift(1)).astype(int).rolling(window=10).sum()
        
        return df

    def _add_volatility_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility and momentum indicators for all strategies."""
        # Spread volatility (multiple timeframes)
        df['spread_vol_5'] = df['combined_spread'].rolling(window=5).std()
        df['spread_vol_10'] = df['combined_spread'].rolling(window=10).std()
        df['spread_vol_20'] = df['combined_spread'].rolling(window=20).std()
        
        # Momentum indicators
        df['spread_momentum_3'] = df['combined_spread'].diff(3)
        df['spread_momentum_5'] = df['combined_spread'].diff(5)
        df['spread_momentum_10'] = df['combined_spread'].diff(10)
        
        # Rate of change
        df['spread_roc_5'] = (df['combined_spread'] / df['combined_spread'].shift(5) - 1) * 100
        df['spread_roc_10'] = (df['combined_spread'] / df['combined_spread'].shift(10) - 1) * 100
        
        # Volatility regime
        df['vol_regime'] = 'LOW'
        df.loc[df['spread_vol_20'] > df['spread_vol_20'].rolling(window=100).quantile(0.66), 'vol_regime'] = 'MEDIUM'
        df.loc[df['spread_vol_20'] > df['spread_vol_20'].rolling(window=100).quantile(0.90), 'vol_regime'] = 'HIGH'
        
        # Momentum regime
        df['momentum_regime'] = 'NEUTRAL'
        df.loc[df['spread_momentum_5'] > 0.1, 'momentum_regime'] = 'POSITIVE'
        df.loc[df['spread_momentum_5'] < -0.1, 'momentum_regime'] = 'NEGATIVE'
        
        return df

    def _add_correlation_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add correlation and divergence indicators."""
        mexc_spread = df[AnalyzerKeys.mexc_vs_gateio_futures_arb]
        gateio_spread = df[AnalyzerKeys.gateio_spot_vs_futures_arb]
        
        # Rolling correlation between MEXC and Gate.io spreads
        df['spread_correlation_10'] = mexc_spread.rolling(window=10).corr(gateio_spread)
        df['spread_correlation_20'] = mexc_spread.rolling(window=20).corr(gateio_spread)
        
        # Spread divergence
        df['spread_divergence'] = abs(mexc_spread - gateio_spread)
        df['spread_divergence_zscore'] = ((df['spread_divergence'] - 
                                          df['spread_divergence'].rolling(window=20).mean()) /
                                         df['spread_divergence'].rolling(window=20).std())
        
        # Spread convergence indicator
        df['spread_convergence'] = (df['spread_divergence'] < df['spread_divergence'].shift(1)).astype(int)
        
        # Price correlation between exchanges
        mexc_price = (df[AnalyzerKeys.mexc_ask] + df[AnalyzerKeys.mexc_bid]) / 2
        gateio_spot_price = (df[AnalyzerKeys.gateio_spot_ask] + df[AnalyzerKeys.gateio_spot_bid]) / 2
        gateio_futures_price = (df[AnalyzerKeys.gateio_futures_ask] + df[AnalyzerKeys.gateio_futures_bid]) / 2
        
        df['price_correlation_spot'] = mexc_price.rolling(window=20).corr(gateio_spot_price)
        df['price_correlation_futures'] = mexc_price.rolling(window=20).corr(gateio_futures_price)
        
        return df

    def _add_combined_strategy_analysis(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add combined strategy performance analysis."""
        # Combined P&L from all strategies
        rdn_pnl = df.get('rdn_cumulative_pnl', 0)
        inv_pnl = df.get('inv_cumulative_pnl', 0) 
        svh_pnl = df.get('svh_cumulative_pnl', 0)
        
        df['total_combined_pnl'] = rdn_pnl + inv_pnl + svh_pnl
        
        # Strategy allocation indicators
        df['active_strategies'] = (
            (df.get('rdn_position_open', False).astype(int)) +
            (df.get('inv_signal', 'HOLD') == 'TRADE').astype(int) +
            (df.get('svh_active_positions', 0) > 0).astype(int)
        )
        
        # Risk indicators
        df['total_exposure'] = (
            df.get('rdn_position_size', 0) +
            df.get('inv_trade_size_usd', 0) +
            df.get('svh_position_size', 0)
        )
        
        # Performance metrics per strategy
        strategies = ['rdn', 'inv', 'svh']
        for strategy in strategies:
            pnl_col = f'{strategy}_cumulative_pnl'
            if pnl_col in df.columns:
                # Rolling Sharpe ratio (annualized)
                returns = df[pnl_col].diff()
                df[f'{strategy}_sharpe_20'] = (
                    returns.rolling(window=20).mean() * np.sqrt(252 * 288) /  # 5-min periods
                    returns.rolling(window=20).std()
                )
                
                # Maximum drawdown
                rolling_max = df[pnl_col].expanding().max()
                df[f'{strategy}_drawdown'] = df[pnl_col] - rolling_max
                df[f'{strategy}_max_drawdown'] = df[f'{strategy}_drawdown'].expanding().min()
        
        return df

    def generate_reverse_arbitrage_report(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate comprehensive performance report for all reverse arbitrage strategies.
        
        Args:
            df: DataFrame with all strategy results
            
        Returns:
            Dictionary with performance metrics for each strategy
        """
        report = {
            'period_summary': {
                'total_periods': len(df),
                'date_range': f"{df.index[0]} to {df.index[-1]}" if len(df) > 0 else "No data",
                'market_regimes': df['market_regime'].value_counts().to_dict() if 'market_regime' in df.columns else {}
            },
            'strategies': {}
        }
        
        # Analyze each strategy
        strategies = [
            ('reverse_delta_neutral', 'rdn', 'Reverse Delta-Neutral'),
            ('inventory_arbitrage', 'inv', 'Inventory Spot Arbitrage'),
            ('volatility_harvesting', 'svh', 'Spread Volatility Harvesting')
        ]
        
        for strategy_name, prefix, display_name in strategies:
            pnl_col = f'{prefix}_cumulative_pnl'
            
            if pnl_col in df.columns and not df[pnl_col].isna().all():
                final_pnl = df[pnl_col].iloc[-1]
                returns = df[pnl_col].diff().dropna()
                
                # Calculate metrics
                total_trades = (df[f'{prefix}_trade_pnl'] != 0).sum() if f'{prefix}_trade_pnl' in df.columns else 0
                winning_trades = (df[f'{prefix}_trade_pnl'] > 0).sum() if f'{prefix}_trade_pnl' in df.columns else 0
                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                
                avg_return = returns.mean() if len(returns) > 0 else 0
                std_return = returns.std() if len(returns) > 0 else 0
                sharpe = (avg_return / std_return * np.sqrt(252 * 288)) if std_return > 0 else 0
                
                # Drawdown calculation
                rolling_max = df[pnl_col].expanding().max()
                drawdown = df[pnl_col] - rolling_max
                max_drawdown = drawdown.min()
                
                report['strategies'][strategy_name] = {
                    'display_name': display_name,
                    'final_pnl_pct': final_pnl,
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'win_rate_pct': win_rate,
                    'avg_trade_pnl': df[f'{prefix}_trade_pnl'].mean() if f'{prefix}_trade_pnl' in df.columns else 0,
                    'max_trade_pnl': df[f'{prefix}_trade_pnl'].max() if f'{prefix}_trade_pnl' in df.columns else 0,
                    'min_trade_pnl': df[f'{prefix}_trade_pnl'].min() if f'{prefix}_trade_pnl' in df.columns else 0,
                    'sharpe_ratio': sharpe,
                    'max_drawdown_pct': max_drawdown,
                    'volatility_pct': std_return * np.sqrt(252 * 288) if std_return > 0 else 0,
                }
            else:
                report['strategies'][strategy_name] = {
                    'display_name': display_name,
                    'status': 'No data or not executed'
                }
        
        # Combined portfolio metrics
        if 'total_combined_pnl' in df.columns:
            combined_pnl = df['total_combined_pnl'].iloc[-1]
            combined_returns = df['total_combined_pnl'].diff().dropna()
            
            report['combined_portfolio'] = {
                'final_pnl_pct': combined_pnl,
                'sharpe_ratio': (combined_returns.mean() / combined_returns.std() * np.sqrt(252 * 288)) if combined_returns.std() > 0 else 0,
                'max_drawdown_pct': (df['total_combined_pnl'] - df['total_combined_pnl'].expanding().max()).min(),
                'correlation_benefit': 'Calculated' if len([s for s in strategies if f'{s[1]}_cumulative_pnl' in df.columns]) > 1 else 'N/A'
            }
        
        return report

    def _analyze_streaks(self, is_profitable: pd.Series) -> Dict[str, Any]:
        """Analyze consecutive profitable periods."""
        streaks = []
        current_streak = 0
        
        for profitable in is_profitable:
            if profitable:
                current_streak += 1
            else:
                if current_streak > 0:
                    streaks.append(current_streak)
                current_streak = 0
        
        if current_streak > 0:
            streaks.append(current_streak)
        
        if not streaks:
            return {'count': 0, 'avg_length': 0, 'max_length': 0}
        
        return {
            'count': len(streaks),
            'avg_length': sum(streaks) / len(streaks),
            'max_length': max(streaks),
            'total_profitable_periods': sum(streaks)
        }
    
    def format_report(self, results: Dict[str, Any]) -> str:
        """Format analysis results into a readable report."""
        symbol = results['symbol']
        days = results['days_analyzed']
        
        report = f"""
🎯 ARBITRAGE ANALYSIS REPORT - {symbol} ({days} days)
{'='*60}

📊 OVERALL PROFITABILITY:
  • Profitable periods: {results['profitability_pct']:.1f}%
  • Average profit when profitable: {results['avg_profit_when_profitable']:.3f}%
  • Max profit observed: {results['max_profit']:.3f}%
  • Min profit observed: {results['min_profit']:.3f}%

🚀 OPTIMAL ENTRY POINTS (Total Arbitrage Sum):
  • Conservative (25th percentile): {results['entry_thresholds']['25th_percentile']:.3f}%
  • Aggressive (10th percentile): {results['entry_thresholds']['10th_percentile']:.3f}%
  • Very Aggressive (5th percentile): {results['entry_thresholds']['5th_percentile']:.3f}%

📈 INDIVIDUAL METRICS:
  MEXC → Gate.io Futures Arbitrage:
    Mean: {results['mexc_futures_arb_stats']['mean']:.3f}% | Std: {results['mexc_futures_arb_stats']['std']:.3f}%

  Gate.io Spot vs Futures Arbitrage:  
    Mean: {results['spot_futures_arb_stats']['mean']:.3f}% | Std: {results['spot_futures_arb_stats']['std']:.3f}%

  Total Arbitrage (After Fees):
    Mean: {results['total_arb_stats']['mean']:.3f}% | Std: {results['total_arb_stats']['std']:.3f}%

⏱️  PROFITABLE STREAKS:
  • Number of profitable streaks: {results['profitable_streaks']['count']}
  • Average streak length: {results['profitable_streaks']['avg_length']:.1f} periods
  • Longest streak: {results['profitable_streaks']['max_length']} periods

💡 STRATEGY RECOMMENDATIONS:
  1. Enter positions when total arbitrage > {results['entry_thresholds']['10th_percentile']:.3f}%
  2. Exit when arbitrage approaches 0% or turns negative
  3. Average holding period: ~{results['profitable_streaks']['avg_length']:.0f} × 5min = {results['profitable_streaks']['avg_length']*5:.0f} minutes
  
⚠️  RISK FACTORS:
  • Assumes {self.SPREAD_BPS} bps spread | {self.TOTAL_FEES}% total fees
  • Based on simulated bid/ask from close prices
  • Historical analysis - future results may vary
"""
        return report


if __name__ == "__main__":
    async def main():
        await initialize_database_manager()  # Ensure DB manager is initialized
        analyzer = ArbitrageAnalyzer()
        
        # Quick test with 1 day of data
        try:
            df, results = await analyzer.run_analysis("F_USDT", days=1)
            print(analyzer.format_report(results))
            
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
    
    asyncio.run(main())