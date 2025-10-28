#!/usr/bin/env python3
"""
Standalone Database Backtest

Simple backtest using database snapshots without complex dependencies.
"""

import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import os


class Signal(Enum):
    ENTER = "ENTER"
    EXIT = "EXIT"
    HOLD = "HOLD"


@dataclass
class BacktestConfig:
    symbol_base: str = "F"
    symbol_quote: str = "USDT"
    days: int = 3
    position_size_usd: float = 1000.0
    fees_bps: float = 20.0  # 0.2% total fees
    min_transfer_time_minutes: int = 10


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime] = None
    entry_spread: float = 0.0
    exit_spread: float = 0.0
    pnl: Optional[float] = None
    reason: str = ""


class DatabaseBacktest:
    """Simplified backtest using database snapshots"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.trades: List[Trade] = []
        self.open_trades: List[Trade] = []
        
        # History for signal calculation (same as proven backtest)
        self.mexc_futures_history: List[float] = []
        self.gateio_spot_futures_history: List[float] = []
    
    async def connect_db(self):
        """Connect to database"""
        # Use environment variables for database connection
        db_host = os.getenv('POSTGRES_HOST', 'localhost')
        db_port = int(os.getenv('POSTGRES_PORT', '5432'))
        db_user = os.getenv('POSTGRES_USER', 'arbitrage_user')
        db_password = os.getenv('POSTGRES_PASSWORD', 'dev_password_2024')
        db_name = os.getenv('POSTGRES_DB', 'arbitrage_data')
        
        self.conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
    
    async def load_data(self) -> pd.DataFrame:
        """Load book ticker snapshots from database"""
        print(f"📥 Loading {self.config.symbol_base}/{self.config.symbol_quote} data...")
        
        # Calculate time range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=self.config.days)
        
        # Query for synchronized book ticker data
        query = """
        WITH mexc_data AS (
            SELECT 
                timestamp,
                bid_price as mexc_bid,
                ask_price as mexc_ask
            FROM book_ticker_snapshots
            WHERE exchange = 'MEXC'
            AND symbol_base = $1
            AND symbol_quote = $2
            AND timestamp BETWEEN $3 AND $4
        ),
        gateio_spot_data AS (
            SELECT 
                timestamp,
                bid_price as gateio_spot_bid,
                ask_price as gateio_spot_ask
            FROM book_ticker_snapshots
            WHERE exchange = 'GATEIO'
            AND symbol_base = $1
            AND symbol_quote = $2
            AND timestamp BETWEEN $3 AND $4
        ),
        gateio_futures_data AS (
            SELECT 
                timestamp,
                bid_price as gateio_futures_bid,
                ask_price as gateio_futures_ask
            FROM book_ticker_snapshots
            WHERE exchange = 'GATEIO_FUTURES'
            AND symbol_base = $1
            AND symbol_quote = $2
            AND timestamp BETWEEN $3 AND $4
        )
        SELECT 
            m.timestamp,
            m.mexc_bid,
            m.mexc_ask,
            g.gateio_spot_bid,
            g.gateio_spot_ask,
            f.gateio_futures_bid,
            f.gateio_futures_ask
        FROM mexc_data m
        FULL OUTER JOIN gateio_spot_data g ON m.timestamp = g.timestamp
        FULL OUTER JOIN gateio_futures_data f ON m.timestamp = f.timestamp
        WHERE m.mexc_bid IS NOT NULL 
        AND g.gateio_spot_bid IS NOT NULL 
        AND f.gateio_futures_bid IS NOT NULL
        ORDER BY timestamp
        """
        
        rows = await self.conn.fetch(
            query, 
            self.config.symbol_base, 
            self.config.symbol_quote,
            start_time, 
            end_time
        )
        
        if not rows:
            raise ValueError(f"No data found for {self.config.symbol_base}/{self.config.symbol_quote}")
        
        # Convert to DataFrame and ensure numeric columns are float
        df = pd.DataFrame([dict(row) for row in rows])
        
        # Convert decimal columns to float for pandas compatibility
        numeric_cols = ['mexc_bid', 'mexc_ask', 'gateio_spot_bid', 'gateio_spot_ask', 
                       'gateio_futures_bid', 'gateio_futures_ask']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        print(f"✅ Loaded {len(df)} synchronized snapshots")
        print(f"   Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        return df
    
    def calculate_spreads(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate arbitrage spreads using exact backtest formula"""
        
        # MEXC vs Gate.io Futures (using backtest formula)
        df['mexc_futures_spread'] = (
            (df['gateio_futures_bid'] - df['mexc_ask']) / 
            df['gateio_futures_bid'] * 100
        )
        
        # Gate.io Spot vs Futures (using backtest formula)
        df['gateio_spot_futures_spread'] = (
            (df['gateio_spot_bid'] - df['gateio_futures_ask']) /
            df['gateio_spot_bid'] * 100
        )
        
        # Show spread statistics
        print(f"\n📊 Spread Statistics:")
        mexc_mean = df['mexc_futures_spread'].mean()
        mexc_std = df['mexc_futures_spread'].std()
        gateio_mean = df['gateio_spot_futures_spread'].mean() 
        gateio_std = df['gateio_spot_futures_spread'].std()
        
        print(f"MEXC→Futures: mean={mexc_mean:.4f}%, std={mexc_std:.4f}%")
        print(f"Gate.io Spot→Futures: mean={gateio_mean:.4f}%, std={gateio_std:.4f}%")
        
        return df
    
    def generate_signal(self, mexc_spread: float, gateio_spread: float) -> Signal:
        """Simple signal generation (can be replaced with actual calculate_arb_signals)"""
        
        # Add to history
        self.mexc_futures_history.append(mexc_spread)
        self.gateio_spot_futures_history.append(gateio_spread)
        
        # Keep only recent history
        max_history = 500
        if len(self.mexc_futures_history) > max_history:
            self.mexc_futures_history = self.mexc_futures_history[-max_history:]
            self.gateio_spot_futures_history = self.gateio_spot_futures_history[-max_history:]
        
        # Need minimum history
        if len(self.mexc_futures_history) < 50:
            return Signal.HOLD
        
        # Simple percentile-based signals (simplified version of backtest logic)
        mexc_history = self.mexc_futures_history
        gateio_history = self.gateio_spot_futures_history
        
        # Calculate thresholds
        mexc_25th = np.percentile(mexc_history, 25)
        gateio_75th = np.percentile(gateio_history, 75)
        
        # Entry: MEXC spread below 25th percentile (good arbitrage opportunity)
        if mexc_spread < mexc_25th:
            return Signal.ENTER
        
        # Exit: Gate.io spread above 75th percentile (close arbitrage)
        elif gateio_spread > gateio_75th:
            return Signal.EXIT
        
        return Signal.HOLD
    
    def run_simulation(self, df: pd.DataFrame):
        """Run trading simulation"""
        print(f"\n🔄 Running simulation on {len(df)} data points...")
        
        for idx, row in df.iterrows():
            current_time = row['timestamp']
            mexc_spread = row['mexc_futures_spread']
            gateio_spread = row['gateio_spot_futures_spread']
            
            # Update trade statuses (transfer delays)
            self.update_trades(current_time)
            
            # Generate signal
            signal = self.generate_signal(mexc_spread, gateio_spread)
            
            # Execute trades
            if signal == Signal.ENTER and len(self.open_trades) == 0:
                self.open_trade(current_time, mexc_spread, gateio_spread)
            elif signal == Signal.EXIT and self.open_trades:
                self.close_trades(current_time, mexc_spread, gateio_spread)
    
    def update_trades(self, current_time: datetime):
        """Update trade statuses based on transfer delays"""
        # For simplicity, assume transfer completes after min_transfer_time_minutes
        pass
    
    def open_trade(self, timestamp: datetime, mexc_spread: float, gateio_spread: float):
        """Open new arbitrage trade"""
        trade = Trade(
            entry_time=timestamp,
            entry_spread=mexc_spread,
            reason="Entry signal"
        )
        self.trades.append(trade)
        self.open_trades.append(trade)
        print(f"📈 ENTER at {timestamp}: mexc_spread={mexc_spread:.4f}%")
    
    def close_trades(self, timestamp: datetime, mexc_spread: float, gateio_spread: float):
        """Close open trades"""
        for trade in self.open_trades:
            # Check minimum transfer time
            elapsed = (timestamp - trade.entry_time).total_seconds() / 60
            if elapsed >= self.config.min_transfer_time_minutes:
                
                # Calculate PnL (simplified)
                spread_improvement = gateio_spread - trade.entry_spread
                gross_pnl = spread_improvement / 100 * self.config.position_size_usd
                fees = (self.config.fees_bps / 10000) * self.config.position_size_usd
                net_pnl = gross_pnl - fees
                
                trade.exit_time = timestamp
                trade.exit_spread = gateio_spread
                trade.pnl = net_pnl
                
                print(f"📉 EXIT at {timestamp}: spread_improvement={spread_improvement:.4f}%, pnl=${net_pnl:.2f}")
        
        # Clear open trades
        self.open_trades = [t for t in self.open_trades if t.exit_time is None]
    
    def calculate_performance(self) -> Dict:
        """Calculate performance metrics"""
        completed_trades = [t for t in self.trades if t.pnl is not None]
        
        if not completed_trades:
            return {"total_trades": 0, "total_pnl": 0}
        
        pnls = [t.pnl for t in completed_trades]
        total_pnl = sum(pnls)
        winning_trades = len([p for p in pnls if p > 0])
        
        return {
            "total_trades": len(completed_trades),
            "total_pnl": total_pnl,
            "winning_trades": winning_trades,
            "losing_trades": len(completed_trades) - winning_trades,
            "win_rate": winning_trades / len(completed_trades) * 100,
            "avg_pnl": total_pnl / len(completed_trades),
            "best_trade": max(pnls),
            "worst_trade": min(pnls)
        }
    
    async def run(self):
        """Run complete backtest"""
        await self.connect_db()
        
        try:
            # Load and process data
            df = await self.load_data()
            df = self.calculate_spreads(df)
            
            # Store df for reference
            self.df = df
            
            # Run simulation
            self.run_simulation(df)
            
            # Calculate results
            performance = self.calculate_performance()
            
            return performance
            
        finally:
            await self.conn.close()


