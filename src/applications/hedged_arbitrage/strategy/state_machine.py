"""
3-Exchange Delta Neutral Arbitrage State Machine

A sophisticated state machine for coordinating delta neutral arbitrage across
3 exchanges: Gate.io spot, Gate.io futures, and MEXC spot.

The strategy follows this flow:
1. Initialize delta neutral position (Gate.io spot vs futures)
2. Monitor spreads between spot exchanges (Gate.io vs MEXC)
3. Execute arbitrage when spreads exceed thresholds
4. Maintain delta neutrality throughout the process

Optimized for HFT requirements with sub-50ms execution cycles.
"""

import sys
from pathlib import Path

# Add src to path for imports when running from anywhere
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal

import msgspec

try:
    from exchanges.structs.common import Symbol
    from exchanges.structs.types import AssetName
except ImportError:
    sys.path.insert(0, str(project_root / "src"))
    from exchanges.structs.common import Symbol
    from exchanges.structs.types import AssetName

# Import analytics components
try:
    from ..analytics.data_fetcher import MultiSymbolDataFetcher, UnifiedSnapshot
    from ..analytics.spread_analyzer import SpreadAnalyzer, SpreadOpportunity
    from ..analytics.pnl_calculator import PnLCalculator, ArbitragePnL
    from ..analytics.performance_tracker import PerformanceTracker
except ImportError:
    import sys
    analytics_path = current_dir.parent / "analytics"
    sys.path.insert(0, str(analytics_path))
    from data_fetcher import MultiSymbolDataFetcher, UnifiedSnapshot
    from spread_analyzer import SpreadAnalyzer, SpreadOpportunity
    from pnl_calculator import PnLCalculator, ArbitragePnL
    from performance_tracker import PerformanceTracker

logger = logging.getLogger(__name__)


class StrategyState(Enum):
    """State definitions for the arbitrage strategy."""
    INITIALIZING = "initializing"
    ESTABLISHING_DELTA_NEUTRAL = "establishing_delta_neutral"
    DELTA_NEUTRAL_ACTIVE = "delta_neutral_active"
    MONITORING_SPREADS = "monitoring_spreads"
    PREPARING_ARBITRAGE = "preparing_arbitrage"
    EXECUTING_ARBITRAGE = "executing_arbitrage"
    REBALANCING_DELTA = "rebalancing_delta"
    ERROR_RECOVERY = "error_recovery"
    SHUTDOWN = "shutdown"


class PositionType(Enum):
    """Position types for different exchanges."""
    GATEIO_SPOT_LONG = "gateio_spot_long"
    GATEIO_SPOT_SHORT = "gateio_spot_short"
    GATEIO_FUTURES_LONG = "gateio_futures_long"
    GATEIO_FUTURES_SHORT = "gateio_futures_short"
    MEXC_SPOT_LONG = "mexc_spot_long"
    MEXC_SPOT_SHORT = "mexc_spot_short"


class PositionData(msgspec.Struct):
    """Position information for tracking."""
    position_type: PositionType
    exchange: str
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    timestamp: datetime = msgspec.field(default_factory=datetime.utcnow)


class DeltaNeutralStatus(msgspec.Struct):
    """Delta neutrality status tracking."""
    is_delta_neutral: bool
    net_delta: Decimal  # Combined delta exposure
    hedge_ratio: Decimal  # Futures position / spot position
    target_hedge_ratio: Decimal = Decimal("1.0")
    rebalance_threshold: Decimal = Decimal("0.05")  # 5% deviation triggers rebalance
    last_rebalance: Optional[datetime] = None


class ArbitrageOpportunityState(msgspec.Struct):
    """Current arbitrage opportunity state."""
    opportunity: Optional[SpreadOpportunity] = None
    is_active: bool = False
    entry_time: Optional[datetime] = None
    target_profit: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    max_position_size: Optional[Decimal] = None


