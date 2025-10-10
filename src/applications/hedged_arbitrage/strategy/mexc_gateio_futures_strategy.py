"""
MEXC Spot + Gate.io Futures Arbitrage Strategy

Simplified 2-exchange implementation for spot-futures arbitrage between MEXC spot and Gate.io futures.
This strategy provides delta-neutral arbitrage opportunities by:

1. Monitoring spread between MEXC spot and Gate.io futures prices
2. Executing simultaneous trades when spreads exceed thresholds
3. Maintaining delta neutrality through position balancing
4. Real-time execution with sub-50ms cycles

Features:
- Real-time WebSocket market data integration
- Event-driven execution with HFT performance
- Automatic position balancing for delta neutrality
- Risk management with position limits and stop-losses
- Compatible with DualExchange and BaseTradingTask patterns
"""

import asyncio
from typing import Optional, Dict
import time

from exchanges.structs import Symbol, Side, ExchangeEnum
from exchanges.structs.common import FuturesBalance
from infrastructure.logging import HFTLoggerInterface, get_logger
from utils.exchange_utils import is_order_done
from utils import calculate_weighted_price

from applications.hedged_arbitrage.strategy.base_arbitrage_strategy import (
    BaseArbitrageStrategy, 
    ArbitrageTaskContext, 
    ArbitrageOpportunity,
    ArbitrageState,
    create_spot_futures_arbitrage_roles
)
from applications.hedged_arbitrage.strategy.exchange_manager import ExchangeManager, OrderPlacementParams


class MexcGateioFuturesContext(ArbitrageTaskContext):
    """Context specific to MEXC spot + Gate.io futures arbitrage strategy."""
    
    # Strategy-specific configuration (fields not in base class)
    futures_leverage: float = 1.0  # Leverage for futures position
    max_position_hold_seconds: int = 300  # 5 minutes max hold time
    
    # Strategy-specific position tracking
    mexc_position: float = 0.0  # MEXC spot position
    gateio_position: float = 0.0  # Gate.io futures position
    mexc_avg_price: float = 0.0  # Average price for MEXC position
    gateio_avg_price: float = 0.0  # Average price for Gate.io position
    
    # Delta neutrality tracking
    current_delta: float = 0.0  # Current delta exposure
    delta_tolerance: float = 0.05  # 5% tolerance before rebalance
    
    # Additional strategy-specific fields
    target_delta: float = 0.0  # Target delta (0 = neutral)
    max_drawdown: float = 0.0  # Strategy-specific max drawdown tracking
    total_spread_captured: float = 0.0  # Total spread captured in arbitrage


