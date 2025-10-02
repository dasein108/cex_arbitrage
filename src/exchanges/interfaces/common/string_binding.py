"""
String-based BoundHandlerInterface

Flexible binding interface using string literals instead of enum dependencies.
Provides backward compatibility while enabling external adapter patterns.
"""

from abc import ABC
from typing import Dict, Callable, Any, Awaitable, Union, Optional


class StringBoundHandlerInterface:
    """
    String-based interface for binding handlers to channels.
    
    This interface replaces enum-based binding with flexible string literals,
    enabling external adapters and reducing dependency coupling. Provides
    backward compatibility with existing enum-based code.
    
    Features:
    - String-based channel identification
    - Backward compatibility with enums
    - Support for external adapters
    - Flexible channel naming
    - Error handling for unbound channels
    """

    def __init__(self):
        """Initialize string-based handler interface."""
        self._bound_handlers: Dict[str, Callable[[Any], Awaitable[None]]] = {}
        self._channel_mapping: Dict[Any, str] = {}  # For enum compatibility

    def bind(self, channel: Union[str, Any], handler: Callable[[Any], Awaitable[None]]) -> None:
        """
        Bind a handler function to a channel.

        Args:
            channel: Channel identifier (string or enum for backward compatibility)
            handler: Async function to handle messages for this channel

        Raises:
            ValueError: If handler is not callable
        """
        if not callable(handler):
            raise ValueError("Handler must be callable")

        # Convert channel to string if it's an enum
        channel_str = self._normalize_channel(channel)
        
        # Store the handler
        self._bound_handlers[channel_str] = handler
        
        # Track enum mapping for backward compatibility
        if hasattr(channel, 'name') and hasattr(channel, 'value'):
            self._channel_mapping[channel] = channel_str

        if hasattr(self, 'logger'):
            self.logger.debug(f"Bound handler for channel: {channel_str}")

    def unbind(self, channel: Union[str, Any]) -> bool:
        """
        Unbind handler from channel.

        Args:
            channel: Channel identifier (string or enum)

        Returns:
            True if handler was found and removed, False otherwise
        """
        channel_str = self._normalize_channel(channel)
        
        if channel_str in self._bound_handlers:
            del self._bound_handlers[channel_str]
            
            # Remove from enum mapping if present
            enum_keys_to_remove = [k for k, v in self._channel_mapping.items() if v == channel_str]
            for key in enum_keys_to_remove:
                del self._channel_mapping[key]
            
            if hasattr(self, 'logger'):
                self.logger.debug(f"Unbound handler for channel: {channel_str}")
            return True
        
        return False

    def _normalize_channel(self, channel: Union[str, Any]) -> str:
        """
        Normalize channel to string format.

        Args:
            channel: Channel identifier (string or enum)

        Returns:
            Normalized string channel identifier
        """
        if isinstance(channel, str):
            return channel
        
        # Handle enum types
        if hasattr(channel, 'name'):
            # Use enum name for consistent string representation
            return channel.name.lower()
        elif hasattr(channel, 'value'):
            # Fallback to enum value
            return str(channel.value)
        else:
            # Convert anything else to string
            return str(channel)

    def _get_bound_handler(self, channel: Union[str, Any]) -> Callable[[Any], Awaitable[None]]:
        """
        Get bound handler for channel.

        Args:
            channel: Channel identifier (string or enum)

        Returns:
            The bound handler function, or no-op if not bound
        """
        channel_str = self._normalize_channel(channel)
        
        if channel_str in self._bound_handlers:
            return self._bound_handlers[channel_str]
        
        # Return no-op handler if not bound
        async def _noop(*args, **kwargs) -> None:
            if hasattr(self, 'logger'):
                self.logger.debug(f"No handler bound for channel: {channel_str}")
        
        return _noop

    async def _exec_bound_handler(self, channel: Union[str, Any], *args, **kwargs) -> None:
        """
        Execute the bound handler for a channel.

        Args:
            channel: Channel identifier (string or enum)
            *args: Arguments to pass to handler
            **kwargs: Keyword arguments to pass to handler
        """
        handler = self._get_bound_handler(channel)
        try:
            await handler(*args, **kwargs)
        except Exception as e:
            if hasattr(self, 'logger'):
                channel_str = self._normalize_channel(channel)
                self.logger.error("Error executing bound handler",
                                channel=channel_str,
                                error_type=type(e).__name__,
                                error_message=str(e))

    def is_bound(self, channel: Union[str, Any]) -> bool:
        """
        Check if a handler is bound to a channel.

        Args:
            channel: Channel identifier (string or enum)

        Returns:
            True if handler is bound, False otherwise
        """
        channel_str = self._normalize_channel(channel)
        return channel_str in self._bound_handlers

    def get_bound_channels(self) -> list[str]:
        """
        Get list of all bound channel names.

        Returns:
            List of channel names that have bound handlers
        """
        return list(self._bound_handlers.keys())

    def get_handler_count(self) -> int:
        """
        Get count of bound handlers.

        Returns:
            Number of bound handlers
        """
        return len(self._bound_handlers)

    def clear_handlers(self) -> None:
        """Clear all bound handlers."""
        self._bound_handlers.clear()
        self._channel_mapping.clear()
        
        if hasattr(self, 'logger'):
            self.logger.debug("All handlers cleared")


class BackwardCompatibleBoundHandlerInterface(StringBoundHandlerInterface):
    """
    Backward compatible interface that supports both old enum-based and new string-based binding.
    
    This class extends StringBoundHandlerInterface to provide complete backward compatibility
    with existing enum-based code while enabling new string-based patterns.
    """

    def bind_enum(self, channel_enum, handler: Callable[[Any], Awaitable[None]]) -> None:
        """
        Bind handler using enum channel (backward compatibility).

        Args:
            channel_enum: Enum channel type
            handler: Async handler function
        """
        self.bind(channel_enum, handler)

    def bind_string(self, channel: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        """
        Bind handler using string channel (new approach).

        Args:
            channel: String channel identifier
            handler: Async handler function
        """
        self.bind(channel, handler)

    def get_enum_mapping(self) -> Dict[Any, str]:
        """
        Get mapping of enums to string channels.

        Returns:
            Dictionary mapping enum objects to string channel names
        """
        return self._channel_mapping.copy()


# Alias for easier migration
BoundHandlerInterface = BackwardCompatibleBoundHandlerInterface