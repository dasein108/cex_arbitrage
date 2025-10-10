"""
Base Arbitrage Strategy Framework

Provides abstract base classes and interfaces for implementing flexible arbitrage strategies
that are compatible with the existing DualExchange and BaseTradingTask patterns.

This framework supports:
- Variable exchange count (2, 3, or N exchanges)
- Real-time WebSocket integration
- Event-driven execution with HFT performance
- Flexible exchange type combinations (spot, futures, mixed)
- BaseTradingTask integration with proper state management
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type, Union, Callable, Any, TypeVar, Generic
from enum import IntEnum
import time

import msgspec

from exchanges.dual_exchange import DualExchange
from exchanges.structs import Symbol, BookTicker, Order, AssetBalance, Position, ExchangeEnum
from exchanges.structs.common import FuturesBalance
from exchanges.structs.common import Side
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from trading.tasks.base_task import BaseTradingTask, TaskContext
from trading.struct import TradingStrategyState
from config.config_manager import get_exchange_config


# Generic type parameter for strategy context that inherits from ArbitrageTaskContext
T = TypeVar('T', bound='ArbitrageTaskContext')


class ArbitrageState(IntEnum):
    """Enhanced states for arbitrage strategy execution."""
    IDLE = 0
    INITIALIZING = 1        # Initialize exchanges and connections
    MONITORING = 2          # Monitor spreads and opportunities
    ANALYZING = 3           # Analyze opportunity viability
    PREPARING = 4           # Prepare for execution (position sizing, risk checks)
    EXECUTING = 5           # Execute arbitrage trades
    REBALANCING = 6         # Rebalance positions for delta neutrality
    COMPLETING = 7          # Finalize arbitrage cycle
    ERROR_RECOVERY = 8      # Handle errors and recovery


class ExchangeRole(msgspec.Struct):
    """Defines role and configuration for an exchange in arbitrage strategy."""
    exchange_enum: ExchangeEnum
    role: str  # e.g., 'primary_spot', 'hedge_futures', 'arbitrage_target'
    side: Optional[Side] = None  # For strategies with fixed sides per exchange
    max_position_size: Optional[float] = None
    priority: int = 0  # Execution priority (0 = highest)


class ArbitrageOpportunity(msgspec.Struct):
    """Represents an arbitrage opportunity between exchanges."""
    primary_exchange: ExchangeEnum
    target_exchange: ExchangeEnum
    symbol: Symbol
    spread_pct: float
    primary_price: float
    target_price: float
    max_quantity: float
    estimated_profit: float
    confidence_score: float
    timestamp: float = msgspec.field(default_factory=time.time)


class ArbitrageTaskContext(TaskContext):
    """Context for arbitrage trading tasks."""
    # Strategy configuration
    symbol: Symbol
    exchange_roles: Dict[str, ExchangeRole] = msgspec.field(default_factory=dict)
    base_position_size: float = 100.0
    max_position_multiplier: float = 3.0
    
    # Opportunity thresholds
    entry_threshold_pct: float = 0.1  # 0.1% minimum spread
    exit_threshold_pct: float = 0.01   # 0.01% minimum exit spread
    max_slippage_pct: float = 0.05     # 5% max slippage tolerance
    
    # Position tracking (generic for all strategies)
    positions: Dict[str, float] = msgspec.field(default_factory=dict)  # exchange_key -> position_size
    avg_prices: Dict[str, float] = msgspec.field(default_factory=dict)  # exchange_key -> avg_price
    unrealized_pnl: Dict[str, float] = msgspec.field(default_factory=dict)  # exchange_key -> pnl
    
    # Current opportunity
    current_opportunity: Optional[ArbitrageOpportunity] = None
    opportunity_start_time: Optional[float] = None
    
    # Performance tracking
    total_trades: int = 0
    total_volume: float = 0.0
    total_profit: float = 0.0
    total_fees: float = 0.0
    arbitrage_cycles: int = 0
    
    # Risk management
    max_drawdown_pct: float = 2.0
    position_timeout_seconds: int = 300  # 5 minutes max position hold
    
    # State tracking
    last_price_check: float = 0.0
    price_check_interval: float = 0.1  # 100ms between price checks


class BaseArbitrageStrategy(BaseTradingTask[T, ArbitrageState], Generic[T], ABC):
    """
    Abstract base class for arbitrage strategies.
    
    Provides common functionality for:
    - Multi-exchange management using DualExchange pattern
    - Real-time market data subscriptions
    - Event-driven execution with HFT performance
    - State machine management compatible with BaseTradingTask
    - Flexible exchange role configuration
    """
    
    name: str = "BaseArbitrageStrategy"
    
    @property
    def context_class(self) -> Type[T]:
        """Return the arbitrage context class."""
        return ArbitrageTaskContext
    
    def __init__(self, 
                 logger: HFTLoggerInterface,
                 context: T,
                 **kwargs):
        """Initialize base arbitrage strategy.
        
        Args:
            logger: HFT logger instance
            context: Arbitrage task context with exchange roles and configuration
        """
        super().__init__(logger, context, **kwargs)
        
        # Initialize DualExchange instances for each configured exchange
        self._exchanges: Dict[str, DualExchange] = {}
        self._exchange_roles: Dict[str, ExchangeRole] = context.exchange_roles
        
        # Initialize exchanges based on roles
        for role_key, role_config in self._exchange_roles.items():
            config = get_exchange_config(role_config.exchange_enum.value)
            self._exchanges[role_key] = DualExchange.get_instance(config, self.logger)
        
        # Market data storage (fresh, no caching per HFT policy)
        self._current_book_tickers: Dict[str, BookTicker] = {}
        self._pending_orders: Dict[str, List[Order]] = {}
        
        # Performance tracking
        self._cycle_start_time: float = 0.0
        self._last_opportunity_check: float = 0.0
    
    def _build_tag(self) -> None:
        """Build logging tag with arbitrage-specific fields."""
        exchange_names = [role.exchange_enum.name for role in self._exchange_roles.values()]
        self._tag = f'{self.name}_{self.context.symbol}_{"+".join(exchange_names)}'
    
    async def start(self, **kwargs):
        """Start arbitrage strategy with DualExchange initialization."""
        await super().start(**kwargs)
        
        # Initialize all DualExchanges in parallel for HFT performance
        init_tasks = []
        for role_key, exchange in self._exchanges.items():
            init_tasks.append(
                exchange.initialize(
                    symbols=[self.context.symbol],
                    public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                    private_channels=[
                        PrivateWebsocketChannelType.ORDER,
                        PrivateWebsocketChannelType.BALANCE
                        # Note: POSITION channel removed - not supported by MEXC, use order fills for position tracking
                    ]
                )
            )
        
        await asyncio.gather(*init_tasks)
        
        # Bind event handlers for real-time updates
        await self._bind_event_handlers()
        
        self.logger.info(f"✅ Arbitrage strategy initialized with {len(self._exchanges)} exchanges")
    
    async def _bind_event_handlers(self):
        """Bind WebSocket event handlers for real-time market data."""
        for role_key, exchange in self._exchanges.items():
            await exchange.bind_handlers(
                on_book_ticker=self._create_book_ticker_handler(role_key),
                on_order=self._create_order_handler(role_key),
                on_balance=self._create_balance_handler(role_key),
                on_position=self._create_position_handler(role_key)
            )
    
    def _create_book_ticker_handler(self, role_key: str) -> Callable[[BookTicker], None]:
        """Create book ticker handler for specific exchange role."""
        async def handle_book_ticker(book_ticker: BookTicker):
            if book_ticker.symbol == self.context.symbol:
                self._current_book_tickers[role_key] = book_ticker
                # Trigger opportunity analysis if enough time has passed
                current_time = time.time()
                if (current_time - self._last_opportunity_check) >= self.context.price_check_interval:
                    self._last_opportunity_check = current_time
                    if self.context.state == ArbitrageState.MONITORING:
                        # Schedule opportunity analysis (don't block WebSocket handler)
                        asyncio.create_task(self._analyze_opportunity_async())
        return handle_book_ticker
    
    def _create_order_handler(self, role_key: str) -> Callable[[Order], None]:
        """Create order update handler for specific exchange role."""
        async def handle_order(order: Order):
            if order.symbol == self.context.symbol:
                await self._process_order_update(role_key, order)
        return handle_order
    
    def _create_balance_handler(self, role_key: str) -> Callable[[AssetBalance], None]:
        """Create balance update handler for specific exchange role."""
        async def handle_balance(balance: AssetBalance):
            await self._process_balance_update(role_key, balance)
        return handle_balance
    
    def _create_position_handler(self, role_key: str) -> Callable[[Position], None]:
        """Create position update handler for specific exchange role."""
        async def handle_position(position: Position):
            if position.symbol == self.context.symbol:
                await self._process_position_update(role_key, position)
        return handle_position
    
    async def _analyze_opportunity_async(self):
        """Asynchronously analyze arbitrage opportunity without blocking."""
        try:
            if len(self._current_book_tickers) >= 2:  # Need at least 2 exchanges for arbitrage
                opportunity = await self._identify_arbitrage_opportunity()
                if opportunity and opportunity.spread_pct >= self.context.entry_threshold_pct:
                    self.evolve_context(current_opportunity=opportunity)
                    if self.context.state == ArbitrageState.MONITORING:
                        self._transition(ArbitrageState.ANALYZING)
        except Exception as e:
            self.logger.warning(f"Opportunity analysis failed: {e}")
    
    # Abstract methods for strategy-specific implementation
    
    @abstractmethod
    async def _identify_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """Identify arbitrage opportunities from current market data.
        
        Must be implemented by subclasses to define specific arbitrage logic.
        
        Returns:
            ArbitrageOpportunity or None if no opportunity exists
        """
        pass
    
    @abstractmethod
    async def _execute_arbitrage_trades(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute arbitrage trades for the given opportunity.
        
        Must be implemented by subclasses to define specific execution logic.
        
        Args:
            opportunity: The arbitrage opportunity to execute
            
        Returns:
            bool: True if execution was successful
        """
        pass
    
    @abstractmethod
    async def _rebalance_positions(self) -> bool:
        """Rebalance positions to maintain strategy objectives (e.g., delta neutrality).
        
        Must be implemented by subclasses to define rebalancing logic.
        
        Returns:
            bool: True if rebalancing was successful
        """
        pass
    
    # Common state handlers (can be overridden by subclasses)
    
    async def _handle_idle(self):
        """Handle idle state - transition to initialization."""
        await super()._handle_idle()
        self._transition(ArbitrageState.INITIALIZING)
    
    async def _handle_initializing(self):
        """Initialize strategy components and market data."""
        self.logger.info(f"Initializing arbitrage strategy for {self.context.symbol}")
        
        try:
            # Verify all exchanges are connected and have market data
            all_ready = True
            for role_key, exchange in self._exchanges.items():
                if not exchange.public.symbols_info.get(self.context.symbol):
                    all_ready = False
                    break
            
            if all_ready:
                self.logger.info("✅ All exchanges initialized successfully")
                self._transition(ArbitrageState.MONITORING)
            else:
                # Wait and retry
                await asyncio.sleep(1.0)
                
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            self._transition(ArbitrageState.ERROR_RECOVERY)
    
    async def _handle_monitoring(self):
        """Monitor market for arbitrage opportunities."""
        # Opportunity detection is handled by event handlers
        # This state just maintains monitoring status
        await asyncio.sleep(0.1)  # Small delay to prevent tight loops
    
    async def _handle_analyzing(self):
        """Analyze current opportunity for viability."""
        if not self.context.current_opportunity:
            self._transition(ArbitrageState.MONITORING)
            return
        
        opportunity = self.context.current_opportunity
        
        # Verify opportunity is still valid (prices haven't moved significantly)
        if await self._validate_opportunity(opportunity):
            self.logger.info(f"💰 Valid arbitrage opportunity: {opportunity.spread_pct:.4f}% spread")
            self._transition(ArbitrageState.PREPARING)
        else:
            self.logger.info("⚠️ Opportunity no longer valid, returning to monitoring")
            self.evolve_context(current_opportunity=None)
            self._transition(ArbitrageState.MONITORING)
    
    async def _handle_preparing(self):
        """Prepare for arbitrage execution."""
        if not self.context.current_opportunity:
            self._transition(ArbitrageState.MONITORING)
            return
        
        opportunity = self.context.current_opportunity
        
        # Calculate position sizes and risk parameters
        max_position = min(
            self.context.base_position_size * self.context.max_position_multiplier,
            opportunity.max_quantity
        )
        
        # Final validation before execution
        if await self._pre_execution_checks(opportunity, max_position):
            self.evolve_context(opportunity_start_time=time.time())
            self._transition(ArbitrageState.EXECUTING)
        else:
            self.logger.warning("Pre-execution checks failed, aborting opportunity")
            self.evolve_context(current_opportunity=None)
            self._transition(ArbitrageState.MONITORING)
    
    async def _handle_executing(self):
        """Execute arbitrage trades."""
        if not self.context.current_opportunity:
            self._transition(ArbitrageState.MONITORING)
            return
        
        opportunity = self.context.current_opportunity
        self._cycle_start_time = time.time()
        
        try:
            success = await self._execute_arbitrage_trades(opportunity)
            
            if success:
                self.logger.info(f"✅ Arbitrage execution successful")
                # Update performance metrics
                self.evolve_context(total_trades=self.context.total_trades + 1)
                self._transition(ArbitrageState.REBALANCING)
            else:
                self.logger.warning("❌ Arbitrage execution failed")
                self._transition(ArbitrageState.ERROR_RECOVERY)
                
        except Exception as e:
            self.logger.error(f"Execution error: {e}")
            self._transition(ArbitrageState.ERROR_RECOVERY)
    
    async def _handle_rebalancing(self):
        """Rebalance positions after arbitrage execution."""
        try:
            success = await self._rebalance_positions()
            
            if success:
                self.logger.info("✅ Position rebalancing successful")
                self._transition(ArbitrageState.COMPLETING)
            else:
                self.logger.warning("⚠️ Rebalancing had issues, proceeding to completion")
                self._transition(ArbitrageState.COMPLETING)
                
        except Exception as e:
            self.logger.error(f"Rebalancing error: {e}")
            self._transition(ArbitrageState.ERROR_RECOVERY)
    
    async def _handle_completing(self):
        """Complete arbitrage cycle and return to monitoring."""
        # Calculate cycle performance
        cycle_time = time.time() - self._cycle_start_time
        self.logger.info(f"⏱️ Arbitrage cycle completed in {cycle_time*1000:.1f}ms")
        
        # Clear current opportunity
        self.evolve_context(current_opportunity=None, opportunity_start_time=None)
        
        # Return to monitoring for next opportunity
        self._transition(ArbitrageState.MONITORING)
    
    async def _handle_error_recovery(self):
        """Handle errors and attempt recovery."""
        self.logger.info("🔄 Attempting error recovery")
        
        # Clear any failed opportunity
        self.evolve_context(current_opportunity=None, opportunity_start_time=None)
        
        # Cancel any pending orders
        cancel_tasks = []
        for role_key, exchange in self._exchanges.items():
            cancel_tasks.append(self._cancel_all_orders(exchange))
        
        await asyncio.gather(*cancel_tasks, return_exceptions=True)
        
        # Wait before returning to monitoring
        await asyncio.sleep(1.0)
        self._transition(ArbitrageState.MONITORING)
    
    # Utility methods
    
    def _get_role_key_for_exchange(self, exchange_enum: ExchangeEnum) -> Optional[str]:
        """Map ExchangeEnum to role key used in _current_book_tickers.
        
        Args:
            exchange_enum: The exchange enum (e.g., ExchangeEnum.MEXC)
            
        Returns:
            Role key string (e.g., 'spot', 'futures') or None if not found
        """
        for role_key, role_config in self._exchange_roles.items():
            if role_config.exchange_enum == exchange_enum:
                return role_key
        return None
    
    async def _validate_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate that opportunity is still viable."""
        # Map exchange enums to role keys to access current book tickers
        primary_role_key = self._get_role_key_for_exchange(opportunity.primary_exchange)
        target_role_key = self._get_role_key_for_exchange(opportunity.target_exchange)
        
        if not primary_role_key or not target_role_key:
            self.logger.warning(f"Cannot find role keys for exchanges: primary={opportunity.primary_exchange}, target={opportunity.target_exchange}")
            return False
        
        # Get current book tickers using role keys (not exchange names)
        primary_ticker = self._current_book_tickers.get(primary_role_key)
        target_ticker = self._current_book_tickers.get(target_role_key)
        
        if not primary_ticker or not target_ticker:
            self.logger.debug(f"Missing book ticker data: primary_role='{primary_role_key}' ticker={bool(primary_ticker)}, target_role='{target_role_key}' ticker={bool(target_ticker)}")
            return False
        
        # Calculate current spread using proper cross-exchange bid/ask comparison
        # For arbitrage, we need to check if we can still execute profitably
        
        # Direction 1: Buy from primary exchange, sell to target exchange
        primary_buy_price = primary_ticker.ask_price  # Price to buy from primary
        target_sell_price = target_ticker.bid_price   # Price to sell to target
        primary_to_target_spread = (target_sell_price - primary_buy_price) / primary_buy_price * 100
        
        # Direction 2: Buy from target exchange, sell to primary exchange  
        target_buy_price = target_ticker.ask_price    # Price to buy from target
        primary_sell_price = primary_ticker.bid_price # Price to sell to primary
        target_to_primary_spread = (primary_sell_price - target_buy_price) / target_buy_price * 100
        
        # Use the better spread (maximum profitability)
        best_current_spread = max(primary_to_target_spread, target_to_primary_spread)
        
        # Entry threshold is already in percentage format, no conversion needed
        entry_threshold_pct = float(self.context.entry_threshold_pct)
        
        return best_current_spread >= entry_threshold_pct
    
    async def _pre_execution_checks(self, opportunity: ArbitrageOpportunity, position_size: float) -> bool:
        """Perform pre-execution validation and risk checks."""
        try:
            # Prepare orders for validation
            orders = await self._prepare_orders_for_opportunity(opportunity, position_size)
            if not orders:
                self.logger.error("❌ Failed to prepare orders for validation")
                return False
            
            # Validate sufficient balance for all orders
            if not await self._validate_sufficient_balance(orders):
                self.logger.error("❌ Insufficient balance for arbitrage execution")
                return False
            
            # Validate position sizes are within limits
            if not await self._validate_position_limits(position_size):
                self.logger.error("❌ Position size exceeds limits")
                return False
            
            # Validate market conditions are suitable
            if not await self._validate_market_conditions(opportunity):
                self.logger.error("❌ Market conditions unsuitable for execution")
                return False
            
            self.logger.info(f"✅ Pre-execution checks passed for position size {position_size}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Pre-execution check failed: {e}")
            return False
    
    async def _prepare_orders_for_opportunity(self, opportunity: ArbitrageOpportunity, position_size: float) -> Optional[Dict[str, dict]]:
        """Prepare order structure for validation - to be implemented by subclasses."""
        # This method should be implemented by subclasses to prepare the actual order structure
        # based on their specific exchange roles and trading logic
        self.logger.warning("_prepare_orders_for_opportunity not implemented in subclass")
        return None
    
    async def _validate_sufficient_balance(self, orders: Dict[str, dict]) -> bool:
        """Validate sufficient balance for all planned orders with futures margin support."""
        try:
            for role_key, order_params in orders.items():
                exchange = self._exchanges.get(role_key)
                if not exchange:
                    self.logger.warning(f"Exchange not found for role: {role_key}")
                    continue
                
                # Get current balances
                try:
                    balances = exchange.private.balances
                except Exception as e:
                    self.logger.error(f"Failed to get balances for {role_key}: {e}")
                    return False
                
                # Check if this is a futures exchange (balances are FuturesBalance type)
                is_futures = role_key == 'futures'
                
                # For sell orders, check base asset availability
                if order_params['side'] == Side.SELL:
                    base_asset = self.context.symbol.base
                    base_balance = balances.get(base_asset, AssetBalance(base_asset, 0, 0))
                    
                    required_quantity = float(order_params['quantity'])
                    available_quantity = float(base_balance.available) if base_balance else 0.0
                    
                    if available_quantity < required_quantity:
                        self.logger.warning(
                            f"Insufficient {base_asset} balance on {role_key}: "
                            f"need {required_quantity}, have {available_quantity}"
                        )
                        return False
                    
                    self.logger.debug(f"✅ {role_key} {base_asset} balance check passed: {available_quantity} >= {required_quantity}")
                
                # For buy orders, check quote asset availability (or margin for futures)
                elif order_params['side'] == Side.BUY:
                    quote_asset = self.context.symbol.quote
                    quote_balance = balances[quote_asset]
                    
                    required_quote = float(order_params['quantity']) * float(order_params['price'])
                    
                    if is_futures and isinstance(quote_balance, FuturesBalance):
                        # For futures, check available margin and utilization
                        available_margin = float(quote_balance.available)
                        margin_utilization = quote_balance.margin_utilization
                        
                        # Add 5% buffer for fees and margin requirements
                        required_margin_with_buffer = required_quote * 1.05
                        
                        # Check margin availability
                        if available_margin < required_margin_with_buffer:
                            self.logger.warning(
                                f"Insufficient margin on {role_key}: "
                                f"need {required_margin_with_buffer:.6f}, available {available_margin:.6f} "
                                f"(utilization: {margin_utilization*100:.2f}%)"
                            )
                            return False
                        
                        # Warn if margin utilization will be high
                        if margin_utilization > 0.7:  # >70% utilization
                            self.logger.warning(
                                f"High margin utilization on {role_key}: {margin_utilization*100:.2f}% "
                                f"(Available: {available_margin:.6f}, Total: {quote_balance.total:.6f})"
                            )
                        
                        self.logger.debug(
                            f"✅ {role_key} {quote_asset} margin check passed: "
                            f"{available_margin:.6f} >= {required_margin_with_buffer:.6f} "
                            f"(utilization: {margin_utilization*100:.2f}%)"
                        )
                    else:
                        # Regular spot balance check
                        available_quote = float(quote_balance.available) if quote_balance else 0.0
                        
                        # Add 1% buffer for fees and price movements
                        required_quote_with_buffer = required_quote * 1.01
                        
                        if available_quote < required_quote_with_buffer:
                            self.logger.warning(
                                f"Insufficient {quote_asset} balance on {role_key}: "
                                f"need {required_quote_with_buffer:.6f} (including buffer), have {available_quote:.6f}"
                            )
                            return False
                        
                        self.logger.debug(f"✅ {role_key} {quote_asset} balance check passed: {available_quote:.6f} >= {required_quote_with_buffer:.6f}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Balance validation failed: {e}")
            return False
    
    async def _validate_position_limits(self, position_size: float) -> bool:
        """Validate position size is within allowed limits."""
        try:
            # Check against base position size limit
            max_allowed = float(self.context.base_position_size * self.context.max_position_multiplier)
            if position_size > max_allowed:
                self.logger.warning(f"Position size {position_size} exceeds maximum allowed {max_allowed}")
                return False
            
            # Check minimum position size (prevent dust trades)
            min_allowed = float(self.context.base_position_size * 0.01)  # 1% of base position
            if position_size < min_allowed:
                self.logger.warning(f"Position size {position_size} below minimum allowed {min_allowed}")
                return False
            
            self.logger.debug(f"✅ Position size {position_size} within limits [{min_allowed}, {max_allowed}]")
            return True
            
        except Exception as e:
            self.logger.error(f"Position limit validation failed: {e}")
            return False
    
    async def _validate_market_conditions(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate market conditions are suitable for execution."""
        try:
            # Check opportunity is still fresh (not stale)
            max_age_seconds = 5.0  # Opportunity must be less than 5 seconds old
            opportunity_age = time.time() - float(opportunity.timestamp)
            if opportunity_age > max_age_seconds:
                self.logger.warning(f"Opportunity is stale: {opportunity_age:.2f}s old (max: {max_age_seconds}s)")
                return False
            
            # Check confidence score is acceptable
            min_confidence = 0.6  # Minimum confidence threshold
            if float(opportunity.confidence_score) < min_confidence:
                self.logger.warning(f"Opportunity confidence {opportunity.confidence_score} below minimum {min_confidence}")
                return False
            
            # Check estimated profit is positive
            if float(opportunity.estimated_profit) <= 0:
                self.logger.warning(f"Opportunity has non-positive profit: {opportunity.estimated_profit}")
                return False
            
            self.logger.debug(f"✅ Market conditions validated - age: {opportunity_age:.2f}s, confidence: {opportunity.confidence_score}")
            return True
            
        except Exception as e:
            self.logger.error(f"Market condition validation failed: {e}")
            return False
    
    async def _cancel_all_orders(self, exchange: DualExchange):
        """Cancel all pending orders for an exchange."""
        try:
            # Get and cancel active orders
            orders = await exchange.private._orders[self.context.symbol]
            for order in orders:
                await exchange.private.cancel_order(self.context.symbol, order.order_id)
        except Exception as e:
            self.logger.warning(f"Failed to cancel orders: {e}")
    
    async def _process_order_update(self, role_key: str, order: Order):
        """Process order updates from exchanges."""
        # Update order tracking and position calculations
        # This is handled by subclasses for specific order logic
        pass
    
    async def _process_balance_update(self, role_key: str, balance: AssetBalance):
        """Process balance updates from exchanges."""
        # Update balance tracking for risk management
        pass
    
    async def _process_position_update(self, role_key: str, position: Position):
        """Process position updates from exchanges (futures)."""
        # Update position tracking for delta neutrality
        pass
    
    def get_extended_state_handlers(self) -> Dict[ArbitrageState, str]:
        """Get arbitrage-specific state handlers."""
        return {
            ArbitrageState.INITIALIZING: '_handle_initializing',
            ArbitrageState.MONITORING: '_handle_monitoring',
            ArbitrageState.ANALYZING: '_handle_analyzing',
            ArbitrageState.PREPARING: '_handle_preparing',
            ArbitrageState.EXECUTING: '_handle_executing',
            ArbitrageState.REBALANCING: '_handle_rebalancing',
            ArbitrageState.COMPLETING: '_handle_completing',
            ArbitrageState.ERROR_RECOVERY: '_handle_error_recovery',
        }
    
    async def cleanup(self):
        """Cleanup resources when task completes."""
        # Cancel all orders and close connections
        cleanup_tasks = []
        for exchange in self._exchanges.values():
            cleanup_tasks.append(exchange.close())
        
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        self.logger.info("✅ Arbitrage strategy cleanup completed")