class MexcGateioFuturesStrategy(BaseArbitrageStrategy[MexcGateioFuturesContext]):
    """
    MEXC Spot + Gate.io Futures arbitrage strategy.
    
    Executes delta-neutral arbitrage between MEXC spot and Gate.io futures markets
    by simultaneously buying spot and selling futures (or vice versa) when spreads
    exceed profitability thresholds.
    """
    
    name: str = "MexcGateioFuturesStrategy"
    
    @property
    def context_class(self):
        return MexcGateioFuturesContext
    
    def __init__(self, 
                 symbol: Symbol,
                 base_position_size: float = 100.0,
                 entry_threshold_pct: float = 0.1,   # 0.1% minimum spread
                 exit_threshold_pct: float = 0.03,   # 0.03% minimum exit spread
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize MEXC + Gate.io futures arbitrage strategy.
        
        Args:
            symbol: Trading symbol (e.g., NEIROETH)
            base_position_size: Base position size for arbitrage trades
            entry_threshold_pct: Entry threshold as percentage (e.g., 0.1 for 0.1%)
            exit_threshold_pct: Exit threshold as percentage (e.g., 0.03 for 0.03%)
            logger: Optional HFT logger (auto-created if not provided)
        """
        
        # Create exchange roles for spot-futures arbitrage
        exchange_roles = create_spot_futures_arbitrage_roles(
            spot_exchange=ExchangeEnum.MEXC,
            futures_exchange=ExchangeEnum.GATEIO_FUTURES,
            base_position_size=base_position_size
        )
        
        # Create context with strategy-specific configuration
        context = MexcGateioFuturesContext(
            symbol=symbol,
            exchange_roles=exchange_roles,
            base_position_size=base_position_size,
            entry_threshold_pct=entry_threshold_pct,  # Already in percentage format
            exit_threshold_pct=exit_threshold_pct,    # Already in percentage format
            max_position_multiplier=2.0  # Conservative for 2-exchange strategy
        )
        
        # Initialize logger
        if logger is None:
            logger = get_logger(f'mexc_gateio_futures_strategy.{symbol}')
        
        super().__init__(logger, context)
        
        # Strategy-specific components
        self.exchange_manager = ExchangeManager(symbol, exchange_roles, logger)
        
        # Performance tracking
        self._last_spread_check = 0.0
        self._spread_check_interval = 0.1  # 100ms between spread checks
        
        # Subscribe to events from exchange manager
        self.exchange_manager.event_bus.subscribe('book_ticker', self._on_book_ticker_update)
        self.exchange_manager.event_bus.subscribe('order', self._on_order_update)
        self.exchange_manager.event_bus.subscribe('position', self._on_position_update)
    
    def _build_tag(self) -> None:
        """Build logging tag with strategy-specific fields."""
        self._tag = f'{self.name}_{self.context.symbol}_MEXC-GATEIO'
    
    async def start(self, **kwargs):
        """Start strategy with exchange manager initialization."""
        await super().start(**kwargs)
        
        # Initialize exchange manager
        success = await self.exchange_manager.initialize()
        if not success:
            self.logger.error("Failed to initialize exchange manager")
            self._transition(ArbitrageState.ERROR_RECOVERY)
            return
        
        self.logger.info(f"✅ {self.name} strategy started for {self.context.symbol}")
    
    # Event handlers for real-time market data
    
    async def _on_book_ticker_update(self, book_ticker, exchange_key: str):
        """Handle real-time book ticker updates."""
        current_time = time.time()
        
        # Rate limit spread analysis to prevent excessive computation
        if (current_time - self._last_spread_check) >= self._spread_check_interval:
            self._last_spread_check = current_time
            
            # Trigger spread analysis if we have data from both exchanges
            spot_ticker = self.exchange_manager.get_book_ticker('spot')
            futures_ticker = self.exchange_manager.get_book_ticker('futures')
            
            if spot_ticker and futures_ticker and self.context.state == ArbitrageState.MONITORING:
                # Schedule opportunity analysis (don't block event handler)
                asyncio.create_task(self._check_arbitrage_opportunity_async())
    
    async def _on_order_update(self, order, exchange_key: str):
        """Handle real-time order updates."""
        if is_order_done(order):
            await self._process_filled_order(exchange_key, order)
    
    async def _on_position_update(self, position, exchange_key: str):
        """Handle real-time position updates from futures exchange."""
        if exchange_key == 'futures':
            # Update futures position tracking
            self.evolve_context(gateio_position=position.quantity)
            await self._update_delta_calculation()
    
    async def _check_arbitrage_opportunity_async(self):
        """Asynchronously check for arbitrage opportunities."""
        try:
            if self.context.state == ArbitrageState.MONITORING:
                # Check if we need to exit existing positions first
                if await self._should_exit_positions():
                    await self._exit_all_positions()
                    return
                
                # Look for new entry opportunities
                opportunity = await self._identify_arbitrage_opportunity()
                if opportunity:
                    self.logger.info(f"💰 Arbitrage opportunity found: {opportunity.spread_pct:.4f}% spread")
                    self.evolve_context(current_opportunity=opportunity)
                    self._transition(ArbitrageState.ANALYZING)
        except Exception as e:
            self.logger.warning(f"Opportunity check failed: {e}")
    
    # Core arbitrage strategy implementation
    
    async def _should_exit_positions(self) -> bool:
        """Check if we should exit existing positions based on spread thresholds."""
        # Only check exit if we have positions
        if self.context.mexc_position == 0 and self.context.gateio_position == 0:
            return False
        
        spot_ticker = self.exchange_manager.get_book_ticker('spot')
        futures_ticker = self.exchange_manager.get_book_ticker('futures')
        
        if not spot_ticker or not futures_ticker:
            return False
        
        # Calculate the current spread based on our position direction
        # We need to check if we can still exit profitably in the REVERSE direction
        
        # Determine our current position direction
        long_mexc = self.context.mexc_position > 0
        long_gateio = self.context.gateio_position > 0
        
        if long_mexc and not long_gateio:
            # We're long spot, short futures
            # To exit: sell spot (at bid), buy futures (at ask)
            exit_spot_price = spot_ticker.bid_price  # Sell spot at bid
            exit_futures_price = futures_ticker.ask_price  # Buy futures at ask
            # Current spread for exit = what we get from spot - what we pay for futures
            current_exit_spread = (exit_spot_price - exit_futures_price) / exit_futures_price * 100
        elif not long_mexc and long_gateio:
            # We're short spot, long futures  
            # To exit: buy spot (at ask), sell futures (at bid)
            exit_spot_price = spot_ticker.ask_price  # Buy spot at ask
            exit_futures_price = futures_ticker.bid_price  # Sell futures at bid
            # Current spread for exit = what we get from futures - what we pay for spot
            current_exit_spread = (exit_futures_price - exit_spot_price) / exit_spot_price * 100
        else:
            # Unclear position state, use conservative approach
            # Calculate both directions and use the worse (more conservative) spread
            spot_to_futures_spread = (futures_ticker.bid_price - spot_ticker.ask_price) / spot_ticker.ask_price * 100
            futures_to_spot_spread = (spot_ticker.bid_price - futures_ticker.ask_price) / futures_ticker.ask_price * 100
            current_exit_spread = min(spot_to_futures_spread, futures_to_spot_spread)
        
        # Exit threshold is already in percentage format, no conversion needed
        exit_threshold_pct = float(self.context.exit_threshold_pct)
        
        # Exit when spread falls below exit threshold (profit margin is too small)
        should_exit = current_exit_spread < exit_threshold_pct
        
        if should_exit:
            self.logger.info(f"🚪 Exit condition met: current exit spread {current_exit_spread:.4f}% < exit threshold {exit_threshold_pct:.4f}%")
        
        return should_exit
    
    async def _exit_all_positions(self):
        """Exit all positions by closing long position and covering short position."""
        try:
            self.logger.info("🔄 Exiting all positions...")
            
            # Get current market prices for immediate execution
            spot_ticker = self.exchange_manager.get_book_ticker('spot')
            futures_ticker = self.exchange_manager.get_book_ticker('futures')
            
            if not spot_ticker or not futures_ticker:
                self.logger.error("❌ Cannot exit positions - missing market data")
                return
            
            exit_orders = {}
            
            # Close MEXC spot position
            if self.context.mexc_position != 0:
                spot_side = Side.SELL if self.context.mexc_position > 0 else Side.BUY
                spot_price = spot_ticker.bid_price if spot_side == Side.SELL else spot_ticker.ask_price
                exit_orders['spot'] = OrderPlacementParams(
                    side=spot_side,
                    quantity=abs(self.context.mexc_position),
                    price=spot_price
                )
            
            # Close Gate.io futures position
            if self.context.gateio_position != 0:
                futures_side = Side.BUY if self.context.gateio_position < 0 else Side.SELL
                futures_price = futures_ticker.ask_price if futures_side == Side.BUY else futures_ticker.bid_price
                exit_orders['futures'] = OrderPlacementParams(
                    side=futures_side,
                    quantity=abs(self.context.gateio_position),
                    price=futures_price
                )
            
            if exit_orders:
                self.logger.info(f"🚀 Executing exit orders: {len(exit_orders)} exchanges")
                placed_orders = await self.exchange_manager.place_order_parallel(exit_orders)
                
                if all(placed_orders.values()):
                    self.logger.info("✅ All exit orders placed successfully")
                else:
                    self.logger.warning("⚠️ Some exit orders failed")
            
        except Exception as e:
            self.logger.error(f"❌ Error exiting positions: {e}")
    
    async def _identify_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """Identify arbitrage opportunities between spot and futures exchanges."""
        spot_ticker = self.exchange_manager.get_book_ticker('spot')
        futures_ticker = self.exchange_manager.get_book_ticker('futures')
        
        if not spot_ticker or not futures_ticker:
            return None
        
        # Analyze both arbitrage directions using proper bid/ask spreads
        # Direction 1: Buy spot, sell futures
        spot_buy_price = spot_ticker.ask_price  # Price to buy on spot
        futures_sell_price = futures_ticker.bid_price  # Price to sell on futures
        spot_to_futures_spread = (futures_sell_price - spot_buy_price) / spot_buy_price * 100
        
        # Direction 2: Buy futures, sell spot
        futures_buy_price = futures_ticker.ask_price  # Price to buy on futures
        spot_sell_price = spot_ticker.bid_price  # Price to sell on spot
        futures_to_spot_spread = (spot_sell_price - futures_buy_price) / futures_buy_price * 100
        
        # Choose the direction with better spread (if any)
        # Note: context thresholds are already in percentage format, spreads are calculated as percentages
        entry_threshold_pct = float(self.context.entry_threshold_pct)
        
        best_opportunity = None
        if spot_to_futures_spread >= entry_threshold_pct:
            best_opportunity = {
                'direction': 'spot_to_futures',
                'spread_pct': spot_to_futures_spread,
                'primary_exchange': ExchangeEnum.MEXC,
                'target_exchange': ExchangeEnum.GATEIO_FUTURES,
                'primary_price': spot_buy_price,
                'target_price': futures_sell_price
            }
        
        if futures_to_spot_spread >= entry_threshold_pct:
            # Take the better opportunity if both are profitable
            if not best_opportunity or futures_to_spot_spread > best_opportunity['spread_pct']:
                best_opportunity = {
                    'direction': 'futures_to_spot',
                    'spread_pct': futures_to_spot_spread,
                    'primary_exchange': ExchangeEnum.GATEIO_FUTURES,
                    'target_exchange': ExchangeEnum.MEXC,
                    'primary_price': futures_buy_price,
                    'target_price': spot_sell_price
                }
        
        if not best_opportunity:
            return None
        
        # If we have open positions, ensure we can still exit profitably
        if self.context.mexc_position != 0 or self.context.gateio_position != 0:
            # Use exit threshold for position closing (already in percentage format)
            exit_threshold_pct = float(self.context.exit_threshold_pct)
            if best_opportunity['spread_pct'] < exit_threshold_pct:
                return None
        
        # Calculate maximum quantity based on order book depth and direction
        if best_opportunity['direction'] == 'spot_to_futures':
            max_quantity = min(
                spot_ticker.ask_quantity,  # Spot ask depth (what we're buying)
                futures_ticker.bid_quantity,  # Futures bid depth (what we're selling to)
                float(self.context.base_position_size * self.context.max_position_multiplier)
            )
        else:  # futures_to_spot
            max_quantity = min(
                futures_ticker.ask_quantity,  # Futures ask depth (what we're buying)
                spot_ticker.bid_quantity,  # Spot bid depth (what we're selling to)
                float(self.context.base_position_size * self.context.max_position_multiplier)
            )
        
        # Estimate profit using actual executable prices
        quantity = min(float(self.context.base_position_size), max_quantity)
        estimated_profit = (best_opportunity['target_price'] - best_opportunity['primary_price']) * quantity
        
        return ArbitrageOpportunity(
            primary_exchange=best_opportunity['primary_exchange'],
            target_exchange=best_opportunity['target_exchange'],
            symbol=self.context.symbol,
            spread_pct=best_opportunity['spread_pct'],
            primary_price=best_opportunity['primary_price'],
            target_price=best_opportunity['target_price'],
            max_quantity=max_quantity,
            estimated_profit=estimated_profit,
            confidence_score=0.8,  # High confidence for 2-exchange strategy
            timestamp=time.time()
        )
    
    async def _calculate_max_executable_size(self, opportunity: ArbitrageOpportunity) -> float:
        """Calculate maximum executable position size based on balance constraints."""
        try:
            base_size = min(
                float(self.context.base_position_size),
                float(opportunity.max_quantity)
            )
            
            # Get exchanges for balance checking
            spot_exchange = self.exchange_manager.get_exchange('spot')
            futures_exchange = self.exchange_manager.get_exchange('futures')
            
            if not spot_exchange or not futures_exchange:
                self.logger.warning("Could not get exchanges for balance checking")
                return base_size
            
            # Determine trade direction and check relevant balances
            if opportunity.primary_exchange == ExchangeEnum.MEXC:
                # Buying MEXC spot, selling Gate.io futures
                quote_balance = await spot_exchange.private.get_asset_balance(opportunity.symbol.quote)
                if quote_balance:
                    # Calculate max position based on available quote balance
                    required_quote_per_unit = float(opportunity.primary_price) * 1.01  # Add 1% buffer for fees
                    max_spot_buy = float(quote_balance.available) / required_quote_per_unit
                    base_size = min(base_size, max_spot_buy)
                    self.logger.debug(f"💰 MEXC quote balance limit: {max_spot_buy:.6f} (available: {quote_balance.available})")
                
            else:
                # Selling MEXC spot, buying Gate.io futures
                base_balance = await spot_exchange.private.get_asset_balance(opportunity.symbol.quote)
                if base_balance:
                    # Calculate max position based on available base balance
                    max_spot_sell = float(base_balance.available)
                    base_size = min(base_size, max_spot_sell)
                    self.logger.debug(f"💰 MEXC base balance limit: {max_spot_sell:.6f} (available: {base_balance.available})")
            
            # Additional check for futures margin (if applicable)
            # For simplicity, we assume futures exchange has sufficient margin
            # In production, this would check margin requirements
            
            if base_size != min(float(self.context.base_position_size), float(opportunity.max_quantity)):
                self.logger.info(f"📊 Position size adjusted for balance: {base_size:.6f} (original: {min(float(self.context.base_position_size), float(opportunity.max_quantity)):.6f})")
            
            return max(base_size, 0.0)  # Ensure non-negative
            
        except Exception as e:
            self.logger.error(f"Error calculating executable size: {e}")
            return min(float(self.context.base_position_size), float(opportunity.max_quantity))
    
    async def _prepare_orders_for_opportunity(self, opportunity: ArbitrageOpportunity, position_size: float) -> Optional[Dict[str, dict]]:
        """Prepare order structure for balance validation."""
        try:
            # Determine trade sides based on opportunity direction
            if opportunity.primary_exchange == ExchangeEnum.MEXC:
                # Buy MEXC spot, sell Gate.io futures
                mexc_side = Side.BUY
                gateio_side = Side.SELL
                mexc_price = opportunity.primary_price
                gateio_price = opportunity.target_price
            else:
                # Buy Gate.io futures, sell MEXC spot
                mexc_side = Side.SELL
                gateio_side = Side.BUY
                mexc_price = opportunity.target_price
                gateio_price = opportunity.primary_price
            
            # Prepare order structure for validation
            orders = {
                'spot': {
                    'side': mexc_side,
                    'quantity': position_size,
                    'price': mexc_price
                },
                'futures': {
                    'side': gateio_side,
                    'quantity': position_size,
                    'price': gateio_price
                }
            }
            
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to prepare orders for validation: {e}")
            return None
    
    async def _execute_arbitrage_trades(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute simultaneous arbitrage trades on MEXC and Gate.io."""
        try:
            # Calculate balance-aware position size
            position_size = await self._calculate_max_executable_size(opportunity)
            
            if position_size <= 0:
                self.logger.error("❌ No executable position size available")
                return False
            
            # Determine trade sides based on opportunity direction
            if opportunity.primary_exchange == ExchangeEnum.MEXC:
                # Buy MEXC spot, sell Gate.io futures
                mexc_side = Side.BUY
                gateio_side = Side.SELL
                mexc_price = float(opportunity.primary_price)
                gateio_price = float(opportunity.target_price)
            else:
                # Buy Gate.io futures, sell MEXC spot
                mexc_side = Side.SELL
                gateio_side = Side.BUY
                mexc_price = float(opportunity.target_price)
                gateio_price = float(opportunity.primary_price)
            
            # Prepare orders for parallel execution
            orders = {
                'spot': OrderPlacementParams(
                    side=mexc_side,
                    quantity=position_size,
                    price=mexc_price
                ),
                'futures': OrderPlacementParams(
                    side=gateio_side,
                    quantity=position_size,
                    price=gateio_price
                )
            }
            
            # Execute orders in parallel for HFT performance
            self.logger.info(f"🚀 Executing arbitrage trades: {position_size} @ MEXC:{mexc_price}, Gate.io:{gateio_price}")
            start_time = time.time()
            
            placed_orders = await self.exchange_manager.place_order_parallel(orders)
            
            execution_time = (time.time() - start_time) * 1000
            self.logger.info(f"⚡ Order execution completed in {execution_time:.1f}ms")
            
            # Check if both orders were placed successfully
            mexc_order = placed_orders.get('spot')
            gateio_order = placed_orders.get('futures')
            
            if mexc_order and gateio_order:
                self.logger.info(f"✅ Both arbitrage orders placed successfully")
                # Update performance metrics
                self.evolve_context(
                    arbitrage_cycles=self.context.arbitrage_cycles + 1,
                    total_volume=self.context.total_volume + position_size
                )
                return True
            else:
                self.logger.error(f"❌ Arbitrage execution failed - MEXC: {bool(mexc_order)}, Gate.io: {bool(gateio_order)}")
                
                # Cancel any successful orders to avoid unbalanced positions
                if mexc_order or gateio_order:
                    await self.exchange_manager.cancel_all_orders()
                    
                return False
                
        except Exception as e:
            self.logger.error(f"Arbitrage execution error: {e}")
            # Emergency order cancellation
            await self.exchange_manager.cancel_all_orders()
            return False
    
    async def _rebalance_positions(self) -> bool:
        """Rebalance positions to maintain delta neutrality."""
        try:
            # Calculate current delta
            await self._update_delta_calculation()
            
            # Check if rebalancing is needed
            delta_deviation = abs(self.context.current_delta)
            if delta_deviation <= self.context.delta_tolerance:
                self.logger.info(f"✅ Delta within tolerance: {delta_deviation:.4f}")
                return True
            
            self.logger.info(f"⚖️ Rebalancing required - Delta deviation: {delta_deviation:.4f}")
            
            # Determine rebalancing action
            if self.context.current_delta > self.context.delta_tolerance:
                # Long bias - need to reduce long exposure or increase short
                await self._rebalance_reduce_long_bias()
            elif self.context.current_delta < -self.context.delta_tolerance:
                # Short bias - need to reduce short exposure or increase long
                await self._rebalance_reduce_short_bias()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Position rebalancing error: {e}")
            return False
    
    async def _update_delta_calculation(self):
        """Update delta calculation based on current positions."""
        # For spot-futures arbitrage, delta = spot_position - futures_position
        current_delta = self.context.mexc_position - self.context.gateio_position
        self.evolve_context(current_delta=current_delta)
    
    async def _rebalance_reduce_long_bias(self):
        """Reduce long bias by selling spot (with balance validation)."""
        spot_exchange = self.exchange_manager.get_exchange('spot')
        if not spot_exchange:
            self.logger.warning("Spot exchange not available for rebalancing")
            return
        
        try:
            # Get available balance for the base asset
            balances = await spot_exchange.private.get_balances()
            base_balance = next((b for b in balances if b.asset == self.context.symbol.base), None)
            
            if not base_balance:
                self.logger.warning("No base asset balance found for rebalancing")
                return
            
            # Calculate rebalance quantity limited by available balance
            desired_quantity = abs(float(self.context.current_delta)) / 2
            max_sellable = float(base_balance.available)
            rebalance_quantity = min(desired_quantity, max_sellable)
            
            if rebalance_quantity <= 0:
                self.logger.warning(f"Insufficient balance for rebalancing: need {desired_quantity:.6f}, have {max_sellable:.6f}")
                return
            
            # Get current price for market order
            spot_ticker = self.exchange_manager.get_book_ticker('spot')
            if not spot_ticker:
                self.logger.warning("No market data available for rebalancing")
                return
            
            # Execute rebalance trade
            await spot_exchange.private.place_market_order(
                symbol=self.context.symbol,
                side=Side.SELL,
                price=float(spot_ticker.bid_price),
                quote_quantity=rebalance_quantity
            )
            
            if rebalance_quantity < desired_quantity:
                self.logger.info(f"📉 Rebalance sell: {rebalance_quantity:.6f} on MEXC (limited by balance, wanted {desired_quantity:.6f})")
            else:
                self.logger.info(f"📉 Rebalance sell: {rebalance_quantity:.6f} on MEXC")
                
        except Exception as e:
            self.logger.error(f"Failed to execute long bias rebalancing: {e}")
    
    async def _rebalance_reduce_short_bias(self):
        """Reduce short bias by buying spot (with balance validation)."""
        spot_exchange = self.exchange_manager.get_exchange('spot')
        if not spot_exchange:
            self.logger.warning("Spot exchange not available for rebalancing")
            return
        
        try:
            # Get available balance for the quote asset
            balances = await spot_exchange.private.get_balances()
            quote_balance = next((b for b in balances if b.asset == self.context.symbol.quote), None)
            
            if not quote_balance:
                self.logger.warning("No quote asset balance found for rebalancing")
                return
            
            # Get current price for market order
            spot_ticker = self.exchange_manager.get_book_ticker('spot')
            if not spot_ticker:
                self.logger.warning("No market data available for rebalancing")
                return
            
            # Calculate rebalance quantity limited by available balance
            desired_quantity = abs(float(self.context.current_delta)) / 2
            required_quote_per_unit = float(spot_ticker.ask_price) * 1.01  # Add 1% buffer for fees
            max_buyable = float(quote_balance.available) / required_quote_per_unit
            rebalance_quantity = min(desired_quantity, max_buyable)
            
            if rebalance_quantity <= 0:
                self.logger.warning(f"Insufficient balance for rebalancing: need {desired_quantity:.6f}, can buy {max_buyable:.6f}")
                return
            
            # Execute rebalance trade
            await spot_exchange.private.place_market_order(
                symbol=self.context.symbol,
                side=Side.BUY,
                price=float(spot_ticker.ask_price),
                quote_quantity=rebalance_quantity
            )
            
            if rebalance_quantity < desired_quantity:
                self.logger.info(f"📈 Rebalance buy: {rebalance_quantity:.6f} on MEXC (limited by balance, wanted {desired_quantity:.6f})")
            else:
                self.logger.info(f"📈 Rebalance buy: {rebalance_quantity:.6f} on MEXC")
                
        except Exception as e:
            self.logger.error(f"Failed to execute short bias rebalancing: {e}")
    
    async def _process_filled_order(self, exchange_key: str, order):
        """Process filled orders and update position tracking."""
        try:
            filled_quantity = order.filled_quantity
            avg_price = order.price
            
            if exchange_key == 'spot':
                # Update MEXC spot position
                if order.side == Side.BUY:
                    new_position = self.context.mexc_position + filled_quantity
                else:
                    new_position = self.context.mexc_position - filled_quantity
                
                # Calculate weighted average price
                if self.context.mexc_position != 0:
                    new_quantity, new_avg_price = calculate_weighted_price(
                        float(self.context.mexc_avg_price),
                        float(self.context.mexc_position),
                        avg_price,
                        filled_quantity
                    )
                    self.evolve_context(
                        mexc_position=new_quantity,
                        mexc_avg_price=new_avg_price
                    )
                else:
                    self.evolve_context(
                        mexc_position=new_position,
                        mexc_avg_price=avg_price
                    )
                
            elif exchange_key == 'futures':
                # Update Gate.io futures position
                if order.side == Side.BUY:
                    new_position = self.context.gateio_position + filled_quantity
                else:
                    new_position = self.context.gateio_position - filled_quantity
                
                # Calculate weighted average price
                if self.context.gateio_position != 0:
                    new_quantity, new_avg_price = calculate_weighted_price(
                        float(self.context.gateio_avg_price),
                        float(self.context.gateio_position),
                        avg_price,
                        filled_quantity
                    )
                    self.evolve_context(
                        gateio_position=new_quantity,
                        gateio_avg_price=new_avg_price
                    )
                else:
                    self.evolve_context(
                        gateio_position=new_position,
                        gateio_avg_price=avg_price
                    )
            
            # Update delta calculation
            await self._update_delta_calculation()
            
            self.logger.info(f"✅ Order filled on {exchange_key}: {filled_quantity} @ {avg_price}")
            self.logger.info(f"📊 Positions - MEXC: {self.context.mexc_position}, Gate.io: {self.context.gateio_position}, Delta: {self.context.current_delta}")
            
        except Exception as e:
            self.logger.error(f"Error processing filled order: {e}")
    
    # Strategy-specific state handlers
    
    async def _handle_initializing(self):
        """Enhanced initialization for MEXC + Gate.io strategy."""
        await super()._handle_initializing()
        
        # Additional initialization for futures leverage
        if self.context.state == ArbitrageState.MONITORING:
            await self._setup_futures_leverage()
    
    async def _setup_futures_leverage(self):
        """Setup leverage for Gate.io futures trading."""
        try:
            pass
            # SKIP LEVERAGE
            # gateio_exchange = self.exchange_manager.get_exchange('futures')
            # if gateio_exchange and hasattr(gateio_exchange.private, 'set_leverage'):
            #     # Set leverage if supported
            #     await gateio_exchange.private.set_leverage(
            #         symbol=self.context.symbol,
            #         leverage=float(self.context.futures_leverage)
            #     )
            #     self.logger.info(f"⚙️ Futures leverage set to {self.context.futures_leverage}x")
        except Exception as e:
            self.logger.warning(f"Failed to set futures leverage: {e}")
    
    async def cleanup(self):
        """Cleanup strategy resources."""
        await super().cleanup()
        if hasattr(self, 'exchange_manager'):
            await self.exchange_manager.shutdown()
    
    def get_strategy_summary(self) -> Dict:
        """Get comprehensive strategy performance summary."""
        return {
            'strategy_name': self.name,
            'symbol': str(self.context.symbol),
            'exchanges': ['MEXC', 'GATEIO_FUTURES'],
            'configuration': {
                'base_position_size': float(self.context.base_position_size),
                'entry_threshold_pct': float(self.context.entry_threshold_pct) * 100,  # Convert back to percentage for display
                'exit_threshold_pct': float(self.context.exit_threshold_pct) * 100,
                # 'futures_leverage': float(self.context.futures_leverage),
                'delta_tolerance': float(self.context.delta_tolerance)
            },
            'positions': {
                'mexc_spot': float(self.context.mexc_position),
                'gateio_futures': float(self.context.gateio_position),
                'current_delta': float(self.context.current_delta),
                'mexc_avg_price': float(self.context.mexc_avg_price),
                'gateio_avg_price': float(self.context.gateio_avg_price)
            },
            'performance': {
                'arbitrage_cycles': self.context.arbitrage_cycles,
                'total_volume': float(self.context.total_volume),
                'total_profit': float(self.context.total_profit),
                'total_fees': float(self.context.total_fees),
                'spread_captured': float(self.context.total_spread_captured)
            },
            'exchange_manager': self.exchange_manager.get_performance_summary() if hasattr(self, 'exchange_manager') else {}
        }


# Utility function for easy strategy creation
async def create_mexc_gateio_strategy(
    symbol: Symbol,
    base_position_size: float = 100.0,
    entry_threshold_pct: float = 0.1,
    exit_threshold_pct: float = 0.03,
    futures_leverage: float = 1.0
) -> MexcGateioFuturesStrategy:
    """Create and initialize MEXC + Gate.io futures arbitrage strategy.
    
    Args:
        symbol: Trading symbol
        base_position_size: Base position size for trades
        entry_threshold_pct: Entry threshold as percentage (e.g., 0.1 for 0.1%)
        exit_threshold_pct: Exit threshold as percentage (e.g., 0.03 for 0.03%)
        futures_leverage: Leverage for futures trading
        
    Returns:
        Initialized MexcGateioFuturesStrategy instance
    """
    strategy = MexcGateioFuturesStrategy(
        symbol=symbol,
        base_position_size=base_position_size,
        entry_threshold_pct=entry_threshold_pct,
        exit_threshold_pct=exit_threshold_pct
    )
    
    # Set futures leverage
    strategy.evolve_context(futures_leverage=futures_leverage)
    
    await strategy.start()
    return strategy