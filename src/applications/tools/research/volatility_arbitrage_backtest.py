"""
Simple MVP backtest framework for volatility arbitrage strategy.

This module implements a minimal lines-of-code backtest for testing volatility-based
cross-pair arbitrage with delta-neutral positioning through futures hedging.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json

from applications.tools.research.volatility_indicators import VolatilityIndicators, VolatilitySignal


@dataclass
class BacktestConfig:
    """Configuration for volatility arbitrage backtest"""
    initial_capital: float = 100000.0
    max_position_size: float = 0.1  # 10% of capital per position
    maker_fee: float = 0.001  # 0.1%
    taker_fee: float = 0.0015  # 0.15%
    futures_fee: float = 0.0005  # 0.05% for futures hedge
    default_execution: str = 'taker'  # 'maker', 'taker', or 'hybrid'
    stop_loss_pct: float = 0.05  # 5% stop loss
    take_profit_pct: float = 0.03  # 3% take profit


@dataclass
class Position:
    """Represents a trading position"""
    symbol: str
    size: float
    entry_price: float
    entry_time: datetime
    position_type: str  # 'spot_long', 'spot_short', 'futures_hedge'
    
    @property
    def notional(self) -> float:
        return abs(self.size * self.entry_price)


@dataclass
class Trade:
    """Represents a completed trade"""
    timestamp: datetime
    action: str  # 'open', 'close', 'switch'
    from_symbol: Optional[str]
    to_symbol: Optional[str]
    size: float
    price: float
    fees: float
    execution_type: str
    pnl: float = 0.0
    notes: str = ""


@dataclass
class BacktestResults:
    """Backtest results summary"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)


