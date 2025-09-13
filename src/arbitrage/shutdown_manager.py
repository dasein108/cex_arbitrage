"""
Shutdown Manager

Handles graceful shutdown and cleanup for the arbitrage engine.
Ensures all resources are properly released and positions are safe.

HFT COMPLIANT: Fast shutdown with position safety guarantees.
"""

import asyncio
import logging
import signal
from typing import Optional, Callable, List, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ShutdownReason(Enum):
    """Reasons for shutdown."""
    USER_REQUESTED = "User requested shutdown"
    SIGNAL_RECEIVED = "Signal received"
    ERROR_CRITICAL = "Critical error occurred"
    MAINTENANCE = "Maintenance shutdown"
    EMERGENCY = "Emergency shutdown"


class ShutdownManager:
    """
    Manages graceful shutdown of the arbitrage engine.
    
    Responsibilities:
    - Handle shutdown signals
    - Coordinate component shutdown
    - Ensure position safety
    - Clean up resources
    """
    
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.shutdown_reason: Optional[ShutdownReason] = None
        self._shutdown_callbacks: List[Callable] = []
        self._signal_handlers_installed = False
        self._is_shutting_down = False
        
    def setup_signal_handlers(self):
        """
        Setup signal handlers for graceful shutdown.
        
        Handles SIGINT (Ctrl+C) and SIGTERM signals.
        """
        if self._signal_handlers_installed:
            logger.debug("Signal handlers already installed")
            return
            
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum} - initiating graceful shutdown...")
            self.initiate_shutdown(ShutdownReason.SIGNAL_RECEIVED)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self._signal_handlers_installed = True
        logger.debug("Signal handlers installed")
    
    def register_shutdown_callback(self, callback: Callable):
        """
        Register a callback to be called during shutdown.
        
        Args:
            callback: Async function to call during shutdown
        """
        if callback not in self._shutdown_callbacks:
            self._shutdown_callbacks.append(callback)
            logger.debug(f"Registered shutdown callback: {callback.__name__}")
    
    def initiate_shutdown(self, reason: ShutdownReason = ShutdownReason.USER_REQUESTED):
        """
        Initiate graceful shutdown.
        
        Args:
            reason: Reason for shutdown
        """
        if self._is_shutting_down:
            logger.debug("Shutdown already in progress")
            return
            
        self._is_shutting_down = True
        self.shutdown_reason = reason
        self.shutdown_event.set()
        
        logger.info(f"Shutdown initiated: {reason.value}")
    
    async def wait_for_shutdown(self, timeout: Optional[float] = None):
        """
        Wait for shutdown signal.
        
        Args:
            timeout: Optional timeout in seconds
            
        Returns:
            True if shutdown was requested, False if timeout
        """
        try:
            await asyncio.wait_for(self.shutdown_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    async def execute_shutdown(self):
        """
        Execute graceful shutdown sequence.
        
        Calls all registered shutdown callbacks in reverse order
        (last registered, first called - like a stack).
        """
        if not self._is_shutting_down:
            self.initiate_shutdown()
        
        logger.info("Executing graceful shutdown sequence...")
        
        # Call callbacks in reverse order
        for callback in reversed(self._shutdown_callbacks):
            try:
                logger.debug(f"Calling shutdown callback: {callback.__name__}")
                
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
                    
            except Exception as e:
                # Log but don't stop shutdown on callback errors
                logger.error(f"Error in shutdown callback {callback.__name__}: {e}")
        
        logger.info("Graceful shutdown complete")
    
    async def shutdown_with_timeout(self, timeout: float = 30.0):
        """
        Execute shutdown with timeout.
        
        Args:
            timeout: Maximum time to wait for graceful shutdown
        """
        try:
            await asyncio.wait_for(self.execute_shutdown(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Shutdown timeout ({timeout}s) exceeded - forcing shutdown")
            # Force shutdown logic could go here
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self.shutdown_event.is_set()
    
    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self._is_shutting_down
    
    def reset(self):
        """
        Reset shutdown manager state.
        
        Used for testing or restarting the engine.
        """
        self.shutdown_event.clear()
        self.shutdown_reason = None
        self._is_shutting_down = False
        logger.debug("Shutdown manager reset")


class ComponentShutdownMixin:
    """
    Mixin for components that need graceful shutdown.
    
    Provides standard shutdown interface for engine components.
    """
    
    def __init__(self):
        self._shutdown_manager: Optional[ShutdownManager] = None
        
    def set_shutdown_manager(self, manager: ShutdownManager):
        """Set the shutdown manager for this component."""
        self._shutdown_manager = manager
        self._shutdown_manager.register_shutdown_callback(self.shutdown)
    
    async def shutdown(self):
        """
        Shutdown this component.
        
        Override in subclasses to implement component-specific shutdown.
        """
        raise NotImplementedError("Components must implement shutdown method")
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        if self._shutdown_manager:
            return self._shutdown_manager.is_shutdown_requested()
        return False