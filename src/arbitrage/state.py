"""
HFT Arbitrage State Controller

Finite state machine for atomic arbitrage operations with comprehensive
state tracking, transition validation, and recovery coordination.

Architecture:
- Finite state machine with well-defined transitions
- Atomic operation state tracking
- Recovery state management and coordination
- State persistence and recovery
- Event-driven state change notifications
- Thread-safe state operations

State Machine Design:
- IDLE → DETECTING → OPPORTUNITY_FOUND → EXECUTING → COMPLETED/FAILED
- Any state can transition to RECOVERING for error handling
- RECOVERING can transition back to appropriate operational state
- All transitions are logged and validated

Performance Targets:
- <1ms state transitions
- <5ms state validation and persistence
- >99.9% state consistency accuracy
- Real-time state change notifications
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass
from enum import Enum
from weakref import WeakSet

from .structures import (
    ArbitrageState,
    ExecutionStage,
    ArbitrageOpportunity,
    ArbitrageConfig,
)

from ..common.exceptions import StateTransitionError


logger = logging.getLogger(__name__)


class StateTransitionTrigger(Enum):
    """
    Triggers that can cause state transitions.
    
    Used for state machine validation and auditing to ensure
    all state changes have appropriate authorization and context.
    """
    OPPORTUNITY_DETECTED = "opportunity_detected"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    RECOVERY_INITIATED = "recovery_initiated"
    RECOVERY_COMPLETED = "recovery_completed"
    MANUAL_INTERVENTION = "manual_intervention"
    SYSTEM_SHUTDOWN = "system_shutdown"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class StateTransition:
    """
    Record of state transition with complete audit information.
    
    Maintains comprehensive transition history for debugging,
    compliance, and performance analysis.
    """
    transition_id: str
    from_state: ArbitrageState
    to_state: ArbitrageState
    trigger: StateTransitionTrigger
    timestamp: int
    context: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    execution_time_ms: Optional[float] = None


@dataclass
class OperationContext:
    """
    Complete context for arbitrage operation state tracking.
    
    Maintains all state information needed for atomic operation
    management, recovery, and monitoring.
    """
    operation_id: str
    opportunity_id: str
    current_state: ArbitrageState
    execution_stage: ExecutionStage
    created_timestamp: int
    last_updated: int
    state_history: List[StateTransition]
    recovery_attempts: int
    max_recovery_attempts: int
    requires_manual_intervention: bool
    metadata: Dict[str, Any]


class StateController:
    """
    Finite state machine controller for arbitrage operations.
    
    Manages complete state lifecycle for atomic arbitrage operations
    with comprehensive validation, persistence, and recovery capabilities.
    
    HFT Design:
    - Lock-free state operations for maximum performance
    - Event-driven state change notifications
    - Comprehensive audit trail for all transitions
    - Atomic state updates with rollback capabilities
    - Real-time state monitoring and alerting
    """
    
    def __init__(
        self,
        config: ArbitrageConfig,
        state_change_callback: Optional[Callable[[OperationContext, StateTransition], None]] = None,
    ):
        """
        Initialize state controller with configuration and callbacks.
        
        TODO: Complete initialization with state machine setup.
        
        Logic Requirements:
        - Define valid state transition matrix
        - Set up state persistence and recovery
        - Initialize callback system for state changes
        - Configure state validation rules
        - Set up monitoring and alerting
        
        Questions:
        - Should state be persisted to database or in-memory only?
        - How to handle state recovery during system restart?
        - Should we support custom state transition rules?
        
        Performance: Initialization should complete in <1 second
        """
        self.config = config
        self.state_change_callback = state_change_callback
        
        # State Management
        self._operations: Dict[str, OperationContext] = {}  # operation_id -> context
        self._state_lock = asyncio.Lock()
        
        # State Machine Configuration
        self._valid_transitions = self._define_state_transitions()
        self._transition_history: List[StateTransition] = []
        
        # Performance Metrics
        self._total_transitions = 0
        self._failed_transitions = 0
        self._average_transition_time_ms = 0.0
        
        # Recovery Management
        self._recovery_operations: Set[str] = set()
        self._manual_intervention_required: Set[str] = set()
        
        logger.info("State controller initialized with finite state machine")
    
    def _define_state_transitions(self) -> Dict[ArbitrageState, Set[ArbitrageState]]:
        """
        Define valid state transition matrix.
        
        TODO: Complete state transition definition with validation rules.
        
        Logic Requirements:
        - Define all valid state transitions
        - Include recovery paths from any state
        - Set up emergency transitions for circuit breakers
        - Validate transition logic and completeness
        - Document transition requirements and conditions
        
        State Transition Rules:
        - IDLE can only go to DETECTING or FAILED
        - DETECTING can go to OPPORTUNITY_FOUND, IDLE, or FAILED
        - OPPORTUNITY_FOUND can go to EXECUTING, IDLE, or FAILED
        - EXECUTING can go to COMPLETED, FAILED, or RECOVERING
        - RECOVERING can go to any appropriate operational state
        - Any state can transition to FAILED for emergency stops
        
        Performance: <1ms transition validation
        """
        return {
            ArbitrageState.IDLE: {
                ArbitrageState.DETECTING,
                ArbitrageState.FAILED,
            },
            ArbitrageState.DETECTING: {
                ArbitrageState.OPPORTUNITY_FOUND,
                ArbitrageState.IDLE,
                ArbitrageState.FAILED,
                ArbitrageState.RECOVERING,
            },
            ArbitrageState.OPPORTUNITY_FOUND: {
                ArbitrageState.EXECUTING,
                ArbitrageState.DETECTING,
                ArbitrageState.IDLE,
                ArbitrageState.FAILED,
                ArbitrageState.RECOVERING,
            },
            ArbitrageState.EXECUTING: {
                ArbitrageState.POSITION_OPEN,
                ArbitrageState.COMPLETED,
                ArbitrageState.FAILED,
                ArbitrageState.RECOVERING,
            },
            ArbitrageState.POSITION_OPEN: {
                ArbitrageState.EXECUTING,
                ArbitrageState.COMPLETED,
                ArbitrageState.FAILED,
                ArbitrageState.RECOVERING,
            },
            ArbitrageState.RECOVERING: {
                ArbitrageState.IDLE,
                ArbitrageState.DETECTING,
                ArbitrageState.EXECUTING,
                ArbitrageState.COMPLETED,
                ArbitrageState.FAILED,
            },
            ArbitrageState.COMPLETED: {
                ArbitrageState.IDLE,
            },
            ArbitrageState.FAILED: {
                ArbitrageState.IDLE,
                ArbitrageState.RECOVERING,
            },
        }
    
    async def create_operation(
        self,
        opportunity: ArbitrageOpportunity,
        initial_stage: ExecutionStage = ExecutionStage.PREPARING,
    ) -> OperationContext:
        """
        Create new operation context with initial state.
        
        TODO: Implement complete operation creation with validation.
        
        Logic Requirements:
        - Generate unique operation identifier
        - Initialize operation context with defaults
        - Set initial state and execution stage
        - Create state transition record
        - Add to operation tracking
        - Trigger state change notifications
        
        Performance Target: <2ms operation creation
        HFT Critical: Atomic operation creation without race conditions
        """
        async with self._state_lock:
            operation_id = f"op_{opportunity.opportunity_id}_{int(asyncio.get_event_loop().time() * 1000)}"
            
            # Create operation context
            context = OperationContext(
                operation_id=operation_id,
                opportunity_id=opportunity.opportunity_id,
                current_state=ArbitrageState.IDLE,
                execution_stage=initial_stage,
                created_timestamp=int(asyncio.get_event_loop().time() * 1000),
                last_updated=int(asyncio.get_event_loop().time() * 1000),
                state_history=[],
                recovery_attempts=0,
                max_recovery_attempts=self.config.risk_limits.max_recovery_attempts,
                requires_manual_intervention=False,
                metadata={
                    "opportunity_type": opportunity.opportunity_type.name,
                    "symbol": str(opportunity.symbol),
                    "profit_margin_bps": opportunity.profit_margin_bps,
                },
            )
            
            # Add to tracking
            self._operations[operation_id] = context
            
            logger.info(f"Created operation context: {operation_id}")
            
            return context
    
    async def transition_state(
        self,
        operation_id: str,
        new_state: ArbitrageState,
        trigger: StateTransitionTrigger,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Transition operation to new state with validation.
        
        TODO: Implement comprehensive state transition with validation.
        
        Logic Requirements:
        - Validate operation exists and transition is valid
        - Check transition permissions and prerequisites
        - Update operation state atomically
        - Create transition record with audit information
        - Trigger callbacks and notifications
        - Handle transition failures gracefully
        
        Validation Process:
        1. Verify operation exists and is in valid current state
        2. Check if transition is allowed per state machine rules
        3. Validate any prerequisite conditions are met
        4. Execute atomic state update
        5. Record transition in audit trail
        6. Trigger any registered callbacks
        
        Performance Target: <1ms state transition
        HFT Critical: Atomic transitions without inconsistent states
        """
        transition_start_time = asyncio.get_event_loop().time()
        
        async with self._state_lock:
            # Validate operation exists
            if operation_id not in self._operations:
                logger.error(f"Operation not found for state transition: {operation_id}")
                return False
            
            operation = self._operations[operation_id]
            current_state = operation.current_state
            
            # Validate transition is allowed
            if not self._is_transition_valid(current_state, new_state):
                error_msg = f"Invalid transition: {current_state} -> {new_state}"
                logger.error(f"State transition failed for {operation_id}: {error_msg}")
                
                # Record failed transition
                await self._record_transition(
                    operation, current_state, new_state, trigger,
                    context_data or {}, False, error_msg, transition_start_time
                )
                
                return False
            
            try:
                # TODO: Validate transition prerequisites
                await self._validate_transition_prerequisites(operation, new_state, trigger)
                
                # Execute state transition
                operation.current_state = new_state
                operation.last_updated = int(asyncio.get_event_loop().time() * 1000)
                
                # TODO: Handle state-specific actions
                await self._handle_state_entry_actions(operation, new_state, context_data or {})
                
                # Record successful transition
                await self._record_transition(
                    operation, current_state, new_state, trigger,
                    context_data or {}, True, None, transition_start_time
                )
                
                # Update performance metrics
                self._update_transition_metrics(transition_start_time, True)
                
                logger.info(f"State transition: {operation_id} {current_state} -> {new_state}")
                
                return True
                
            except Exception as e:
                error_msg = f"Transition execution failed: {e}"
                logger.error(f"State transition error for {operation_id}: {error_msg}")
                
                # Record failed transition
                await self._record_transition(
                    operation, current_state, new_state, trigger,
                    context_data or {}, False, error_msg, transition_start_time
                )
                
                self._update_transition_metrics(transition_start_time, False)
                
                return False
    
    async def transition_to_recovery(
        self,
        operation_id: str,
        recovery_reason: str,
        recovery_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Transition operation to recovery state with context.
        
        TODO: Implement recovery state transition with comprehensive tracking.
        
        Logic Requirements:
        - Validate operation can transition to recovery
        - Increment recovery attempt counter
        - Check if maximum recovery attempts exceeded
        - Set manual intervention flag if needed
        - Record recovery reason and context
        - Trigger recovery notifications
        
        Recovery Management:
        - Track number of recovery attempts
        - Escalate to manual intervention if needed
        - Maintain recovery context for debugging
        - Coordinate with recovery manager
        
        Performance Target: <2ms recovery transition
        """
        async with self._state_lock:
            if operation_id not in self._operations:
                logger.error(f"Operation not found for recovery transition: {operation_id}")
                return False
            
            operation = self._operations[operation_id]
            
            # Increment recovery attempts
            operation.recovery_attempts += 1
            
            # Check if max recovery attempts exceeded
            if operation.recovery_attempts >= operation.max_recovery_attempts:
                operation.requires_manual_intervention = True
                self._manual_intervention_required.add(operation_id)
                logger.warning(f"Max recovery attempts exceeded: {operation_id}")
            
            # Add to recovery tracking
            self._recovery_operations.add(operation_id)
            
            # Record recovery context
            recovery_data = {
                "recovery_reason": recovery_reason,
                "recovery_attempt": operation.recovery_attempts,
                "requires_intervention": operation.requires_manual_intervention,
                **(recovery_context or {}),
            }
            
            # Execute transition to recovery
            return await self.transition_state(
                operation_id,
                ArbitrageState.RECOVERING,
                StateTransitionTrigger.RECOVERY_INITIATED,
                recovery_data,
            )
    
    async def complete_recovery(
        self,
        operation_id: str,
        target_state: ArbitrageState,
        recovery_success: bool,
    ) -> bool:
        """
        Complete recovery and transition to target state.
        
        TODO: Implement recovery completion with validation.
        
        Logic Requirements:
        - Validate recovery operation exists
        - Verify target state is appropriate for recovery outcome
        - Clear recovery tracking if successful
        - Maintain recovery context for failed recoveries
        - Update recovery statistics and metrics
        
        Performance Target: <2ms recovery completion
        """
        async with self._state_lock:
            if operation_id not in self._operations:
                logger.error(f"Operation not found for recovery completion: {operation_id}")
                return False
            
            operation = self._operations[operation_id]
            
            if operation.current_state != ArbitrageState.RECOVERING:
                logger.error(f"Operation not in recovery state: {operation_id}")
                return False
            
            # Clear recovery tracking if successful
            if recovery_success:
                self._recovery_operations.discard(operation_id)
                if not operation.requires_manual_intervention:
                    self._manual_intervention_required.discard(operation_id)
            
            # Execute transition to target state
            return await self.transition_state(
                operation_id,
                target_state,
                StateTransitionTrigger.RECOVERY_COMPLETED,
                {"recovery_success": recovery_success},
            )
    
    # State Validation and Management
    
    def _is_transition_valid(
        self,
        from_state: ArbitrageState,
        to_state: ArbitrageState,
    ) -> bool:
        """Check if state transition is valid according to state machine rules."""
        return to_state in self._valid_transitions.get(from_state, set())
    
    async def _validate_transition_prerequisites(
        self,
        operation: OperationContext,
        new_state: ArbitrageState,
        trigger: StateTransitionTrigger,
    ) -> None:
        """
        Validate prerequisites for state transition.
        
        TODO: Implement state-specific prerequisite validation.
        
        Logic Requirements:
        - Check state-specific prerequisites
        - Validate trigger appropriateness for transition
        - Verify operation context completeness
        - Check external dependencies and constraints
        
        Prerequisites by state:
        - EXECUTING: Verify balances and exchange connectivity
        - RECOVERING: Ensure recovery context is available
        - COMPLETED: Verify all positions are properly closed
        - FAILED: Ensure error context is documented
        """
        # TODO: Implement prerequisite validation
        pass
    
    async def _handle_state_entry_actions(
        self,
        operation: OperationContext,
        new_state: ArbitrageState,
        context_data: Dict[str, Any],
    ) -> None:
        """
        Handle actions required when entering new state.
        
        TODO: Implement state entry actions.
        
        Logic Requirements:
        - Execute state-specific initialization actions
        - Set up monitoring and alerting for new state
        - Configure timeouts and cleanup for state
        - Initialize any state-specific resources
        
        State Entry Actions:
        - EXECUTING: Start execution monitoring
        - RECOVERING: Initialize recovery procedures
        - COMPLETED: Cleanup resources and update metrics
        - FAILED: Generate failure alerts and logs
        """
        # TODO: Implement state entry actions
        pass
    
    async def _record_transition(
        self,
        operation: OperationContext,
        from_state: ArbitrageState,
        to_state: ArbitrageState,
        trigger: StateTransitionTrigger,
        context: Dict[str, Any],
        success: bool,
        error_message: Optional[str],
        start_time: float,
    ) -> None:
        """Record state transition in audit trail."""
        transition_id = f"trans_{operation.operation_id}_{len(operation.state_history)}"
        execution_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        
        transition = StateTransition(
            transition_id=transition_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            timestamp=int(asyncio.get_event_loop().time() * 1000),
            context=context,
            success=success,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
        )
        
        # Add to operation history
        operation.state_history.append(transition)
        
        # Add to global transition history
        self._transition_history.append(transition)
        
        # Trigger callback if configured
        if self.state_change_callback:
            try:
                await asyncio.create_task(
                    self._safe_callback(operation, transition)
                )
            except Exception as e:
                logger.error(f"State change callback failed: {e}")
    
    async def _safe_callback(
        self,
        operation: OperationContext,
        transition: StateTransition,
    ) -> None:
        """Safely execute state change callback."""
        try:
            if asyncio.iscoroutinefunction(self.state_change_callback):
                await self.state_change_callback(operation, transition)
            else:
                self.state_change_callback(operation, transition)
        except Exception as e:
            logger.error(f"State change callback error: {e}")
    
    def _update_transition_metrics(self, start_time: float, success: bool) -> None:
        """Update state transition performance metrics."""
        self._total_transitions += 1
        
        if not success:
            self._failed_transitions += 1
        
        # Update average transition time
        transition_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        alpha = 0.1
        
        if self._average_transition_time_ms == 0:
            self._average_transition_time_ms = transition_time_ms
        else:
            self._average_transition_time_ms = (
                alpha * transition_time_ms + (1 - alpha) * self._average_transition_time_ms
            )
    
    # Public Interface Methods
    
    def get_operation(self, operation_id: str) -> Optional[OperationContext]:
        """Get operation context by ID."""
        return self._operations.get(operation_id)
    
    def get_operations_by_state(self, state: ArbitrageState) -> List[OperationContext]:
        """Get all operations in specified state."""
        return [op for op in self._operations.values() if op.current_state == state]
    
    def get_recovery_operations(self) -> List[OperationContext]:
        """Get all operations requiring recovery."""
        return [
            self._operations[op_id] for op_id in self._recovery_operations
            if op_id in self._operations
        ]
    
    def get_manual_intervention_operations(self) -> List[OperationContext]:
        """Get operations requiring manual intervention."""
        return [
            self._operations[op_id] for op_id in self._manual_intervention_required
            if op_id in self._operations
        ]
    
    def get_state_statistics(self) -> Dict[str, Any]:
        """Get comprehensive state controller statistics."""
        state_counts = {}
        for state in ArbitrageState:
            state_counts[state.name] = len(self.get_operations_by_state(state))
        
        return {
            "total_operations": len(self._operations),
            "total_transitions": self._total_transitions,
            "failed_transitions": self._failed_transitions,
            "success_rate": (
                (self._total_transitions - self._failed_transitions) / 
                max(self._total_transitions, 1) * 100
            ),
            "average_transition_time_ms": round(self._average_transition_time_ms, 2),
            "recovery_operations": len(self._recovery_operations),
            "manual_intervention_required": len(self._manual_intervention_required),
            "state_counts": state_counts,
        }
    
    async def cleanup_completed_operations(self, max_age_hours: int = 24) -> int:
        """
        Clean up completed operations older than specified age.
        
        TODO: Implement operation cleanup with persistence.
        
        Logic Requirements:
        - Identify completed operations older than threshold
        - Persist operation data if required for compliance
        - Remove from active tracking
        - Update cleanup statistics and metrics
        
        Performance Target: <100ms for typical cleanup
        """
        cleanup_count = 0
        current_time = int(asyncio.get_event_loop().time() * 1000)
        max_age_ms = max_age_hours * 60 * 60 * 1000
        
        operations_to_remove = []
        
        async with self._state_lock:
            for op_id, operation in self._operations.items():
                if (operation.current_state in (ArbitrageState.COMPLETED, ArbitrageState.FAILED) and
                    current_time - operation.last_updated > max_age_ms):
                    operations_to_remove.append(op_id)
            
            for op_id in operations_to_remove:
                # TODO: Persist operation data if needed
                del self._operations[op_id]
                cleanup_count += 1
        
        logger.info(f"Cleaned up {cleanup_count} completed operations")
        
        return cleanup_count