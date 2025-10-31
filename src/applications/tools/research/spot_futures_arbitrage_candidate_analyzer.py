from config import HftConfig
from exchanges.exchange_factory import get_rest_implementation
from exchanges.structs import SymbolInfo, Symbol
from exchanges.structs.common import AssetInfo
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from typing import List, Optional, Dict, Any, NamedTuple, Tuple
import asyncio
from datetime import datetime, UTC, timedelta
import pandas as pd
import numpy as np
import json
from pathlib import Path
from dataclasses import dataclass, field
from infrastructure.logging import get_logger
from trading.analysis.data_sources import CandlesLoader
from trading.research.cross_arbitrage.book_ticker_source import BookTickerDbSource, CandlesBookTickerSource
from trading.research.cross_arbitrage.hedged_cross_arbitrage_backtest import HedgedCrossArbitrageBacktest, BacktestConfig
from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer, AnalyzerKeys
from db import get_database_manager
from scipy import stats
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

ANALYZER_TF = KlineInterval.MINUTE_1


class ExecutionMode(Enum):
    """Execution strategy for arbitrage trades."""
    TAKER_TAKER = "taker_taker"      # Immediate execution both sides
    MAKER_TAKER = "maker_taker"      # Limit order entry, market exit
    MAKER_MAKER = "maker_maker"      # Limit orders both sides
    ADAPTIVE = "adaptive"            # Dynamic based on market conditions


@dataclass
class FeeStructure:
    """Fee structure for different execution modes."""
    spot_taker_fee: float = 0.001      # 0.1% taker fee
    spot_maker_fee: float = 0.0005     # 0.05% maker fee
    futures_taker_fee: float = 0.0005  # 0.05% futures taker
    futures_maker_fee: float = 0.0002  # 0.02% futures maker
    
    def get_total_fees(self, mode: ExecutionMode) -> float:
        """Calculate total round-trip fees for execution mode."""
        if mode == ExecutionMode.TAKER_TAKER:
            # Both entry and exit at taker fees
            return 2 * (self.spot_taker_fee + self.futures_taker_fee)
        elif mode == ExecutionMode.MAKER_TAKER:
            # Entry at maker, exit at taker
            entry = self.spot_maker_fee + self.futures_maker_fee
            exit = self.spot_taker_fee + self.futures_taker_fee
            return entry + exit
        elif mode == ExecutionMode.MAKER_MAKER:
            # Both at maker fees
            return 2 * (self.spot_maker_fee + self.futures_maker_fee)
        else:  # ADAPTIVE
            # Use weighted average
            return self.get_total_fees(ExecutionMode.MAKER_TAKER)


@dataclass
class ArbitrageOpportunity:
    """Represents a detected arbitrage opportunity."""
    symbol: Symbol
    timestamp: datetime
    spot_exchange: ExchangeEnum
    futures_exchange: ExchangeEnum
    spot_price: float
    futures_price: float
    basis_spread: float  # (futures - spot) / spot
    funding_rate: float
    execution_mode: ExecutionMode
    expected_profit_bps: float  # After fees
    confidence_score: float  # 0-100
    z_score: float
    entry_signal: str
    risk_metrics: Dict[str, float] = field(default_factory=dict)
    

@dataclass 
class BacktestResult:
    """Results from backtesting an arbitrage opportunity."""
    opportunity: ArbitrageOpportunity
    executed_trades: int
    total_pnl_usd: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    avg_holding_period_minutes: float
    execution_analysis: Dict[ExecutionMode, Dict[str, float]]