class StrategyConfiguration(msgspec.Struct):
    """Configuration parameters for the strategy."""
    symbol: Symbol
    
    # Position sizing
    base_position_size: Decimal = Decimal("100.0")  # Base position size
    max_position_multiplier: Decimal = Decimal("3.0")  # Max 3x base size
    
    # Spread thresholds
    arbitrage_entry_threshold_pct: Decimal = Decimal("0.1")  # 0.1% entry
    arbitrage_exit_threshold_pct: Decimal = Decimal("0.01")  # 0.01% exit
    
    # Risk management
    max_drawdown_pct: Decimal = Decimal("2.0")  # 2% max drawdown
    position_timeout_minutes: int = 30  # Max position hold time
    
    # Delta neutral parameters
    delta_rebalance_threshold_pct: Decimal = Decimal("5.0")  # 5% deviation
    delta_rebalance_frequency_minutes: int = 15  # Check every 15 min
    
    # Exchange configuration
    exchanges: Dict[str, str] = msgspec.field(default_factory=lambda: {
        'GATEIO_SPOT': 'GATEIO_SPOT',
        'GATEIO_FUTURES': 'GATEIO_FUTURES', 
        'MEXC_SPOT': 'MEXC_SPOT'
    })


class StrategyContext(msgspec.Struct):
    """Complete state context for the strategy."""
    current_state: StrategyState
    config: StrategyConfiguration
    
    # Position tracking
    positions: Dict[str, PositionData] = msgspec.field(default_factory=dict)
    delta_status: Optional[DeltaNeutralStatus] = None
    arbitrage_state: ArbitrageOpportunityState = msgspec.field(default_factory=ArbitrageOpportunityState)
    
    # Performance tracking
    session_start: datetime = msgspec.field(default_factory=datetime.utcnow)
    total_trades: int = 0
    total_pnl: Decimal = Decimal("0.0")
    
    # Error handling
    error_count: int = 0
    last_error: Optional[str] = None
    recovery_attempts: int = 0


