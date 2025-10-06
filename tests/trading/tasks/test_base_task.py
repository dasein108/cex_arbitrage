"""
Base Trading Task Tests

Tests for the base trading task functionality including context management,
state transitions, and serialization.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock

from trading.tasks.base_task import BaseTradingTask, TaskContext, TaskExecutionResult
from trading.struct import TradingStrategyState
from tests.trading.helpers import TestDataFactory


class TestTaskContext(TaskContext):
    """Test context implementation for base task testing."""
    test_field: str = "test_value"
    test_number: int = 42


class TestBaseTradingTaskImpl(BaseTradingTask[TestTaskContext]):
    """Test implementation of BaseTradingTask."""
    
    name = "TestTask"
    
    @property
    def context_class(self):
        return TestTaskContext
    
    async def _handle_executing(self):
        """Simple executing handler for testing."""
        await asyncio.sleep(0.001)  # Simulate work
        self._transition(TradingStrategyState.COMPLETED)


class TestBaseTradingTask:
    """Test base trading task functionality."""
    
    def test_context_validation(self, logger):
        """Test context type validation."""
        valid_context = TestTaskContext()
        
        # Should accept valid context
        task = TestBaseTradingTaskImpl(logger=logger, context=valid_context)
        assert isinstance(task.context, TestTaskContext)
        
        # Should reject invalid context type
        with pytest.raises(TypeError):
            TestBaseTradingTaskImpl(logger=logger, context="invalid")
    
    def test_task_id_generation(self, logger):
        """Test automatic task ID generation."""
        context = TestTaskContext()
        task = TestBaseTradingTaskImpl(logger=logger, context=context)
        
        assert task.task_id != ""
        assert "TestTask" in task.task_id
        assert len(task.task_id) > 10  # Should include timestamp
    
    def test_context_evolution(self, logger):
        """Test context evolution functionality."""
        context = TestTaskContext(test_field="original")
        task = TestBaseTradingTaskImpl(logger=logger, context=context)
        
        # Test simple field update
        task.evolve_context(test_field="updated", test_number=99)
        
        assert task.context.test_field == "updated"
        assert task.context.test_number == 99
    
    @pytest.mark.asyncio
    async def test_state_transitions(self, logger):
        """Test basic state transitions."""
        context = TestTaskContext()
        task = TestBaseTradingTaskImpl(logger=logger, context=context)
        
        # Initial state
        assert task.state == TradingStrategyState.NOT_STARTED
        
        # Start task
        await task.start()
        assert task.state == TradingStrategyState.IDLE
        
        # Pause task
        await task.pause()
        assert task.state == TradingStrategyState.PAUSED
    
    @pytest.mark.asyncio
    async def test_execution_cycle(self, logger):
        """Test task execution cycle."""
        context = TestTaskContext()
        task = TestBaseTradingTaskImpl(logger=logger, context=context)
        
        await task.start()
        
        # Execute one cycle
        result = await task.execute_once()
        
        assert isinstance(result, TaskExecutionResult)
        assert result.task_id == task.task_id
        assert result.execution_time_ms > 0
        assert isinstance(result.should_continue, bool)
    
    def test_context_serialization(self, logger):
        """Test context serialization and restoration."""
        original_context = TestTaskContext(
            test_field="serialization_test",
            test_number=123
        )
        
        task = TestBaseTradingTaskImpl(logger=logger, context=original_context)
        
        # Serialize context
        serialized = task.save_context()
        assert isinstance(serialized, str)
        assert len(serialized) > 0
        
        # Create new task and restore
        new_context = TestTaskContext()
        new_task = TestBaseTradingTaskImpl(logger=logger, context=new_context)
        new_task.restore_context(serialized)
        
        # Verify restoration
        assert new_task.context.test_field == "serialization_test"
        assert new_task.context.test_number == 123


class TestTaskExecutionResult:
    """Test TaskExecutionResult functionality."""
    
    def test_result_creation(self):
        """Test creation of execution results."""
        context = TestTaskContext()
        
        result = TaskExecutionResult(
            task_id="test_123",
            context=context,
            should_continue=True,
            next_delay=0.1,
            execution_time_ms=5.0
        )
        
        assert result.task_id == "test_123"
        assert result.context == context
        assert result.should_continue is True
        assert result.next_delay == 0.1
        assert result.execution_time_ms == 5.0
        assert result.error is None
    
    def test_result_with_error(self):
        """Test execution result with error."""
        context = TestTaskContext()
        error = Exception("Test error")
        
        result = TaskExecutionResult(
            task_id="test_error",
            context=context,
            should_continue=False,
            error=error
        )
        
        assert result.error == error
        assert result.should_continue is False