class SpotFuturesArbitrageCandidateAnalyzer:
    """Enhanced arbitrage candidate analyzer with multi-stage pipeline."""
    
    def __init__(self, exchanges: Optional[List[ExchangeEnum]] = None, output_dir: str = "results"):
        self.exchanges = exchanges or [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
        self.config = HftConfig()
        self.logger = get_logger("SpotFuturesArbitrageCandidateAnalyzer")
        # self.candle_loader = CandlesLoader(logger=self.logger)
        
        # Output configuration
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        

        self.clients = {exchange: self._get_exchange_client(exchange) for exchange in self.exchanges}
        self.symbol_df_cache: Dict[Symbol, pd.DataFrame] = {}
        self.candles_loader = CandlesLoader()
        self.fees: Dict[ExchangeEnum, float] = {ExchangeEnum.MEXC: 0.0005,
                                                ExchangeEnum.GATEIO: 0.001,
                                                ExchangeEnum.GATEIO_FUTURES: 0.0005}


    def _get_exchange_client(self, exchange: ExchangeEnum):
        return get_rest_implementation(self.config.get_exchange_config(exchange.value), False)

    async def get_tradable_pairs(self):
        si_result = await asyncio.gather(*[c.get_symbols_info() for c in self.clients.values()])

        symbols_info: Dict[ExchangeEnum, SymbolInfo] = {}
        symbol_exchanges: Dict[Symbol, List[ExchangeEnum]] = {}
        for exchange, symbols in zip(self.clients.keys(), si_result):
            symbols_info[exchange] = symbols
            for symbol in symbols.keys():
                if symbol not in symbol_exchanges:
                    symbol_exchanges[symbol] = []
                symbol_exchanges[symbol].append(exchange)


        symbols_with_futures = {symbol: exchanges for symbol, exchanges in symbol_exchanges.items() if ExchangeEnum.GATEIO_FUTURES in exchanges}

        pairs = []
        for symbol, exchanges in symbols_with_futures.items():
            for ex in exchanges:
                if ex != ExchangeEnum.GATEIO_FUTURES:
                    pairs.append((symbol, ex, ExchangeEnum.GATEIO_FUTURES))

        return pairs

    async def get_candles(self, exchanges: List[ExchangeEnum], symbol: Symbol, tf: KlineInterval,
                            start_date: datetime, end_date: datetime):
        tasks = [
            self.candles_loader.download_candles(
                exchange=exchange,
                symbol=symbol,
                timeframe=tf,
                start_date=start_date,
                end_date=end_date,
            )
            for exchange in exchanges
        ]

        results = await asyncio.gather(*tasks)

        exchange_df_map: dict[ExchangeEnum, Optional[pd.DataFrame]] = {}
        for exchange, df in zip(exchanges, results):
            exchange_df_map[exchange] = df

        return exchange_df_map


    async def quick_screening(self, pair: Tuple[Symbol, ExchangeEnum, ExchangeEnum], 
                             date_to: Optional[datetime]=None, hours: int = 24) -> Optional[ArbitrageOpportunity]:
        """
        Stage 1: Quick screening for spot-futures arbitrage opportunities.
        
        Args:
            pair: (Symbol, spot_exchange, futures_exchange)
            date_to: End time for analysis
            hours: Hours to analyze
            
        Returns:
            ArbitrageOpportunity if profitable, None otherwise
        """
        try:
            symbol, spot_ex, futures_ex = pair
            
            if date_to is None:
                date_to = datetime.now(UTC)
            date_from = date_to - timedelta(hours=hours)
            
            # Load candles for both exchanges
            candles = await self.get_candles(
                [spot_ex, futures_ex], 
                symbol, 
                KlineInterval.MINUTE_5,
                date_from, 
                date_to
            )
            
            spot_df = candles.get(spot_ex)
            futures_df = candles.get(futures_ex)
            
            if spot_df is None or futures_df is None or spot_df.empty or futures_df.empty:
                self.logger.warning(f"No data for {symbol} on {spot_ex}/{futures_ex}")
                return None
            
            # Merge dataframes on timestamp
            df = self._merge_candle_data(spot_df, futures_df, spot_ex, futures_ex)
            
            # Calculate arbitrage metrics
            opportunity = self._analyze_arbitrage_opportunity(df, symbol, spot_ex, futures_ex)
            
            return opportunity

        except Exception as e:
            self.logger.warning(f"Failed quick screening for {pair}: {e}")
            return None

    def _merge_candle_data(self, spot_df: pd.DataFrame, futures_df: pd.DataFrame, 
                          spot_ex: ExchangeEnum, futures_ex: ExchangeEnum) -> pd.DataFrame:
        """Merge spot and futures candle data with proper naming."""
        # Rename columns to avoid conflicts
        spot_df = spot_df.copy()
        futures_df = futures_df.copy()
        
        spot_cols = {
            'open': f'{spot_ex.value}_open',
            'high': f'{spot_ex.value}_high',
            'low': f'{spot_ex.value}_low',
            'close': f'{spot_ex.value}_close',
            'volume': f'{spot_ex.value}_volume'
        }
        
        futures_cols = {
            'open': f'{futures_ex.value}_open',
            'high': f'{futures_ex.value}_high',
            'low': f'{futures_ex.value}_low',
            'close': f'{futures_ex.value}_close',
            'volume': f'{futures_ex.value}_volume'
        }
        
        spot_df.rename(columns=spot_cols, inplace=True)
        futures_df.rename(columns=futures_cols, inplace=True)
        
        # Merge on timestamp
        df = pd.merge(spot_df, futures_df, on='timestamp', how='inner')
        df.sort_values('timestamp', inplace=True)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df.reset_index(drop=True, inplace=True)
        
        return df
    
    def _calculate_basis_metrics(self, df: pd.DataFrame, spot_col: str, futures_col: str) -> pd.DataFrame:
        """Calculate basis spread and statistical metrics."""
        # Basis spread as percentage
        df['basis_spread'] = ((df[futures_col] - df[spot_col]) / df[spot_col]) * 100
        
        # Rolling statistics for z-score
        window = 20  # 20 periods for statistics
        df['basis_mean'] = df['basis_spread'].rolling(window=window).mean()
        df['basis_std'] = df['basis_spread'].rolling(window=window).std()
        df['basis_z_score'] = (df['basis_spread'] - df['basis_mean']) / df['basis_std']
        
        # Volatility metrics
        df['spot_returns'] = df[spot_col].pct_change()
        df['futures_returns'] = df[futures_col].pct_change()
        df['spot_volatility'] = df['spot_returns'].rolling(window=window).std()
        df['futures_volatility'] = df['futures_returns'].rolling(window=window).std()
        
        return df
    
    def _analyze_execution_modes(self, df: pd.DataFrame, spot_ex: str, futures_ex: str, 
                                 fee_structure: FeeStructure) -> Dict[ExecutionMode, Dict[str, float]]:
        """Analyze profitability for different execution modes."""
        results = {}
        
        for mode in ExecutionMode:
            if mode == ExecutionMode.ADAPTIVE:
                continue  # Skip adaptive for now
                
            total_fees = fee_structure.get_total_fees(mode) * 100  # Convert to bps
            
            # Taker-Taker: Use close prices (immediate execution)
            if mode == ExecutionMode.TAKER_TAKER:
                entry_spread = df['basis_spread']
                profitable_periods = (entry_spread.abs() > total_fees).sum()
                avg_profit = (entry_spread.abs() - total_fees).clip(lower=0).mean()
                
            # Maker-Taker: Use high/low for limit order estimation
            elif mode == ExecutionMode.MAKER_TAKER:
                # Estimate limit order fills using high/low
                spot_limit_price = (df[f'{spot_ex}_high'] + df[f'{spot_ex}_low']) / 2
                futures_limit_price = (df[f'{futures_ex}_high'] + df[f'{futures_ex}_low']) / 2
                
                limit_basis = ((futures_limit_price - spot_limit_price) / spot_limit_price) * 100
                profitable_periods = (limit_basis.abs() > total_fees).sum()
                avg_profit = (limit_basis.abs() - total_fees).clip(lower=0).mean()
                
            # Maker-Maker: Most favorable prices
            else:  # MAKER_MAKER
                # Best possible execution using extremes
                best_spot = df[f'{spot_ex}_low']  # Best buy price
                best_futures = df[f'{futures_ex}_high']  # Best sell price
                
                best_basis = ((best_futures - best_spot) / best_spot) * 100
                profitable_periods = (best_basis > total_fees).sum()
                avg_profit = (best_basis - total_fees).clip(lower=0).mean()
            
            results[mode] = {
                'total_fees_bps': total_fees,
                'profitable_periods': profitable_periods,
                'profitable_ratio': profitable_periods / len(df) if len(df) > 0 else 0,
                'avg_profit_bps': avg_profit,
                'max_profit_bps': (df['basis_spread'].abs().max() - total_fees) if not df.empty else 0
            }
        
        return results
    
    def _calculate_risk_metrics(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate comprehensive risk metrics."""
        if df.empty or len(df) < 20:
            return {}
            
        returns = df['basis_spread'].pct_change().dropna()
        
        # Value at Risk (95% confidence)
        var_95 = np.percentile(returns, 5) if len(returns) > 0 else 0
        
        # Conditional VaR (Expected Shortfall)
        cvar_95 = returns[returns <= var_95].mean() if len(returns[returns <= var_95]) > 0 else 0
        
        # Maximum drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min() if len(drawdown) > 0 else 0
        
        # Sharpe ratio (assuming 0 risk-free rate)
        sharpe = returns.mean() / returns.std() if returns.std() > 0 else 0
        
        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        sortino = returns.mean() / downside_returns.std() if len(downside_returns) > 0 and downside_returns.std() > 0 else 0
        
        return {
            'var_95': var_95 * 100,  # Convert to percentage
            'cvar_95': cvar_95 * 100,
            'max_drawdown': max_drawdown * 100,
            'sharpe_ratio': sharpe * np.sqrt(252 * 24 * 12),  # Annualized for 5-min data
            'sortino_ratio': sortino * np.sqrt(252 * 24 * 12),
            'volatility': returns.std() * 100,
            'skewness': returns.skew() if len(returns) > 0 else 0,
            'kurtosis': returns.kurtosis() if len(returns) > 0 else 0
        }
    
    def _analyze_arbitrage_opportunity(self, df: pd.DataFrame, symbol: Symbol,
                                      spot_ex: ExchangeEnum, futures_ex: ExchangeEnum) -> Optional[ArbitrageOpportunity]:
        """Comprehensive analysis of arbitrage opportunity."""
        if df.empty or len(df) < 20:
            return None
            
        spot_col = f'{spot_ex.value}_close'
        futures_col = f'{futures_ex.value}_close'
        
        # Calculate basis metrics
        df = self._calculate_basis_metrics(df, spot_col, futures_col)
        
        # Analyze execution modes
        fee_structure = self.fees.get(spot_ex, 0.001), self.fees.get(futures_ex, 0.0005)
        fee_struct = FeeStructure(
            spot_taker_fee=self.fees.get(spot_ex, 0.001),
            futures_taker_fee=self.fees.get(futures_ex, 0.0005)
        )
        execution_analysis = self._analyze_execution_modes(df, spot_ex.value, futures_ex.value, fee_struct)
        
        # Calculate risk metrics
        risk_metrics = self._calculate_risk_metrics(df)
        
        # Find best execution mode
        best_mode = ExecutionMode.TAKER_TAKER
        best_profit = 0
        
        for mode, metrics in execution_analysis.items():
            if metrics['avg_profit_bps'] > best_profit:
                best_profit = metrics['avg_profit_bps']
                best_mode = mode
        
        # Skip if not profitable
        if best_profit <= 0:
            return None
        
        # Calculate confidence score based on multiple factors
        confidence = self._calculate_confidence_score(
            df, 
            execution_analysis[best_mode], 
            risk_metrics
        )
        
        # Get latest values
        latest = df.iloc[-1]
        
        return ArbitrageOpportunity(
            symbol=symbol,
            timestamp=latest['timestamp'],
            spot_exchange=spot_ex,
            futures_exchange=futures_ex,
            spot_price=latest[spot_col],
            futures_price=latest[futures_col],
            basis_spread=latest['basis_spread'],
            funding_rate=0.0,  # TODO: Get actual funding rate
            execution_mode=best_mode,
            expected_profit_bps=best_profit,
            confidence_score=confidence,
            z_score=latest.get('basis_z_score', 0),
            entry_signal=self._generate_entry_signal(latest, best_mode),
            risk_metrics=risk_metrics
        )
    
    def _calculate_confidence_score(self, df: pd.DataFrame, exec_metrics: Dict, 
                                   risk_metrics: Dict) -> float:
        """Calculate confidence score (0-100) for opportunity."""
        score = 50.0  # Base score
        
        # Profitability factor (up to +30)
        profit_factor = min(exec_metrics['avg_profit_bps'] * 10, 30)
        score += profit_factor
        
        # Hit rate factor (up to +20)
        hit_rate_factor = exec_metrics['profitable_ratio'] * 20
        score += hit_rate_factor
        
        # Risk adjustment (up to -30)
        if 'sharpe_ratio' in risk_metrics:
            if risk_metrics['sharpe_ratio'] < 0:
                score -= 10
            elif risk_metrics['sharpe_ratio'] > 2:
                score += 10
                
        if 'max_drawdown' in risk_metrics:
            if abs(risk_metrics['max_drawdown']) > 5:
                score -= 10
            elif abs(risk_metrics['max_drawdown']) < 2:
                score += 10
        
        # Statistical significance
        if len(df) > 100:
            score += 5
        
        # Clamp to 0-100
        return max(0, min(100, score))
    
    def _generate_entry_signal(self, latest: pd.Series, mode: ExecutionMode) -> str:
        """Generate descriptive entry signal."""
        signals = []
        
        # Z-score signal
        if 'basis_z_score' in latest:
            z = latest['basis_z_score']
            if abs(z) > 2:
                signals.append(f"High Z-score: {z:.2f}")
            elif abs(z) > 1:
                signals.append(f"Moderate Z-score: {z:.2f}")
        
        # Basis signal
        basis = latest.get('basis_spread', 0)
        if basis > 0:
            signals.append(f"Futures premium: {basis:.2f}%")
        else:
            signals.append(f"Futures discount: {abs(basis):.2f}%")
        
        # Execution mode
        signals.append(f"Mode: {mode.value}")
        
        return " | ".join(signals)

    async def pick_candidates(self, date_to: datetime, hours: int = 24) -> List[ArbitrageOpportunity]:
        """Stage 1: Screen all common symbols and identify candidates."""
        self.logger.info("🔍 Stage 1: Picking candidates...")
        
        # Get all tradable exchanges for arbitrage by symbol
        tradable_pairs = await self.get_tradable_pairs()
        self.logger.info(f"Found {len(tradable_pairs)} tradable pairs across {len(self.exchanges)} exchanges")
        
        # Process symbols with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Limit concurrent processing
        
        async def process_symbol(pair):
            async with semaphore:
                return await self.quick_screening(pair, date_to, hours)
        
        # Process all symbols in parallel
        tasks = [process_symbol(pair) for pair in tradable_pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None and exceptions
        opportunities = [r for r in results if isinstance(r, ArbitrageOpportunity)]
        
        # Sort by expected profit
        opportunities.sort(key=lambda x: x.expected_profit_bps, reverse=True)
        
        self.logger.info(f"Found {len(opportunities)} profitable opportunities")
        return opportunities

    
    async def backtest_opportunity(self, opportunity: ArbitrageOpportunity, 
                                  lookback_days: int = 7) -> BacktestResult:
        """
        Stage 2: Detailed backtesting of arbitrage opportunity.
        
        Simulates actual trading with:
        - Realistic entry/exit based on execution mode
        - Slippage estimation
        - Transaction costs
        - Position management
        """
        self.logger.info(f"📊 Backtesting {opportunity.symbol} ({opportunity.spot_exchange} vs {opportunity.futures_exchange})")
        
        # Load extended data for backtesting
        end_date = opportunity.timestamp
        start_date = end_date - timedelta(days=lookback_days)
        
        candles = await self.get_candles(
            [opportunity.spot_exchange, opportunity.futures_exchange],
            opportunity.symbol,
            KlineInterval.MINUTE_1,  # Use 1-min for detailed backtesting
            start_date,
            end_date
        )

        spot_df = candles.get(opportunity.spot_exchange)
        futures_df = candles.get(opportunity.futures_exchange)
        
        if spot_df is None or futures_df is None:
            return BacktestResult(
                opportunity=opportunity,
                executed_trades=0,
                total_pnl_usd=0,
                win_rate=0,
                sharpe_ratio=0,
                max_drawdown=0,
                avg_holding_period_minutes=0,
                execution_analysis={}
            )
        
        # Merge data
        df = self._merge_candle_data(spot_df, futures_df, 
                                     opportunity.spot_exchange, 
                                     opportunity.futures_exchange)
        
        # Run backtest simulation
        trades = self._simulate_trades(df, opportunity)
        
        # Calculate performance metrics
        if trades:
            pnl_series = pd.Series([t['pnl'] for t in trades])
            returns = pnl_series / 1000  # Assuming $1000 position size
            
            total_pnl = pnl_series.sum()
            win_rate = (pnl_series > 0).sum() / len(pnl_series) * 100
            
            # Sharpe ratio
            sharpe = returns.mean() / returns.std() * np.sqrt(252 * 24 * 60) if returns.std() > 0 else 0
            
            # Max drawdown
            cumulative = (1 + returns).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            max_dd = abs(drawdown.min()) * 100
            
            # Average holding period
            holding_periods = [t['holding_minutes'] for t in trades]
            avg_holding = np.mean(holding_periods)
            
            # Execution analysis by mode
            exec_analysis = self._analyze_execution_performance(trades)
        else:
            total_pnl = 0
            win_rate = 0
            sharpe = 0
            max_dd = 0
            avg_holding = 0
            exec_analysis = {}
        
        return BacktestResult(
            opportunity=opportunity,
            executed_trades=len(trades),
            total_pnl_usd=total_pnl,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            avg_holding_period_minutes=avg_holding,
            execution_analysis=exec_analysis
        )
    
    def _simulate_trades(self, df: pd.DataFrame, opportunity: ArbitrageOpportunity) -> List[Dict]:
        """Simulate trades based on z-score signals and execution mode."""
        trades = []
        position_open = False
        entry_index = None
        
        spot_col = f'{opportunity.spot_exchange.value}_close'
        futures_col = f'{opportunity.futures_exchange.value}_close'
        
        # Calculate signals
        df = self._calculate_basis_metrics(df, spot_col, futures_col)
        
        # Get fee structure
        fee_struct = FeeStructure(
            spot_taker_fee=self.fees.get(opportunity.spot_exchange, 0.001),
            futures_taker_fee=self.fees.get(opportunity.futures_exchange, 0.0005)
        )
        
        total_fees = fee_struct.get_total_fees(opportunity.execution_mode)
        
        for i in range(20, len(df)):  # Start after warm-up period
            row = df.iloc[i]
            
            if not position_open:
                # Entry logic based on z-score
                if abs(row['basis_z_score']) > 2 and abs(row['basis_spread']) > total_fees * 100:
                    # Enter position
                    entry_index = i
                    position_open = True
                    
            else:
                # Exit logic
                entry_row = df.iloc[entry_index]
                holding_time = (row['timestamp'] - entry_row['timestamp']).total_seconds() / 60
                
                # Exit conditions
                exit_signal = False
                if abs(row['basis_z_score']) < 0.5:  # Mean reversion
                    exit_signal = True
                elif holding_time > 240:  # 4 hour max holding
                    exit_signal = True
                elif row['basis_spread'] * entry_row['basis_spread'] < 0:  # Sign flip
                    exit_signal = True
                
                if exit_signal:
                    # Calculate PnL based on execution mode
                    pnl = self._calculate_trade_pnl(
                        entry_row, row, 
                        opportunity.execution_mode,
                        fee_struct,
                        opportunity.spot_exchange.value,
                        opportunity.futures_exchange.value
                    )
                    
                    trades.append({
                        'entry_time': entry_row['timestamp'],
                        'exit_time': row['timestamp'],
                        'entry_basis': entry_row['basis_spread'],
                        'exit_basis': row['basis_spread'],
                        'holding_minutes': holding_time,
                        'pnl': pnl,
                        'execution_mode': opportunity.execution_mode.value
                    })
                    
                    position_open = False
        
        return trades
    
    def _calculate_trade_pnl(self, entry_row: pd.Series, exit_row: pd.Series,
                            mode: ExecutionMode, fee_struct: FeeStructure,
                            spot_ex: str, futures_ex: str) -> float:
        """Calculate PnL for a single trade."""
        position_size = 1000  # $1000 position
        
        # Get prices based on execution mode
        if mode == ExecutionMode.TAKER_TAKER:
            # Use close prices for market orders
            entry_spot = entry_row[f'{spot_ex}_close']
            entry_futures = entry_row[f'{futures_ex}_close']
            exit_spot = exit_row[f'{spot_ex}_close']
            exit_futures = exit_row[f'{futures_ex}_close']
            
        elif mode == ExecutionMode.MAKER_TAKER:
            # Use mid prices for entry (limit), close for exit (market)
            entry_spot = (entry_row[f'{spot_ex}_high'] + entry_row[f'{spot_ex}_low']) / 2
            entry_futures = (entry_row[f'{futures_ex}_high'] + entry_row[f'{futures_ex}_low']) / 2
            exit_spot = exit_row[f'{spot_ex}_close']
            exit_futures = exit_row[f'{futures_ex}_close']
            
        else:  # MAKER_MAKER
            # Use favorable prices
            entry_spot = entry_row[f'{spot_ex}_low']
            entry_futures = entry_row[f'{futures_ex}_high']
            exit_spot = exit_row[f'{spot_ex}_high']
            exit_futures = exit_row[f'{futures_ex}_low']
        
        # Calculate returns
        spot_return = (exit_spot - entry_spot) / entry_spot
        futures_return = (exit_futures - entry_futures) / entry_futures
        
        # For delta-neutral: long spot, short futures
        if entry_row['basis_spread'] > 0:  # Futures premium
            # Cash and carry: Buy spot, sell futures
            gross_return = spot_return - futures_return
        else:  # Futures discount
            # Reverse: Sell spot, buy futures
            gross_return = futures_return - spot_return
        
        # Apply fees
        total_fees = fee_struct.get_total_fees(mode)
        net_return = gross_return - total_fees
        
        return position_size * net_return
    
    def _analyze_execution_performance(self, trades: List[Dict]) -> Dict:
        """Analyze performance by execution mode."""
        mode_performance = {}
        
        for mode in ExecutionMode:
            mode_trades = [t for t in trades if t.get('execution_mode') == mode.value]
            
            if mode_trades:
                pnls = [t['pnl'] for t in mode_trades]
                mode_performance[mode] = {
                    'count': len(mode_trades),
                    'total_pnl': sum(pnls),
                    'avg_pnl': np.mean(pnls),
                    'win_rate': sum(1 for p in pnls if p > 0) / len(pnls) * 100,
                    'best_trade': max(pnls),
                    'worst_trade': min(pnls)
                }
        
        return mode_performance
    
    async def backtest_candidates(self, candidates: List[ArbitrageOpportunity], 
                                 max_backtests: int = 50) -> List[BacktestResult]:
        """Stage 2: Backtest top candidates."""
        self.logger.info(f"📈 Stage 2: Backtesting top {max_backtests} candidates...")
        
        # Take top candidates
        top_candidates = candidates[:max_backtests]
        
        # Backtest each candidate
        # backtest_tasks = [
        #     self.backtest_opportunity(candidate, lookback_days=2)
        #     for candidate in top_candidates
        # ]
        #
        # results = await asyncio.gather(*backtest_tasks)
        results = []
        for candidate in top_candidates:
            result = await self.backtest_opportunity(candidate, lookback_days=2)
            results.append(result)
        # Sort by total PnL
        results.sort(key=lambda x: x.total_pnl_usd, reverse=True)
        
        return results
    
    async def save_results(self, results: List[BacktestResult]):
        """Stage 3: Save analysis results."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save summary CSV
        summary_data = []
        for result in results:
            summary_data.append({
                'symbol': str(result.opportunity.symbol),
                'spot_exchange': result.opportunity.spot_exchange.value,
                'futures_exchange': result.opportunity.futures_exchange.value,
                'basis_spread': result.opportunity.basis_spread,
                'execution_mode': result.opportunity.execution_mode.value,
                'expected_profit_bps': result.opportunity.expected_profit_bps,
                'confidence_score': result.opportunity.confidence_score,
                'executed_trades': result.executed_trades,
                'total_pnl_usd': result.total_pnl_usd,
                'win_rate': result.win_rate,
                'sharpe_ratio': result.sharpe_ratio,
                'max_drawdown': result.max_drawdown
            })
        
        summary_df = pd.DataFrame(summary_data)
        summary_file = self.output_dir / f"arbitrage_analysis_{timestamp}.csv"
        summary_df.to_csv(summary_file, index=False)
        
        # Save detailed JSON
        detailed_results = []
        for result in results:
            detailed_results.append({
                'opportunity': {
                    'symbol': str(result.opportunity.symbol),
                    'timestamp': result.opportunity.timestamp.isoformat(),
                    'spot_exchange': result.opportunity.spot_exchange.value,
                    'futures_exchange': result.opportunity.futures_exchange.value,
                    'spot_price': result.opportunity.spot_price,
                    'futures_price': result.opportunity.futures_price,
                    'basis_spread': result.opportunity.basis_spread,
                    'execution_mode': result.opportunity.execution_mode.value,
                    'expected_profit_bps': result.opportunity.expected_profit_bps,
                    'confidence_score': result.opportunity.confidence_score,
                    'z_score': result.opportunity.z_score,
                    'entry_signal': result.opportunity.entry_signal,
                    'risk_metrics': result.opportunity.risk_metrics
                },
                'backtest': {
                    'executed_trades': result.executed_trades,
                    'total_pnl_usd': result.total_pnl_usd,
                    'win_rate': result.win_rate,
                    'sharpe_ratio': result.sharpe_ratio,
                    'max_drawdown': result.max_drawdown,
                    'avg_holding_period_minutes': result.avg_holding_period_minutes,
                    'execution_analysis': {
                        mode.value: metrics for mode, metrics in result.execution_analysis.items()
                    }
                }
            })
        
        json_file = self.output_dir / f"arbitrage_details_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(detailed_results, f, indent=2)
        
        self.logger.info(f"💾 Results saved to {summary_file} and {json_file}")
    
    def print_summary(self, results: List[BacktestResult]):
        """Print analysis summary."""
        print("\n" + "="*80)
        print("📊 SPOT-FUTURES ARBITRAGE ANALYSIS SUMMARY")
        print("="*80)
        
        if not results:
            print("No profitable opportunities found")
            return
        
        print(f"\nTop {len(results)} Arbitrage Opportunities:\n")
        
        for i, result in enumerate(results[:5], 1):
            opp = result.opportunity
            print(f"{i}. {opp.symbol} ({opp.spot_exchange.value} vs {opp.futures_exchange.value})")
            print(f"   Basis Spread: {opp.basis_spread:.2f}%")
            print(f"   Execution Mode: {opp.execution_mode.value}")
            print(f"   Expected Profit: {opp.expected_profit_bps:.2f} bps")
            print(f"   Confidence: {opp.confidence_score:.1f}/100")
            print(f"   Z-Score: {opp.z_score:.2f}")
            
            print(f"\n   Backtest Results:")
            print(f"   - Trades Executed: {result.executed_trades}")
            print(f"   - Total PnL: ${result.total_pnl_usd:.2f}")
            print(f"   - Win Rate: {result.win_rate:.1f}%")
            print(f"   - Sharpe Ratio: {result.sharpe_ratio:.2f}")
            print(f"   - Max Drawdown: {result.max_drawdown:.1f}%")
            print(f"   - Avg Holding: {result.avg_holding_period_minutes:.0f} minutes")
            
            # Risk metrics
            if opp.risk_metrics:
                print(f"\n   Risk Metrics:")
                print(f"   - VaR (95%): {opp.risk_metrics.get('var_95', 0):.2f}%")
                print(f"   - Volatility: {opp.risk_metrics.get('volatility', 0):.2f}%")
                print(f"   - Sortino Ratio: {opp.risk_metrics.get('sortino_ratio', 0):.2f}")
            
            print("-" * 40)
        
        # Overall statistics
        total_pnl = sum(r.total_pnl_usd for r in results)
        avg_sharpe = np.mean([r.sharpe_ratio for r in results])
        avg_confidence = np.mean([r.opportunity.confidence_score for r in results])
        
        print(f"\nOverall Statistics:")
        print(f"  Total Opportunities: {len(results)}")
        print(f"  Combined PnL: ${total_pnl:.2f}")
        print(f"  Average Sharpe: {avg_sharpe:.2f}")
        print(f"  Average Confidence: {avg_confidence:.1f}/100")
        
        # Execution mode breakdown
        mode_counts = {}
        for r in results:
            mode = r.opportunity.execution_mode
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        
        print(f"\nExecution Mode Distribution:")
        for mode, count in mode_counts.items():
            print(f"  {mode.value}: {count} ({count/len(results)*100:.1f}%)")
        
        print("="*80)

    async def analyze(self, date_to: datetime, hours: int, max_backtests: int = 10):
        """Complete 3-stage analysis pipeline."""
        try:
            # Initialize database connection if needed
            # await get_database_manager()
            
            # Stage 1: Pick candidates
            candidates = await self.pick_candidates(date_to, hours)
            
            if not candidates:
                self.logger.warning("No candidates found during screening")
                return
            
            # Stage 2: Backtest top candidates
            backtest_results = await self.backtest_candidates(candidates, max_backtests)
            
            # Stage 3: Save results
            await self.save_results(backtest_results)
            
            # Print summary
            self.print_summary(backtest_results)
            
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            raise
    


if __name__ == "__main__":
    async def main():
        """Example usage of the enhanced analyzer."""
        analyzer = SpotFuturesArbitrageCandidateAnalyzer(
            exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES],
            output_dir="../arbitrage_results"
        )
        
        # end_time = datetime.now(UTC)
        hours = 24

        end_time = datetime.fromisoformat("2025-10-30 03:00:00+00:00")
        start_time = end_time - pd.Timedelta(hours=hours)

        print("🚀 Starting Arbitrage Candidate Analysis")
        print(f"📅 Analysis Period: {start_time} to {end_time}")
        print(f"🏢 Exchanges: {[e.value for e in analyzer.exchanges]}")
        
        await analyzer.analyze(end_time, hours, max_backtests=50)
        
        print("\n✅ Analysis completed successfully!")
    
    asyncio.run(main())

