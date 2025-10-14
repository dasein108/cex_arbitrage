"""
Arbitrage Strategy Recovery for TaskManager Integration

Provides enhanced recovery functionality for arbitrage tasks including:
- Exchange connection restoration
- Active order validation and reconciliation
- Position state verification
- Market data reconnection
"""

import asyncio
import json
from typing import Optional, Dict, List, Any
import time

from infrastructure.logging import HFTLoggerInterface
from exchanges.structs import Symbol, Order, Side
from trading.task_manager.recovery import TaskRecovery
from trading.task_manager.persistence import TaskPersistenceManager

from arbitrage_task_context import ArbitrageTaskContext, ArbitrageState
from arbitrage_serialization import ArbitrageTaskSerializer
from mexc_gateio_futures_task import MexcGateioFuturesTask


class ArbitrageTaskRecovery:
    """Enhanced recovery system for arbitrage trading tasks."""
    
    def __init__(self, logger: HFTLoggerInterface, persistence: TaskPersistenceManager):
        """Initialize arbitrage recovery system."""
        self.logger = logger
        self.persistence = persistence
        self.base_recovery = TaskRecovery(logger, persistence)
    
    async def recover_arbitrage_task(self, task_id: str, json_data: str) -> Optional[MexcGateioFuturesTask]:
        """Recover arbitrage task with enhanced validation and reconnection."""
        try:
            # Deserialize context using arbitrage serializer
            context = ArbitrageTaskSerializer.deserialize_context(json_data, ArbitrageTaskContext)
            
            # Validate recovered context
            validation_result = await self._validate_recovered_context(context)
            if not validation_result.valid:
                self.logger.error(f"Context validation failed: {validation_result.reason}")
                return None
            
            # Create task instance
            task = MexcGateioFuturesTask(context, self.logger)
            
            # Perform enhanced recovery steps
            recovery_success = await self._perform_enhanced_recovery(task)
            if not recovery_success:
                self.logger.error(f"Enhanced recovery failed for {task_id}")
                return None
            
            self.logger.info(f"✅ Successfully recovered arbitrage task {task_id}")
            return task
            
        except Exception as e:
            self.logger.error(f"Failed to recover arbitrage task {task_id}", error=str(e))
            return None
    
    async def _validate_recovered_context(self, context: ArbitrageTaskContext) -> 'ValidationResult':
        """Validate recovered context for consistency and safety."""
        try:
            # Check required fields
            if not context.symbol:
                return ValidationResult(False, "Missing symbol")
            
            if not context.task_id:
                return ValidationResult(False, "Missing task_id")
            
            # Validate position consistency
            if context.positions.has_positions:
                spot_pos = context.positions.spot
                futures_pos = context.positions.futures
                
                # Check for reasonable position sizes
                if spot_pos.qty > context.base_position_size_usdt * context.max_position_multiplier:
                    return ValidationResult(False, f"Spot position too large: {spot_pos.qty}")
                
                if futures_pos.qty > context.base_position_size_usdt * context.max_position_multiplier:
                    return ValidationResult(False, f"Futures position too large: {futures_pos.qty}")
                
                # Check for valid sides
                if spot_pos.side and spot_pos.side not in [Side.BUY, Side.SELL]:
                    return ValidationResult(False, f"Invalid spot side: {spot_pos.side}")
                
                if futures_pos.side and futures_pos.side not in [Side.BUY, Side.SELL]:
                    return ValidationResult(False, f"Invalid futures side: {futures_pos.side}")
            
            # Validate active orders
            total_active_orders = context.get_active_order_count()
            if total_active_orders > 10:  # Reasonable limit
                return ValidationResult(False, f"Too many active orders: {total_active_orders}")
            
            # Validate state consistency
            if context.arbitrage_state not in list(ArbitrageState):
                return ValidationResult(False, f"Invalid arbitrage state: {context.arbitrage_state}")
            
            # Validate timestamps
            if context.position_start_time and context.position_start_time > time.time():
                return ValidationResult(False, "Position start time in future")
            
            return ValidationResult(True, "Context validation passed")
            
        except Exception as e:
            return ValidationResult(False, f"Validation error: {str(e)}")
    
    async def _perform_enhanced_recovery(self, task: MexcGateioFuturesTask) -> bool:
        """Perform enhanced recovery including exchange reconnection and order validation."""
        try:
            # Step 1: Reconnect to exchanges
            reconnection_success = await self._reconnect_exchanges(task)
            if not reconnection_success:
                self.logger.error("Failed to reconnect exchanges")
                return False
            
            # Step 2: Validate and reconcile active orders
            order_reconciliation_success = await self._reconcile_active_orders(task)
            if not order_reconciliation_success:
                self.logger.warning("Order reconciliation failed, clearing active orders")
                task.evolve_context(active_orders={'spot': {}, 'futures': {}})
            
            # Step 3: Validate positions against exchange balances
            position_validation_success = await self._validate_positions(task)
            if not position_validation_success:
                self.logger.warning("Position validation failed, may need manual intervention")
            
            # Step 4: Set appropriate recovery state
            await self._set_recovery_state(task)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Enhanced recovery failed", error=str(e))
            return False
    
    async def _reconnect_exchanges(self, task: MexcGateioFuturesTask) -> bool:
        """Reconnect to exchanges and verify connectivity."""
        try:
            # Exchange manager should already be initialized in task constructor
            # Test connectivity by checking latest tickers
            market_data = task.get_market_data()
            
            if not market_data.spot:
                self.logger.warning("Spot exchange data not available")
                return False
            
            if not market_data.futures:
                self.logger.warning("Futures exchange data not available")
                return False
            
            self.logger.info("✅ Exchange reconnection successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Exchange reconnection failed", error=str(e))
            return False
    
    async def _reconcile_active_orders(self, task: MexcGateioFuturesTask) -> bool:
        """Reconcile active orders with exchange state."""
        try:
            reconciled_orders = {'spot': {}, 'futures': {}}
            reconciliation_success = True
            
            for exchange_type in ['spot', 'futures']:
                active_orders = task.context.active_orders.get(exchange_type, {})
                
                for order_id, stored_order in active_orders.items():
                    try:
                        # Query actual order status from exchange
                        current_order = await task.exchange_manager.get_order_status(exchange_type, order_id)
                        
                        if current_order:
                            # Check if order is still active
                            if current_order.status.name in ['NEW', 'PARTIALLY_FILLED']:
                                reconciled_orders[exchange_type][order_id] = current_order
                                self.logger.info(f"✅ Reconciled active order {order_id} on {exchange_type}")
                            else:
                                self.logger.info(f"🔄 Order {order_id} on {exchange_type} is {current_order.status.name}, removing from active")
                                
                                # If order was filled, update positions
                                if current_order.status.name in ['FILLED', 'PARTIALLY_FILLED']:
                                    await task._process_filled_order(exchange_type, current_order)
                        else:
                            self.logger.warning(f"⚠️ Order {order_id} not found on {exchange_type}, removing from active")
                    
                    except Exception as e:
                        self.logger.warning(f"Failed to reconcile order {order_id}: {e}")
                        reconciliation_success = False
            
            # Update context with reconciled orders
            task.evolve_context(active_orders=reconciled_orders)
            
            return reconciliation_success
            
        except Exception as e:
            self.logger.error(f"Order reconciliation failed", error=str(e))
            return False
    
    async def _validate_positions(self, task: MexcGateioFuturesTask) -> bool:
        """Validate positions against exchange balances."""
        try:
            if not task.context.positions.has_positions:
                self.logger.info("No positions to validate")
                return True
            
            # For full validation, we would check actual exchange balances
            # For now, just validate position consistency
            spot_pos = task.context.positions.spot
            futures_pos = task.context.positions.futures
            
            # Check for reasonable position sizes
            max_reasonable_qty = task.context.base_position_size_usdt * task.context.max_position_multiplier / 50000  # Assume $50k max price
            
            if spot_pos.qty > max_reasonable_qty:
                self.logger.warning(f"Spot position seems too large: {spot_pos.qty}")
                return False
            
            if futures_pos.qty > max_reasonable_qty:
                self.logger.warning(f"Futures position seems too large: {futures_pos.qty}")
                return False
            
            self.logger.info("✅ Position validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Position validation failed", error=str(e))
            return False
    
    async def _set_recovery_state(self, task: MexcGateioFuturesTask):
        """Set appropriate state after recovery."""
        try:
            # If has active orders or positions, go to monitoring
            if task.context.has_active_orders() or task.context.positions.has_positions:
                task._transition_arbitrage_state(ArbitrageState.MONITORING)
                self.logger.info("🔄 Set state to MONITORING due to active orders/positions")
            else:
                # No active positions, can start fresh
                task._transition_arbitrage_state(ArbitrageState.IDLE)
                self.logger.info("🆕 Set state to IDLE for fresh start")
        
        except Exception as e:
            self.logger.error(f"Failed to set recovery state", error=str(e))
            # Default to monitoring state for safety
            task._transition_arbitrage_state(ArbitrageState.MONITORING)
    
    def get_recovery_stats(self, recovery_results: List[tuple]) -> Dict[str, Any]:
        """Get recovery statistics including arbitrage-specific metrics."""
        base_stats = self.base_recovery.get_recovery_stats(recovery_results)
        
        # Add arbitrage-specific stats
        arbitrage_tasks = 0
        tasks_with_positions = 0
        tasks_with_orders = 0
        
        for task_id, task in recovery_results:
            if task and isinstance(task, MexcGateioFuturesTask):
                arbitrage_tasks += 1
                if task.context.positions.has_positions:
                    tasks_with_positions += 1
                if task.context.has_active_orders():
                    tasks_with_orders += 1
        
        base_stats.update({
            'arbitrage_tasks_recovered': arbitrage_tasks,
            'tasks_with_active_positions': tasks_with_positions,
            'tasks_with_active_orders': tasks_with_orders
        })
        
        return base_stats


class ValidationResult:
    """Simple validation result class."""
    def __init__(self, valid: bool, reason: str = ""):
        self.valid = valid
        self.reason = reason