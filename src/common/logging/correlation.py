"""
HFT Logging Correlation Management

Distributed tracing and correlation ID management for HFT systems.
Provides context correlation across trading operations and components.

Key Features:
- High-performance correlation ID generation
- Context-aware correlation propagation
- Thread-safe correlation management
- Integration with async/await patterns
- Minimal overhead for HFT compliance

HFT OPTIMIZATION: Correlation operations are optimized for
sub-microsecond performance in hot trading paths.
"""

import asyncio
import time
import uuid
import threading
from typing import Optional, Dict, Any, Set
from contextvars import ContextVar
from dataclasses import dataclass, field


# Context variable for current correlation ID
_current_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


@dataclass
class CorrelationContext:
    """
    Correlation context for tracking related operations.
    
    Tracks correlation IDs and related metadata across
    distributed trading operations.
    """
    correlation_id: str
    parent_id: Optional[str] = None
    root_id: Optional[str] = None
    session_id: Optional[str] = None
    operation_type: Optional[str] = None
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'correlation_id': self.correlation_id,
            'parent_id': self.parent_id,
            'root_id': self.root_id,
            'session_id': self.session_id,
            'operation_type': self.operation_type,
            'exchange': self.exchange,
            'symbol': self.symbol,
            'created_at': self.created_at,
            'metadata': self.metadata
        }


