"""
Inventory Spot Strategy Signal V2

Implements spot arbitrage strategy matching the exact logic from arbitrage_analyzer.py.
Focuses on cross-exchange spot arbitrage opportunities using bid/ask spikes
and market-market execution patterns.

Key Logic Patterns from arbitrage_analyzer.py:
- Market-market opportunities: Direct bid/ask arbitrage 
- Bid spike detection: GATEIO bid > MEXC ask
- Ask spike detection: MEXC bid > GATEIO ask
- Safe offset calculation for execution
- Spread calculation in basis points
- Execution confidence scoring
"""

from typing import Dict, Any, Tuple, Union
import pandas as pd
import numpy as np
from datetime import datetime

from trading.strategies.base.base_strategy_signal import BaseStrategySignal, TradeEntry, Position
from ..types import PerformanceMetrics
from trading.signals.types import Signal
from exchanges.structs.enums import ExchangeEnum, Side


class InventorySpotStrategySignalV2(BaseStrategySignal):
    """
    Inventory spot arbitrage strategy V2 - matches arbitrage_analyzer.py logic.
    
    Strategy Logic (from CrossExchangeArbitrageAnalyzer):
    - ENTER: Direct market-market arbitrage opportunities
      * GATEIO bid > MEXC ask (sell MEXC, buy GATEIO)
      * MEXC bid > GATEIO ask (sell GATEIO, buy MEXC)
    - EXIT: Spread normalizes below profit threshold
    - Uses safe offset calculation for execution safety
    - Focuses on execution confidence and risk assessment
    """
    
    def __init__(self, 
                 strategy_type: str = 'inventory_spot_v2',
                 min_profit_bps: float = 10.0,  # 10 basis points minimum profit
                 min_execution_confidence: float = 0.7,
                 safe_offset_percentile: float = 75.0,
                 safe_offset_pct: float = 0.05,  # 0.05% safe offset 
                 execution_confidence_threshold: float = 0.7,
                 volatility_window: int = 20,
                 **params):
        """
        Initialize inventory spot strategy V2.
        
        Args:
            strategy_type: Strategy identifier
            min_profit_bps: Minimum profit in basis points (10 bps = 0.1%)
            min_execution_confidence: Minimum execution confidence (matches V2 pattern)
            safe_offset_percentile: Percentile for safe offset calculation (matches V2 pattern)
            safe_offset_pct: Safe offset percentage for execution safety
            execution_confidence_threshold: Minimum confidence score to enter
            volatility_window: Window for volatility calculations
            **params: Additional parameters passed to base class
        """
        self.min_profit_bps = min_profit_bps
        self.min_execution_confidence = min_execution_confidence
        self.safe_offset_percentile = safe_offset_percentile
        self.safe_offset_pct = safe_offset_pct / 100.0  # Convert to decimal
        self.execution_confidence_threshold = execution_confidence_threshold
        self.volatility_window = volatility_window

        super().__init__(
            strategy_type=strategy_type,
            min_profit_bps=min_profit_bps,
            min_execution_confidence=min_execution_confidence,
            safe_offset_percentile=safe_offset_percentile,
            safe_offset_pct=safe_offset_pct,
            execution_confidence_threshold=execution_confidence_threshold,
            volatility_window=volatility_window,
            **params
        )
        
        # Strategy-specific tracking (matches OpportunityDetector)
        self.current_opportunity = None
        self.volatility_metrics = {}

        self.col_mexc_bid = f'{ExchangeEnum.MEXC.value}:bid'
        self.col_mexc_ask = f'{ExchangeEnum.MEXC.value}:ask'
        self.col_gateio_bid = f'{ExchangeEnum.GATEIO.value}:bid'
        self.col_gateio_ask = f'{ExchangeEnum.GATEIO.value}:ask'
        self.col_mexc_balance = f'{ExchangeEnum.MEXC.value}:balance_usd'
        self.col_gateio_balance = f'{ExchangeEnum.GATEIO.value}:balance_usd'

        self.price_history = {
            self.col_mexc_bid: [],
            self.col_mexc_ask: [],
            self.col_gateio_bid: [],
            self.col_gateio_ask: []
        }
    
    def generate_live_signal(self, market_data: Dict[str, Any], **params) -> Tuple[Signal, float]:
        """
        Generate live trading signal using arbitrage analyzer logic.
        
        Args:
            market_data: Current market data snapshot
            **params: Override parameters
            
        Returns:
            Tuple of (Signal, confidence_score)
        """
        # Validate market data
        if not self.validate_market_data(market_data):
            return Signal.HOLD, 0.0

        mexc_spot_bid_price = market_data.get('MEXC_SPOT:bid_price', 0)
        mexc_spot_ask_price = market_data.get('MEXC_SPOT:ask_price', 0)
        gateio_spot_bid_price = market_data.get('GATEIO_SPOT:bid_price', 0)
        gateio_spot_ask_price = market_data.get('GATEIO_SPOT:ask_price', 0)

        if not all([mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price]):
            return Signal.HOLD, 0.0
        
        # Update price history for volatility calculation
        self._update_price_history(mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price)
        
        # Calculate safe offset using volatility analysis
        safe_offset = self._calculate_safe_offset(**params)
        
        # Override parameters
        min_profit = params.get('min_profit_bps', self.min_profit_bps)
        confidence_threshold = params.get('execution_confidence_threshold', 
                                        self.execution_confidence_threshold)
        
        # Detect market-market opportunities (core arbitrage logic)
        opportunity = self._detect_market_market_opportunity(
            mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price, safe_offset, min_profit
        )
        
        if not opportunity:
            return Signal.HOLD, 0.0
        
        # Check execution confidence
        if opportunity['execution_confidence'] < confidence_threshold:
            return Signal.HOLD, opportunity['execution_confidence']
        
        # Generate signal based on opportunity type
        signal = self._determine_signal_from_opportunity(opportunity)
        confidence = opportunity['execution_confidence']
        
        # Update tracking
        self.current_opportunity = opportunity
        self.last_signal = signal
        self.last_signal_time = datetime.now()
        self.signal_count += 1
        
        return signal, confidence
    
    def _emulate_trading(self, df: pd.DataFrame, **params) -> pd.DataFrame:
        """
        Apply strategy signals to historical data using arbitrage analyzer logic.
        
        Args:
            df: Historical market data DataFrame
            **params: Override parameters
            
        Returns:
            DataFrame with added signal columns
        """

        # Override parameters
        min_profit_bps = params.get('min_profit_bps', self.min_profit_bps)
        confidence_threshold = params.get('execution_confidence_threshold', 
                                        self.execution_confidence_threshold)
        
        # Calculate safe offset for entire DataFrame
        df = self._calculate_vectorized_safe_offset(df)

        # df['inv_mexc_to_gateio_spread'] = ((df[AnalyzerKeys.gateio_spot_bid] - df[AnalyzerKeys.mexc_ask]) /
        #                                    df[AnalyzerKeys.mexc_ask] * 100)
        # df['inv_gateio_to_mexc_spread'] = ((df[AnalyzerKeys.mexc_bid] - df[AnalyzerKeys.gateio_spot_ask]) /
        #                                    df[AnalyzerKeys.gateio_spot_ask] * 100)
        #

        # gateio_bid_opps = df[self.col_gateio_bid] > df[self.col_mexc_bid]
        gateio_spread_bps = ((df[self.col_gateio_bid] - df[self.col_mexc_ask]) /
                             df[self.col_mexc_ask] * 10000)
        gateio_profit = gateio_spread_bps - (df['safe_offset'] * 10000)
        # gateio_profitable = (gateio_profit > min_profit_bps) & gateio_bid_opps
        gateio_profitable = (gateio_profit > min_profit_bps)

        df['gateio_profitable'] = gateio_profitable


        # Check MEXC bid > GATEIO ask opportunities
        # mexc_bid_opps = df['MEXC_SPOT:bid_price'] > df['GATEIO_SPOT:ask_price']
        mexc_spread_bps = ((df[self.col_mexc_bid] - df[self.col_gateio_ask]) /
                           df[self.col_gateio_ask] * 10000)

        mexc_profit = mexc_spread_bps - (df['safe_offset'] * 10000)
        # mexc_profitable = (mexc_profit > min_profit_bps) & mexc_bid_opps
        mexc_profitable = (mexc_profit > min_profit_bps)
        df['mexc_profitable'] = mexc_profitable

        #         df['inv_mexc_to_gateio_spread'] = ((df[AnalyzerKeys.gateio_spot_bid] - df[AnalyzerKeys.mexc_ask]) /
        #                                            df[AnalyzerKeys.mexc_ask] * 100)
        # Combine opportunities
        df['opportunity_detected'] = gateio_profitable | mexc_profitable
        df['spread_bps'] = np.where(gateio_profitable, gateio_spread_bps,
                                    np.where(mexc_profitable, mexc_spread_bps, 0))
        df['expected_profit_bps'] = np.where(gateio_profitable, gateio_profit,
                                             np.where(mexc_profitable, mexc_profit, 0))


        # Initialize signal columns
        df['signal'] = Signal.HOLD.value
        df['confidence'] = 0.0
        
        # Apply signals based on opportunities and confidence
        enter_condition = (
            (df['opportunity_detected'] == True)
        )
        
        exit_condition = (
            (df['opportunity_detected'] == False)
        )
        
        # Apply signals
        df.loc[enter_condition, 'signal'] = Signal.ENTER.value
        df.loc[exit_condition, 'signal'] = Signal.EXIT.value

        return df

    def _open_position(self, signal: Signal, row: pd.Series, **params) -> Dict[str, Any]:
        """
        Calculate position opening details with support for same-exchange trading.
        
        Supports both cross-exchange arbitrage and same-exchange trading with rotating amounts.
        Accepts direct price input via market_data or derives from current market conditions.
        
        Args:
            signal: Trading signal (should be ENTER)
            row: Current market data (can include direct entry prices)
            **params: Position parameters including:
                - position_size_usd: Position size in USD
                - entry_buy_price: Direct buy price (optional)
                - entry_sell_price: Direct sell price (optional)
                - same_exchange: True for same-exchange trading
                - rotating_amount: Amount variation for same-exchange
                
        Returns:
            Position details dictionary
        """
        if signal != Signal.ENTER:
            return {}

        position_size = params.get('position_size_usd', self.position_size_usd)
        same_exchange = params.get('same_exchange', False)
        rotating_amount = params.get('rotating_amount', 1.0)

        mexc_spot_bid_price = row.get('MEXC_SPOT:bid_price', 0)
        mexc_spot_ask_price = row.get('MEXC_SPOT:ask_price', 0)
        gateio_spot_bid_price = row.get('GATEIO_SPOT:bid_price', 0)
        gateio_spot_ask_price = row.get('GATEIO_SPOT:ask_price', 0)

        
        # Handle direct price input
        entry_buy_price = params.get('entry_buy_price') or row.get('entry_buy_price')
        entry_sell_price = params.get('entry_sell_price') or row.get('entry_sell_price')

        if row['mexc_profitable']:
            buy_price = row[self.col_mexc_ask]
            sell_price = row[self.col_gateio_bid]
            trade_size_usd = 10
            quantity = trade_size_usd / buy_price
            buy_cost = trade_size_usd
            sell_proceeds = quantity * sell_price
            total_fees: float = 0.0015 # 0.1% gateio, 0.05% mexc fees

            fees = (buy_cost + sell_proceeds) * total_fees  # Fees on both sides
            net_pnl = sell_proceeds - buy_cost - fees
            pnl_percentage = (net_pnl / trade_size_usd) * 100
            print(f"MEXC->Gate.io Trade at idx {row.index}: {buy_price} -> {sell_price} Size {trade_size_usd}, PnL% {pnl_percentage}")

        if same_exchange:
            # Same-exchange trading scenario (e.g., rotating amounts on Gate.io)
            exchange = params.get('exchange', 'GATEIO_SPOT')
            
            if entry_buy_price and entry_sell_price:
                # Direct price input mode
                buy_price = entry_buy_price
                sell_price = entry_sell_price
                action = f'same_exchange_rotation_{exchange.lower()}'
                spread_bps = ((sell_price - buy_price) / buy_price) * 10000
            else:
                if exchange == 'GATEIO_SPOT':
                    # Use Gate.io prices with rotation
                    buy_price = gateio_spot_ask_price * rotating_amount  # Buy at ask with rotation
                    sell_price = gateio_spot_bid_price * (2.0 - rotating_amount)  # Sell at bid with inverse rotation
                    action = 'same_exchange_gateio_rotation'
                else:
                    # Use MEXC prices with rotation
                    buy_price = mexc_spot_ask_price * rotating_amount
                    sell_price = mexc_spot_bid_price * (2.0 - rotating_amount)
                    action = 'same_exchange_mexc_rotation'
                
                spread_bps = ((sell_price - buy_price) / buy_price) * 10000
            
            # Create TradeEntry objects for same-exchange trading
            exchange_enum = ExchangeEnum.GATEIO if exchange == 'GATEIO_SPOT' else ExchangeEnum.MEXC
            
            # For same-exchange: buy and sell on same exchange with different sides
            buy_trade_entry = TradeEntry(
                side=Side.BUY,
                entry_price=buy_price,
                exit_price=None
            )
            
            sell_trade_entry = TradeEntry(
                side=Side.SELL,
                entry_price=sell_price,
                exit_price=None
            )
            
            # Create entries dict for position
            trade_entries = {
                exchange_enum: buy_trade_entry,  # Primary trade entry
                # Note: For same-exchange, we track both buy and sell as separate concepts
            }
            
            # Create entry_data for backward compatibility and additional data
            entry_data = {
                # Same-exchange details
                'opportunity_type': 'same_exchange',
                'action': action,
                'exchange': exchange,
                'buy_exchange': exchange,
                'sell_exchange': exchange,
                
                # Entry prices (kept for backward compatibility)
                'buy_price': buy_price,
                'sell_price': sell_price,
                'rotating_amount': rotating_amount,
                
                # Metrics
                'spread_bps': spread_bps,
                'expected_profit_bps': max(0, spread_bps - 10),  # Minus costs
                'safe_offset': 0.0005,  # 5 bps for same-exchange
                'execution_confidence': 0.8,  # Lower confidence for same-exchange
                
                # Risk metrics
                'volatility_risk': 0.4,  # Higher risk for same-exchange
                'liquidity_risk': 0.3,
                'timing_risk': 0.2,
                'max_loss_bps': -30,  # Tighter stop loss
            }
            
            position = Position(
                entry_time=datetime.now(),
                strategy_type=self.strategy_type,
                entry_signal=signal,
                entry_data=entry_data,
                position_size_usd=position_size,
                entries=trade_entries,
                unrealized_pnl_usd=0.0,
                unrealized_pnl_pct=0.0,
                hold_time_minutes=0.0
            )
            
        else:
            # Cross-exchange arbitrage (handle cross_exchange parameter)
            cross_exchange = params.get('cross_exchange', False)
            buy_exchange = params.get('buy_exchange', 'MEXC_SPOT')
            sell_exchange = params.get('sell_exchange', 'GATEIO_SPOT')
            
            if entry_buy_price and entry_sell_price:
                # Direct price input for cross-exchange
                buy_price = entry_buy_price
                sell_price = entry_sell_price
                buy_exchange = params.get('buy_exchange', 'GATEIO_SPOT')
                sell_exchange = params.get('sell_exchange', 'MEXC_SPOT')
                action = 'direct_price_arbitrage'
                spread_bps = ((sell_price - buy_price) / buy_price) * 10000
                
                # Create TradeEntry objects for direct price arbitrage
                buy_exchange_enum = ExchangeEnum.GATEIO if buy_exchange == 'GATEIO_SPOT' else ExchangeEnum.MEXC
                sell_exchange_enum = ExchangeEnum.GATEIO if sell_exchange == 'GATEIO_SPOT' else ExchangeEnum.MEXC
                
                trade_entries = {
                    buy_exchange_enum: TradeEntry(
                        side=Side.BUY,
                        entry_price=buy_price,
                        exit_price=None
                    ),
                    sell_exchange_enum: TradeEntry(
                        side=Side.SELL,
                        entry_price=sell_price,
                        exit_price=None
                    )
                }
                
                # Create entry_data for backward compatibility and additional data
                entry_data = {
                    # Direct price details
                    'opportunity_type': 'direct_price',
                    'action': action,
                    'buy_exchange': buy_exchange,
                    'sell_exchange': sell_exchange,
                    
                    # Entry prices (kept for backward compatibility)
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    
                    # Metrics
                    'spread_bps': spread_bps,
                    'expected_profit_bps': max(0, spread_bps - 20),
                    'safe_offset': 0.001,
                    'execution_confidence': 0.9,
                    
                    # Risk metrics
                    'volatility_risk': 0.3,
                    'liquidity_risk': 0.2,
                    'timing_risk': 0.1,
                    'max_loss_bps': -50,
                }
                
                position = Position(
                    entry_time=datetime.now(),
                    strategy_type=self.strategy_type,
                    entry_signal=signal,
                    entry_data=entry_data,
                    position_size_usd=position_size,
                    entries=trade_entries,
                    unrealized_pnl_usd=0.0,
                    unrealized_pnl_pct=0.0,
                    hold_time_minutes=0.0
                )
                
            elif cross_exchange:
                # Handle cross-exchange with market data prices
                mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price = self._extract_current_prices(row)
                
                if not all([mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price]):
                    return {}
                
                # Determine buy/sell prices based on exchanges
                if buy_exchange == 'MEXC_SPOT' and sell_exchange == 'GATEIO_SPOT':
                    buy_price = mexc_spot_ask_price  # Buy on MEXC at ask
                    sell_price = gateio_spot_bid_price  # Sell on Gate.io at bid
                    action = 'mexc_buy_gateio_sell'
                elif buy_exchange == 'GATEIO_SPOT' and sell_exchange == 'MEXC_SPOT':
                    buy_price = gateio_spot_ask_price  # Buy on Gate.io at ask
                    sell_price = mexc_spot_bid_price  # Sell on MEXC at bid
                    action = 'gateio_buy_mexc_sell'
                else:
                    # Default to MEXC buy, Gate.io sell
                    buy_price = mexc_spot_ask_price
                    sell_price = gateio_spot_bid_price
                    action = f'{buy_exchange.lower()}_buy_{sell_exchange.lower()}_sell'
                
                spread_bps = ((sell_price - buy_price) / buy_price) * 10000
                
                # Create TradeEntry objects for cross-exchange arbitrage
                buy_exchange_enum = ExchangeEnum.GATEIO if buy_exchange == 'GATEIO_SPOT' else ExchangeEnum.MEXC
                sell_exchange_enum = ExchangeEnum.GATEIO if sell_exchange == 'GATEIO_SPOT' else ExchangeEnum.MEXC
                
                trade_entries = {
                    buy_exchange_enum: TradeEntry(
                        side=Side.BUY,
                        entry_price=buy_price,
                        exit_price=None
                    ),
                    sell_exchange_enum: TradeEntry(
                        side=Side.SELL,
                        entry_price=sell_price,
                        exit_price=None
                    )
                }
                
                # Create entry_data for backward compatibility and additional data
                entry_data = {
                    'opportunity_type': 'cross_exchange',
                    'action': action,
                    'buy_exchange': buy_exchange,
                    'sell_exchange': sell_exchange,
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'spread_bps': spread_bps,
                    'expected_profit_bps': max(0, spread_bps - 20),  # Minus costs
                    'safe_offset': 0.001,  # 10 bps for cross-exchange
                    'execution_confidence': 0.85,  # High confidence for cross-exchange
                    'volatility_risk': 0.2,
                    'liquidity_risk': 0.1,
                    'timing_risk': 0.15,
                    'max_loss_bps': -40,
                }
                
                position = Position(
                    entry_time=datetime.now(),
                    strategy_type=self.strategy_type,
                    entry_signal=signal,
                    entry_data=entry_data,
                    position_size_usd=position_size,
                    entries=trade_entries,
                    unrealized_pnl_usd=0.0,
                    unrealized_pnl_pct=0.0,
                    hold_time_minutes=0.0
                )
                
            else:
                # Original opportunity-based logic (fallback)
                if not self.current_opportunity:
                    return {}
                    
                opp = self.current_opportunity
                # Create TradeEntry objects from opportunity data
                buy_exchange_enum = ExchangeEnum.GATEIO if opp['buy_exchange'] == 'GATEIO_SPOT' else ExchangeEnum.MEXC
                sell_exchange_enum = ExchangeEnum.GATEIO if opp['sell_exchange'] == 'GATEIO_SPOT' else ExchangeEnum.MEXC
                
                trade_entries = {
                    buy_exchange_enum: TradeEntry(
                        side=Side.BUY,
                        entry_price=opp['buy_price'],
                        exit_price=None
                    ),
                    sell_exchange_enum: TradeEntry(
                        side=Side.SELL,
                        entry_price=opp['sell_price'],
                        exit_price=None
                    )
                }
                
                # Create entry_data for backward compatibility and additional data
                entry_data = {
                    'opportunity_type': opp['opportunity_type'],
                    'action': opp['action'],
                    'buy_exchange': opp['buy_exchange'],
                    'sell_exchange': opp['sell_exchange'],
                    'buy_price': opp['buy_price'],
                    'sell_price': opp['sell_price'],
                    'spread_bps': opp['spread_bps'],
                    'expected_profit_bps': opp['expected_profit_bps'],
                    'safe_offset': opp['safe_offset'],
                    'execution_confidence': opp['execution_confidence'],
                    'volatility_risk': 0.3,
                    'liquidity_risk': 0.2,
                    'timing_risk': 0.1,
                    'max_loss_bps': -50,
                }
                
                position = Position(
                    entry_time=datetime.now(),
                    strategy_type=self.strategy_type,
                    entry_signal=signal,
                    entry_data=entry_data,
                    position_size_usd=position_size,
                    entries=trade_entries,
                    unrealized_pnl_usd=0.0,
                    unrealized_pnl_pct=0.0,
                    hold_time_minutes=0.0
                )
        
        self.current_position = position
        return position
    
    def _close_position(self, position: Dict[str, Any], row: pd.Series, **params) -> Dict[str, Any]:
        """
        Calculate position closing details and P&L with support for same-exchange trading.
        
        Handles both cross-exchange arbitrage and same-exchange scenarios.
        Supports direct exit price input and simulated P&L calculations.
        
        Args:
            position: Current position details
            row: Current market data (can include direct exit prices)
            **params: Exit parameters including:
                - exit_buy_price: Direct exit buy price (optional)
                - exit_sell_price: Direct exit sell price (optional)
                - simulate_only: True for unrealized P&L calculation
                
        Returns:
            Trade closure details with P&L
        """

        mexc_spot_bid_price = row.get('MEXC_SPOT:bid_price', 0)
        mexc_spot_ask_price = row.get('MEXC_SPOT:ask_price', 0)
        gateio_spot_bid_price = row.get('GATEIO_SPOT:bid_price', 0)
        gateio_spot_ask_price = row.get('GATEIO_SPOT:ask_price', 0)

        # Handle direct exit price input
        exit_buy_price = params.get('exit_buy_price') or row.get('exit_buy_price')
        exit_sell_price = params.get('exit_sell_price') or row.get('exit_sell_price')
        simulate_only = params.get('simulate_only', False)
        
        # Extract position details
        action = position.get('action', '')
        opportunity_type = position.get('opportunity_type', '')
        entry_buy_price = position.get('buy_price')
        entry_sell_price = position.get('sell_price')
        position_size = position.get('position_size_usd')
        
        if not entry_buy_price or not entry_sell_price:
            # Handle missing price data gracefully
            return {
                'pnl_usd': 0.0,
                'pnl_pct': 0.0,
                'fees_usd': 2.5,  # Default fee
                'exit_reason': 'missing_price_data',
                'entry_signal_strength': 0.0
            }
        
        if opportunity_type == 'same_exchange':
            # Same-exchange trading P&L calculation
            exchange = position.get('exchange', 'GATEIO_SPOT')
            rotating_amount = position.get('rotating_amount', 1.0)
            
            if exit_buy_price and exit_sell_price:
                # Direct price input mode
                current_buy_price = exit_buy_price
                current_sell_price = exit_sell_price
            else:
                if exchange == 'GATEIO_SPOT':
                    current_buy_price = gateio_spot_ask_price * rotating_amount
                    current_sell_price = gateio_spot_bid_price * (2.0 - rotating_amount)
                else:
                    current_buy_price = mexc_spot_ask_price * rotating_amount
                    current_sell_price = mexc_spot_bid_price * (2.0 - rotating_amount)
            
            # Same-exchange P&L: profit from price spread changes
            entry_spread = entry_sell_price - entry_buy_price
            exit_spread = current_sell_price - current_buy_price
            spread_change = exit_spread - entry_spread
            
            # Position units calculation
            units = position_size / ((entry_buy_price + entry_sell_price) / 2)
            gross_pnl_usd = spread_change * units
            
        elif opportunity_type == 'direct_price':
            # Direct price arbitrage P&L
            if exit_buy_price and exit_sell_price:
                exit_mexc_spot_price = exit_buy_price if 'mexc' in action else exit_sell_price
                exit_gateio_spot_price = exit_sell_price if 'mexc' in action else exit_buy_price
            else:
                exit_mexc_spot_price = mexc_spot_bid_price  # Default exit
                exit_gateio_spot_price = gateio_spot_bid_price
            
            # Cross-exchange P&L calculation
            entry_profit = entry_sell_price - entry_buy_price
            exit_cost = exit_gateio_spot_price - exit_mexc_spot_price if 'gateio' in position.get('buy_exchange', '') else exit_mexc_spot_price - exit_gateio_spot_price
            
            units = position_size / entry_buy_price if entry_buy_price > 0 else 0
            gross_pnl_usd = (entry_profit + exit_cost) * units
            
        elif opportunity_type == 'cross_exchange':
            # New cross-exchange arbitrage P&L calculation
            buy_exchange = position.get('buy_exchange', 'MEXC_SPOT')
            sell_exchange = position.get('sell_exchange', 'GATEIO_SPOT')
            
            if exit_buy_price and exit_sell_price:
                # Direct exit prices provided
                current_buy_price = exit_buy_price
                current_sell_price = exit_sell_price
            else:

                if not all([mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price]):
                    return {'pnl_usd': 0.0, 'pnl_pct': 0.0, 'fees_usd': 2.5}
                
                # Determine exit prices (reverse the entry)
                if buy_exchange == 'MEXC_SPOT' and sell_exchange == 'GATEIO_SPOT':
                    # Entry: bought MEXC, sold Gate.io -> Exit: sell MEXC, buy Gate.io
                    current_buy_price = gateio_spot_ask_price  # Buy back Gate.io at ask
                    current_sell_price = mexc_spot_bid_price   # Sell MEXC at bid
                elif buy_exchange == 'GATEIO_SPOT' and sell_exchange == 'MEXC_SPOT':
                    # Entry: bought Gate.io, sold MEXC -> Exit: sell Gate.io, buy MEXC
                    current_buy_price = mexc_spot_ask_price    # Buy back MEXC at ask
                    current_sell_price = gateio_spot_bid_price # Sell Gate.io at bid
                else:
                    # Default
                    current_buy_price = mexc_spot_ask_price
                    current_sell_price = gateio_spot_bid_price
            
            # Cross-exchange P&L: Entry spread + Exit spread (both should be positive)
            entry_spread = entry_sell_price - entry_buy_price  # Profit from entry
            exit_spread = current_sell_price - current_buy_price  # Profit from exit
            total_spread = entry_spread + exit_spread
            
            # Calculate units and gross P&L
            avg_entry_price = (entry_buy_price + entry_sell_price) / 2
            units = position_size / avg_entry_price if avg_entry_price > 0 else 0
            gross_pnl_usd = total_spread * units
            
        else:
            # Original cross-exchange arbitrage logic


            if not all([mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price]):
                return {'pnl_usd': 0.0, 'pnl_pct': 0.0, 'fees_usd': 0.0}
            
            # Determine exit prices based on original action
            if 'gateio_bid_spike' in action:
                # Original: sell MEXC, buy GATEIO -> reverse: sell GATEIO, buy MEXC
                exit_mexc_spot_price = mexc_spot_ask_price  # Buy MEXC at ask
                exit_gateio_spot_price = gateio_spot_bid_price  # Sell GATEIO at bid
            elif 'mexc_bid_spike' in action:
                # Original: sell GATEIO, buy MEXC -> reverse: sell MEXC, buy GATEIO
                exit_mexc_spot_price = mexc_spot_bid_price  # Sell MEXC at bid
                exit_gateio_spot_price = gateio_spot_ask_price  # Buy GATEIO at ask
            else:
                # Default exit
                exit_mexc_spot_price = mexc_spot_bid_price
                exit_gateio_spot_price = gateio_spot_bid_price
            
            # P&L calculation
            if 'gateio_bid_spike' in action:
                entry_profit = entry_sell_price - entry_buy_price
                exit_cost = exit_gateio_spot_price - exit_mexc_spot_price
                gross_pnl_per_unit = entry_profit + exit_cost
            else:
                entry_profit = entry_sell_price - entry_buy_price
                exit_cost = exit_mexc_spot_price - exit_gateio_spot_price
                gross_pnl_per_unit = entry_profit + exit_cost
            
            units = position_size / entry_buy_price if entry_buy_price > 0 else 0
            gross_pnl_usd = gross_pnl_per_unit * units
        
        # Calculate fees and costs
        fees_usd = position_size * self.total_fees
        net_pnl_usd = gross_pnl_usd - fees_usd
        pnl_pct = (net_pnl_usd / position_size) * 100 if position_size > 0 else 0
        
        # Build trade result
        current_time = datetime.now()
        entry_time = position.get('timestamp', current_time)
        
        trade_result = {
            'strategy_type': self.strategy_type,
            'entry_timestamp': entry_time,
            'exit_timestamp': current_time,
            'position_size_usd': position_size,
            'hold_time_seconds': (current_time - entry_time).total_seconds() if entry_time else 0,
            
            # Entry details
            'entry_buy_price': entry_buy_price,
            'entry_sell_price': entry_sell_price,
            'entry_action': action,
            'opportunity_type': opportunity_type,
            
            # Exit details
            'exit_buy_price': exit_buy_price or (current_buy_price if opportunity_type == 'same_exchange' else None),
            'exit_sell_price': exit_sell_price or (current_sell_price if opportunity_type == 'same_exchange' else None),
            
            # P&L breakdown
            'gross_pnl_usd': gross_pnl_usd,
            'fees_usd': fees_usd,
            'pnl_usd': net_pnl_usd,  # Key field for position tracker
            'pnl_pct': pnl_pct,      # Key field for position tracker
            
            # Arbitrage analysis
            'entry_spread_bps': position.get('spread_bps', 0),
            'expected_profit_bps': position.get('expected_profit_bps', 0),
            'execution_confidence': position.get('execution_confidence', 0),
        }
        
        # For same-exchange, add rotation details
        if opportunity_type == 'same_exchange':
            trade_result.update({
                'exchange': position.get('exchange'),
                'rotating_amount': position.get('rotating_amount', 1.0),
                'entry_spread': entry_sell_price - entry_buy_price,
                'exit_spread': (current_sell_price if 'current_sell_price' in locals() else 0) - 
                              (current_buy_price if 'current_buy_price' in locals() else 0)
            })
        
        # Clear position state if not simulating
        if not simulate_only:
            self.current_position = None
            self.current_opportunity = None
        
        return trade_result
    
    # def update_indicators(self, new_data: Union[Dict[str, Any], pd.DataFrame]) -> None:
    #     """
    #     Update rolling indicators with new market data.
    #
    #     Args:
    #         new_data: New market data (single row or snapshot)
    #     """
    #     if isinstance(new_data, pd.DataFrame) and not new_data.empty:
    #         latest_row = new_data.iloc[-1]
    #         mexc_spot_bid_price = latest_row.get('MEXC_SPOT:bid_price', 0)
    #         mexc_spot_ask_price = latest_row.get('MEXC_SPOT:ask_price', 0)
    #         gateio_spot_bid_price = latest_row.get('GATEIO_SPOT:bid_price', 0)
    #         gateio_spot_ask_price = latest_row.get('GATEIO_SPOT:ask_price', 0)
    #     else:
    #         mexc_spot_bid_price = new_data.get('MEXC_SPOT:bid_price', 0)
    #         mexc_spot_ask_price = new_data.get('MEXC_SPOT:ask_price', 0)
    #         gateio_spot_bid_price = new_data.get('GATEIO_SPOT:bid_price', 0)
    #         gateio_spot_ask_price = new_data.get('GATEIO_SPOT:ask_price', 0)
    #
    #     if all([mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price]):
    #         self._update_price_history(mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price)
    #
    def calculate_signal_confidence(self, indicators: Dict[str, float]) -> float:
        """
        Calculate confidence score using arbitrage analyzer logic.
        
        Args:
            indicators: Current indicator values
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.7  # Base confidence for market-market opportunities
        
        # Adjust for spread magnitude
        spread_bps = indicators.get('spread_bps', 0)
        if spread_bps > 50:  # > 0.5%
            confidence = min(confidence * 1.3, 1.0)
        elif spread_bps > 25:  # > 0.25%
            confidence = min(confidence * 1.1, 1.0)
        elif spread_bps < 10:  # < 0.1%
            confidence = confidence * 0.7
        
        # Adjust for volatility
        volatility_risk = indicators.get('volatility_risk', 0.3)
        if volatility_risk > 0.5:
            confidence = confidence * 0.8
        elif volatility_risk < 0.2:
            confidence = min(confidence * 1.1, 1.0)
        
        # Adjust for execution conditions
        safe_offset = indicators.get('safe_offset', 0.0005)
        if safe_offset > 0.001:  # High offset = risky conditions
            confidence = confidence * 0.9
        
        return max(min(confidence, 1.0), 0.0)

    def _update_price_history(self, mexc_spot_bid_price: float, mexc_spot_ask_price: float, 
                             gateio_spot_bid_price: float, gateio_spot_ask_price: float) -> None:
        """Update price history for volatility calculation."""
        for key, value in [
            (self.col_mexc_bid, mexc_spot_bid_price), (self.col_mexc_ask, mexc_spot_ask_price),
            (self.col_gateio_bid, gateio_spot_bid_price), (self.col_gateio_ask, gateio_spot_ask_price)
        ]:
            self.price_history[key].append(value)
            if len(self.price_history[key]) > self.volatility_window:
                self.price_history[key].pop(0)
    
    def _calculate_safe_offset(self, **params) -> float:
        """Calculate safe offset using volatility analysis (matches SafeOffsetCalculator)."""
        safe_offset_pct = params.get('safe_offset_pct', self.safe_offset_pct)
        
        # Calculate volatility from price history
        if len(self.price_history[self.col_mexc_bid]) < 5:
            return safe_offset_pct  # Default if insufficient data
        
        # Calculate price volatility
        mexc_prices = np.array(self.price_history[self.col_mexc_bid])
        gateio_prices = np.array(self.price_history[self.col_mexc_ask])
        
        mexc_volatility = np.std(mexc_prices / mexc_prices[0] - 1) if len(mexc_prices) > 1 else 0.01
        gateio_volatility = np.std(gateio_prices / gateio_prices[0] - 1) if len(gateio_prices) > 1 else 0.01
        
        # Use higher volatility for safety
        volatility = max(mexc_volatility, gateio_volatility)

        # Calculate safe offset: volatility + spread + buffer
        # TODO: tmp disabled
        # safe_offset = volatility * 2 + 0.0005 + safe_offset_pct
        #
        # # Minimum safety margin of 0.05% (5 bps)
        # return max(safe_offset, 0.0005)

        return 0.0
    
    def _detect_market_market_opportunity(self, mexc_spot_bid_price: float, mexc_spot_ask_price: float,
                                         gateio_spot_bid_price: float, gateio_spot_ask_price: float,
                                         safe_offset: float, min_profit_bps: float) -> Dict[str, Any]:
        """Detect market-market opportunities (matches detect_market_market_opportunity)."""
        
        # Check GATEIO bid > MEXC ask (sell MEXC, buy GATEIO)
        if gateio_spot_bid_price > mexc_spot_ask_price:
            spread_bps = ((gateio_spot_bid_price - mexc_spot_ask_price) / mexc_spot_ask_price) * 10000
            expected_profit = spread_bps - (safe_offset * 10000)
            
            if expected_profit > min_profit_bps:
                return {
                    'opportunity_type': 'market_market',
                    'action': 'gateio_bid_spike',
                    'buy_exchange': 'GATEIO_SPOT',
                    'sell_exchange': 'MEXC_SPOT',
                    'buy_price': gateio_spot_bid_price,
                    'sell_price': mexc_spot_ask_price,
                    'spread_bps': spread_bps,
                    'safe_offset': safe_offset,
                    'execution_confidence': 0.9,  # High confidence for market orders
                    'expected_profit_bps': expected_profit,
                    'volatility_risk': 0.3,
                    'liquidity_risk': 0.2,
                    'timing_risk': 0.1
                }
        
        # Check MEXC bid > GATEIO ask (sell GATEIO, buy MEXC)
        if mexc_spot_bid_price > gateio_spot_ask_price:
            spread_bps = ((mexc_spot_bid_price - gateio_spot_ask_price) / gateio_spot_ask_price) * 10000
            expected_profit = spread_bps - (safe_offset * 10000)
            
            if expected_profit > min_profit_bps:
                return {
                    'opportunity_type': 'market_market',
                    'action': 'mexc_bid_spike',
                    'buy_exchange': 'MEXC_SPOT',
                    'sell_exchange': 'GATEIO_SPOT',
                    'buy_price': mexc_spot_bid_price,
                    'sell_price': gateio_spot_ask_price,
                    'spread_bps': spread_bps,
                    'safe_offset': safe_offset,
                    'execution_confidence': 0.9,
                    'expected_profit_bps': expected_profit,
                    'volatility_risk': 0.3,
                    'liquidity_risk': 0.2,
                    'timing_risk': 0.1
                }
        
        return None
    
    def _determine_signal_from_opportunity(self, opportunity: Dict[str, Any]) -> Signal:
        """Determine signal from detected opportunity."""
        if opportunity and opportunity['expected_profit_bps'] > self.min_profit_bps:
            return Signal.ENTER
        return Signal.HOLD
    
    def _calculate_vectorized_safe_offset(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate safe offset for entire DataFrame."""
        window = min(self.volatility_window, len(df))
        
        # Calculate rolling volatility
        mexc_returns = df['MEXC_SPOT:bid_price'].pct_change()
        gateio_returns = df['GATEIO_SPOT:bid_price'].pct_change()
        
        mexc_vol = mexc_returns.rolling(window=window).std().fillna(0.01)
        gateio_vol = gateio_returns.rolling(window=window).std().fillna(0.01)
        
        # Use maximum volatility for safety
        df['volatility'] = np.maximum(mexc_vol, gateio_vol)
        # TODO: tmp disabled
        df['safe_offset'] = 0
        # df['safe_offset'] = df['volatility'] * 2 + 0.0005 + self.safe_offset_pct
        # df['safe_offset'] = np.maximum(df['safe_offset'], 0.0005)
        
        return df

    
    def update_indicators(self, new_data: Union[Dict[str, Any], pd.DataFrame]) -> None:
        """
        Update rolling indicators with new market data.
        
        Args:
            new_data: New market data (single row or snapshot)
        """
        # Extract spread data from new_data
        if isinstance(new_data, dict):
            spreads = self._calculate_spread_from_market_data(new_data)
        else:  # DataFrame
            if len(new_data) > 0:
                latest_row = new_data.iloc[-1].to_dict()
                spreads = self._calculate_spread_from_market_data(latest_row)
            else:
                return
        
        # Update historical data for rolling calculations
        self._update_historical_data(spreads)
    
    def get_required_lookback(self) -> int:
        """
        Get the minimum lookback period required for the strategy.
        
        Returns:
            Number of historical periods needed for indicator calculation
        """
        return max(self.lookback_periods, self.volatility_window * 2)
    

    
    def validate_market_data(self, data: Union[Dict[str, Any], pd.DataFrame]) -> bool:
        """
        Validate that market data has required fields for the strategy.
        
        Args:
            data: Market data to validate
            
        Returns:
            True if data is valid, False otherwise
        """
        if isinstance(data, dict):
            # Check for required price fields
            required_fields = [
                'MEXC_SPOT:bid_price',
                'MEXC_SPOT:ask_price',
                'GATEIO_SPOT:bid_price',
                'GATEIO_SPOT:ask_price'
            ]
            
            for field in required_fields:
                if field not in data or data[field] <= 0:
                    return False
            
            return True
        
        elif isinstance(data, pd.DataFrame):
            if data.empty:
                return False
            
            # Check for required columns
            required_columns = [
                'MEXC_SPOT:bid_price', 'MEXC_SPOT:ask_price',
                'GATEIO_SPOT:bid_price', 'GATEIO_SPOT:ask_price'
            ]
            
            for col in required_columns:
                if col not in data.columns:
                    return False
                if data[col].isna().all() or (data[col] <= 0).all():
                    return False
            
            return True
        
        return False
    
    def calculate_signal_confidence(self, indicators: Dict[str, float]) -> float:
        """
        Calculate confidence score for the current signal.
        
        Args:
            indicators: Current indicator values
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not indicators:
            return 0.0
        
        # Extract key indicators
        execution_confidence = indicators.get('execution_confidence', 0)
        expected_profit_bps = indicators.get('expected_profit_bps', 0)
        spread_bps = indicators.get('spread_bps', 0)
        safe_offset = indicators.get('safe_offset', 0)
        
        # Base confidence from execution confidence
        base_confidence = execution_confidence
        
        # Adjust for profit potential
        profit_adjustment = min(expected_profit_bps / 30.0, 1.0)  # 30 bps = 100% adjustment
        
        # Adjust for spread quality (larger spreads = higher confidence)
        spread_adjustment = min(spread_bps / 50.0, 1.0)  # 50 bps = 100% adjustment
        
        # Adjust for safety margin (lower safe offset = higher confidence)
        safety_adjustment = max(0.5, 1.0 - safe_offset * 100)  # Convert to bps
        
        # Combined confidence
        total_confidence = (
            base_confidence * 0.4 +
            profit_adjustment * 0.3 +
            spread_adjustment * 0.2 +
            safety_adjustment * 0.1
        )
        
        return max(min(total_confidence, 1.0), 0.0)
    
    def _calculate_spread_from_market_data(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate spreads from market data.
        
        Args:
            market_data: Market data dictionary
            
        Returns:
            Dictionary of calculated spreads
        """
        # Extract prices
        mexc_spot_bid_price = market_data.get('MEXC_SPOT:bid_price', 0)
        mexc_spot_ask_price = market_data.get('MEXC_SPOT:ask_price', 0)
        gateio_spot_bid_price = market_data.get('GATEIO_SPOT:bid_price', 0)
        gateio_spot_ask_price = market_data.get('GATEIO_SPOT:ask_price', 0)
        
        if not all([mexc_spot_bid_price, mexc_spot_ask_price, gateio_spot_bid_price, gateio_spot_ask_price]):
            return {}
        
        # Calculate spreads matching arbitrage analyzer logic
        mexc_spot_mid_price = (mexc_spot_bid_price + mexc_spot_ask_price) / 2
        gateio_spot_mid_price = (gateio_spot_bid_price + gateio_spot_ask_price) / 2
        
        # Main spread for analysis
        mexc_vs_gateio_spot = (mexc_spot_mid_price - gateio_spot_mid_price) / gateio_spot_mid_price
        
        # Additional spreads for comprehensive analysis
        mexc_spot_spread = (mexc_spot_ask_price - mexc_spot_bid_price) / mexc_spot_mid_price
        gateio_spot_spread = (gateio_spot_ask_price - gateio_spot_bid_price) / gateio_spot_mid_price
        
        return {
            'mexc_vs_gateio_spot': mexc_vs_gateio_spot,
            'MEXC_SPOT:spread': mexc_spot_spread,
            'GATEIO_SPOT:spread': gateio_spot_spread,
            'MEXC_SPOT:mid_price': mexc_spot_mid_price,
            'GATEIO_SPOT:mid_price': gateio_spot_mid_price
        }
    
    def _update_historical_data(self, spreads: Dict[str, float]) -> None:
        """
        Update historical data for rolling calculations.
        
        Args:
            spreads: Dictionary of calculated spreads
        """
        # Update historical spreads for safe offset calculation
        main_spread = spreads.get('mexc_vs_gateio_spot', 0)
        
        # Add to historical data (simplified for this implementation)
        if not hasattr(self, 'historical_spreads'):
            self.historical_spreads = []
        
        self.historical_spreads.append(main_spread)
        if len(self.historical_spreads) > self.lookback_periods:
            self.historical_spreads.pop(0)