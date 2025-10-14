"""
ArbitrageTask Base Class for TaskManager Integration

Provides base class for arbitrage trading tasks with state mapping and lifecycle management.
Follows PROJECT_GUIDES.md principles with float-only policy and struct-first approach.
"""

import time
from typing import Type, Dict, Union, Optional
from abc import abstractmethod

from infrastructure.logging import HFTLoggerInterface
from trading.tasks.base_task import BaseTradingTask, TaskExecutionResult
from trading.struct import TradingStrategyState

from arbitrage_task_context import ArbitrageTaskContext, ArbitrageState
from arbitrage_serialization import ArbitrageTaskSerializer


class ArbitrageTask(BaseTradingTask[ArbitrageTaskContext, ArbitrageState]):
    """Base class for arbitrage trading tasks with TaskManager integration.
    
    Provides:
    - State mapping between ArbitrageState and TradingStrategyState
    - Context management with arbitrage-specific serialization
    - Lifecycle integration with TaskManager
    - HFT performance optimizations
    """
    
    name: str = "ArbitrageTask"
    
    @property
    def context_class(self) -> Type[ArbitrageTaskContext]:
        """Return the ArbitrageTaskContext class for this task."""
        return ArbitrageTaskContext
    
    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: ArbitrageTaskContext,
                 delay: float = 0.01):  # 10ms for HFT performance
        """Initialize arbitrage task.
        
        Args:
            logger: HFT logger instance
            context: Arbitrage task context
            delay: Delay between execution cycles (default 10ms for HFT)
        """
        # Set TradingStrategyState based on ArbitrageState if not already set
        if context.state == TradingStrategyState.NOT_STARTED:
            if context.arbitrage_state == ArbitrageState.IDLE:
                context.state = TradingStrategyState.IDLE
            elif context.arbitrage_state in [ArbitrageState.MONITORING, ArbitrageState.ANALYZING, ArbitrageState.EXECUTING]:
                context.state = TradingStrategyState.EXECUTING
            elif context.arbitrage_state == ArbitrageState.ERROR_RECOVERY:
                context.state = TradingStrategyState.ERROR
        
        super().__init__(logger, context, delay)
    
    def get_extended_state_handlers(self) -> Dict[ArbitrageState, str]:
        """Map ArbitrageState to handler method names."""
        return {
            ArbitrageState.IDLE: '_handle_arbitrage_idle',
            ArbitrageState.INITIALIZING: '_handle_arbitrage_initializing',
            ArbitrageState.MONITORING: '_handle_arbitrage_monitoring',
            ArbitrageState.ANALYZING: '_handle_arbitrage_analyzing',
            ArbitrageState.EXECUTING: '_handle_arbitrage_executing',
            ArbitrageState.ERROR_RECOVERY: '_handle_arbitrage_error_recovery'
        }
    
    def _build_tag(self) -> None:
        """Build logging tag with arbitrage-specific information."""
        symbol_str = str(self.context.symbol) if self.context.symbol else "NO_SYMBOL"
        arbitrage_state = self.context.arbitrage_state.name if self.context.arbitrage_state else "UNKNOWN"
        self._tag = f"{self.name}_{symbol_str}_{arbitrage_state}"
    
    def save_context(self) -> str:
        """Serialize current context using enhanced arbitrage serializer."""
        return ArbitrageTaskSerializer.serialize_context(self.context)
    
    def restore_context(self, data: str) -> None:
        """Restore context using enhanced arbitrage serializer."""
        self.context = ArbitrageTaskSerializer.deserialize_context(data, ArbitrageTaskContext)
    
    def restore_from_json(self, json_data: str) -> None:
        """Restore task from JSON using enhanced arbitrage serializer."""
        try:
            self.context = ArbitrageTaskSerializer.deserialize_context(json_data, ArbitrageTaskContext)
            self._build_tag()
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Failed to restore arbitrage context from JSON", error=str(e))
            raise
    
    def _transition_arbitrage_state(self, new_arbitrage_state: ArbitrageState) -> None:
        """Transition arbitrage state and update corresponding TradingStrategyState."""
        old_arbitrage_state = self.context.arbitrage_state
        
        # Update arbitrage state
        self.evolve_context(arbitrage_state=new_arbitrage_state)
        
        # Map to corresponding TradingStrategyState
        if new_arbitrage_state == ArbitrageState.IDLE:
            self._transition(TradingStrategyState.IDLE)
        elif new_arbitrage_state in [ArbitrageState.MONITORING, ArbitrageState.ANALYZING, ArbitrageState.EXECUTING]:
            self._transition(TradingStrategyState.EXECUTING)
        elif new_arbitrage_state == ArbitrageState.ERROR_RECOVERY:
            self._transition(TradingStrategyState.ERROR)
        elif new_arbitrage_state == ArbitrageState.INITIALIZING:
            # Keep current state during initialization
            pass
        
        self.logger.debug(f"Arbitrage state transition: {old_arbitrage_state.name} -> {new_arbitrage_state.name}")
        self._build_tag()  # Update tag with new state
    
    async def execute_once(self) -> TaskExecutionResult:
        """Execute one arbitrage cycle with enhanced error handling."""
        start_time = time.time()
        
        try:
            # Execute base task logic which handles both TradingStrategyState and ArbitrageState
            result = await super().execute_once()
            
            # Update execution time for HFT monitoring
            execution_time_ms = (time.time() - start_time) * 1000
            result.execution_time_ms = execution_time_ms
            
            # Log performance warning if execution exceeds HFT target
            if execution_time_ms > 50.0:  # 50ms HFT target
                self.logger.warning(f"Arbitrage execution exceeded HFT target", 
                                  execution_time_ms=execution_time_ms,
                                  target_ms=50.0,
                                  arbitrage_state=self.context.arbitrage_state.name)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Arbitrage task execution failed", 
                            error=str(e),
                            arbitrage_state=self.context.arbitrage_state.name)
            
            # Transition to error recovery state
            self._transition_arbitrage_state(ArbitrageState.ERROR_RECOVERY)
            
            # Return error result
            return TaskExecutionResult(
                task_id=self.context.task_id,
                context=self.context,
                should_continue=False,
                error=e,
                state=self.context.state,
                execution_time_ms=(time.time() - start_time) * 1000
            )
    
    # Base implementation methods - subclasses can override
    
    async def _handle_executing(self):
        """Handle TradingStrategyState.EXECUTING by delegating to arbitrage state."""
        # Delegate to specific arbitrage state handler
        arbitrage_state = self.context.arbitrage_state
        
        if arbitrage_state == ArbitrageState.MONITORING:
            await self._handle_arbitrage_monitoring()
        elif arbitrage_state == ArbitrageState.ANALYZING:
            await self._handle_arbitrage_analyzing()
        elif arbitrage_state == ArbitrageState.EXECUTING:
            await self._handle_arbitrage_executing()
        else:
            # Default to monitoring if state is unclear
            self._transition_arbitrage_state(ArbitrageState.MONITORING)
            await self._handle_arbitrage_monitoring()
    
    # Arbitrage-specific state handlers - subclasses must implement these
    
    async def _handle_arbitrage_idle(self):
        """Handle ArbitrageState.IDLE - default implementation."""
        self.logger.debug(f"Arbitrage IDLE state for {self._tag}")
        # Transition to monitoring if conditions are met
        await self._check_start_conditions()
    
    async def _handle_arbitrage_initializing(self):
        """Handle ArbitrageState.INITIALIZING - default implementation."""
        self.logger.debug(f"Arbitrage INITIALIZING state for {self._tag}")
        # Default: transition to monitoring after initialization
        self._transition_arbitrage_state(ArbitrageState.MONITORING)
    
    @abstractmethod
    async def _handle_arbitrage_monitoring(self):
        """Handle ArbitrageState.MONITORING - subclasses must implement."""
        pass
    
    @abstractmethod  
    async def _handle_arbitrage_analyzing(self):
        """Handle ArbitrageState.ANALYZING - subclasses must implement."""
        pass
    
    @abstractmethod
    async def _handle_arbitrage_executing(self):
        """Handle ArbitrageState.EXECUTING - subclasses must implement."""
        pass
    
    async def _handle_arbitrage_error_recovery(self):
        """Handle ArbitrageState.ERROR_RECOVERY - default implementation."""
        self.logger.info(f"Arbitrage ERROR_RECOVERY state for {self._tag}")
        
        # Basic recovery: clear active orders and return to monitoring
        if self.context.has_active_orders():
            self.logger.warning(f"Clearing {self.context.get_active_order_count()} active orders during recovery")
            self.evolve_context(active_orders={'spot': {}, 'futures': {}})
        
        # Transition back to monitoring
        self._transition_arbitrage_state(ArbitrageState.MONITORING)
    
    # Helper methods
    
    async def _check_start_conditions(self):
        """Check if conditions are met to start arbitrage monitoring."""
        # Default: always transition to monitoring
        # Subclasses can override with specific conditions
        self._transition_arbitrage_state(ArbitrageState.MONITORING)
    
    def _should_continue_arbitrage(self) -> bool:
        """Check if arbitrage should continue based on current state."""
        # Don't continue if in error recovery or task is stopped
        if self.context.arbitrage_state == ArbitrageState.ERROR_RECOVERY:
            return False
        
        if self.context.state in [TradingStrategyState.COMPLETED, 
                                TradingStrategyState.CANCELLED,
                                TradingStrategyState.ERROR]:
            return False
        
        return True
    
    def get_arbitrage_status(self) -> Dict[str, any]:
        """Get arbitrage-specific status information."""
        return {
            "arbitrage_state": self.context.arbitrage_state.name,
            "arbitrage_cycles": self.context.arbitrage_cycles,
            "total_volume_usdt": self.context.total_volume_usdt,
            "total_profit": self.context.total_profit,
            "total_fees": self.context.total_fees,
            "active_orders": self.context.get_active_order_count(),
            "has_positions": self.context.positions.has_positions,
            "current_opportunity": self.context.current_opportunity is not None,
            "position_start_time": self.context.position_start_time
        }