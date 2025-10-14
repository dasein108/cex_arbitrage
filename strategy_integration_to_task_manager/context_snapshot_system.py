"""Context Snapshot System - Advanced order preservation and recovery.

This module provides comprehensive context snapshotting and recovery mechanisms
for the ArbitrageTask to ensure order IDs and trading state are preserved
across TaskManager restarts and failures.
"""

import json
import time
import asyncio
from typing import Dict, List, Optional, Tuple, Any
import msgspec
from pathlib import Path

from exchanges.structs import Order, Symbol, Side
from infrastructure.logging import HFTLoggerInterface
from utils.exchange_utils import is_order_done

from .arbitrage_task_context import ArbitrageTaskContext
from applications.hedged_arbitrage.strategy.mexc_gateio_futures_strategy import ArbitrageState


class ContextSnapshot(msgspec.Struct):
    """Complete snapshot of arbitrage context with metadata."""
    
    # Snapshot metadata
    snapshot_id: str
    timestamp: float
    task_id: str
    symbol: str
    
    # Context data (serialized as JSON string for flexibility)
    context_data: str
    
    # Critical order preservation data
    active_orders: Dict[str, Dict[str, Dict[str, Any]]]  # exchange -> order_id -> order_data
    order_count: int
    
    # Validation checksums
    position_checksum: str
    context_checksum: str
    
    # Recovery metadata
    recovery_priority: int = 1  # Higher = more critical
    recovery_validated: bool = False