async def main():
    """Run standalone database backtest"""
    print("🚀 Standalone Database Backtest")
    print("=" * 50)
    
    # Check environment variables
    required_vars = ['POSTGRES_HOST', 'POSTGRES_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {missing_vars}")
        print("Example setup:")
        print("export POSTGRES_HOST=localhost")
        print("export POSTGRES_PASSWORD=dev_password_2024")
        return
    
    # Configuration
    config = BacktestConfig(
        symbol_base="F",
        symbol_quote="USDT", 
        days=2,
        position_size_usd=1000
    )
    
    print(f"📊 Configuration:")
    print(f"  Symbol: {config.symbol_base}/{config.symbol_quote}")
    print(f"  Period: {config.days} days")
    print(f"  Position Size: ${config.position_size_usd}")
    
    # Run backtest
    backtest = DatabaseBacktest(config)
    
    try:
        results = await backtest.run()
        
        print(f"\n🎯 RESULTS:")
        print(f"💰 Total P&L: ${results['total_pnl']:.2f}")
        print(f"📈 Total Trades: {results['total_trades']}")
        
        if results['total_trades'] > 0:
            print(f"🎯 Win Rate: {results['win_rate']:.1f}%")
            print(f"📊 Avg P&L per Trade: ${results['avg_pnl']:.2f}")
            print(f"🔥 Best Trade: ${results['best_trade']:.2f}")
            print(f"💀 Worst Trade: ${results['worst_trade']:.2f}")
        else:
            print(f"ℹ️  No trades executed - signals may need adjustment")
            print(f"   MEXC spread range: {backtest.df['mexc_futures_spread'].min():.4f}% to {backtest.df['mexc_futures_spread'].max():.4f}%")
            print(f"   Gate.io spread range: {backtest.df['gateio_spot_futures_spread'].min():.4f}% to {backtest.df['gateio_spot_futures_spread'].max():.4f}%")
        
        if results['total_pnl'] > 0:
            print(f"\n🎉 Strategy is PROFITABLE with database data!")
        else:
            print(f"\n⚠️  Strategy shows LOSSES with database data")
            print("This suggests the production losses are real, not just implementation bugs")
            
    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())