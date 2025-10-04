import asyncio

from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, get_logger
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from .exchange_factory import get_composite_implementation
from typing import List, Optional, Awaitable, Callable, Dict
from exchanges.adapters import BindedEventHandlersAdapter
from exchanges.structs import Order, AssetBalance, BookTicker, Position, ExchangeEnum

_DUAL_CLIENTS: Dict[ExchangeEnum, 'DualExchange']  = {}


class DualExchange:
    def __init__(self, config: ExchangeConfig, logger: HFTLoggerInterface = None):
        """
        Initialize dual exchange with public and private composites.
        Args:
            config: Exchange configuration
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        self.config = config
        self.logger = logger or get_logger(f'dual_exchange.{config.name.lower()}')
        self.private = get_composite_implementation(config, is_private=True)
        self.public = get_composite_implementation(config, is_private=False)
        self.adapter_private = BindedEventHandlersAdapter(self.logger).bind_to_exchange(self.private)
        self.adapter_public = BindedEventHandlersAdapter(self.logger).bind_to_exchange(self.public)

    @staticmethod
    def get_instance(config: ExchangeConfig, logger: HFTLoggerInterface = None) -> 'DualExchange':
        """Get or create a singleton DualExchange instance per exchange enum."""
        if config.exchange_enum not in _DUAL_CLIENTS:
            _DUAL_CLIENTS[config.exchange_enum] = DualExchange(config, logger)
        return _DUAL_CLIENTS[config.exchange_enum]


    async def initialize(self, symbols=None, public_channels: List[PublicWebsocketChannelType] = None,
                         private_channels: List[PrivateWebsocketChannelType] = None) -> None:
        """
        Initialize both public and private exchanges.
        Args:
            symbols: Optional list of symbols to track
            channels: Optional list of WebSocket channels to subscribe to
            public_channels: Optional list of public WebSocket channels
            private_channels: Optional list of private WebSocket channels
        """
        await asyncio.gather(*[self.public.initialize(symbols, public_channels),
                              self.private.initialize(None, private_channels)])
        # deferred symbol info
        self.private.set_symbol_info(self.public.symbols_info)

    async def subscribe_symbols(self, symbols: List) -> None:
        """Subscribe to symbols on both public and private exchanges."""
        await asyncio.gather(*[self.public.subscribe_symbols(symbols),
                              self.private.subscribe_symbols(symbols)])

    async def unsubscribe_symbols(self, symbols: List) -> None:
        """Unsubscribe from symbols on both public and private exchanges."""
        await asyncio.gather(*[self.public.unsubscribe_symbols(symbols),
                              self.private.unsubscribe_symbols(symbols)])

    async def bind_handlers(self,
                           on_book_ticker: Optional[Callable[[BookTicker], Awaitable[None]]]=None,
                           on_order: Optional[Callable[[Order], Awaitable[None]]]=None,
                           on_balance: Optional[Callable[[AssetBalance], Awaitable[None]]]=None,
                           on_position: Optional[Callable[[Position], Awaitable[None]]]=None) -> None:
        """Add event handlers to both public and private exchanges."""
        on_book_ticker and self.adapter_public.bind(PublicWebsocketChannelType.BOOK_TICKER, on_book_ticker)
        on_order and self.adapter_private.bind(PrivateWebsocketChannelType.ORDER, on_order)
        on_balance and self.adapter_private.bind(PrivateWebsocketChannelType.BALANCE, on_balance)
        on_position and self.adapter_private.bind(PrivateWebsocketChannelType.POSITION, on_position)

    async def unbind_handlers(self,
                             on_book_ticker: Optional[Callable[[BookTicker], Awaitable[None]]]=None,
                             on_order: Optional[Callable[[Order], Awaitable[None]]]=None,
                             on_balance: Optional[Callable[[AssetBalance], Awaitable[None]]]=None,
                             on_position: Optional[Callable[[Position], Awaitable[None]]]=None) -> None:
        """Remove event handlers from both public and private exchanges."""
        on_book_ticker and self.adapter_public.unbind(PublicWebsocketChannelType.BOOK_TICKER, on_book_ticker)
        on_order and self.adapter_private.unbind(PrivateWebsocketChannelType.ORDER, on_order)
        on_balance and self.adapter_private.unbind(PrivateWebsocketChannelType.BALANCE, on_balance)
        on_position and self.adapter_private.unbind(PrivateWebsocketChannelType.POSITION, on_position)

    async def close(self) -> None:
        """Close both public and private exchanges."""
        await asyncio.gather(*[self.public.close(), self.private.close()])

    @classmethod
    async def cleanup_all(cls) -> None:
        """Close all DualExchange instances and clear singleton registry."""
        close_tasks = []
        for instance in _DUAL_CLIENTS.values():
            close_tasks.append(instance.close())
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # Clear singleton registry
        _DUAL_CLIENTS.clear()
