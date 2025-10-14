"""
Strategy Factory for TaskManager Integration

Provides factory functions to create arbitrage tasks compatible with TaskManager.
Supports both direct execution and TaskManager-managed execution modes.

Features:
- Factory pattern for creating arbitrage tasks
- Configuration management and validation
- Support for both standalone and TaskManager execution
- Recovery and persistence integration
"""

import asyncio
import time
from typing import Optional, Dict, Any, Union
from enum import Enum

from infrastructure.logging import HFTLoggerInterface, get_logger
from exchanges.structs import Symbol, ExchangeEnum
from trading.task_manager.task_manager import TaskManager
from trading.task_manager.persistence import TaskPersistenceManager

from arbitrage_task_context import ArbitrageTaskContext, ArbitrageState, TradingParameters
from mexc_gateio_futures_task import MexcGateioFuturesTask
from arbitrage_recovery import ArbitrageTaskRecovery


class ExecutionMode(Enum):
    """Execution mode for arbitrage strategies."""
    STANDALONE = "standalone"      # Direct execution without TaskManager
    TASK_MANAGER = "task_manager"  # TaskManager-managed execution


class ArbitrageStrategyFactory:
    """Factory for creating arbitrage trading strategies with TaskManager integration."""
    
    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        """Initialize strategy factory."""
        self.logger = logger or get_logger("arbitrage_strategy_factory")
        self._task_manager: Optional[TaskManager] = None
        self._recovery_system: Optional[ArbitrageTaskRecovery] = None
    
    def create_mexc_gateio_futures_strategy(self,
                                          symbol: Union[Symbol, str],
                                          base_position_size_usdt: float = 100.0,
                                          max_entry_cost_pct: float = 0.5,
                                          min_profit_pct: float = 0.1,
                                          max_hours: float = 6.0,
                                          futures_leverage: float = 1.0,
                                          execution_mode: ExecutionMode = ExecutionMode.TASK_MANAGER,
                                          task_id: Optional[str] = None,
                                          logger: Optional[HFTLoggerInterface] = None) -> MexcGateioFuturesTask:
        """Create MEXC + Gate.io futures arbitrage strategy.
        
        Args:
            symbol: Trading symbol (Symbol object or string like "BTC/USDT")
            base_position_size_usdt: Base position size in USDT
            max_entry_cost_pct: Maximum entry cost percentage
            min_profit_pct: Minimum profit percentage for exit
            max_hours: Maximum hours to hold position
            futures_leverage: Leverage for futures trading
            execution_mode: Execution mode (standalone or task_manager)
            task_id: Custom task ID (auto-generated if None)
            logger: Custom logger (auto-generated if None)
            
        Returns:
            MexcGateioFuturesTask: Configured arbitrage task
        """
        # Convert string symbol to Symbol object
        if isinstance(symbol, str):
            if '/' in symbol:
                base, quote = symbol.split('/')
                symbol = Symbol(base=base, quote=quote)
            else:
                raise ValueError(f"Invalid symbol format: {symbol}. Expected 'BASE/QUOTE' format.")
        
        # Generate task ID if not provided
        if not task_id:
            timestamp = int(time.time() * 1000)
            task_id = f"mexc_gateio_futures_{symbol.base}{symbol.quote}_{timestamp}"
        
        # Create logger if not provided
        if not logger:
            logger = get_logger(f"arbitrage.{symbol.base}{symbol.quote}")
        
        # Create trading parameters
        params = TradingParameters(
            max_entry_cost_pct=max_entry_cost_pct,
            min_profit_pct=min_profit_pct,
            max_hours=max_hours
        )
        
        # Create arbitrage context
        context = ArbitrageTaskContext(
            task_id=task_id,
            symbol=symbol,
            base_position_size_usdt=base_position_size_usdt,
            futures_leverage=futures_leverage,
            params=params,
            arbitrage_state=ArbitrageState.IDLE,
            min_quote_quantity={'spot': 10.0, 'futures': 10.0}  # Default minimums
        )
        
        # Create task
        task = MexcGateioFuturesTask(context, logger)
        
        logger.info(f"✅ Created {task.name} for {symbol} in {execution_mode.value} mode")
        
        return task
    
    def setup_task_manager(self, 
                          base_path: str = "task_data",
                          logger: Optional[HFTLoggerInterface] = None) -> TaskManager:
        """Setup TaskManager for arbitrage strategy execution.
        
        Args:
            base_path: Base path for task persistence
            logger: Custom logger
            
        Returns:
            TaskManager: Configured task manager
        """
        if not logger:
            logger = get_logger("arbitrage_task_manager")
        
        # Create task manager
        self._task_manager = TaskManager(logger, base_path)
        
        # Setup recovery system
        persistence = TaskPersistenceManager(logger, base_path)
        self._recovery_system = ArbitrageTaskRecovery(logger, persistence)
        
        logger.info(f"✅ TaskManager setup completed with base path: {base_path}")
        
        return self._task_manager
    
    async def add_strategy_to_task_manager(self, 
                                         strategy: MexcGateioFuturesTask,
                                         task_manager: Optional[TaskManager] = None) -> str:
        """Add strategy to TaskManager for managed execution.
        
        Args:
            strategy: Arbitrage strategy to add
            task_manager: TaskManager instance (uses internal if None)
            
        Returns:
            str: Task ID
        """
        if not task_manager:
            if not self._task_manager:
                raise ValueError("No TaskManager available. Call setup_task_manager() first.")
            task_manager = self._task_manager
        
        # Add task to manager
        task_id = await task_manager.add_task(strategy)
        
        self.logger.info(f"✅ Added strategy {strategy.name} to TaskManager with ID: {task_id}")
        
        return task_id
    
    async def recover_arbitrage_tasks(self, 
                                    task_manager: Optional[TaskManager] = None) -> Dict[str, Any]:
        """Recover arbitrage tasks from persistence.
        
        Args:
            task_manager: TaskManager instance (uses internal if None)
            
        Returns:
            Dict: Recovery statistics
        """
        if not task_manager:
            if not self._task_manager:
                raise ValueError("No TaskManager available. Call setup_task_manager() first.")
            task_manager = self._task_manager
        
        if not self._recovery_system:
            raise ValueError("No recovery system available. Call setup_task_manager() first.")
        
        # Recover tasks using TaskManager's built-in recovery
        await task_manager.start(recover_tasks=True)
        
        # Get recovery statistics
        stats = task_manager.get_persistence_stats()
        
        self.logger.info(f"🔄 Task recovery completed", **stats)
        
        return stats
    
    def create_strategy_config(self, 
                             symbol: Union[Symbol, str],
                             **kwargs) -> Dict[str, Any]:
        """Create strategy configuration dictionary.
        
        Args:
            symbol: Trading symbol
            **kwargs: Additional configuration parameters
            
        Returns:
            Dict: Strategy configuration
        """
        # Convert symbol to dict format
        if isinstance(symbol, Symbol):
            symbol_dict = {'base': symbol.base, 'quote': symbol.quote}
        else:
            base, quote = symbol.split('/')
            symbol_dict = {'base': base, 'quote': quote}
        
        # Default configuration
        config = {
            'symbol': symbol_dict,
            'base_position_size_usdt': 100.0,
            'max_entry_cost_pct': 0.5,
            'min_profit_pct': 0.1,
            'max_hours': 6.0,
            'futures_leverage': 1.0,
            'execution_mode': ExecutionMode.TASK_MANAGER.value
        }
        
        # Override with provided kwargs
        config.update(kwargs)
        
        return config
    
    def create_strategy_from_config(self, config: Dict[str, Any]) -> MexcGateioFuturesTask:
        """Create strategy from configuration dictionary.
        
        Args:
            config: Strategy configuration
            
        Returns:
            MexcGateioFuturesTask: Configured strategy
        """
        # Extract symbol
        symbol_dict = config['symbol']
        symbol = Symbol(base=symbol_dict['base'], quote=symbol_dict['quote'])
        
        # Extract execution mode
        execution_mode_str = config.get('execution_mode', ExecutionMode.TASK_MANAGER.value)
        execution_mode = ExecutionMode(execution_mode_str)
        
        # Create strategy
        return self.create_mexc_gateio_futures_strategy(
            symbol=symbol,
            base_position_size_usdt=config.get('base_position_size_usdt', 100.0),
            max_entry_cost_pct=config.get('max_entry_cost_pct', 0.5),
            min_profit_pct=config.get('min_profit_pct', 0.1),
            max_hours=config.get('max_hours', 6.0),
            futures_leverage=config.get('futures_leverage', 1.0),
            execution_mode=execution_mode,
            task_id=config.get('task_id'),
            logger=config.get('logger')
        )
    
    async def run_standalone_strategy(self, strategy: MexcGateioFuturesTask):
        """Run strategy in standalone mode (without TaskManager).
        
        Args:
            strategy: Arbitrage strategy to run
        """
        self.logger.info(f"🚀 Running {strategy.name} in standalone mode")
        
        try:
            await strategy.start()
            
            while True:
                result = await strategy.execute_once()
                
                if not result.should_continue:
                    self.logger.info(f"🏁 Strategy completed: {result.state.name}")
                    break
                
                # Sleep for next execution based on result
                if result.next_delay > 0:
                    await asyncio.sleep(result.next_delay)
        
        except KeyboardInterrupt:
            self.logger.info("🛑 Received interrupt signal, stopping strategy")
            await strategy.stop()
        except Exception as e:
            self.logger.error(f"❌ Strategy execution failed", error=str(e))
            raise
        finally:
            await strategy.cleanup()
    
    async def run_task_manager_strategy(self, 
                                      strategy: MexcGateioFuturesTask,
                                      task_manager: Optional[TaskManager] = None):
        """Run strategy using TaskManager.
        
        Args:
            strategy: Arbitrage strategy to run
            task_manager: TaskManager instance (uses internal if None)
        """
        if not task_manager:
            if not self._task_manager:
                task_manager = self.setup_task_manager()
            else:
                task_manager = self._task_manager
        
        self.logger.info(f"🚀 Running {strategy.name} with TaskManager")
        
        try:
            # Add strategy to task manager
            await self.add_strategy_to_task_manager(strategy, task_manager)
            
            # Start task manager
            await task_manager.start()
            
            # Keep running until interrupted
            while True:
                await asyncio.sleep(1.0)
                
                # Check task manager status
                status = task_manager.get_status()
                if status['active_tasks'] == 0:
                    self.logger.info("🏁 No active tasks remaining")
                    break
        
        except KeyboardInterrupt:
            self.logger.info("🛑 Received interrupt signal, stopping TaskManager")
        except Exception as e:
            self.logger.error(f"❌ TaskManager execution failed", error=str(e))
            raise
        finally:
            await task_manager.stop()


# Convenience factory instance
arbitrage_factory = ArbitrageStrategyFactory()


# Convenience functions
def create_mexc_gateio_futures_strategy(symbol: Union[Symbol, str], **kwargs) -> MexcGateioFuturesTask:
    """Convenience function to create MEXC + Gate.io futures strategy."""
    return arbitrage_factory.create_mexc_gateio_futures_strategy(symbol, **kwargs)


async def run_arbitrage_strategy(strategy: MexcGateioFuturesTask, 
                               execution_mode: ExecutionMode = ExecutionMode.TASK_MANAGER):
    """Convenience function to run arbitrage strategy."""
    if execution_mode == ExecutionMode.STANDALONE:
        await arbitrage_factory.run_standalone_strategy(strategy)
    else:
        await arbitrage_factory.run_task_manager_strategy(strategy)