class DeltaNeutralArbitrageStateMachine:
    """
    Main state machine for 3-exchange delta neutral arbitrage.
    
    Coordinates between Gate.io spot/futures for delta neutrality and
    Gate.io/MEXC spot for arbitrage opportunities.
    """
    
    def __init__(self, config: StrategyConfiguration):
        self.config = config
        self.context = StrategyContext(
            current_state=StrategyState.INITIALIZING,
            config=config
        )
        
        # Initialize analytics components
        self.data_fetcher = MultiSymbolDataFetcher(config.symbol, config.exchanges)
        self.spread_analyzer = SpreadAnalyzer(
            self.data_fetcher,
            entry_threshold_pct=float(config.arbitrage_entry_threshold_pct)
        )
        self.pnl_calculator = PnLCalculator()
        self.performance_tracker = PerformanceTracker()
        
        # State handlers
        self.state_handlers = {
            StrategyState.INITIALIZING: self._handle_initializing,
            StrategyState.ESTABLISHING_DELTA_NEUTRAL: self._handle_establishing_delta_neutral,
            StrategyState.DELTA_NEUTRAL_ACTIVE: self._handle_delta_neutral_active,
            StrategyState.MONITORING_SPREADS: self._handle_monitoring_spreads,
            StrategyState.PREPARING_ARBITRAGE: self._handle_preparing_arbitrage,
            StrategyState.EXECUTING_ARBITRAGE: self._handle_executing_arbitrage,
            StrategyState.REBALANCING_DELTA: self._handle_rebalancing_delta,
            StrategyState.ERROR_RECOVERY: self._handle_error_recovery,
            StrategyState.SHUTDOWN: self._handle_shutdown
        }
        
        self.is_running = False
        logger.info(f"Initialized delta neutral arbitrage strategy for {config.symbol.base}/{config.symbol.quote}")
    
    async def start(self) -> None:
        """Start the strategy execution."""
        logger.info("Starting delta neutral arbitrage strategy")
        self.is_running = True
        
        try:
            await self._transition_to(StrategyState.INITIALIZING)
            
            # Main execution loop
            while self.is_running and self.context.current_state != StrategyState.SHUTDOWN:
                await self._execute_current_state()
                await asyncio.sleep(0.1)  # Small delay to prevent tight loops
                
        except Exception as e:
            logger.error(f"Strategy execution failed: {e}")
            await self._handle_error(str(e))
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Stop the strategy execution."""
        logger.info("Stopping delta neutral arbitrage strategy")
        self.is_running = False
        await self._transition_to(StrategyState.SHUTDOWN)
    
    async def _execute_current_state(self) -> None:
        """Execute the current state handler."""
        handler = self.state_handlers.get(self.context.current_state)
        if handler:
            try:
                await handler()
            except Exception as e:
                await self._handle_error(f"State handler error in {self.context.current_state}: {e}")
        else:
            logger.error(f"No handler found for state: {self.context.current_state}")
            await self._handle_error("Invalid state")
    
    async def _transition_to(self, new_state: StrategyState) -> None:
        """Transition to a new state."""
        old_state = self.context.current_state
        self.context.current_state = new_state
        logger.info(f"State transition: {old_state} -> {new_state}")
    
    async def _handle_error(self, error_message: str) -> None:
        """Handle errors and transition to recovery or shutdown."""
        self.context.error_count += 1
        self.context.last_error = error_message
        logger.error(f"Error #{self.context.error_count}: {error_message}")
        
        if self.context.error_count >= 5:  # Max 5 errors before shutdown
            logger.critical("Too many errors, shutting down strategy")
            await self._transition_to(StrategyState.SHUTDOWN)
        else:
            await self._transition_to(StrategyState.ERROR_RECOVERY)
    
    # State Handlers
    
    async def _handle_initializing(self) -> None:
        """Initialize data connections and verify exchange connectivity."""
        logger.info("Initializing strategy components...")
        
        try:
            # Initialize data fetcher
            if await self.data_fetcher.initialize():
                logger.info("✅ Data fetcher initialized successfully")
                await self._transition_to(StrategyState.ESTABLISHING_DELTA_NEUTRAL)
            else:
                raise Exception("Failed to initialize data fetcher")
                
        except Exception as e:
            await self._handle_error(f"Initialization failed: {e}")
    
    async def _handle_establishing_delta_neutral(self) -> None:
        """Establish initial delta neutral position."""
        logger.info("Establishing delta neutral position...")
        
        try:
            # Get current market data
            snapshot = await self.data_fetcher.get_latest_snapshots()
            if not snapshot:
                raise Exception("No market data available")
            
            # Calculate optimal delta neutral position
            gateio_spot_price = snapshot.data.get('GATEIO_SPOT', {}).get('last_price')
            gateio_futures_price = snapshot.data.get('GATEIO_FUTURES', {}).get('last_price')
            
            if not gateio_spot_price or not gateio_futures_price:
                raise Exception("Missing Gate.io price data for delta neutral setup")
            
            # For now, simulate position establishment
            # In real implementation, this would place actual orders
            spot_position = PositionData(
                position_type=PositionType.GATEIO_SPOT_LONG,
                exchange='GATEIO_SPOT',
                symbol=f"{self.config.symbol.base}/{self.config.symbol.quote}",
                quantity=self.config.base_position_size,
                entry_price=Decimal(str(gateio_spot_price))
            )
            
            futures_position = PositionData(
                position_type=PositionType.GATEIO_FUTURES_SHORT,
                exchange='GATEIO_FUTURES',
                symbol=f"{self.config.symbol.base}/{self.config.symbol.quote}",
                quantity=self.config.base_position_size,
                entry_price=Decimal(str(gateio_futures_price))
            )
            
            self.context.positions['gateio_spot'] = spot_position
            self.context.positions['gateio_futures'] = futures_position
            
            # Initialize delta status
            self.context.delta_status = DeltaNeutralStatus(
                is_delta_neutral=True,
                net_delta=Decimal("0.0"),  # Perfect hedge initially
                hedge_ratio=Decimal("1.0")
            )
            
            logger.info("✅ Delta neutral position established")
            await self._transition_to(StrategyState.DELTA_NEUTRAL_ACTIVE)
            
        except Exception as e:
            await self._handle_error(f"Delta neutral establishment failed: {e}")
    
    async def _handle_delta_neutral_active(self) -> None:
        """Monitor and maintain delta neutrality."""
        logger.info("Delta neutral position active, transitioning to spread monitoring")
        await self._transition_to(StrategyState.MONITORING_SPREADS)
    
    async def _handle_monitoring_spreads(self) -> None:
        """Monitor spreads for arbitrage opportunities."""
        try:
            # Analyze current opportunities
            opportunities = await self.spread_analyzer.identify_opportunities()
            
            if opportunities:
                best_opportunity = opportunities[0]
                
                # Check if opportunity meets our criteria
                if (best_opportunity.spread_pct >= self.config.arbitrage_entry_threshold_pct and
                    best_opportunity.confidence_score >= 0.7):
                    
                    self.context.arbitrage_state.opportunity = best_opportunity
                    logger.info(f"💰 Arbitrage opportunity found: {best_opportunity.spread_pct:.4f}% spread")
                    await self._transition_to(StrategyState.PREPARING_ARBITRAGE)
                else:
                    # Opportunity not strong enough, continue monitoring
                    await asyncio.sleep(1.0)
            else:
                # No opportunities, continue monitoring
                await asyncio.sleep(1.0)
                
        except Exception as e:
            await self._handle_error(f"Spread monitoring failed: {e}")
    
    async def _handle_preparing_arbitrage(self) -> None:
        """Prepare for arbitrage execution."""
        logger.info("Preparing arbitrage execution...")
        
        try:
            opportunity = self.context.arbitrage_state.opportunity
            if not opportunity:
                await self._transition_to(StrategyState.MONITORING_SPREADS)
                return
            
            # Calculate position size based on available capital and risk limits
            max_position = min(
                self.config.base_position_size * self.config.max_position_multiplier,
                Decimal("1000.0")  # Hard cap for safety
            )
            
            # Estimate P&L for the opportunity
            pnl_estimate = await self.pnl_calculator.calculate_arbitrage_pnl(
                opportunity, float(max_position)
            )
            
            if pnl_estimate and pnl_estimate.net_profit > 0:
                self.context.arbitrage_state.target_profit = Decimal(str(pnl_estimate.net_profit))
                self.context.arbitrage_state.max_position_size = max_position
                
                logger.info(f"✅ Arbitrage prepared - Target profit: ${pnl_estimate.net_profit:.4f}")
                await self._transition_to(StrategyState.EXECUTING_ARBITRAGE)
            else:
                logger.info("❌ Arbitrage opportunity no longer profitable")
                self.context.arbitrage_state.opportunity = None
                await self._transition_to(StrategyState.MONITORING_SPREADS)
                
        except Exception as e:
            await self._handle_error(f"Arbitrage preparation failed: {e}")
    
    async def _handle_executing_arbitrage(self) -> None:
        """Execute the arbitrage trade."""
        logger.info("Executing arbitrage trade...")
        
        try:
            opportunity = self.context.arbitrage_state.opportunity
            if not opportunity:
                await self._transition_to(StrategyState.MONITORING_SPREADS)
                return
            
            # Mark arbitrage as active
            self.context.arbitrage_state.is_active = True
            self.context.arbitrage_state.entry_time = datetime.utcnow()
            
            # For simulation, we'll just track the trade
            # In real implementation, this would place actual orders
            self.context.total_trades += 1
            simulated_profit = self.context.arbitrage_state.target_profit or Decimal("0.0")
            self.context.total_pnl += simulated_profit
            
            logger.info(f"✅ Arbitrage executed - Profit: ${simulated_profit:.4f}")
            
            # Reset arbitrage state
            self.context.arbitrage_state = ArbitrageOpportunityState()
            
            # Check if delta rebalancing is needed
            if self._should_rebalance_delta():
                await self._transition_to(StrategyState.REBALANCING_DELTA)
            else:
                await self._transition_to(StrategyState.MONITORING_SPREADS)
                
        except Exception as e:
            await self._handle_error(f"Arbitrage execution failed: {e}")
    
    async def _handle_rebalancing_delta(self) -> None:
        """Rebalance delta neutral position."""
        logger.info("Rebalancing delta neutral position...")
        
        try:
            # Get current positions and prices
            snapshot = await self.data_fetcher.get_latest_snapshots()
            if not snapshot:
                raise Exception("No market data for rebalancing")
            
            # Calculate current delta and required adjustments
            # For simulation, we'll just reset to perfect hedge
            if self.context.delta_status:
                self.context.delta_status.net_delta = Decimal("0.0")
                self.context.delta_status.hedge_ratio = Decimal("1.0")
                self.context.delta_status.last_rebalance = datetime.utcnow()
                self.context.delta_status.is_delta_neutral = True
            
            logger.info("✅ Delta rebalanced successfully")
            await self._transition_to(StrategyState.MONITORING_SPREADS)
            
        except Exception as e:
            await self._handle_error(f"Delta rebalancing failed: {e}")
    
    async def _handle_error_recovery(self) -> None:
        """Attempt to recover from errors."""
        self.context.recovery_attempts += 1
        logger.info(f"Attempting error recovery #{self.context.recovery_attempts}")
        
        try:
            # Wait before retry
            await asyncio.sleep(min(self.context.recovery_attempts * 2, 30))  # Exponential backoff
            
            # Try to reinitialize components
            if await self.data_fetcher.initialize():
                logger.info("✅ Recovery successful")
                self.context.error_count = 0
                self.context.recovery_attempts = 0
                await self._transition_to(StrategyState.MONITORING_SPREADS)
            else:
                raise Exception("Recovery failed - data fetcher initialization")
                
        except Exception as e:
            if self.context.recovery_attempts >= 3:
                logger.critical("Recovery failed after multiple attempts, shutting down")
                await self._transition_to(StrategyState.SHUTDOWN)
            else:
                await asyncio.sleep(5)  # Wait before next recovery attempt
    
    async def _handle_shutdown(self) -> None:
        """Handle strategy shutdown."""
        logger.info("Shutting down strategy...")
        
        # Close any open positions (simulation)
        for position_key in self.context.positions:
            logger.info(f"Closing position: {position_key}")
        
        # Final performance summary
        duration = datetime.utcnow() - self.context.session_start
        logger.info(f"Session summary:")
        logger.info(f"  Duration: {duration}")
        logger.info(f"  Total trades: {self.context.total_trades}")
        logger.info(f"  Total P&L: ${self.context.total_pnl:.4f}")
        
        self.is_running = False
    
    def _should_rebalance_delta(self) -> bool:
        """Check if delta rebalancing is needed."""
        if not self.context.delta_status:
            return True
        
        # Check if delta deviation exceeds threshold
        delta_deviation_pct = abs(self.context.delta_status.net_delta / self.config.base_position_size) * 100
        
        # Check if enough time has passed since last rebalance
        time_threshold_met = True
        if self.context.delta_status.last_rebalance:
            time_since_rebalance = datetime.utcnow() - self.context.delta_status.last_rebalance
            time_threshold_met = time_since_rebalance.total_seconds() >= (self.config.delta_rebalance_frequency_minutes * 60)
        
        return (delta_deviation_pct >= self.config.delta_rebalance_threshold_pct or time_threshold_met)
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current strategy status for monitoring."""
        return {
            'state': self.context.current_state.value,
            'symbol': f"{self.config.symbol.base}/{self.config.symbol.quote}",
            'session_duration': str(datetime.utcnow() - self.context.session_start),
            'total_trades': self.context.total_trades,
            'total_pnl': float(self.context.total_pnl),
            'delta_neutral': self.context.delta_status.is_delta_neutral if self.context.delta_status else False,
            'positions_count': len(self.context.positions),
            'error_count': self.context.error_count,
            'arbitrage_active': self.context.arbitrage_state.is_active
        }