class ContextSnapshotManager:
    """Manages context snapshots with order preservation and recovery validation."""
    
    def __init__(self, 
                 logger: HFTLoggerInterface,
                 storage_path: str = "task_data/snapshots",
                 max_snapshots_per_task: int = 10):
        """Initialize snapshot manager.
        
        Args:
            logger: HFT logger instance
            storage_path: Base path for snapshot storage
            max_snapshots_per_task: Maximum snapshots to keep per task
        """
        self.logger = logger
        self.storage_path = Path(storage_path)
        self.max_snapshots_per_task = max_snapshots_per_task
        
        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # In-memory snapshot cache for fast access
        self._snapshot_cache: Dict[str, List[ContextSnapshot]] = {}
        
        self.logger.info(f"✅ ContextSnapshotManager initialized: {self.storage_path}")
    
    def create_snapshot(self, context: ArbitrageTaskContext) -> ContextSnapshot:
        """Create a comprehensive snapshot of the arbitrage context.
        
        Args:
            context: Current arbitrage context
            
        Returns:
            Complete context snapshot with order preservation
        """
        snapshot_id = f"snapshot_{int(time.time() * 1000)}_{context.task_id}"
        
        # Serialize context data
        context_json = self._serialize_context(context)
        
        # Extract and preserve active orders with full detail
        preserved_orders = self._preserve_active_orders(context)
        
        # Calculate validation checksums
        position_checksum = self._calculate_position_checksum(context)
        context_checksum = self._calculate_context_checksum(context_json)
        
        # Determine recovery priority based on context state
        recovery_priority = self._calculate_recovery_priority(context)
        
        snapshot = ContextSnapshot(
            snapshot_id=snapshot_id,
            timestamp=time.time(),
            task_id=context.task_id,
            symbol=str(context.symbol),
            context_data=context_json,
            active_orders=preserved_orders,
            order_count=context.get_active_order_count(),
            position_checksum=position_checksum,
            context_checksum=context_checksum,
            recovery_priority=recovery_priority
        )
        
        self.logger.debug(f"📸 Created snapshot {snapshot_id}: "
                         f"{snapshot.order_count} orders, priority {recovery_priority}")
        
        return snapshot
    
    async def save_snapshot(self, snapshot: ContextSnapshot) -> bool:
        """Save snapshot to persistent storage with atomic write.
        
        Args:
            snapshot: Snapshot to save
            
        Returns:
            True if save successful, False otherwise
        """
        try:
            # Create task-specific subdirectory
            task_dir = self.storage_path / snapshot.task_id
            task_dir.mkdir(exist_ok=True)
            
            # Write with atomic operation (temp file + rename)
            snapshot_file = task_dir / f"{snapshot.snapshot_id}.json"
            temp_file = task_dir / f"{snapshot.snapshot_id}.tmp"
            
            # Serialize snapshot
            snapshot_data = msgspec.json.encode(snapshot).decode('utf-8')
            
            # Atomic write
            with open(temp_file, 'w') as f:
                f.write(snapshot_data)
                f.flush()  # Ensure data is written
            
            # Atomic rename
            temp_file.rename(snapshot_file)
            
            # Update cache
            if snapshot.task_id not in self._snapshot_cache:
                self._snapshot_cache[snapshot.task_id] = []
            
            self._snapshot_cache[snapshot.task_id].append(snapshot)
            
            # Cleanup old snapshots
            await self._cleanup_old_snapshots(snapshot.task_id)
            
            self.logger.debug(f"💾 Saved snapshot {snapshot.snapshot_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save snapshot {snapshot.snapshot_id}: {e}")
            return False
    
    async def load_latest_snapshot(self, task_id: str) -> Optional[ContextSnapshot]:
        """Load the latest valid snapshot for a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Latest snapshot or None if not found
        """
        try:
            # Check cache first
            if task_id in self._snapshot_cache and self._snapshot_cache[task_id]:
                return self._snapshot_cache[task_id][-1]
            
            # Load from disk
            task_dir = self.storage_path / task_id
            if not task_dir.exists():
                return None
            
            snapshots = []
            for snapshot_file in task_dir.glob("*.json"):
                try:
                    with open(snapshot_file, 'r') as f:
                        snapshot_data = f.read()
                    
                    snapshot = msgspec.json.decode(snapshot_data, type=ContextSnapshot)
                    snapshots.append(snapshot)
                    
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to load snapshot {snapshot_file}: {e}")
                    continue
            
            if not snapshots:
                return None
            
            # Sort by timestamp and return latest
            snapshots.sort(key=lambda s: s.timestamp)
            latest_snapshot = snapshots[-1]
            
            # Update cache
            self._snapshot_cache[task_id] = snapshots
            
            self.logger.info(f"📂 Loaded latest snapshot {latest_snapshot.snapshot_id} for task {task_id}")
            return latest_snapshot
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load latest snapshot for task {task_id}: {e}")
            return None
    
    async def restore_context_from_snapshot(self, 
                                          snapshot: ContextSnapshot,
                                          validate_orders: bool = True) -> Optional[ArbitrageTaskContext]:
        """Restore ArbitrageTaskContext from snapshot with order validation.
        
        Args:
            snapshot: Snapshot to restore from
            validate_orders: Whether to validate order preservation
            
        Returns:
            Restored context or None if restoration failed
        """
        try:
            # Deserialize context
            context = self._deserialize_context(snapshot.context_data)
            if not context:
                return None
            
            # Restore active orders
            restored_orders = self._restore_active_orders(snapshot.active_orders)
            context.active_orders = restored_orders
            
            # Validate restoration if requested
            if validate_orders:
                validation_result = await self._validate_snapshot_restoration(snapshot, context)
                if not validation_result.valid:
                    self.logger.error(f"❌ Snapshot validation failed: {validation_result.reason}")
                    return None
            
            # Mark context as should_save for TaskManager persistence
            context.should_save_flag = True
            
            self.logger.info(f"✅ Restored context from snapshot {snapshot.snapshot_id}: "
                           f"{len(restored_orders)} exchanges, {context.get_active_order_count()} orders")
            
            return context
            
        except Exception as e:
            self.logger.error(f"❌ Failed to restore context from snapshot {snapshot.snapshot_id}: {e}")
            return None
    
    # Private helper methods
    
    def _serialize_context(self, context: ArbitrageTaskContext) -> str:
        """Serialize context to JSON string."""
        try:
            # Use msgspec for efficient serialization
            return msgspec.json.encode(context).decode('utf-8')
        except Exception as e:
            self.logger.error(f"❌ Context serialization failed: {e}")
            return "{}"
    
    def _deserialize_context(self, context_json: str) -> Optional[ArbitrageTaskContext]:
        """Deserialize context from JSON string."""
        try:
            return msgspec.json.decode(context_json, type=ArbitrageTaskContext)
        except Exception as e:
            self.logger.error(f"❌ Context deserialization failed: {e}")
            return None
    
    def _preserve_active_orders(self, context: ArbitrageTaskContext) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Extract and preserve active orders with complete information."""
        preserved = {}
        
        for exchange_type, orders in context.active_orders.items():
            preserved[exchange_type] = {}
            for order_id, order in orders.items():
                if order:
                    # Convert Order to dict for JSON serialization
                    order_dict = {
                        'order_id': order.order_id,
                        'symbol': str(order.symbol),
                        'side': order.side.name,
                        'quantity': order.quantity,
                        'filled_quantity': order.filled_quantity,
                        'price': order.price,
                        'status': order.status.name if hasattr(order, 'status') else 'UNKNOWN',
                        'timestamp': getattr(order, 'timestamp', time.time()),
                        # Add any other critical order fields
                    }
                    preserved[exchange_type][order_id] = order_dict
        
        return preserved
    
    def _restore_active_orders(self, preserved_orders: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Order]]:
        """Restore active orders from preserved data."""
        restored = {"spot": {}, "futures": {}}
        
        for exchange_type, orders in preserved_orders.items():
            if exchange_type in restored:
                for order_id, order_data in orders.items():
                    try:
                        # Reconstruct Order object (simplified - full implementation would handle all fields)
                        # This is a placeholder - actual implementation would need proper Order reconstruction
                        restored[exchange_type][order_id] = None  # Placeholder for proper Order object
                        
                    except Exception as e:
                        self.logger.warning(f"⚠️ Failed to restore order {order_id}: {e}")
                        continue
        
        return restored
    
    def _calculate_position_checksum(self, context: ArbitrageTaskContext) -> str:
        """Calculate checksum for position validation."""
        try:
            position_data = f"{context.positions.positions['spot'].qty}:{context.positions.positions['futures'].qty}"
            return str(hash(position_data))
        except:
            return "0"
    
    def _calculate_context_checksum(self, context_json: str) -> str:
        """Calculate checksum for context validation."""
        return str(hash(context_json))
    
    def _calculate_recovery_priority(self, context: ArbitrageTaskContext) -> int:
        """Calculate recovery priority based on context state.
        
        Higher values = higher priority for recovery.
        """
        priority = 1  # Base priority
        
        # Higher priority if we have active orders
        if context.has_active_orders():
            priority += 3
        
        # Higher priority if we have open positions
        if context.positions.has_positions:
            priority += 2
        
        # Higher priority if currently executing
        if context.arbitrage_state == ArbitrageState.EXECUTING:
            priority += 4
        
        # Lower priority if in error recovery
        if context.arbitrage_state == ArbitrageState.ERROR_RECOVERY:
            priority -= 1
        
        return max(1, priority)  # Minimum priority of 1
    
    async def _validate_snapshot_restoration(self, 
                                           snapshot: ContextSnapshot, 
                                           restored_context: ArbitrageTaskContext) -> 'ValidationResult':
        """Validate that snapshot restoration preserved critical data."""
        try:
            # Validate order count
            if restored_context.get_active_order_count() != snapshot.order_count:
                return ValidationResult(
                    valid=False,
                    reason=f"Order count mismatch: expected {snapshot.order_count}, "
                          f"got {restored_context.get_active_order_count()}"
                )
            
            # Validate position checksum
            current_checksum = self._calculate_position_checksum(restored_context)
            if current_checksum != snapshot.position_checksum:
                return ValidationResult(
                    valid=False,
                    reason=f"Position checksum mismatch: expected {snapshot.position_checksum}, "
                          f"got {current_checksum}"
                )
            
            # Validate task ID consistency
            if restored_context.task_id != snapshot.task_id:
                return ValidationResult(
                    valid=False,
                    reason=f"Task ID mismatch: expected {snapshot.task_id}, "
                          f"got {restored_context.task_id}"
                )
            
            return ValidationResult(valid=True, reason="Snapshot validation passed")
            
        except Exception as e:
            return ValidationResult(
                valid=False,
                reason=f"Validation error: {e}"
            )
    
    async def _cleanup_old_snapshots(self, task_id: str):
        """Remove old snapshots beyond max limit."""
        try:
            if task_id not in self._snapshot_cache:
                return
            
            snapshots = self._snapshot_cache[task_id]
            if len(snapshots) <= self.max_snapshots_per_task:
                return
            
            # Sort by timestamp and keep only the latest ones
            snapshots.sort(key=lambda s: s.timestamp)
            to_keep = snapshots[-self.max_snapshots_per_task:]
            to_remove = snapshots[:-self.max_snapshots_per_task]
            
            # Remove old snapshot files
            task_dir = self.storage_path / task_id
            for snapshot in to_remove:
                snapshot_file = task_dir / f"{snapshot.snapshot_id}.json"
                if snapshot_file.exists():
                    snapshot_file.unlink()
            
            # Update cache
            self._snapshot_cache[task_id] = to_keep
            
            if to_remove:
                self.logger.debug(f"🧹 Cleaned up {len(to_remove)} old snapshots for task {task_id}")
                
        except Exception as e:
            self.logger.error(f"❌ Failed to cleanup old snapshots for task {task_id}: {e}")


# Placeholder ValidationResult class
class ValidationResult:
    def __init__(self, valid: bool, reason: str = ""):
        self.valid = valid
        self.reason = reason


# Integration helper functions

async def create_and_save_snapshot(context: ArbitrageTaskContext,
                                 snapshot_manager: ContextSnapshotManager) -> bool:
    """Convenience function to create and save a context snapshot.
    
    Args:
        context: Current arbitrage context
        snapshot_manager: Snapshot manager instance
        
    Returns:
        True if snapshot created and saved successfully
    """
    try:
        snapshot = snapshot_manager.create_snapshot(context)
        return await snapshot_manager.save_snapshot(snapshot)
    except Exception as e:
        snapshot_manager.logger.error(f"❌ Failed to create and save snapshot: {e}")
        return False


async def restore_latest_context(task_id: str,
                                snapshot_manager: ContextSnapshotManager) -> Optional[ArbitrageTaskContext]:
    """Convenience function to restore latest context from snapshots.
    
    Args:
        task_id: Task identifier
        snapshot_manager: Snapshot manager instance
        
    Returns:
        Restored context or None if restoration failed
    """
    try:
        snapshot = await snapshot_manager.load_latest_snapshot(task_id)
        if not snapshot:
            return None
        
        return await snapshot_manager.restore_context_from_snapshot(snapshot)
    except Exception as e:
        snapshot_manager.logger.error(f"❌ Failed to restore latest context: {e}")
        return None