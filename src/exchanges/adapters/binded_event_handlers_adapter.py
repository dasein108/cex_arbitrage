"""
BindedEventHandlersAdapter - Multiple Handler Support

Provides an adapter that allows multiple handlers to be bound to a single channel.
Enables flexible event processing without tight coupling to exchange internals.
"""

import asyncio
from typing import Dict, List, Callable, Awaitable, Any, Optional, Set, Union
from threading import Lock

from infrastructure.networking.websocket.structs import WebsocketChannelType
from utils.task_utils import cancel_tasks_with_timeout
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

ChannelType =  Union[str, PublicWebsocketChannelType, PrivateWebsocketChannelType]

class BindedEventHandlersAdapter:
    """
    Adapter that supports multiple handlers per channel.
    
    This adapter allows binding multiple event handlers to a single channel,
    enabling flexible event processing patterns. Handlers are executed
    concurrently for optimal performance.
    
    Features:
    - Multiple handlers per channel
    - Concurrent handler execution
    - Independent lifecycle management
    - Error isolation between handlers
    - Timeout-protected cleanup
    - Thread-safe operation
    
    Usage:
        adapter = BindedEventHandlersAdapter()
        adapter.bind_to_exchange(exchange)
        
        # Bind multiple handlers to the same channel
        adapter.bind("book_ticker", handler1)
        adapter.bind("book_ticker", handler2)
        adapter.bind("book_ticker", handler3)
        
        # All handlers will receive events concurrently
        # Cleanup
        await adapter.dispose()
    """
    
    def __init__(self, logger=None):
        """
        Initialize BindedEventHandlersAdapter.
        
        Args:
            logger: Optional logger for debugging and metrics
        """
        self.logger = logger
        self._exchange = None
        self._bound_to_exchange = False
        self._disposed = False
        self._lock = Lock()
        
        # Channel -> List of handlers mapping
        self._channel_handlers: Dict[str, List[Callable[[Any], Awaitable[None]]]] = {}
        
        # Track active handler tasks for cleanup
        self._active_tasks: Set[asyncio.Task] = set()
        
        # Internal handler that receives events from exchange
        self._exchange_handler = self._handle_exchange_event
    
    def bind_to_exchange(self, exchange) -> 'BindedEventHandlersAdapter':
        """
        Bind adapter to exchange publish() events.
        
        Args:
            exchange: Exchange instance with bind() method
            
        Raises:
            ValueError: If exchange doesn't have bind() method
            RuntimeError: If adapter is already bound or disposed
        """
        with self._lock:
            if self._disposed:
                raise RuntimeError("Cannot bind to disposed adapter")
            if self._bound_to_exchange:
                raise RuntimeError("Adapter is already bound to an exchange")
            if not hasattr(exchange, 'bind'):
                raise ValueError("Exchange must have bind() method for adapter integration")
            
            self._exchange = exchange
            self._bound_to_exchange = True
            
            if self.logger:
                self.logger.info("BindedEventHandlersAdapter bound to exchange",
                               exchange_name=getattr(exchange, '_exchange_name', 'unknown'))

            return self
    
    def bind(self, channel: ChannelType,
             handler: Callable[[Any], Awaitable[None]]) -> None:
        """
        Bind handler to channel. Multiple handlers can be bound to the same channel.
        
        Args:
            channel: Channel identifier (e.g., "book_ticker", "orderbook")  
            handler: Async handler function
            
        Raises:
            RuntimeError: If adapter is disposed
            ValueError: If handler is not callable
        """
        if self._disposed:
            raise RuntimeError("Cannot bind to disposed adapter")
        if not callable(handler):
            raise ValueError("Handler must be callable")
        
        with self._lock:
            # Initialize channel if not exists
            if channel not in self._channel_handlers:
                self._channel_handlers[channel] = []
                
                # Bind to exchange for this channel if we're connected
                if self._bound_to_exchange and self._exchange:
                    try:
                        self._exchange.bind(channel, self._exchange_handler)
                        if self.logger:
                            self.logger.debug(f"Bound to exchange channel: {channel}")
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(f"Could not bind to exchange channel {channel}: {e}")
            
            # Add handler to channel
            self._channel_handlers[channel].append(handler)
            
            if self.logger:
                handler_count = len(self._channel_handlers[channel])
                self.logger.debug(f"Handler bound to channel {channel} (total handlers: {handler_count})")
    
    def unbind(self, channel: ChannelType, handler: Callable[[Any], Awaitable[None]]) -> bool:
        """
        Unbind specific handler from channel.
        
        Args:
            channel: Channel identifier
            handler: Handler function to remove
            
        Returns:
            True if handler was found and removed, False otherwise
        """
        if self._disposed:
            return False
            
        with self._lock:
            if channel not in self._channel_handlers:
                return False
            
            try:
                self._channel_handlers[channel].remove(handler)
                
                # If no handlers remain for this channel, unbind from exchange
                if not self._channel_handlers[channel]:
                    del self._channel_handlers[channel]
                    
                    if self._bound_to_exchange and self._exchange and hasattr(self._exchange, 'unbind'):
                        try:
                            self._exchange.unbind(channel, self._exchange_handler)
                            if self.logger:
                                self.logger.debug(f"Unbound from exchange channel: {channel}")
                        except Exception as e:
                            if self.logger:
                                self.logger.warning(f"Could not unbind from exchange channel {channel}: {e}")
                
                if self.logger:
                    remaining_count = len(self._channel_handlers.get(channel, []))
                    self.logger.debug(f"Handler unbound from channel {channel} (remaining handlers: {remaining_count})")
                
                return True
                
            except ValueError:
                return False
    
    async def _handle_exchange_event(self, channel: ChannelType, data: Any) -> None:
        """
        Handle events from exchange and dispatch to all bound handlers.
        
        Args:
            channel: Channel name
            data: Event data
        """
        if self._disposed:
            return
        
        handlers = []
        with self._lock:
            handlers = self._channel_handlers.get(channel, []).copy()
        
        if not handlers:
            return
        
        # Execute all handlers concurrently
        tasks = []
        for handler in handlers:
            try:
                task = asyncio.create_task(self._execute_handler_safely(handler, data, channel))
                tasks.append(task)
                self._active_tasks.add(task)
                
                # Remove task from tracking when done
                def cleanup_task(completed_task):
                    self._active_tasks.discard(completed_task)
                task.add_done_callback(cleanup_task)
                
            except Exception as e:
                if self.logger:
                    self.logger.error("Error creating handler task",
                                    channel=channel,
                                    error_type=type(e).__name__,
                                    error_message=str(e))
        
        # Optional: Wait for all handlers to complete (can be disabled for performance)
        # await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_handler_safely(self, handler: Callable, data: Any, channel: ChannelType) -> None:
        """
        Execute handler with error isolation.
        
        Args:
            handler: Handler function to execute
            data: Event data
            channel: Channel name for logging
        """
        try:
            await handler(data)
            
        except Exception as e:
            if self.logger:
                self.logger.error("Error in event handler",
                                channel=channel,
                                handler_name=getattr(handler, '__name__', 'unknown'),
                                error_type=type(e).__name__,
                                error_message=str(e))
    
    def get_channel_handlers(self, channel: ChannelType) -> List[Callable]:
        """
        Get list of handlers for a channel.
        
        Args:
            channel: Channel identifier
            
        Returns:
            List of handler functions (copy)
        """
        with self._lock:
            return self._channel_handlers.get(channel, []).copy()
    
    def get_all_channels(self) -> List[ChannelType]:
        """
        Get list of all channels with bound handlers.
        
        Returns:
            List of channel names
        """
        with self._lock:
            return list(self._channel_handlers.keys())
    
    def get_handler_count(self, channel: ChannelType = None) -> int:
        """
        Get count of handlers.
        
        Args:
            channel: Specific channel to count, or None for total across all channels
            
        Returns:
            Number of handlers
        """
        with self._lock:
            if channel is not None:
                return len(self._channel_handlers.get(channel, []))
            else:
                return sum(len(handlers) for handlers in self._channel_handlers.values())
    
    async def dispose(self, timeout: float = 2.0) -> bool:
        """
        Dispose adapter and cleanup all resources.
        
        Args:
            timeout: Maximum time to wait for cleanup
            
        Returns:
            True if cleanup completed within timeout
        """
        with self._lock:
            if self._disposed:
                return True
            self._disposed = True
        
        success = True
        
        try:
            # Cancel all active handler tasks
            active_tasks = list(self._active_tasks)
            if active_tasks:
                if self.logger:
                    self.logger.debug(f"Cancelling {len(active_tasks)} active handler tasks")
                
                task_success = await cancel_tasks_with_timeout(active_tasks, timeout, self.logger)
                if not task_success:
                    success = False
            
            self._active_tasks.clear()
            
            # Unbind from exchange for all channels
            if self._bound_to_exchange and self._exchange and hasattr(self._exchange, 'unbind'):
                channels_to_unbind = list(self._channel_handlers.keys())
                for channel in channels_to_unbind:
                    try:
                        self._exchange.unbind(channel, self._exchange_handler)
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(f"Error unbinding from channel {channel}: {e}")
                        success = False
            
            # Clear all handlers
            self._channel_handlers.clear()
            self._bound_to_exchange = False
            self._exchange = None
            
            if self.logger:
                self.logger.info("BindedEventHandlersAdapter disposed successfully")
            
            return success
            
        except Exception as e:
            if self.logger:
                self.logger.error("Error during BindedEventHandlersAdapter disposal",
                                error_type=type(e).__name__,
                                error_message=str(e))
            return False
    
    @property
    def is_disposed(self) -> bool:
        """Check if adapter has been disposed."""
        return self._disposed
    
    @property
    def is_bound(self) -> bool:
        """Check if adapter is bound to an exchange."""
        return self._bound_to_exchange and not self._disposed
    
    @property
    def active_task_count(self) -> int:
        """Get count of active handler tasks."""
        return len(self._active_tasks)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get adapter status for debugging.
        
        Returns:
            Dictionary with adapter status information
        """
        with self._lock:
            return {
                'bound_to_exchange': self._bound_to_exchange,
                'disposed': self._disposed,
                'total_handlers': self.get_handler_count(),
                'channel_count': len(self._channel_handlers),
                'active_tasks': self.active_task_count,
                'channels': list(self._channel_handlers.keys()),
                'exchange_bound': self._exchange is not None
            }


class BindedEventHandlersAdapterFactory:
    """Factory for creating BindedEventHandlersAdapter instances."""
    
    @staticmethod
    def create_for_exchange(exchange, logger=None) -> BindedEventHandlersAdapter:
        """
        Create and bind BindedEventHandlersAdapter to exchange.
        
        Args:
            exchange: Exchange instance to bind to
            logger: Optional logger
            
        Returns:
            Configured and bound BindedEventHandlersAdapter
        """
        adapter = BindedEventHandlersAdapter(logger=logger)
        adapter.bind_to_exchange(exchange)
        return adapter