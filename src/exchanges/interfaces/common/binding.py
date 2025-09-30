from abc import ABC
from typing import Generic, Dict, Callable, Any, Awaitable

from exchanges.interfaces.ws.interfaces.common import T


class BoundHandlerInterface(Generic[T]):
    """Generic interface for binding handlers to channel types."""

    def __init__(self):
        self._bound_handlers: Dict[T, Callable[[Any], Awaitable[None]]] = {}

    def bind(self, channel: T, handler: Callable[[Any], Awaitable[None]]) -> None:
        """Bind a handler function to a WebSocket channel.

        Args:
            channel: The channel type to bind
            handler: Async function to handle messages for this channel
        """
        self._bound_handlers[channel] = handler
        if hasattr(self, 'logger'):
            self.logger.debug(f"Bound handler for channel: {channel.name}")

    def _get_bound_handler(self, channel: T) -> Callable[[Any], Awaitable[None]]:
        """Get bound handler for channel or raise exception if not bound.

        Args:
            channel: The channel type

        Returns:
            The bound handler function

        Raises:
            ValueError: If no handler is bound for the channel
        """
        if channel not in self._bound_handlers:
            raise ValueError(f"No handler bound for channel {channel.name} (value: {channel.value}). "
                           f"Use bind({channel.name}, your_handler_function) to bind a handler.")
        return self._bound_handlers[channel]

    async def _exec_bound_handler(self, channel: T, *args, **kwargs) -> None:
        """Execute the bound handler for a channel with the given message.

        Args:
            channel: The channel type
            message: The message to pass to the handler
        """
        handler = self._get_bound_handler(channel)
        return await handler(*args, **kwargs)
