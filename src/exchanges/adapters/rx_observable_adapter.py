"""
RxObservableAdapter - External RxPY Integration

Provides external RxPY observable streams that bind to exchange events
without inheriting from composite exchange classes. Solves AsyncIO cleanup
issues by maintaining independent lifecycle management.
"""

import asyncio
from typing import Dict, Any, Optional, Callable, Set
from threading import Lock

try:
    import reactivex as rx
    from reactivex import operators as ops
    from reactivex.subject import BehaviorSubject
    from reactivex.disposable import Disposable
    RX_AVAILABLE = True
except ImportError:
    RX_AVAILABLE = False
    # Create mock classes for when RxPY is not available
    class BehaviorSubject:
        def __init__(self, initial_value=None):
            pass
        def on_next(self, value):
            pass
        def on_completed(self):
            pass
        def dispose(self):
            pass
        def subscribe(self, observer):
            class MockDisposable:
                def dispose(self):
                    pass
            return MockDisposable()
    
    class Disposable:
        def dispose(self):
            pass

from utils.task_utils import cancel_tasks_with_timeout


class RxObservableAdapter:
    """
    External RxPY adapter that binds to exchange publish() events.
    
    This adapter provides RxPY observable streams without requiring inheritance
    from exchange classes. It solves AsyncIO cleanup issues by maintaining
    independent lifecycle management and proper subscription tracking.
    
    Features:
    - External binding to exchange.publish() events
    - Independent lifecycle management
    - Subscription tracking for proper cleanup
    - Timeout-protected disposal
    - Thread-safe operation
    
    Usage:
        rx_adapter = RxObservableAdapter()
        rx_adapter.bind_to_exchange(exchange)
        
        # Subscribe to streams
        subscription = rx_adapter.book_tickers_stream.subscribe(my_handler)
        
        # Cleanup
        await rx_adapter.dispose()
    """
    
    def __init__(self, logger=None):
        """
        Initialize RxObservableAdapter.
        
        Args:
            logger: Optional logger for debugging and metrics
        """
        if not RX_AVAILABLE:
            raise ImportError("reactivex is required for RxObservableAdapter")
            
        self.logger = logger
        self._exchange = None
        self._bound = False
        self._disposed = False
        self._lock = Lock()
        
        # Observable streams
        self._streams: Dict[str, BehaviorSubject] = {}
        self._subscriptions: Set[Disposable] = set()
        
        # Initialize standard market data streams
        self._initialize_streams()
        
        # Bound handler for exchange events
        self._bound_handler = self._handle_exchange_event
    
    def _initialize_streams(self) -> None:
        """Initialize standard observable streams."""
        # Public market data streams
        self._streams = {
            'book_tickers': BehaviorSubject(None),
            'orderbooks': BehaviorSubject(None),
            'tickers': BehaviorSubject(None),
            'trades': BehaviorSubject(None),
            
            # Private trading streams
            'balances': BehaviorSubject(None),
            'orders': BehaviorSubject(None),
            'positions': BehaviorSubject(None),
            'executions': BehaviorSubject(None)
        }
    
    def bind_to_exchange(self, exchange) -> None:
        """
        Bind adapter to exchange publish() events.
        
        Args:
            exchange: Exchange instance with publish() method
            
        Raises:
            ValueError: If exchange doesn't have publish() method
            RuntimeError: If adapter is already bound or disposed
        """
        with self._lock:
            if self._disposed:
                raise RuntimeError("Cannot bind to disposed adapter")
            if self._bound:
                raise RuntimeError("Adapter is already bound to an exchange")
            if not hasattr(exchange, 'bind'):
                raise ValueError("Exchange must have bind() method for adapter integration")
            
            self._exchange = exchange
            
            # Bind to each stream type
            for stream_name in self._streams.keys():
                try:
                    exchange.bind(stream_name, self._bound_handler)
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Could not bind to channel {stream_name}: {e}")
            
            self._bound = True
            
            if self.logger:
                self.logger.info("RxObservableAdapter bound to exchange",
                               exchange_name=getattr(exchange, '_exchange_name', 'unknown'),
                               stream_count=len(self._streams))
    
    async def _handle_exchange_event(self, channel: str, data: Any) -> None:
        """
        Handle events from exchange publish() method.
        
        Args:
            channel: Channel name (e.g., "book_tickers", "orderbooks")
            data: Event data
        """
        if self._disposed:
            return
            
        # Map channel to stream if available
        if channel in self._streams:
            try:
                self._streams[channel].on_next(data)
                
                if self.logger:
                    self.logger.debug("Event published to RxPY stream",
                                    channel=channel,
                                    data_type=type(data).__name__)
            except Exception as e:
                if self.logger:
                    self.logger.error("Error publishing to RxPY stream",
                                    channel=channel,
                                    error_type=type(e).__name__,
                                    error_message=str(e))
    
    def subscribe_tracked(self, stream_name: str, observer: Callable) -> Optional[Disposable]:
        """
        Subscribe to stream with automatic tracking for cleanup.
        
        Args:
            stream_name: Name of the stream to subscribe to
            observer: Observer function or callable
            
        Returns:
            Disposable subscription or None if stream doesn't exist
        """
        if self._disposed:
            raise RuntimeError("Cannot subscribe to disposed adapter")
            
        if stream_name not in self._streams:
            if self.logger:
                self.logger.warning(f"Unknown stream: {stream_name}")
            return None
        
        stream = self._streams[stream_name]
        subscription = stream.subscribe(observer)
        
        with self._lock:
            self._subscriptions.add(subscription)
        
        # Remove from tracking when disposed
        def on_dispose():
            with self._lock:
                self._subscriptions.discard(subscription)
        
        # Add dispose callback if supported
        if hasattr(subscription, 'add_dispose_callback'):
            subscription.add_dispose_callback(on_dispose)
        
        return subscription
    
    @property
    def book_tickers_stream(self) -> BehaviorSubject:
        """Get book tickers observable stream."""
        return self._streams['book_tickers']
    
    @property
    def orderbooks_stream(self) -> BehaviorSubject:
        """Get orderbooks observable stream."""
        return self._streams['orderbooks']
    
    @property
    def tickers_stream(self) -> BehaviorSubject:
        """Get tickers observable stream."""
        return self._streams['tickers']
    
    @property
    def trades_stream(self) -> BehaviorSubject:
        """Get trades observable stream."""
        return self._streams['trades']
    
    @property
    def balances_stream(self) -> BehaviorSubject:
        """Get balances observable stream."""
        return self._streams['balances']
    
    @property
    def orders_stream(self) -> BehaviorSubject:
        """Get orders observable stream."""
        return self._streams['orders']
    
    @property
    def positions_stream(self) -> BehaviorSubject:
        """Get positions observable stream."""
        return self._streams['positions']
    
    @property
    def executions_stream(self) -> BehaviorSubject:
        """Get executions observable stream."""
        return self._streams['executions']
    
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
            # Dispose all tracked subscriptions
            subscriptions_to_dispose = list(self._subscriptions)
            
            if subscriptions_to_dispose:
                if self.logger:
                    self.logger.debug(f"Disposing {len(subscriptions_to_dispose)} RxPY subscriptions")
                
                for subscription in subscriptions_to_dispose:
                    try:
                        subscription.dispose()
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(f"Error disposing subscription: {e}")
                        success = False
            
            # Clear subscriptions
            self._subscriptions.clear()
            
            # Complete and dispose all streams
            for stream_name, stream in self._streams.items():
                try:
                    stream.on_completed()
                    stream.dispose()
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Error disposing stream {stream_name}: {e}")
                    success = False
            
            # Unbind from exchange if bound
            if self._bound and self._exchange and hasattr(self._exchange, 'unbind'):
                for stream_name in self._streams.keys():
                    try:
                        self._exchange.unbind(stream_name, self._bound_handler)
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(f"Error unbinding from channel {stream_name}: {e}")
            
            self._bound = False
            self._exchange = None
            
            if self.logger:
                self.logger.info("RxObservableAdapter disposed successfully")
            
            return success
            
        except Exception as e:
            if self.logger:
                self.logger.error("Error during RxObservableAdapter disposal",
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
        return self._bound and not self._disposed
    
    @property
    def subscription_count(self) -> int:
        """Get count of active subscriptions."""
        with self._lock:
            return len(self._subscriptions)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get adapter status for debugging.
        
        Returns:
            Dictionary with adapter status information
        """
        return {
            'bound': self._bound,
            'disposed': self._disposed,
            'subscription_count': self.subscription_count,
            'stream_count': len(self._streams),
            'exchange_bound': self._exchange is not None
        }


class RxObservableAdapterFactory:
    """Factory for creating RxObservableAdapter instances."""
    
    @staticmethod
    def create_for_exchange(exchange, logger=None) -> RxObservableAdapter:
        """
        Create and bind RxObservableAdapter to exchange.
        
        Args:
            exchange: Exchange instance to bind to
            logger: Optional logger
            
        Returns:
            Configured and bound RxObservableAdapter
        """
        adapter = RxObservableAdapter(logger=logger)
        adapter.bind_to_exchange(exchange)
        return adapter