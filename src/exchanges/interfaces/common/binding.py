from abc import ABC
from typing import Generic, Dict, Callable, Any, Awaitable, Union

from exchanges.interfaces.ws.interfaces.common import T


class BoundHandlerInterface(Generic[T]):
    """
    Generic interface for binding handlers to channel types.
    
    ENHANCED: Now supports both enum-based (legacy) and string-based (new) channel binding.
    This enables external adapter patterns while maintaining backward compatibility.
    """

    def __init__(self):
        # Legacy enum-based handlers
        self._bound_handlers: Dict[T, Callable[[Any], Awaitable[None]]] = {}
        
        # New string-based handlers
        self._string_handlers: Dict[str, Callable[[Any], Awaitable[None]]] = {}
        
        # Mapping between enums and strings for compatibility
        self._enum_to_string: Dict[T, str] = {}

    def bind(self, channel: Union[T, str], handler: Callable[[Any], Awaitable[None]]) -> None:
        """
        Bind a handler function to a channel.

        Args:
            channel: The channel (enum type for backward compatibility, or string for new approach)
            handler: Async function to handle messages for this channel
        """
        channel_str = self._normalize_channel_to_string(channel)
        print(f"Binding handler to channel: {channel_str}")
        if isinstance(channel, str):
            # New string-based binding
            self._string_handlers[channel] = handler
            if hasattr(self, 'logger'):
                self.logger.debug(f"Bound handler for string channel: {channel_str}")
        else:
            # Legacy enum-based binding
            self._bound_handlers[channel] = handler
            
            # Also create string mapping for unified access
            self._string_handlers[channel_str] = handler
            self._enum_to_string[channel] = channel_str
            
            if hasattr(self, 'logger'):
                self.logger.debug(f"Bound handler for enum channel: {channel.name} -> {channel_str}")

    def unbind(self, channel: Union[T, str]) -> bool:
        """
        Unbind handler from channel.

        Args:
            channel: Channel identifier (enum or string)

        Returns:
            True if handler was found and removed, False otherwise
        """
        if isinstance(channel, str):
            # String-based unbinding
            if channel in self._string_handlers:
                del self._string_handlers[channel]
                
                # Remove corresponding enum mapping if exists
                enum_keys_to_remove = [k for k, v in self._enum_to_string.items() if v == channel]
                for key in enum_keys_to_remove:
                    if key in self._bound_handlers:
                        del self._bound_handlers[key]
                    del self._enum_to_string[key]
                
                return True
            return False
        else:
            # Enum-based unbinding
            if channel in self._bound_handlers:
                del self._bound_handlers[channel]
                
                # Remove corresponding string mapping
                if channel in self._enum_to_string:
                    channel_str = self._enum_to_string[channel]
                    if channel_str in self._string_handlers:
                        del self._string_handlers[channel_str]
                    del self._enum_to_string[channel]
                
                return True
            return False

    def _normalize_channel_to_string(self, channel: T) -> str:
        """
        Convert enum channel to normalized string.

        Args:
            channel: Enum channel

        Returns:
            Normalized string representation
        """
        if hasattr(channel, 'name'):
            return channel.name.lower()
        elif hasattr(channel, 'value'):
            return str(channel.value)
        else:
            return str(channel)

    def _get_bound_handler(self, channel: Union[T, str]) -> Callable[[Any], Awaitable[None]]:
        """
        Get bound handler for channel.

        Args:
            channel: The channel (enum or string)

        Returns:
            The bound handler function or no-op if not bound
        """
        handler = None
        
        if isinstance(channel, str):
            # String-based lookup
            handler = self._string_handlers.get(channel)
        else:
            # Enum-based lookup (legacy)
            handler = self._bound_handlers.get(channel)
            
            # Fallback to string lookup for mixed usage
            if handler is None:
                channel_str = self._normalize_channel_to_string(channel)
                handler = self._string_handlers.get(channel_str)

        if handler is not None:
            return handler

        # Return no-op handler if not bound
        async def _noop(*args, **kwargs) -> None:
            if hasattr(self, 'logger'):
                channel_str = channel if isinstance(channel, str) else self._normalize_channel_to_string(channel)
                self.logger.debug(f"No handler bound for channel: {channel_str}")

        return _noop

    async def _exec_bound_handler(self, channel: Union[T, str], *args, **kwargs) -> None:
        """
        Execute the bound handler for a channel.

        Args:
            channel: The channel (enum or string)
            *args: Arguments to pass to handler
            **kwargs: Keyword arguments to pass to handler
        """
        handler = self._get_bound_handler(channel)
        try:
            return await handler(*args, **kwargs)
        except Exception as e:
            if hasattr(self, 'logger'):
                channel_str = channel if isinstance(channel, str) else self._normalize_channel_to_string(channel)
                self.logger.error("Error executing bound handler",
                                channel=channel_str,
                                error_type=type(e).__name__,
                                error_message=str(e))

    def is_bound(self, channel: Union[T, str]) -> bool:
        """
        Check if a handler is bound to a channel.

        Args:
            channel: Channel identifier (enum or string)

        Returns:
            True if handler is bound, False otherwise
        """
        if isinstance(channel, str):
            return channel in self._string_handlers
        else:
            # Check both enum and string mappings
            if channel in self._bound_handlers:
                return True
            channel_str = self._normalize_channel_to_string(channel)
            return channel_str in self._string_handlers

    def get_bound_channels(self) -> list[str]:
        """
        Get list of all bound channel names as strings.

        Returns:
            List of channel names that have bound handlers
        """
        return list(self._string_handlers.keys())

    def get_handler_count(self) -> int:
        """
        Get count of bound handlers.

        Returns:
            Number of unique bound handlers
        """
        return len(self._string_handlers)

    def clear_handlers(self) -> None:
        """Clear all bound handlers."""
        self._bound_handlers.clear()
        self._string_handlers.clear()
        self._enum_to_string.clear()
        
        if hasattr(self, 'logger'):
            self.logger.debug("All handlers cleared")