class VolatilityArbitrageBacktest:
    """Minimal LoC backtest for volatility arbitrage strategy with delta neutrality"""
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.volatility_indicators = VolatilityIndicators()
        
        # Portfolio state
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.equity_history: List[Tuple[datetime, float]] = []
        self.trades: List[Trade] = []
        
        # Performance tracking
        self.peak_equity = self.config.initial_capital
        self.max_drawdown = 0.0
        
    def get_position_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate total position value"""
        total_value = 0.0
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                total_value += position.size * current_prices[symbol]
        return total_value
    
    def get_total_equity(self, current_prices: Dict[str, float]) -> float:
        """Calculate total portfolio equity"""
        return self.cash + self.get_position_value(current_prices)
    
    def calculate_position_size(self, signal_strength: float, price: float) -> float:
        """Calculate position size based on signal strength and risk management"""
        base_size = self.config.initial_capital * self.config.max_position_size
        adjusted_size = base_size * min(signal_strength, 2.0)  # Cap at 2x base
        return adjusted_size / price  # Convert to units
    
    def calculate_fees(self, notional: float, execution_type: str = None) -> float:
        """Calculate trading fees"""
        execution_type = execution_type or self.config.default_execution
        
        if execution_type == 'maker':
            return notional * self.config.maker_fee
        elif execution_type == 'taker':
            return notional * self.config.taker_fee
        elif execution_type == 'hybrid':
            # Assume 50% maker, 50% taker for hybrid execution
            return notional * (self.config.maker_fee + self.config.taker_fee) / 2
        else:
            return notional * self.config.taker_fee
    
    def calculate_delta_hedge(self, spot_position: Position, correlation: float = 0.8) -> float:
        """Calculate futures hedge size for delta neutrality"""
        # Simplified delta calculation - in practice would use more sophisticated models
        hedge_ratio = correlation * spot_position.size
        return -hedge_ratio  # Opposite direction for hedging
    
    def execute_position_switch(self, signal: VolatilitySignal, current_prices: Dict[str, float], 
                               timestamp: datetime, execution_type: str = None) -> List[Trade]:
        """Execute position switch based on volatility signal"""
        execution_type = execution_type or self.config.default_execution
        trades_executed = []
        
        if signal.action != 'switch' or not signal.from_pair or not signal.to_pair:
            return trades_executed
        
        from_price = current_prices.get(signal.from_pair)
        to_price = current_prices.get(signal.to_pair)
        
        if not from_price or not to_price:
            return trades_executed
        
        # Calculate new position size
        position_size = self.calculate_position_size(signal.strength, to_price)
        
        # Close existing position if any
        if signal.from_pair in self.positions:
            old_position = self.positions[signal.from_pair]
            close_notional = old_position.notional
            close_fees = self.calculate_fees(close_notional, execution_type)
            
            # Calculate PnL for closed position
            pnl = old_position.size * (from_price - old_position.entry_price)
            
            # Record closing trade
            close_trade = Trade(
                timestamp=timestamp,
                action='close',
                from_symbol=signal.from_pair,
                to_symbol=None,
                size=old_position.size,
                price=from_price,
                fees=close_fees,
                execution_type=execution_type,
                pnl=pnl,
                notes=f"Close for switch, VRD: {signal.vrd_score:.3f}"
            )
            
            trades_executed.append(close_trade)
            self.trades.append(close_trade)
            self.cash += old_position.size * from_price - close_fees
            del self.positions[signal.from_pair]
        
        # Open new position
        open_notional = position_size * to_price
        open_fees = self.calculate_fees(open_notional, execution_type)
        
        if self.cash >= open_notional + open_fees:
            # Create new position
            new_position = Position(
                symbol=signal.to_pair,
                size=position_size,
                entry_price=to_price,
                entry_time=timestamp,
                position_type='spot_long'
            )
            
            # Record opening trade
            open_trade = Trade(
                timestamp=timestamp,
                action='open',
                from_symbol=None,
                to_symbol=signal.to_pair,
                size=position_size,
                price=to_price,
                fees=open_fees,
                execution_type=execution_type,
                pnl=0.0,
                notes=f"Open from switch, Strength: {signal.strength:.3f}"
            )
            
            trades_executed.append(open_trade)
            self.trades.append(open_trade)
            self.positions[signal.to_pair] = new_position
            self.cash -= open_notional + open_fees
            
            # Add futures hedge (simplified)
            hedge_size = self.calculate_delta_hedge(new_position)
            hedge_fees = abs(hedge_size) * to_price * self.config.futures_fee
            
            if abs(hedge_size * to_price) > 100:  # Minimum hedge size
                hedge_position = Position(
                    symbol=f"{signal.to_pair}_FUTURES",
                    size=hedge_size,
                    entry_price=to_price,
                    entry_time=timestamp,
                    position_type='futures_hedge'
                )
                
                hedge_trade = Trade(
                    timestamp=timestamp,
                    action='hedge',
                    from_symbol=None,
                    to_symbol=f"{signal.to_pair}_FUTURES",
                    size=hedge_size,
                    price=to_price,
                    fees=hedge_fees,
                    execution_type='taker',  # Futures typically taker
                    pnl=0.0,
                    notes="Delta hedge"
                )
                
                trades_executed.append(hedge_trade)
                self.trades.append(hedge_trade)
                self.positions[f"{signal.to_pair}_FUTURES"] = hedge_position
                self.cash -= hedge_fees
        
        return trades_executed
    
    def check_stop_loss_take_profit(self, current_prices: Dict[str, float], timestamp: datetime) -> List[Trade]:
        """Check and execute stop loss / take profit orders"""
        trades_executed = []
        positions_to_close = []
        
        for symbol, position in self.positions.items():
            if position.position_type == 'futures_hedge':
                continue  # Don't close hedges independently
                
            current_price = current_prices.get(symbol)
            if not current_price:
                continue
            
            # Calculate unrealized PnL percentage
            pnl_pct = (current_price - position.entry_price) / position.entry_price
            
            # Check stop loss
            if pnl_pct <= -self.config.stop_loss_pct:
                positions_to_close.append((symbol, 'stop_loss'))
            
            # Check take profit  
            elif pnl_pct >= self.config.take_profit_pct:
                positions_to_close.append((symbol, 'take_profit'))
        
        # Execute closes
        for symbol, reason in positions_to_close:
            position = self.positions[symbol]
            price = current_prices[symbol]
            notional = position.notional
            fees = self.calculate_fees(notional, 'taker')  # Market orders for stops
            
            pnl = position.size * (price - position.entry_price)
            
            close_trade = Trade(
                timestamp=timestamp,
                action='close',
                from_symbol=symbol,
                to_symbol=None,
                size=position.size,
                price=price,
                fees=fees,
                execution_type='taker',
                pnl=pnl,
                notes=f"Auto close: {reason}"
            )
            
            trades_executed.append(close_trade)
            self.trades.append(close_trade)
            self.cash += position.size * price - fees
            del self.positions[symbol]
            
            # Close corresponding hedge if exists
            hedge_symbol = f"{symbol}_FUTURES"
            if hedge_symbol in self.positions:
                hedge_position = self.positions[hedge_symbol]
                hedge_fees = abs(hedge_position.size) * price * self.config.futures_fee
                
                hedge_close_trade = Trade(
                    timestamp=timestamp,
                    action='close_hedge',
                    from_symbol=hedge_symbol,
                    to_symbol=None,
                    size=hedge_position.size,
                    price=price,
                    fees=hedge_fees,
                    execution_type='taker',
                    pnl=hedge_position.size * (price - hedge_position.entry_price),
                    notes=f"Close hedge for {reason}"
                )
                
                trades_executed.append(hedge_close_trade)
                self.trades.append(hedge_close_trade)
                self.cash += hedge_position.size * price - hedge_fees
                del self.positions[hedge_symbol]
        
        return trades_executed
    
    def update_performance_metrics(self, current_prices: Dict[str, float], timestamp: datetime):
        """Update performance tracking metrics"""
        current_equity = self.get_total_equity(current_prices)
        self.equity_history.append((timestamp, current_equity))
        
        # Update max drawdown
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        else:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity
            self.max_drawdown = max(self.max_drawdown, drawdown)
    
    def run_backtest(self, data_dict: Dict[str, pd.DataFrame], 
                    start_date: datetime = None, end_date: datetime = None) -> BacktestResults:
        """Run backtest over historical data"""
        
        if not data_dict:
            return BacktestResults()
        
        # Get common time index
        all_indices = [df.index for df in data_dict.values() if not df.empty]
        if not all_indices:
            return BacktestResults()
        
        # Find overlapping time range
        common_start = max(idx.min() for idx in all_indices)
        common_end = min(idx.max() for idx in all_indices)
        
        if start_date:
            common_start = max(common_start, start_date)
        if end_date:
            common_end = min(common_end, end_date)
        
        # Resample all data to common frequency
        resampled_data = {}
        for symbol, df in data_dict.items():
            if not df.empty:
                df_slice = df.loc[common_start:common_end]
                if not df_slice.empty:
                    resampled_data[symbol] = df_slice
        
        if not resampled_data:
            return BacktestResults()
        
        # Get common timestamps
        common_index = resampled_data[list(resampled_data.keys())[0]].index
        for df in resampled_data.values():
            common_index = common_index.intersection(df.index)
        
        print(f"🚀 Running backtest from {common_start} to {common_end}")
        print(f"📊 Processing {len(common_index)} time periods")
        
        # Main backtest loop
        for timestamp in common_index:
            
            # Get current prices (using close prices)
            current_prices = {}
            for symbol, df in resampled_data.items():
                if timestamp in df.index:
                    current_prices[symbol] = df.loc[timestamp, 'close']
            
            if len(current_prices) < 2:
                continue
            
            # Check stop loss / take profit
            self.check_stop_loss_take_profit(current_prices, timestamp)
            
            # Generate volatility signals
            opportunities = self.volatility_indicators.scan_opportunities(
                {symbol: df.loc[:timestamp] for symbol, df in resampled_data.items()}
            )
            
            # Execute trades for best opportunity
            if opportunities:
                ranked = self.volatility_indicators.rank_opportunities(opportunities)
                best_signal = ranked[0][1]  # Get best signal
                
                self.execute_position_switch(best_signal, current_prices, timestamp)
            
            # Update performance metrics
            self.update_performance_metrics(current_prices, timestamp)
        
        # Calculate final results
        return self.calculate_results()
    
    def calculate_results(self) -> BacktestResults:
        """Calculate final backtest results"""
        total_trades = len(self.trades)
        total_pnl = sum(trade.pnl for trade in self.trades)
        total_fees = sum(trade.fees for trade in self.trades)
        
        winning_trades = sum(1 for trade in self.trades if trade.pnl > 0)
        losing_trades = sum(1 for trade in self.trades if trade.pnl < 0)
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        avg_trade_pnl = total_pnl / total_trades if total_trades > 0 else 0.0
        
        # Calculate Sharpe ratio (simplified)
        if self.equity_history:
            returns = []
            for i in range(1, len(self.equity_history)):
                prev_equity = self.equity_history[i-1][1]
                curr_equity = self.equity_history[i][1]
                returns.append((curr_equity - prev_equity) / prev_equity)
            
            if returns:
                sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0.0
            else:
                sharpe_ratio = 0.0
        else:
            sharpe_ratio = 0.0
        
        return BacktestResults(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            total_pnl=total_pnl,
            total_fees=total_fees,
            max_drawdown=self.max_drawdown,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            avg_trade_pnl=avg_trade_pnl,
            trades=self.trades,
            equity_curve=self.equity_history
        )
    
    def save_results(self, results: BacktestResults, output_path: str = "backtest_results.json"):
        """Save backtest results to file"""
        results_dict = {
            'summary': {
                'total_trades': results.total_trades,
                'winning_trades': results.winning_trades,
                'losing_trades': results.losing_trades,
                'win_rate': results.win_rate,
                'total_pnl': results.total_pnl,
                'total_fees': results.total_fees,
                'net_pnl': results.total_pnl - results.total_fees,
                'max_drawdown': results.max_drawdown,
                'sharpe_ratio': results.sharpe_ratio,
                'avg_trade_pnl': results.avg_trade_pnl
            },
            'trades': [
                {
                    'timestamp': trade.timestamp.isoformat(),
                    'action': trade.action,
                    'from_symbol': trade.from_symbol,
                    'to_symbol': trade.to_symbol,
                    'size': trade.size,
                    'price': trade.price,
                    'fees': trade.fees,
                    'pnl': trade.pnl,
                    'execution_type': trade.execution_type,
                    'notes': trade.notes
                }
                for trade in results.trades
            ],
            'equity_curve': [
                {
                    'timestamp': timestamp.isoformat(),
                    'equity': equity
                }
                for timestamp, equity in results.equity_curve
            ]
        }
        
        with open(output_path, 'w') as f:
            json.dump(results_dict, f, indent=2, default=str)
        
        print(f"💾 Backtest results saved to {output_path}")
        return output_path