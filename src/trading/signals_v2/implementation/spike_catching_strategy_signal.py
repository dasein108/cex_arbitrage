"""
Spike-Catching Strategy Signal

Strategy that places wide limit orders on spots and futures, catches spikes,
immediately hedges to delta-neutral, then exits when price stabilizes.
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum, IntEnum

from trading.signals_v2.strategy_signal import StrategySignal
from trading.signals_v2.entities import ArbitrageTrade, PerformanceMetrics, BacktestingParams, PositionEntry, TradeEntry
from exchanges.structs import Side
from trading.indicators.candles_spikes_indicator import CandlesSpikeIndicator
from trading.data_sources.column_utils import get_column_key
from exchanges.structs import ExchangeEnum, Symbol, Fees

class SpikeSignal(IntEnum):
    ENTER = 1
    EXIT = 2
    HOLD = 0

class PositionState(Enum):
    SETUP = "setup"          # Placing wide limits
    WAITING = "waiting"      # Waiting for spike to hit limits
    HEDGED = "hedged"        # Delta-neutral position active
    CLOSED = "closed"        # Position closed


@dataclass
class SpikeLimits:
    """Limit order levels for spike catching"""
    mexc_buy: float
    mexc_sell: float
    gateio_buy: float
    gateio_sell: float
    futures_buy: float
    futures_sell: float


class SpikeCatchingStrategySignal(StrategySignal):
    """
    Strategy that catches spikes using wide limits and immediately hedges to delta-neutral
    """
    
    @property
    def name(self) -> str:
        return "Spike Catching Strategy"
    
    def __init__(self, 
                 symbol: Symbol,
                 spike_offset_multiplier: float = 2.5,
                 stabilization_threshold: float = 0.5,
                 max_position_time_minutes: int = 30,
                 backtesting_params: Optional[BacktestingParams] = None,
                 fees: Optional[Dict[ExchangeEnum, Fees]] = None):
        
        self.symbol = symbol
        self.backtesting_params = backtesting_params or BacktestingParams()
        self.fees = fees or {}
        
        self.spike_offset_multiplier = spike_offset_multiplier
        self.stabilization_threshold = stabilization_threshold
        self.max_position_time_minutes = max_position_time_minutes
        
        # Initialize spike indicator
        self.spike_indicator = CandlesSpikeIndicator(
            exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES],
            symbol=symbol,
            timeframe=None,  # Will be set by data
            lookback_period_hours=24
        )
        
        # Strategy state
        self.state = PositionState.SETUP
        self.current_limits: Optional[SpikeLimits] = None
        self.active_position: Optional[PositionEntry] = None
        self.analysis_results = {
            'total_setups': 0,
            'spike_catches': 0,
            'successful_hedges': 0,
            'profitable_exits': 0
        }

    def _get_current_prices(self, data: pd.Series) -> Dict[str, float]:
        """Extract current prices for all exchanges"""
        # Check if we have close prices (from candles) or bid/ask prices (from book ticker)
        mexc_close_col = get_column_key(ExchangeEnum.MEXC, 'close')
        if mexc_close_col in data.index:
            # Use close prices from candles data
            return {
                'mexc': data[get_column_key(ExchangeEnum.MEXC, 'close')],
                'gateio': data[get_column_key(ExchangeEnum.GATEIO, 'close')],
                'futures': data[get_column_key(ExchangeEnum.GATEIO_FUTURES, 'close')]
            }
        else:
            # Use mid prices from bid/ask data
            return {
                'mexc': (data[get_column_key(ExchangeEnum.MEXC, 'bid_price')] + data[get_column_key(ExchangeEnum.MEXC, 'ask_price')]) / 2,
                'gateio': (data[get_column_key(ExchangeEnum.GATEIO, 'bid_price')] + data[get_column_key(ExchangeEnum.GATEIO, 'ask_price')]) / 2,
                'futures': (data[get_column_key(ExchangeEnum.GATEIO_FUTURES, 'bid_price')] + data[get_column_key(ExchangeEnum.GATEIO_FUTURES, 'ask_price')]) / 2
            }

    def _calculate_dynamic_offset(self, data: pd.Series) -> float:
        """Calculate dynamic offset based on volatility"""
        volatilities = []
        for exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]:
            vol_col = get_column_key(exchange, 'volatility')
            if vol_col in data.index:
                volatilities.append(data[vol_col])
        
        if volatilities:
            avg_volatility = np.mean(volatilities)
            # Offset = volatility * multiplier, minimum 1%, maximum 5%
            return np.clip(avg_volatility * self.spike_offset_multiplier, 1.0, 5.0)
        else:
            return 2.0  # Default 2% offset

    def _setup_limits(self, data: pd.Series) -> SpikeLimits:
        """Setup wide limit orders for spike catching"""
        prices = self._get_current_prices(data)
        offset_pct = self._calculate_dynamic_offset(data) / 100.0
        
        # 🔍 DEBUG: Market analysis logging
        print(f"📈 MARKET ANALYSIS at {data.name}:")
        print(f"   Current Prices: MEXC={prices['mexc']:.6f}, GATEIO={prices['gateio']:.6f}, FUTURES={prices['futures']:.6f}")
        
        # Calculate spreads between exchanges
        mexc_gateio_spread = ((prices['mexc'] - prices['gateio']) / prices['gateio']) * 100
        mexc_futures_spread = ((prices['mexc'] - prices['futures']) / prices['futures']) * 100
        gateio_futures_spread = ((prices['gateio'] - prices['futures']) / prices['futures']) * 100
        
        print(f"   Cross-Exchange Spreads: MEXC-GATEIO={mexc_gateio_spread:.3f}%, MEXC-FUTURES={mexc_futures_spread:.3f}%, GATEIO-FUTURES={gateio_futures_spread:.3f}%")
        print(f"   Dynamic Offset: {offset_pct*100:.2f}%")
        
        # Check volatility information if available
        volatilities = []
        for exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]:
            vol_col = get_column_key(exchange, 'volatility')
            if vol_col in data.index:
                volatilities.append(data[vol_col])
        
        if volatilities:
            avg_vol = np.mean(volatilities)
            print(f"   Average Volatility: {avg_vol:.2f}%")
        
        # Spot exchanges: wide buy/sell limits
        mexc_buy = prices['mexc'] * (1 - offset_pct)
        mexc_sell = prices['mexc'] * (1 + offset_pct)
        gateio_buy = prices['gateio'] * (1 - offset_pct)
        gateio_sell = prices['gateio'] * (1 + offset_pct)
        
        # Futures: opposite with safe spread (slightly tighter to ensure hedge profit)
        futures_spread = 0.001  # 0.1% safety margin
        futures_buy = prices['futures'] * (1 - offset_pct + futures_spread)
        futures_sell = prices['futures'] * (1 + offset_pct - futures_spread)
        
        print(f"   New Limits: MEXC buy={mexc_buy:.6f} sell={mexc_sell:.6f}")
        print(f"              GATEIO buy={gateio_buy:.6f} sell={gateio_sell:.6f}")
        print(f"              FUTURES buy={futures_buy:.6f} sell={futures_sell:.6f}")
        
        return SpikeLimits(
            mexc_buy=mexc_buy,
            mexc_sell=mexc_sell,
            gateio_buy=gateio_buy,
            gateio_sell=gateio_sell,
            futures_buy=futures_buy,
            futures_sell=futures_sell
        )

    def _detect_spike_fill(self, data: pd.Series, limits: SpikeLimits) -> Optional[Dict]:
        """Check if any limits would have been filled by current price action"""
        prices = self._get_current_prices(data)
        
        # ✅ DEBUG: Check if we have spike indicator data
        spike_data = {}
        for exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]:
            spike_col = get_column_key(exchange, 'is_spike')
            deviation_col = get_column_key(exchange, 'deviation_pct')
            volatility_col = get_column_key(exchange, 'volatility')
            
            if spike_col in data.index:
                spike_data[exchange.value] = {
                    'is_spike': data[spike_col],
                    'deviation_pct': data.get(deviation_col, 0.0),
                    'volatility': data.get(volatility_col, 0.0)
                }
        
        # 🔍 DEBUG: Log spike indicator status
        if spike_data:
            active_spikes = {ex: info for ex, info in spike_data.items() if info['is_spike']}
            if active_spikes:
                print(f"🔥 SPIKE DETECTED at {data.name}:")
                for exchange, info in active_spikes.items():
                    print(f"   {exchange}: deviation={info['deviation_pct']:.2f}%, volatility={info['volatility']:.2f}%")
        
        # Check each exchange for limit fills
        fills = []
        
        # MEXC spot checks
        mexc_buy_hit = prices['mexc'] <= limits.mexc_buy
        mexc_sell_hit = prices['mexc'] >= limits.mexc_sell
        if mexc_buy_hit:
            fills.append({'exchange': ExchangeEnum.MEXC, 'side': 'buy', 'price': limits.mexc_buy})
            print(f"📊 MEXC BUY FILL: price={prices['mexc']:.6f} <= limit={limits.mexc_buy:.6f}")
        if mexc_sell_hit:
            fills.append({'exchange': ExchangeEnum.MEXC, 'side': 'sell', 'price': limits.mexc_sell})
            print(f"📊 MEXC SELL FILL: price={prices['mexc']:.6f} >= limit={limits.mexc_sell:.6f}")
        
        # GATEIO spot checks
        gateio_buy_hit = prices['gateio'] <= limits.gateio_buy
        gateio_sell_hit = prices['gateio'] >= limits.gateio_sell
        if gateio_buy_hit:
            fills.append({'exchange': ExchangeEnum.GATEIO, 'side': 'buy', 'price': limits.gateio_buy})
            print(f"📊 GATEIO BUY FILL: price={prices['gateio']:.6f} <= limit={limits.gateio_buy:.6f}")
        if gateio_sell_hit:
            fills.append({'exchange': ExchangeEnum.GATEIO, 'side': 'sell', 'price': limits.gateio_sell})
            print(f"📊 GATEIO SELL FILL: price={prices['gateio']:.6f} >= limit={limits.gateio_sell:.6f}")
        
        # GATEIO futures checks
        futures_buy_hit = prices['futures'] <= limits.futures_buy
        futures_sell_hit = prices['futures'] >= limits.futures_sell
        if futures_buy_hit:
            fills.append({'exchange': ExchangeEnum.GATEIO_FUTURES, 'side': 'buy', 'price': limits.futures_buy})
            print(f"📊 FUTURES BUY FILL: price={prices['futures']:.6f} <= limit={limits.futures_buy:.6f}")
        if futures_sell_hit:
            fills.append({'exchange': ExchangeEnum.GATEIO_FUTURES, 'side': 'sell', 'price': limits.futures_sell})
            print(f"📊 FUTURES SELL FILL: price={prices['futures']:.6f} >= limit={limits.futures_sell:.6f}")
        
        # 🔍 DEBUG: Log limit check details every 100 rows
        if hash(str(data.name)) % 100 == 0:  # Sample logging
            print(f"💡 LIMIT CHECK at {data.name}:")
            print(f"   Prices: MEXC={prices['mexc']:.6f}, GATEIO={prices['gateio']:.6f}, FUTURES={prices['futures']:.6f}")
            print(f"   Buy Limits: MEXC={limits.mexc_buy:.6f}, GATEIO={limits.gateio_buy:.6f}, FUTURES={limits.futures_buy:.6f}")
            print(f"   Sell Limits: MEXC={limits.mexc_sell:.6f}, GATEIO={limits.gateio_sell:.6f}, FUTURES={limits.futures_sell:.6f}")
            offset_pct = self._calculate_dynamic_offset(data)
            print(f"   Dynamic offset: {offset_pct:.2f}%")
        
        # Return first fill (simulate fastest execution)
        return fills[0] if fills else None

    def _execute_hedge(self, fill_info: Dict, current_data: pd.Series) -> PositionEntry:
        """Execute immediate hedge to delta-neutral"""
        filled_exchange = fill_info['exchange']
        filled_side = fill_info['side']
        filled_price = fill_info['price']
        
        # Determine hedge exchange and side
        if filled_exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]:
            # Spot filled, hedge with futures
            hedge_exchange = ExchangeEnum.GATEIO_FUTURES
            hedge_side = Side.SELL if filled_side == 'buy' else Side.BUY
        else:
            # Futures filled, hedge with spot (prefer MEXC for liquidity)
            hedge_exchange = ExchangeEnum.MEXC
            hedge_side = Side.SELL if filled_side == 'buy' else Side.BUY
        
        # Get hedge price (current market price with small slippage)
        prices = self._get_current_prices(current_data)
        hedge_price_key = 'mexc' if hedge_exchange == ExchangeEnum.MEXC else 'gateio' if hedge_exchange == ExchangeEnum.GATEIO else 'futures'
        hedge_price = prices[hedge_price_key]
        
        # Apply slippage
        slippage = 0.001  # 0.1% slippage for market order
        if hedge_side == Side.BUY:
            hedge_price *= (1 + slippage)
        else:
            hedge_price *= (1 - slippage)
        
        # Calculate position quantity from USD size
        position_qty = self.backtesting_params.position_size_usd / filled_price
        
        # Create position entry
        position = PositionEntry(entry_time=current_data.name)
        
        # Create the two trades (original spike fill + hedge)
        original_side = Side.BUY if filled_side == 'buy' else Side.SELL
        
        spike_trade = TradeEntry(
            exchange=filled_exchange,
            side=original_side,
            price=filled_price,
            qty=position_qty,
            fee_pct=self.fees.get(filled_exchange, Fees()).taker_fee,
            slippage_pct=0.0  # Already filled at limit price
        )
        
        hedge_trade = TradeEntry(
            exchange=hedge_exchange,
            side=hedge_side,
            price=hedge_price,
            qty=position_qty,
            fee_pct=self.fees.get(hedge_exchange, Fees()).taker_fee,
            slippage_pct=0.1  # Market order slippage already applied above
        )
        
        # Add as arbitrage trade pair
        position.add_arbitrage_trade(current_data.name, [spike_trade, hedge_trade])
        
        return position

    def _check_exit_condition(self, data: pd.Series, position: PositionEntry) -> bool:
        """Check if position should be closed (price stabilized)"""
        # Check time-based exit
        time_elapsed = (data.name - position.entry_time).total_seconds() / 60
        time_exit = time_elapsed > self.max_position_time_minutes
        
        # Check price stabilization (deviation back to normal)
        deviations = []
        for exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]:
            dev_col = get_column_key(exchange, 'deviation_pct')
            if dev_col in data.index:
                deviations.append(abs(data[dev_col]))
        
        stabilization_exit = False
        if deviations:
            max_deviation = max(deviations)
            stabilization_exit = max_deviation < self.stabilization_threshold
            
            # 🔍 DEBUG: Exit condition analysis
            if hash(str(data.name)) % 50 == 0:  # Log every 50 rows when in position
                print(f"🕐 EXIT CHECK at {data.name}: time={time_elapsed:.1f}min/{self.max_position_time_minutes}min, max_dev={max_deviation:.2f}%/{self.stabilization_threshold}%")
                print(f"   Time exit: {time_exit}, Stabilization exit: {stabilization_exit}")
        
        return time_exit or stabilization_exit

    def _close_position(self, position: PositionEntry, current_data: pd.Series) -> ArbitrageTrade:
        """Close delta-neutral position and calculate P&L"""
        # Get current prices for exit trades
        prices = self._get_current_prices(current_data)
        
        # Create exit trades to close the position
        exit_trades = []
        for trade in position.trades:
            # Create opposite trade to close
            opposite_side = Side.SELL if trade.side == Side.BUY else Side.BUY
            
            # Get current price for this exchange
            if trade.exchange == ExchangeEnum.MEXC:
                current_price = prices['mexc']
            elif trade.exchange == ExchangeEnum.GATEIO:
                current_price = prices['gateio']
            else:  # GATEIO_FUTURES
                current_price = prices['futures']
            
            # Apply slippage for market order
            slippage = 0.001  # 0.1% slippage
            if opposite_side == Side.BUY:
                exit_price = current_price * (1 + slippage)
            else:
                exit_price = current_price * (1 - slippage)
            
            exit_trade = TradeEntry(
                exchange=trade.exchange,
                side=opposite_side,
                price=exit_price,
                qty=trade.qty,
                fee_pct=self.fees.get(trade.exchange, Fees()).taker_fee,
                slippage_pct=0.1  # Market order slippage
            )
            exit_trades.append(exit_trade)
        
        # Close the position
        position.close_position(current_data.name, exit_trades)
        
        # Get performance metrics to create ArbitrageTrade
        performance = position.get_performance_metrics(self.backtesting_params.initial_balance_usd)
        
        # Extract original trades for source/dest info
        original_trades = list(position.arbitrage_trades.values())[0]  # First arbitrage trade pair
        buy_trade = next(t for t in original_trades if t.side == Side.BUY)
        sell_trade = next(t for t in original_trades if t.side == Side.SELL)
        
        return ArbitrageTrade(
            timestamp=current_data.name,
            buy_exchange=buy_trade.exchange,
            sell_exchange=sell_trade.exchange,
            buy_price=buy_trade.effective_price,
            sell_price=sell_trade.effective_price,
            qty=buy_trade.qty,
            pnl_pct=position.pnl_pct,
            pnl_usdt=position.pnl_usd
        )

    def generate_signal(self, market_data: pd.Series) -> SpikeSignal:
        """Main strategy logic"""
        
        if self.state == PositionState.SETUP:
            # Setup new limits
            self.current_limits = self._setup_limits(market_data)
            self.state = PositionState.WAITING
            self.analysis_results['total_setups'] += 1
            print(f"🎯 SETUP → WAITING at {market_data.name} (Setup #{self.analysis_results['total_setups']})")
            return SpikeSignal.HOLD
        
        elif self.state == PositionState.WAITING:
            # Check for spike fills
            fill_info = self._detect_spike_fill(market_data, self.current_limits)
            if fill_info:
                # Spike caught! Execute hedge
                self.active_position = self._execute_hedge(fill_info, market_data)
                self.state = PositionState.HEDGED
                self.analysis_results['spike_catches'] += 1
                print(f"⚡ WAITING → HEDGED at {market_data.name}: {fill_info['exchange'].value} {fill_info['side']} @ {fill_info['price']:.6f} (Catch #{self.analysis_results['spike_catches']})")
                self.analysis_results['successful_hedges'] += 1
                return SpikeSignal.ENTER
            return SpikeSignal.HOLD
        
        elif self.state == PositionState.HEDGED:
            # Check exit conditions
            if self._check_exit_condition(market_data, self.active_position):
                # Close position
                trade = self._close_position(self.active_position, market_data)
                self.trades.append(trade)
                
                if trade.pnl_usdt > 0:
                    self.analysis_results['profitable_exits'] += 1
                
                self.state = PositionState.CLOSED
                position_time = (market_data.name - self.active_position.entry_time).total_seconds() / 60
                print(f"💰 HEDGED → CLOSED at {market_data.name}: P&L=${trade.pnl_usdt:.2f} ({trade.pnl_pct:.2f}%), held {position_time:.1f}min (Profitable: {trade.pnl_usdt > 0})")
                return SpikeSignal.EXIT
            return SpikeSignal.HOLD
        
        else:  # CLOSED
            # Reset for next opportunity
            self.state = PositionState.SETUP
            self.current_limits = None
            self.active_position = None
            print(f"🔄 CLOSED → SETUP at {market_data.name} (ready for next opportunity)")
            return SpikeSignal.HOLD

    def backtest(self, df: pd.DataFrame) -> PerformanceMetrics:
        """Execute comprehensive backtest of the spike-catching strategy"""
        # Preload the spike indicator
        self.preload(df)
        
        # Initialize trade tracking
        self.trades = []
        
        # Reset strategy state for backtest
        self.state = PositionState.SETUP
        self.current_limits = None
        self.active_position = None
        self.analysis_results = {
            'total_setups': 0,
            'spike_catches': 0,
            'successful_hedges': 0,
            'profitable_exits': 0
        }
        
        # Run strategy on each data point
        for timestamp, row in df.iterrows():
            signal = self.generate_signal(row)
            # Signal is used internally to manage state
        
        # Calculate performance metrics from all trades
        if self.trades:
            position = PositionEntry()
            for trade in self.trades:
                # Convert ArbitrageTrade back to individual trades for metrics calculation
                buy_trade = TradeEntry(
                    exchange=trade.buy_exchange,
                    side=Side.BUY,
                    price=trade.buy_price,
                    qty=trade.qty,
                    fee_pct=self.fees.get(trade.buy_exchange, Fees()).taker_fee,
                    slippage_pct=0.0
                )
                sell_trade = TradeEntry(
                    exchange=trade.sell_exchange,
                    side=Side.SELL,
                    price=trade.sell_price,
                    qty=trade.qty,
                    fee_pct=self.fees.get(trade.sell_exchange, Fees()).taker_fee,
                    slippage_pct=0.0
                )
                position.add_arbitrage_trade(trade.timestamp, [buy_trade, sell_trade])
            
            return position.get_performance_metrics(self.backtesting_params.initial_balance_usd)
        else:
            # No trades executed
            return PerformanceMetrics()

    def preload(self, df: pd.DataFrame):
        """Preload spike indicator with historical data"""
        # Set dataframe for spike indicator
        self.spike_indicator.df = df.copy()
        
        # Run spike detection for all exchanges
        for exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]:
            self.spike_indicator._detect_adaptive_spikes(exchange)