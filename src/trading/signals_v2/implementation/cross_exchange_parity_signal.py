"""
Cross-Exchange Price Parity Arbitrage Signal

This strategy identifies price parity opportunities between exchanges and profits
from temporary price divergences through mean reversion.

Strategy Logic:
1. Monitor price differences between MEXC spot and Gate.io futures
2. Enter positions when prices are near parity (minimal spread)
3. Exit when price divergence spikes create profit opportunities
4. Profit from mean reversion back to equilibrium

Key Advantages over Momentum:
- Buy at fair value, not momentum peaks
- Profit from predictable mean reversion
- Lower risk due to price parity entry
- Natural stop-loss when divergence exceeds normal ranges
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from exchanges.structs.common import Symbol, AssetName
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from trading.data_sources.candles_loader import CandlesLoader
from trading.signals_v2.entities import PositionEntry, TradeEntry, PerformanceMetrics
from trading.signals_v2.report_utils import generate_generic_report

@dataclass
class CrossExchangeParityParams:
    """Parameters for cross-exchange parity arbitrage strategy."""
    
    # Parity Detection
    parity_threshold_bps: float = 5.0      # Max spread to consider "parity" (5 basis points)
    lookback_periods: int = 50             # Periods to calculate median spread
    divergence_multiplier: float = 2.5     # Exit when spread > median * multiplier
    
    # Position Management
    position_size_usd: float = 1000.0      # Position size
    max_position_time_minutes: int = 120   # Maximum hold time (2 hours)
    min_hold_time_minutes: int = 5         # Minimum hold time to avoid noise
    
    # Risk Management
    max_spread_bps: float = 50.0           # Emergency exit if spread too wide (50 bps)
    take_profit_bps: float = 15.0          # Take profit target (15 basis points)
    max_daily_positions: int = 5           # Conservative position limit
    
    # Quality Filters
    min_volume_ratio: float = 0.1          # Min volume ratio between exchanges
    volatility_filter: bool = True         # Avoid high volatility periods

@dataclass 
class ParityPosition:
    """Represents a cross-exchange parity position."""
    
    entry_time: datetime
    symbol: Symbol
    
    # Position details
    spot_exchange: ExchangeEnum
    futures_exchange: ExchangeEnum
    spot_price: float
    futures_price: float
    entry_spread_bps: float
    
    # Position sizing
    spot_quantity: float
    futures_quantity: float
    position_size_usd: float
    
    # Tracking
    median_spread_bps: float
    target_exit_spread_bps: float
    unrealized_pnl: float = 0.0
    max_favorable_spread: float = 0.0  # Track best unrealized profit

class CrossExchangeParitySignal:
    """
    Cross-Exchange Price Parity Arbitrage Strategy
    
    This strategy profits from temporary price divergences between exchanges
    by entering at parity and exiting on mean reversion spikes.
    
    Key Innovation:
    - Enter when prices are EQUAL (low risk)
    - Exit when prices DIVERGE significantly (high profit)
    - Natural mean reversion provides consistent profits
    """
    
    def __init__(self, params: CrossExchangeParityParams):
        self.params = params
        self.candles_loader = CandlesLoader()
        
        # Strategy state
        self.current_positions: Dict[str, ParityPosition] = {}
        self.daily_position_count = 0
        self.last_trade_date: Optional[datetime] = None
        
        # Price data and analytics
        self.price_data: Dict[ExchangeEnum, pd.DataFrame] = {}
        self.spread_history: List[float] = []
        self.median_spread_bps: float = 0.0
        
    async def update_market_data(self, symbol: Symbol, hours: int = 6) -> None:
        """Update market data and calculate spread analytics."""
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)
        
        # Load price data from both exchanges
        exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO_FUTURES]
        
        for exchange in exchanges:
            try:
                df = await self.candles_loader.download_candles(
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=KlineInterval.MINUTE_1,
                    start_date=start_time,
                    end_date=end_time
                )
                
                if not df.empty:
                    # Add volume-weighted average price
                    df['vwap'] = (df['high'] + df['low'] + df['close'] * 2) / 4
                    df['volume_sma'] = df['volume'].rolling(window=20).mean()
                    self.price_data[exchange] = df
                    
            except Exception as e:
                print(f"Error loading data for {exchange}: {e}")
                continue
                
        # Calculate spread analytics
        await self._update_spread_analytics()
        
    async def _update_spread_analytics(self) -> None:
        """Calculate spread statistics and median spread."""
        
        if len(self.price_data) < 2:
            return
            
        mexc_data = self.price_data.get(ExchangeEnum.MEXC)
        futures_data = self.price_data.get(ExchangeEnum.GATEIO_FUTURES)
        
        if mexc_data is None or futures_data is None:
            return
            
        # Align timestamps and calculate spreads
        common_times = mexc_data.index.intersection(futures_data.index)
        
        if len(common_times) < self.params.lookback_periods:
            return
            
        spreads_bps = []
        
        for timestamp in common_times[-self.params.lookback_periods:]:
            mexc_price = mexc_data.loc[timestamp]['close']
            futures_price = futures_data.loc[timestamp]['close']
            
            # Calculate spread in basis points
            mid_price = (mexc_price + futures_price) / 2
            spread_bps = abs(mexc_price - futures_price) / mid_price * 10000
            spreads_bps.append(spread_bps)
            
        if spreads_bps:
            self.spread_history = spreads_bps
            self.median_spread_bps = np.median(spreads_bps)
    
    def _check_volume_conditions(self, current_time: datetime = None) -> bool:
        """Check if volume conditions are suitable for trading."""
        
        if not self.params.min_volume_ratio:
            return True
            
        mexc_data = self.price_data.get(ExchangeEnum.MEXC)
        futures_data = self.price_data.get(ExchangeEnum.GATEIO_FUTURES)
        
        if mexc_data is None or futures_data is None:
            return False
            
        try:
            if current_time:
                # For backtesting
                mexc_volume = mexc_data.loc[current_time]['volume']
                futures_volume = futures_data.loc[current_time]['volume']
            else:
                # For live trading
                mexc_volume = mexc_data.iloc[-1]['volume']
                futures_volume = futures_data.iloc[-1]['volume']
                
            # Check minimum volume ratio
            if mexc_volume <= 0 or futures_volume <= 0:
                return False
                
            volume_ratio = min(mexc_volume, futures_volume) / max(mexc_volume, futures_volume)
            return volume_ratio >= self.params.min_volume_ratio
            
        except Exception:
            return False
    
    def generate_entry_signal(self, symbol: Symbol, current_time: datetime = None) -> Optional[Dict]:
        """Generate entry signal when prices are at parity."""
        
        # Check daily position limit
        current_date = (current_time or datetime.now(timezone.utc)).date()
        if self.last_trade_date != current_date:
            self.daily_position_count = 0
            self.last_trade_date = current_date
            
        if self.daily_position_count >= self.params.max_daily_positions:
            return None
            
        # Check if we have sufficient data
        if not self.spread_history or self.median_spread_bps <= 0:
            return None
            
        # Check volume conditions
        if not self._check_volume_conditions(current_time):
            return None
            
        # Get current prices
        mexc_data = self.price_data.get(ExchangeEnum.MEXC)
        futures_data = self.price_data.get(ExchangeEnum.GATEIO_FUTURES)
        
        if mexc_data is None or futures_data is None:
            return None
            
        try:
            if current_time is not None:
                # For backtesting
                if current_time not in mexc_data.index or current_time not in futures_data.index:
                    return None
                mexc_price = mexc_data.loc[current_time]['close']
                futures_price = futures_data.loc[current_time]['close']
            else:
                # For live trading
                mexc_price = mexc_data.iloc[-1]['close']
                futures_price = futures_data.iloc[-1]['close']
                
        except Exception:
            return None
        
        # Calculate current spread
        mid_price = (mexc_price + futures_price) / 2
        current_spread_bps = abs(mexc_price - futures_price) / mid_price * 10000
        
        # Check if spread is near parity (within threshold)
        if current_spread_bps <= self.params.parity_threshold_bps:
            
            # Determine direction based on which exchange is cheaper
            if mexc_price < futures_price:
                # MEXC cheaper: BUY spot, SELL futures
                direction = "LONG_SPOT_SHORT_FUTURES"
                spread_direction = "positive"  # Expect futures to drop or spot to rise
            else:
                # Futures cheaper: SELL spot, BUY futures  
                direction = "SHORT_SPOT_LONG_FUTURES"
                spread_direction = "negative"  # Expect spot to drop or futures to rise
                
            # Calculate target exit spread
            target_exit_spread_bps = max(
                self.median_spread_bps * self.params.divergence_multiplier,
                self.params.take_profit_bps
            )
            
            return {
                "action": "ENTER",
                "direction": direction,
                "symbol": symbol,
                "spot_exchange": ExchangeEnum.MEXC,
                "futures_exchange": ExchangeEnum.GATEIO_FUTURES,
                "spot_price": mexc_price,
                "futures_price": futures_price,
                "entry_spread_bps": current_spread_bps,
                "median_spread_bps": self.median_spread_bps,
                "target_exit_spread_bps": target_exit_spread_bps,
                "spread_direction": spread_direction,
                "reason": f"Price parity entry: {current_spread_bps:.1f}bps spread, median: {self.median_spread_bps:.1f}bps"
            }
            
        return None
    
    def check_exit_conditions(self, position: ParityPosition, current_time: datetime = None) -> Optional[Dict]:
        """Check if position should be exited based on spread divergence."""
        
        if current_time is None:
            current_time = datetime.now(timezone.utc)
            
        # Check maximum hold time
        hold_time = (current_time - position.entry_time).total_seconds() / 60
        
        if hold_time >= self.params.max_position_time_minutes:
            return {
                "action": "EXIT",
                "reason": f"Maximum hold time reached: {hold_time:.1f} minutes",
                "exit_type": "time_stop"
            }
        
        # Don't exit too quickly (avoid noise)
        if hold_time < self.params.min_hold_time_minutes:
            return None
            
        # Get current prices
        mexc_data = self.price_data.get(ExchangeEnum.MEXC)
        futures_data = self.price_data.get(ExchangeEnum.GATEIO_FUTURES)
        
        if mexc_data is None or futures_data is None:
            return None
            
        try:
            if current_time not in mexc_data.index or current_time not in futures_data.index:
                return None
                
            current_mexc_price = mexc_data.loc[current_time]['close']
            current_futures_price = futures_data.loc[current_time]['close']
            
        except Exception:
            return None
        
        # Calculate current spread
        mid_price = (current_mexc_price + current_futures_price) / 2
        current_spread_bps = abs(current_mexc_price - current_futures_price) / mid_price * 10000
        
        # Calculate P&L
        spot_pnl = (current_mexc_price - position.spot_price) * position.spot_quantity
        futures_pnl = (position.futures_price - current_futures_price) * position.futures_quantity
        
        if "SHORT_SPOT" in position.symbol.__str__():  # Approximate direction check
            spot_pnl = -spot_pnl  # Reverse P&L for short positions
            futures_pnl = -futures_pnl
            
        total_pnl = spot_pnl + futures_pnl
        pnl_bps = (total_pnl / position.position_size_usd) * 10000
        
        # Update max favorable spread
        position.max_favorable_spread = max(position.max_favorable_spread, current_spread_bps)
        
        # Exit conditions
        
        # 1. Target profit reached (spread diverged enough)
        if current_spread_bps >= position.target_exit_spread_bps:
            return {
                "action": "EXIT",
                "current_spot_price": current_mexc_price,
                "current_futures_price": current_futures_price,
                "current_spread_bps": current_spread_bps,
                "total_pnl": total_pnl,
                "pnl_bps": pnl_bps,
                "reason": f"Target spread reached: {current_spread_bps:.1f}bps >= {position.target_exit_spread_bps:.1f}bps",
                "exit_type": "take_profit"
            }
        
        # 2. Emergency exit if spread becomes too extreme
        if current_spread_bps >= self.params.max_spread_bps:
            return {
                "action": "EXIT",
                "current_spot_price": current_mexc_price,
                "current_futures_price": current_futures_price,
                "current_spread_bps": current_spread_bps,
                "total_pnl": total_pnl,
                "pnl_bps": pnl_bps,
                "reason": f"Emergency exit: spread too wide {current_spread_bps:.1f}bps",
                "exit_type": "emergency_stop"
            }
        
        # 3. Trailing stop: exit if spread has compressed significantly from peak
        if position.max_favorable_spread > position.target_exit_spread_bps:
            spread_compression = (position.max_favorable_spread - current_spread_bps) / position.max_favorable_spread
            if spread_compression > 0.5:  # 50% retracement from peak
                return {
                    "action": "EXIT",
                    "current_spot_price": current_mexc_price,
                    "current_futures_price": current_futures_price,
                    "current_spread_bps": current_spread_bps,
                    "total_pnl": total_pnl,
                    "pnl_bps": pnl_bps,
                    "reason": f"Trailing stop: spread compressed {spread_compression*100:.1f}% from peak {position.max_favorable_spread:.1f}bps",
                    "exit_type": "trailing_stop"
                }
        
        return None
    
    async def run_backtest(self, symbol: Symbol, hours: int = 72) -> Tuple[PerformanceMetrics, List[TradeEntry]]:
        """Run backtest for cross-exchange parity strategy."""
        
        print(f"🧪 Running Cross-Exchange Parity Backtest for {symbol}")
        
        # Update market data
        await self.update_market_data(symbol, hours)
        
        if len(self.price_data) < 2:
            print("❌ Insufficient market data")
            return PerformanceMetrics(), []
        
        # Get time range for backtest
        mexc_data = self.price_data[ExchangeEnum.MEXC]
        futures_data = self.price_data[ExchangeEnum.GATEIO_FUTURES]
        
        common_times = mexc_data.index.intersection(futures_data.index)
        if len(common_times) < 100:
            print("❌ Insufficient overlapping data")
            return PerformanceMetrics(), []
        
        backtest_start = common_times[50]  # Skip first 50 for warm-up
        backtest_end = common_times[-1]
        
        print(f"📅 Backtest period: {backtest_start} to {backtest_end}")
        print(f"📊 Median spread: {self.median_spread_bps:.2f} basis points")
        
        # Run backtest
        trades: List[TradeEntry] = []
        positions: Dict[str, ParityPosition] = {}
        
        for current_time in common_times[50:]:  # Skip warm-up period
            
            # Check for new entry signals
            if not positions:  # Only one position at a time
                entry_signal = self.generate_entry_signal(symbol, current_time)
                
                if entry_signal:
                    # Create position
                    position = ParityPosition(
                        entry_time=current_time,
                        symbol=symbol,
                        spot_exchange=entry_signal["spot_exchange"],
                        futures_exchange=entry_signal["futures_exchange"],
                        spot_price=entry_signal["spot_price"],
                        futures_price=entry_signal["futures_price"],
                        entry_spread_bps=entry_signal["entry_spread_bps"],
                        spot_quantity=self.params.position_size_usd / entry_signal["spot_price"],
                        futures_quantity=self.params.position_size_usd / entry_signal["futures_price"],
                        position_size_usd=self.params.position_size_usd,
                        median_spread_bps=entry_signal["median_spread_bps"],
                        target_exit_spread_bps=entry_signal["target_exit_spread_bps"]
                    )
                    
                    positions[f"{symbol}_parity"] = position
                    self.daily_position_count += 1
                    
                    print(f"📈 Entered parity position at {current_time}: "
                          f"spot@{entry_signal['spot_price']:.4f}, futures@{entry_signal['futures_price']:.4f} "
                          f"({entry_signal['entry_spread_bps']:.1f}bps spread)")
            
            # Check exit conditions for existing positions
            to_close = []
            for pos_key, position in positions.items():
                exit_signal = self.check_exit_conditions(position, current_time)
                
                if exit_signal:
                    # Calculate P&L and trade details
                    hold_time = (current_time - position.entry_time).total_seconds() / 60
                    
                    trade = {
                        "entry_time": position.entry_time,
                        "exit_time": current_time,
                        "symbol": str(symbol),
                        "direction": "ARBITRAGE",
                        "entry_price": (position.spot_price + position.futures_price) / 2,
                        "exit_price": (exit_signal["current_spot_price"] + exit_signal["current_futures_price"]) / 2,
                        "quantity": position.position_size_usd,
                        "pnl_usd": exit_signal["total_pnl"],
                        "pnl_pct": exit_signal["pnl_bps"] / 100,  # Convert bps to percentage
                        "hold_time_minutes": hold_time,
                        "exit_reason": exit_signal["reason"]
                    }
                    
                    trades.append(trade)
                    to_close.append(pos_key)
                    
                    print(f"📉 Closed position: P&L=${exit_signal['total_pnl']:.2f} "
                          f"spot @ {exit_signal['current_spot_price']:.4f} "
                          f"futures @ {exit_signal['current_futures_price']:.4f} "
                          f"({exit_signal['pnl_bps']:.1f}bps) in {hold_time:.1f}min "
                          f"({exit_signal['exit_type']})")
            
            # Remove closed positions
            for pos_key in to_close:
                del positions[pos_key]
        
        # Calculate performance metrics
        total_pnl = sum(trade["pnl_usd"] for trade in trades)
        winning_trades = [t for t in trades if t["pnl_usd"] > 0]
        
        metrics = PerformanceMetrics(
            total_pnl_usd=total_pnl,
            total_pnl_pct=(total_pnl / (self.params.position_size_usd * len(trades))) * 100 if trades else 0,
            win_rate=(len(winning_trades) / len(trades)) * 100 if trades else 0,
            avg_trade_pnl=total_pnl / len(trades) if trades else 0,
            max_drawdown=0,  # TODO: Calculate proper drawdown
            sharpe_ratio=0,  # TODO: Calculate Sharpe ratio
            trade_freq=len(trades) / (hours / 24) if hours > 0 else 0
        )
        
        print(f"📊 Backtest completed: {len(trades)} trades, P&L=${total_pnl:.2f}, Win Rate={metrics.win_rate:.1f}%")
        
        return metrics, trades
