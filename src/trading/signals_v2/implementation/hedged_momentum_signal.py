"""
Hedged Momentum Trading Signal - Delta Neutral Implementation

This strategy captures momentum moves while maintaining hedged exposure through
simultaneous spot and futures positions across exchanges.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import numpy as np

from exchanges.structs.common import Symbol, AssetName
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from trading.data_sources.candles_loader import CandlesLoader
from trading.signals_v2.entities import PositionEntry, TradeEntry, PerformanceMetrics
from trading.signals_v2.report_utils import generate_generic_report

@dataclass
class HedgedMomentumParams:
    """Parameters for hedged momentum strategy."""
    
    # Momentum Detection
    momentum_lookback: int = 20           # Periods for momentum calculation
    momentum_threshold: float = 2.0       # % move to trigger entry
    rsi_oversold: float = 30             # RSI oversold level
    rsi_overbought: float = 70           # RSI overbought level
    
    # Position Management
    position_size_usd: float = 1000.0    # Base position size
    hedge_ratio: float = 0.9             # Hedge ratio (0.9 = 90% hedged)
    max_position_time_minutes: int = 60   # Maximum hold time
    
    # Risk Management
    stop_loss_pct: float = 3.0           # Stop loss percentage
    take_profit_pct: float = 1.5         # Take profit percentage
    max_daily_positions: int = 10        # Maximum positions per day
    
    # Dynamic Hedging
    volatility_adjustment: bool = True    # Adjust hedge based on volatility
    rehedge_threshold: float = 0.2       # When to adjust hedge (20% delta change)

@dataclass 
class HedgedPosition:
    """Represents a hedged position with spot and futures legs."""
    
    entry_time: datetime
    symbol: Symbol
    
    # Spot leg (momentum direction)
    spot_exchange: ExchangeEnum
    spot_side: str  # "long" or "short"
    spot_price: float
    spot_quantity: float
    
    # Futures leg (hedge)
    futures_exchange: ExchangeEnum
    futures_side: str  # opposite of spot
    futures_price: float
    futures_quantity: float
    
    # Position tracking
    unrealized_pnl: float = 0.0
    hedge_ratio: float = 0.9
    last_rehedge_time: Optional[datetime] = None

class HedgedMomentumSignal:
    """
    Hedged Momentum Trading Strategy
    
    Captures momentum moves while maintaining market-neutral exposure through
    simultaneous spot and futures positions.
    
    Strategy Logic:
    1. Detect momentum using technical indicators
    2. Enter spot position in momentum direction
    3. Simultaneously enter offsetting futures position
    4. Monitor and rehedge as needed
    5. Exit when momentum exhausts or risk limits hit
    """
    
    def __init__(self, params: HedgedMomentumParams):
        self.params = params
        self.candles_loader = CandlesLoader()
        
        # Strategy state
        self.current_positions: Dict[str, HedgedPosition] = {}
        self.daily_position_count = 0
        self.last_trade_date: Optional[datetime] = None
        
        # Technical indicators cache
        self.price_data: Dict[ExchangeEnum, pd.DataFrame] = {}
        self.momentum_signals: Dict[ExchangeEnum, Dict] = {}
        
    async def update_market_data(self, symbol: Symbol, hours: int = 4) -> None:
        """Update market data for all exchanges."""
        
        from datetime import datetime, timezone, timedelta
        
        exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
        
        for exchange in exchanges:
            try:
                # Calculate time range
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(hours=hours)
                
                df = await self.candles_loader.download_candles(
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=KlineInterval.MINUTE_1,
                    start_date=start_time,
                    end_date=end_time
                )
                
                if not df.empty:
                    # Calculate technical indicators
                    df = self._calculate_indicators(df)
                    self.price_data[exchange] = df
                    
                    # Generate momentum signals
                    self.momentum_signals[exchange] = self._analyze_momentum(df)
                    
                print(f"INFO: Updated data for {exchange.value}: {len(df)} candles")
                
            except Exception as e:
                print(f"ERROR: Failed to update data for {exchange.value}: {e}")
                
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators for momentum detection."""
        
        # Momentum indicators
        df['returns'] = df['close'].pct_change()
        df['momentum'] = df['returns'].rolling(self.params.momentum_lookback).sum() * 100
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Volatility
        df['volatility'] = df['returns'].rolling(20).std() * 100
        
        # Price levels
        df['sma_20'] = df['close'].rolling(20).mean()
        df['price_vs_sma'] = (df['close'] / df['sma_20'] - 1) * 100
        
        return df
        
    def _analyze_momentum(self, df: pd.DataFrame) -> Dict:
        """Analyze momentum signals from technical indicators."""
        
        if len(df) < self.params.momentum_lookback:
            return {"signal": "HOLD", "strength": 0.0, "reason": "Insufficient data"}
            
        latest = df.iloc[-1]
        
        # Momentum analysis
        momentum = latest['momentum']
        rsi = latest['rsi']
        volatility = latest['volatility']
        price_vs_sma = latest['price_vs_sma']
        
        # Signal generation logic
        signals = []
        
        # Strong upward momentum - LONG signals only (spot market constraints)
        # We can only BUY spot assets (go LONG) since we cannot short without inventory
        if (momentum > self.params.momentum_threshold and 
            rsi > 50 and rsi < self.params.rsi_overbought and
            price_vs_sma > 1.0):
            signals.append(("LONG", abs(momentum)))
            
        # REMOVED: Strong downward momentum SHORT signals
        # Spot markets do not allow shorting without pre-existing asset inventory
        # For hedge strategies, we can only trade LONG momentum in spot markets
            
        # Determine final signal
        if signals:
            direction, strength = max(signals, key=lambda x: x[1])
            return {
                "signal": direction,
                "strength": strength,
                "momentum": momentum,
                "rsi": rsi,
                "volatility": volatility,
                "reason": f"{direction} momentum: {momentum:.2f}%, RSI: {rsi:.1f}"
            }
        else:
            return {
                "signal": "HOLD", 
                "strength": 0.0,
                "momentum": momentum,
                "rsi": rsi,
                "volatility": volatility,
                "reason": f"No clear signal - momentum: {momentum:.2f}%, RSI: {rsi:.1f}"
            }
            
    def _calculate_hedge_ratio(self, volatility: float) -> float:
        """Calculate dynamic hedge ratio based on volatility."""
        
        base_ratio = self.params.hedge_ratio
        
        if not self.params.volatility_adjustment:
            return base_ratio
            
        # Adjust hedge ratio based on volatility
        # Higher volatility = higher hedge ratio (more protection)
        vol_adjustment = min(volatility / 5.0, 0.2)  # Max 20% adjustment
        
        adjusted_ratio = base_ratio + vol_adjustment
        return min(adjusted_ratio, 1.0)  # Cap at 100%
        
    def generate_entry_signal(self, symbol: Symbol, current_time: datetime = None) -> Optional[Dict]:
        """Generate entry signal for hedged momentum strategy."""
        
        # Check if we have data for all required exchanges
        required_exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO_FUTURES]
        
        for exchange in required_exchanges:
            if exchange not in self.momentum_signals:
                return None
                
        # Check daily position limit
        current_date = datetime.now(timezone.utc).date()
        if self.last_trade_date != current_date:
            self.daily_position_count = 0
            self.last_trade_date = current_date
            
        if self.daily_position_count >= self.params.max_daily_positions:
            return None
            
        # Get momentum signals
        mexc_signal = self.momentum_signals[ExchangeEnum.MEXC]
        futures_signal = self.momentum_signals[ExchangeEnum.GATEIO_FUTURES]
        
        # Check for strong momentum signal - LONG only (spot market constraints)
        if mexc_signal["signal"] == "LONG" and mexc_signal["strength"] > self.params.momentum_threshold:
            
            # Get current prices - FIX: Use specific time instead of always using latest
            if current_time is not None:
                # For backtest: use specific time
                mexc_data = self.price_data[ExchangeEnum.MEXC]
                futures_data = self.price_data[ExchangeEnum.GATEIO_FUTURES]
                
                if current_time in mexc_data.index and current_time in futures_data.index:
                    mexc_price = mexc_data.loc[current_time]['close']
                    futures_price = futures_data.loc[current_time]['close']
                else:
                    # Use closest available data
                    mexc_idx = mexc_data.index.get_indexer([current_time], method='ffill')[0]
                    futures_idx = futures_data.index.get_indexer([current_time], method='ffill')[0]
                    
                    if mexc_idx == -1 or futures_idx == -1:
                        return None  # No data available
                        
                    mexc_price = mexc_data.iloc[mexc_idx]['close']
                    futures_price = futures_data.iloc[futures_idx]['close']
            else:
                # For live trading: use latest data
                mexc_price = self.price_data[ExchangeEnum.MEXC].iloc[-1]['close']
                futures_price = self.price_data[ExchangeEnum.GATEIO_FUTURES].iloc[-1]['close']
            
            # Calculate position sizes
            spot_size_usd = self.params.position_size_usd
            volatility = mexc_signal["volatility"]
            hedge_ratio = self._calculate_hedge_ratio(volatility)
            futures_size_usd = spot_size_usd * hedge_ratio
            
            return {
                "action": "ENTER",
                "direction": mexc_signal["signal"],
                "symbol": symbol,
                "spot_exchange": ExchangeEnum.MEXC,
                "futures_exchange": ExchangeEnum.GATEIO_FUTURES,
                "spot_price": mexc_price,
                "futures_price": futures_price,
                "spot_size_usd": spot_size_usd,
                "futures_size_usd": futures_size_usd,
                "hedge_ratio": hedge_ratio,
                "signal_strength": mexc_signal["strength"],
                "volatility": volatility,
                "reason": mexc_signal["reason"]
            }
            
        return None
        
    def check_exit_conditions(self, position: HedgedPosition, current_time: datetime = None) -> Optional[Dict]:
        """Check if position should be exited."""
        
        if current_time is None:
            current_time = datetime.now(timezone.utc)
            
        # Ensure both timestamps have timezone info
        if position.entry_time.tzinfo is None:
            position.entry_time = position.entry_time.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
            
        hold_time = (current_time - position.entry_time).total_seconds() / 60
        
        # Get current prices at the specific time during backtest
        try:
            # Ensure current_time is timezone-aware and matches DataFrame index
            spot_data = self.price_data[position.spot_exchange]
            futures_data = self.price_data[position.futures_exchange]
            
            # Convert current_time to match the DataFrame's timezone
            if spot_data.index.tz is not None and current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=spot_data.index.tz)
            elif spot_data.index.tz is None and current_time.tzinfo is not None:
                current_time = current_time.replace(tzinfo=None)
            
            # Find the exact current time or the closest previous time
            try:
                # Try exact time first
                if current_time in spot_data.index:
                    spot_price = spot_data.loc[current_time]['close']
                    futures_price = futures_data.loc[current_time]['close']
                else:
                    # Use the closest available time using proper indexing
                    spot_idx = spot_data.index.get_indexer([current_time], method='ffill')[0]
                    futures_idx = futures_data.index.get_indexer([current_time], method='ffill')[0]
                    
                    if spot_idx == -1 or futures_idx == -1:
                        return None  # No data available
                        
                    actual_spot_time = spot_data.index[spot_idx]
                    actual_futures_time = futures_data.index[futures_idx]
                    spot_price = spot_data.iloc[spot_idx]['close']
                    futures_price = futures_data.iloc[futures_idx]['close']
                    
            except (KeyError, IndexError, TypeError):
                # Fallback to latest available price
                spot_price = spot_data.iloc[-1]['close']
                futures_price = futures_data.iloc[-1]['close']
            
            # DEBUG: Check if prices are realistic
            if spot_price < position.spot_price * 0.5 or spot_price > position.spot_price * 2.0:
                print(f"WARNING: Unrealistic exit price detected!")
                print(f"  Entry: spot=${position.spot_price:.4f}, futures=${position.futures_price:.4f}")
                print(f"  Exit:  spot=${spot_price:.4f}, futures=${futures_price:.4f}")
                print(f"  Time: {current_time}, Hold time: {hold_time:.1f}min")
                print(f"  Spot data columns: {list(spot_data.columns)}")
                print(f"  Spot data shape: {spot_data.shape}, last 3 prices: {spot_data['close'].tail(3).values}")
                
                # Use entry price as fallback to prevent unrealistic exits
                spot_price = position.spot_price
                futures_price = position.futures_price
                print(f"  Using entry prices as fallback")
            
        except (KeyError, IndexError, TypeError) as e:
            # Fallback to latest available price if time lookup fails
            print(f"WARNING: Time lookup failed for P&L calculation: {e}, using latest prices")
            spot_price = self.price_data[position.spot_exchange].iloc[-1]['close']
            futures_price = self.price_data[position.futures_exchange].iloc[-1]['close']
        
        # Calculate current P&L
        if position.spot_side == "long":
            spot_pnl = (spot_price - position.spot_price) * position.spot_quantity
        else:
            spot_pnl = (position.spot_price - spot_price) * position.spot_quantity
            
        if position.futures_side == "short":
            futures_pnl = (position.futures_price - futures_price) * position.futures_quantity
        else:
            futures_pnl = (futures_price - position.futures_price) * position.futures_quantity
            
        total_pnl = spot_pnl + futures_pnl
        total_invested = position.spot_price * position.spot_quantity
        pnl_pct = (total_pnl / total_invested) * 100
        
        # Exit conditions
        exit_reasons = []
        
        # Time-based exit
        if hold_time >= self.params.max_position_time_minutes:
            exit_reasons.append(f"Max hold time reached: {hold_time:.1f}min")
            
        # Profit taking
        if pnl_pct >= self.params.take_profit_pct:
            exit_reasons.append(f"Take profit hit: {pnl_pct:.2f}%")
            
        # Stop loss
        if pnl_pct <= -self.params.stop_loss_pct:
            exit_reasons.append(f"Stop loss hit: {pnl_pct:.2f}%")
            
        # Momentum reversal
        momentum_signal = self.momentum_signals.get(position.spot_exchange, {})
        if momentum_signal.get("signal") == "HOLD":
            exit_reasons.append("Momentum exhausted")
            
        if exit_reasons:
            return {
                "action": "EXIT",
                "position": position,
                "spot_price": spot_price,
                "futures_price": futures_price,
                "pnl_usd": total_pnl,
                "pnl_pct": pnl_pct,
                "hold_time_minutes": hold_time,
                "reasons": exit_reasons
            }
            
        return None
        
    async def run_backtest(self, symbol: Symbol, hours: int = 48) -> PerformanceMetrics:
        """Run backtest for hedged momentum strategy."""
        
        print(f"INFO: Starting hedged momentum backtest for {symbol} over {hours} hours")
        
        # Get historical data
        await self.update_market_data(symbol, hours)
        
        # Initialize backtesting
        trades = []
        positions = []
        equity_curve = []
        
        # Get the common time range across all exchanges
        mexc_data = self.price_data[ExchangeEnum.MEXC]
        futures_data = self.price_data[ExchangeEnum.GATEIO_FUTURES]
        
        start_time = max(mexc_data.index.min(), futures_data.index.min())
        end_time = min(mexc_data.index.max(), futures_data.index.max())
        
        print(f"INFO: Backtest period: {start_time} to {end_time}")
        
        # Simulate trading on minute-by-minute basis
        current_time = start_time
        current_positions = {}
        
        while current_time <= end_time:
            # Update to current time slice
            for exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO_FUTURES]:
                if exchange in self.price_data:
                    current_data = self.price_data[exchange].loc[:current_time]
                    if len(current_data) >= self.params.momentum_lookback:
                        # Recalculate indicators up to current time
                        current_df = current_data.copy()
                        current_df = self._calculate_indicators(current_df)
                        self.momentum_signals[exchange] = self._analyze_momentum(current_df)
            
            # Check for new entry signals
            if len(current_positions) == 0:  # Only one position at a time for simplicity
                entry_signal = self.generate_entry_signal(symbol, current_time)
                
                if entry_signal:
                    # Create hedged position - LONG spot only (spot market constraints)
                    # We BUY spot assets and HEDGE with SHORT futures position
                    position = HedgedPosition(
                        entry_time=current_time,
                        symbol=symbol,
                        spot_exchange=entry_signal["spot_exchange"],
                        spot_side="long",  # Always LONG in spot (BUY assets)
                        spot_price=entry_signal["spot_price"],
                        spot_quantity=entry_signal["spot_size_usd"] / entry_signal["spot_price"],
                        futures_exchange=entry_signal["futures_exchange"],
                        futures_side="short",  # Always SHORT futures (hedge the spot position)
                        futures_price=entry_signal["futures_price"],
                        futures_quantity=entry_signal["futures_size_usd"] / entry_signal["futures_price"],
                        hedge_ratio=entry_signal["hedge_ratio"]
                    )
                    
                    current_positions[f"pos_{len(positions)}"] = position
                    self.daily_position_count += 1
                    
                    print(f"INFO: Entered hedged position at {current_time}: {entry_signal['direction']} "
                          f"spot@{entry_signal['spot_price']:.4f}, "
                          f"hedge@{entry_signal['futures_price']:.4f}")
            
            # Check exit conditions for existing positions
            positions_to_close = []
            for pos_id, position in current_positions.items():
                exit_signal = self.check_exit_conditions(position, current_time)
                
                if exit_signal:
                    positions_to_close.append((pos_id, exit_signal))
                    
            # Close positions
            for pos_id, exit_signal in positions_to_close:
                position = exit_signal["position"]
                
                # Create trade record
                trade = {
                    "entry_time": position.entry_time,
                    "exit_time": current_time,
                    "symbol": str(symbol),
                    "direction": position.spot_side,
                    "spot_entry": position.spot_price,
                    "spot_exit": exit_signal["spot_price"],
                    "futures_entry": position.futures_price,
                    "futures_exit": exit_signal["futures_price"],
                    "pnl_usd": exit_signal["pnl_usd"],
                    "pnl_pct": exit_signal["pnl_pct"],
                    "hold_time": exit_signal["hold_time_minutes"],
                    "exit_reason": ", ".join(exit_signal["reasons"])
                }
                
                trades.append(trade)
                positions.append(position)
                del current_positions[pos_id]
                exit_spot = exit_signal["spot_price"]
                exit_futures = exit_signal["futures_price"]
                print(f"INFO: Closed position: P&L=${exit_signal['pnl_usd']:.2f} "
                      f"spot @ {exit_spot} futures @ {exit_futures} "
                      f"({exit_signal['pnl_pct']:.2f}%) in {exit_signal['hold_time_minutes']:.1f}min")
            
            # Move to next minute
            current_time += pd.Timedelta(minutes=1)
            
        # Calculate performance metrics
        if trades:
            total_pnl = sum(t["pnl_usd"] for t in trades)
            win_rate = sum(1 for t in trades if t["pnl_usd"] > 0) / len(trades) * 100
            avg_trade = total_pnl / len(trades)
            
            # Calculate Sharpe ratio
            returns = [t["pnl_pct"] for t in trades]
            if len(returns) > 1:
                sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
            else:
                sharpe = 0
                
            # Max drawdown calculation
            cumulative_pnl = []
            running_pnl = 0
            for trade in trades:
                running_pnl += trade["pnl_usd"]
                cumulative_pnl.append(running_pnl)
                
            max_drawdown = 0
            if cumulative_pnl:
                peak = 0
                for pnl in cumulative_pnl:
                    peak = max(peak, pnl)
                    if peak > 0:
                        drawdown = (peak - pnl) / self.params.position_size_usd * 100
                        max_drawdown = max(max_drawdown, drawdown)
            
            metrics = PerformanceMetrics(
                total_pnl_usd=total_pnl,
                total_pnl_pct=(total_pnl / self.params.position_size_usd) * 100,
                win_rate=win_rate,
                avg_trade_pnl=avg_trade,
                max_drawdown=max_drawdown,
                sharpe_ratio=sharpe,
                trades=[],  # We'll store trade details separately
                trade_freq=len(trades) / (hours / 24)  # trades per day
            )
            
            print(f"INFO: Backtest completed: {len(trades)} trades, "
                  f"P&L=${total_pnl:.2f}, Win Rate={win_rate:.1f}%")
            
            return metrics, trades
            
        else:
            print("WARNING: No trades generated during backtest period")
            return PerformanceMetrics(), []