# Utility functions for strategy configuration

def create_spot_futures_arbitrage_roles(
    spot_exchange: ExchangeEnum,
    futures_exchange: ExchangeEnum,
    base_position_size: float = 100.0
) -> Dict[str, ExchangeRole]:
    """Create exchange roles for spot-futures arbitrage strategy."""
    return {
        'spot': ExchangeRole(
            exchange_enum=spot_exchange,
            role='spot_trading',
            max_position_size=base_position_size,
            priority=0
        ),
        'futures': ExchangeRole(
            exchange_enum=futures_exchange,
            role='futures_hedge',
            max_position_size=base_position_size,
            priority=1
        )
    }


def create_three_exchange_arbitrage_roles(
    primary_spot: ExchangeEnum,
    hedge_futures: ExchangeEnum,
    arbitrage_spot: ExchangeEnum,
    base_position_size: float = 100.0
) -> Dict[str, ExchangeRole]:
    """Create exchange roles for 3-exchange delta neutral arbitrage."""
    return {
        'primary_spot': ExchangeRole(
            exchange_enum=primary_spot,
            role='primary_spot',
            side=Side.BUY,  # Primary position
            max_position_size=base_position_size,
            priority=0
        ),
        'hedge_futures': ExchangeRole(
            exchange_enum=hedge_futures,
            role='hedge_futures',
            side=Side.SELL,  # Hedge position
            max_position_size=base_position_size,
            priority=1
        ),
        'arbitrage_spot': ExchangeRole(
            exchange_enum=arbitrage_spot,
            role='arbitrage_target',
            max_position_size=base_position_size * 0.5,  # Smaller arbitrage positions
            priority=2
        )
    }