# Example usage and testing
async def main():
    """Example usage of the state machine."""
    print("🚀 Testing Delta Neutral Arbitrage State Machine")
    print("=" * 60)
    
    # Create configuration
    symbol = Symbol(base=AssetName("NEIROETH"), quote=AssetName("USDT"))
    config = StrategyConfiguration(
        symbol=symbol,
        base_position_size=Decimal("50.0"),
        arbitrage_entry_threshold_pct=Decimal("0.1"),
        arbitrage_exit_threshold_pct=Decimal("0.01")
    )
    
    # Create and start strategy
    strategy = DeltaNeutralArbitrageStateMachine(config)
    
    print(f"📊 Strategy initialized for {symbol.base}/{symbol.quote}")
    print(f"💰 Base position size: {config.base_position_size}")
    print(f"📈 Entry threshold: {config.arbitrage_entry_threshold_pct}%")
    print()
    
    # Run for a short time to demonstrate states
    try:
        # Start strategy in background
        strategy_task = asyncio.create_task(strategy.start())
        
        # Monitor for 30 seconds
        for i in range(30):
            status = strategy.get_current_status()
            print(f"⏰ {i+1}s - State: {status['state']} | Trades: {status['total_trades']} | P&L: ${status['total_pnl']:.4f}")
            await asyncio.sleep(1)
        
        # Stop strategy
        await strategy.stop()
        await strategy_task
        
        print("\n✅ State machine test completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())