class CorrelationManager:
    """
    High-performance correlation ID manager for HFT systems.
    
    Manages correlation context across async operations and threads
    with minimal performance overhead for trading-critical paths.
    
    HFT FEATURES:
    - Sub-microsecond correlation ID generation
    - Lock-free context management where possible
    - Automatic parent-child relationship tracking
    - Context propagation across async boundaries
    - Memory-efficient correlation storage
    """
    
    def __init__(self, 
                 max_contexts: int = 100000,
                 cleanup_interval_seconds: int = 300,
                 context_ttl_seconds: int = 3600):
        
        self.max_contexts = max_contexts
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.context_ttl_seconds = context_ttl_seconds
        
        # Active correlation contexts
        self._contexts: Dict[str, CorrelationContext] = {}
        self._contexts_lock = threading.RLock()
        
        # Performance optimization: Pre-generated ID pool
        self._id_pool: Set[str] = set()
        self._id_pool_lock = threading.Lock()
        self._id_counter = 0
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Statistics
        self.stats = {
            'contexts_created': 0,
            'contexts_retrieved': 0,
            'contexts_cleaned': 0,
            'pool_hits': 0,
            'pool_misses': 0
        }
        
        # Initialize ID pool
        self._populate_id_pool()
        
        # Start cleanup task
        self._start_cleanup_task()
    
    def _populate_id_pool(self, count: int = 1000) -> None:
        """Pre-populate correlation ID pool for performance"""
        with self._id_pool_lock:
            while len(self._id_pool) < count:
                # Generate high-performance correlation IDs
                timestamp = int(time.time_ns() // 1000)  # microseconds
                counter = self._id_counter
                self._id_counter += 1
                
                # Format: timestamp_counter (compact but unique)
                correlation_id = f"{timestamp:016x}_{counter:08x}"
                self._id_pool.add(correlation_id)
    
    def generate_correlation_id(self) -> str:
        """
        Generate a new correlation ID with high performance.
        
        HFT CRITICAL: Optimized for sub-microsecond generation
        using pre-populated ID pool when possible.
        
        Returns:
            Unique correlation ID string
        """
        # Try to use pre-generated ID from pool
        with self._id_pool_lock:
            if self._id_pool:
                correlation_id = self._id_pool.pop()
                self.stats['pool_hits'] += 1
                
                # Repopulate pool if running low
                if len(self._id_pool) < 100:
                    self._populate_id_pool(500)
                
                return correlation_id
        
        # Pool empty - generate new ID (slower path)
        self.stats['pool_misses'] += 1
        timestamp = int(time.time_ns() // 1000)
        counter = self._id_counter
        self._id_counter += 1
        
        return f"{timestamp:016x}_{counter:08x}"
    
    def create_context(self,
                      correlation_id: Optional[str] = None,
                      parent_id: Optional[str] = None,
                      operation_type: Optional[str] = None,
                      exchange: Optional[str] = None,
                      symbol: Optional[str] = None,
                      **metadata) -> CorrelationContext:
        """
        Create a new correlation context.
        
        Args:
            correlation_id: Specific ID to use (generates if None)
            parent_id: Parent correlation ID for hierarchy
            operation_type: Type of operation (e.g., 'trade_execution')
            exchange: Exchange name for context
            symbol: Trading symbol for context
            **metadata: Additional context metadata
            
        Returns:
            New CorrelationContext instance
        """
        if correlation_id is None:
            correlation_id = self.generate_correlation_id()
        
        # Determine root ID for hierarchy tracking
        root_id = None
        if parent_id:
            with self._contexts_lock:
                parent_context = self._contexts.get(parent_id)
                if parent_context:
                    root_id = parent_context.root_id or parent_context.correlation_id
        
        if root_id is None:
            root_id = correlation_id  # This is the root
        
        context = CorrelationContext(
            correlation_id=correlation_id,
            parent_id=parent_id,
            root_id=root_id,
            operation_type=operation_type,
            exchange=exchange,
            symbol=symbol,
            metadata=metadata
        )
        
        # Store context
        with self._contexts_lock:
            # Clean up if approaching limit
            if len(self._contexts) >= self.max_contexts:
                self._cleanup_expired_contexts()
            
            self._contexts[correlation_id] = context
        
        self.stats['contexts_created'] += 1
        return context
    
    def get_context(self, correlation_id: str) -> Optional[CorrelationContext]:
        """
        Retrieve correlation context by ID.
        
        Args:
            correlation_id: Correlation ID to retrieve
            
        Returns:
            CorrelationContext if found, None otherwise
        """
        with self._contexts_lock:
            context = self._contexts.get(correlation_id)
            if context:
                self.stats['contexts_retrieved'] += 1
            return context
    
    def set_current(self, correlation_id: str) -> None:
        """
        Set the current correlation ID for the async context.
        
        Args:
            correlation_id: Correlation ID to set as current
        """
        _current_correlation_id.set(correlation_id)
    
    def get_current(self) -> str:
        """
        Get the current correlation ID from async context.
        
        Returns:
            Current correlation ID or generates a new one
        """
        current = _current_correlation_id.get()
        if current is None:
            # Generate new correlation ID for orphaned operations
            current = self.generate_correlation_id()
            self.set_current(current)
        return current
    
    def clear_current(self) -> None:
        """Clear the current correlation ID from async context"""
        _current_correlation_id.set(None)
    
    def create_child_context(self,
                           operation_type: Optional[str] = None,
                           exchange: Optional[str] = None,
                           symbol: Optional[str] = None,
                           **metadata) -> CorrelationContext:
        """
        Create a child context from the current correlation.
        
        Args:
            operation_type: Type of operation for child context
            exchange: Exchange name for child context
            symbol: Trading symbol for child context
            **metadata: Additional metadata for child context
            
        Returns:
            New child CorrelationContext
        """
        parent_id = self.get_current()
        
        # Copy relevant metadata from parent if available
        parent_context = self.get_context(parent_id)
        if parent_context:
            # Inherit from parent if not explicitly provided
            if exchange is None:
                exchange = parent_context.exchange
            if symbol is None:
                symbol = parent_context.symbol
            
            # Merge metadata
            combined_metadata = parent_context.metadata.copy()
            combined_metadata.update(metadata)
            metadata = combined_metadata
        
        child_context = self.create_context(
            parent_id=parent_id,
            operation_type=operation_type,
            exchange=exchange,
            symbol=symbol,
            **metadata
        )
        
        # Set as current context
        self.set_current(child_context.correlation_id)
        
        return child_context
    
    def _cleanup_expired_contexts(self) -> None:
        """Clean up expired correlation contexts (thread-safe)"""
        cutoff_time = time.time() - self.context_ttl_seconds
        expired_ids = []
        
        # Find expired contexts
        for correlation_id, context in self._contexts.items():
            if context.created_at < cutoff_time:
                expired_ids.append(correlation_id)
        
        # Remove expired contexts
        for correlation_id in expired_ids:
            del self._contexts[correlation_id]
            self.stats['contexts_cleaned'] += 1
    
    def _start_cleanup_task(self) -> None:
        """Start background cleanup task for expired contexts"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup of expired correlation contexts"""
        while not self._shutdown_event.is_set():
            try:
                with self._contexts_lock:
                    self._cleanup_expired_contexts()
                
                await asyncio.sleep(self.cleanup_interval_seconds)
                
            except Exception:
                # Continue cleanup even if one iteration fails
                await asyncio.sleep(self.cleanup_interval_seconds)
    
    async def shutdown(self) -> None:
        """Gracefully shutdown correlation manager"""
        self._shutdown_event.set()
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get correlation manager statistics"""
        with self._contexts_lock:
            active_contexts = len(self._contexts)
        
        with self._id_pool_lock:
            pool_size = len(self._id_pool)
        
        return {
            'active_contexts': active_contexts,
            'max_contexts': self.max_contexts,
            'id_pool_size': pool_size,
            'contexts_created': self.stats['contexts_created'],
            'contexts_retrieved': self.stats['contexts_retrieved'],
            'contexts_cleaned': self.stats['contexts_cleaned'],
            'pool_hits': self.stats['pool_hits'],
            'pool_misses': self.stats['pool_misses'],
            'pool_hit_rate': self.stats['pool_hits'] / max(1, self.stats['pool_hits'] + self.stats['pool_misses'])
        }


# Global correlation manager instance
_correlation_manager: Optional[CorrelationManager] = None


def get_correlation_manager() -> CorrelationManager:
    """Get the global correlation manager instance"""
    global _correlation_manager
    if _correlation_manager is None:
        _correlation_manager = CorrelationManager()
    return _correlation_manager


def generate_correlation_id() -> str:
    """Generate a new correlation ID using the global manager"""
    return get_correlation_manager().generate_correlation_id()


def get_current_correlation_id() -> str:
    """Get the current correlation ID from async context"""
    return get_correlation_manager().get_current()


def set_correlation_context(correlation_id: str) -> None:
    """Set the current correlation ID in async context"""
    get_correlation_manager().set_current(correlation_id)


class correlation_context:
    """
    Async context manager for correlation ID management.
    
    Usage:
        async with correlation_context("trade_execution") as ctx:
            # All logging within this block will use the correlation ID
            await log_trade_execution(...)
    """
    
    def __init__(self,
                 operation_type: Optional[str] = None,
                 correlation_id: Optional[str] = None,
                 exchange: Optional[str] = None,
                 symbol: Optional[str] = None,
                 **metadata):
        
        self.operation_type = operation_type
        self.correlation_id = correlation_id
        self.exchange = exchange
        self.symbol = symbol
        self.metadata = metadata
        self.context: Optional[CorrelationContext] = None
        self.previous_correlation_id: Optional[str] = None
    
    async def __aenter__(self) -> CorrelationContext:
        """Enter correlation context"""
        manager = get_correlation_manager()
        
        # Save previous correlation ID
        self.previous_correlation_id = _current_correlation_id.get()
        
        if self.correlation_id:
            # Use provided correlation ID
            self.context = manager.create_context(
                correlation_id=self.correlation_id,
                parent_id=self.previous_correlation_id,
                operation_type=self.operation_type,
                exchange=self.exchange,
                symbol=self.symbol,
                **self.metadata
            )
        else:
            # Create child context from current
            self.context = manager.create_child_context(
                operation_type=self.operation_type,
                exchange=self.exchange,
                symbol=self.symbol,
                **self.metadata
            )
        
        # Set as current context
        manager.set_current(self.context.correlation_id)
        
        return self.context
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit correlation context"""
        # Restore previous correlation ID
        if self.previous_correlation_id:
            get_correlation_manager().set_current(self.previous_correlation_id)
        else:
            get_correlation_manager().clear_current()


# Convenience decorators for automatic correlation
def with_correlation(operation_type: str, exchange: Optional[str] = None, symbol: Optional[str] = None):
    """
    Decorator for automatic correlation context management.
    
    Usage:
        @with_correlation("order_submission", exchange="MEXC", symbol="BTC_USDT")
        async def submit_order(...):
            # Function automatically gets correlation context
            await log_trade_execution(...)
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async with correlation_context(operation_type, exchange=exchange, symbol=symbol):
                return await func(*args, **kwargs)
        return wrapper
    return decorator