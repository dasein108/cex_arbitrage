"""
Abstract base classes for all trading state machines.

Provides the foundation for all strategy implementations with common state
management, context handling, and result tracking patterns.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Dict, List, TYPE_CHECKING

# Direct imports of real structures
from exchanges.structs.common import Symbol, Order
from infrastructure.logging import HFTLoggerInterface


class StrategyState(Enum):
    """Base states for all trading strategies."""
    IDLE = "idle"
    ANALYZING = "analyzing"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    ADJUSTING = "adjusting"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class StrategyResult:
    """Standard result structure for all trading strategies."""
    strategy_name: str
    symbol: Symbol
    success: bool
    profit_usdt: float = 0.0
    execution_time_ms: float = 0.0
    orders_executed: List[Order] = field(default_factory=list)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class StrategyError(Exception):
    """Base exception for strategy execution errors."""
    def __init__(self, state: StrategyState, message: str, original_error: Optional[Exception] = None):
        self.state = state
        self.original_error = original_error
        super().__init__(f"Strategy error in state {state.value}: {message}")


@dataclass
class BaseStrategyContext:
    """Base context for all trading strategies."""
    strategy_name: str
    symbol: Symbol
    logger: HFTLoggerInterface
    
    # State management
    current_state: StrategyState = StrategyState.IDLE
    start_time: float = field(default_factory=time.time)
    
    # Error tracking
    error: Optional[Exception] = None
    
    # Performance tracking
    execution_count: int = 0
    total_profit_usdt: float = 0.0
    
    # Orders tracking
    active_orders: List[Order] = field(default_factory=list)
    completed_orders: List[Order] = field(default_factory=list)


class BaseStrategyStateMachine(ABC):
    """
    Abstract base class for all trading strategy state machines.
    
    Provides common state management patterns, error handling, and
    performance tracking for all strategy implementations.
    """
    
    def __init__(self, context: BaseStrategyContext):
        self.context = context
        self._execution_start_time: Optional[float] = None
    
    async def execute_strategy(self) -> StrategyResult:
        """
        Execute the complete trading strategy.
        
        Returns:
            StrategyResult with execution details and performance metrics
        """
        self._execution_start_time = time.time()
        
        try:
            self.context.logger.info(f"Starting {self.context.strategy_name} strategy execution")
            
            # Run the main strategy loop
            while self.context.current_state not in [StrategyState.COMPLETED, StrategyState.ERROR]:
                self.context.logger.info(f"State: {self.context.current_state.value}")
                
                # Execute state-specific logic
                await self._handle_current_state()
                
                # Small delay to prevent busy loop
                await asyncio.sleep(0.01)
            
            # Handle final states
            if self.context.current_state == StrategyState.ERROR:
                raise self.context.error or StrategyError(
                    self.context.current_state, 
                    "Strategy execution failed"
                )
            
            # Calculate execution metrics
            execution_time = (time.time() - self._execution_start_time) * 1000
            
            result = StrategyResult(
                strategy_name=self.context.strategy_name,
                symbol=self.context.symbol,
                success=True,
                profit_usdt=self.context.total_profit_usdt,
                execution_time_ms=execution_time,
                orders_executed=self.context.completed_orders.copy()
            )
            
            self.context.logger.info(
                f"Strategy completed successfully",
                profit_usdt=result.profit_usdt,
                execution_time_ms=result.execution_time_ms,
                orders_count=len(result.orders_executed)
            )
            
            return result
            
        except Exception as e:
            execution_time = (time.time() - self._execution_start_time) * 1000 if self._execution_start_time else 0
            
            self.context.error = e
            self.context.current_state = StrategyState.ERROR
            
            result = StrategyResult(
                strategy_name=self.context.strategy_name,
                symbol=self.context.symbol,
                success=False,
                execution_time_ms=execution_time,
                error_message=str(e)
            )
            
            self.context.logger.error(
                f"Strategy execution failed",
                error=str(e),
                state=self.context.current_state.value
            )
            
            return result
    
    async def _handle_current_state(self) -> None:
        """Route to appropriate state handler based on current state."""
        state_handlers = {
            StrategyState.IDLE: self._handle_idle,
            StrategyState.ANALYZING: self._handle_analyzing,
            StrategyState.EXECUTING: self._handle_executing,
            StrategyState.MONITORING: self._handle_monitoring,
            StrategyState.ADJUSTING: self._handle_adjusting,
        }
        
        handler = state_handlers.get(self.context.current_state)
        if handler:
            await handler()
        else:
            raise StrategyError(
                self.context.current_state,
                f"No handler for state: {self.context.current_state}"
            )
    
    @abstractmethod
    async def _handle_idle(self) -> None:
        """Handle the idle state - strategy initialization."""
        pass
    
    @abstractmethod
    async def _handle_analyzing(self) -> None:
        """Handle the analyzing state - market analysis and opportunity detection."""
        pass
    
    @abstractmethod
    async def _handle_executing(self) -> None:
        """Handle the executing state - order placement and trade execution."""
        pass
    
    @abstractmethod
    async def _handle_monitoring(self) -> None:
        """Handle the monitoring state - track order fills and market conditions."""
        pass
    
    @abstractmethod
    async def _handle_adjusting(self) -> None:
        """Handle the adjusting state - modify orders or positions as needed."""
        pass
    
    def _transition_to_state(self, new_state: StrategyState) -> None:
        """Safely transition to a new state with logging."""
        old_state = self.context.current_state
        self.context.current_state = new_state
        self.context.logger.info(f"State transition: {old_state.value} -> {new_state.value}")
    
    def _handle_error(self, error: Exception, state: Optional[StrategyState] = None) -> None:
        """Handle strategy errors with proper logging and state transition."""
        error_state = state or self.context.current_state
        self.context.error = StrategyError(error_state, str(error), error)
        self.context.current_state = StrategyState.ERROR
        self.context.logger.error(f"Strategy error in state {error_state.value}", error=str(error))