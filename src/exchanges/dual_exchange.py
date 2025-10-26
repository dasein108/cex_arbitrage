import asyncio

from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, get_logger
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from .exchange_factory import get_composite_implementation
from typing import List, Optional, Awaitable, Callable, Dict
from exchanges.adapters import BindedEventHandlersAdapter
from exchanges.structs import Order, AssetBalance, BookTicker, Position, ExchangeEnum, Symbol, AssetName
from .interfaces.composite import BasePrivateComposite, BasePublicComposite

_DUAL_CLIENTS: Dict[ExchangeEnum, 'DualExchange'] = {}


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
        self.private: BasePrivateComposite = get_composite_implementation(config, is_private=True, balance_sync_interval=30)
        self.public: BasePublicComposite = get_composite_implementation(config, is_private=False,
                                                                        balance_sync_interval=30)
        self.adapter_private = BindedEventHandlersAdapter(self.logger).bind_to_exchange(self.private)
        self.adapter_public = BindedEventHandlersAdapter(self.logger).bind_to_exchange(self.public)

        self.name = config.name
        self.is_futures = config.is_futures
        self.exchange_enum = config.exchange_enum

    @staticmethod
    def get_instance(config: ExchangeConfig, logger: HFTLoggerInterface = None) -> 'DualExchange':
        """Get or create a singleton DualExchange instance per exchange enum."""
        if config.exchange_enum not in _DUAL_CLIENTS:
            _DUAL_CLIENTS[config.exchange_enum] = DualExchange(config, logger)
        return _DUAL_CLIENTS[config.exchange_enum]

    @property
    def is_connected(self) -> bool:
        """Check if both public and private exchanges are connected."""
        return self.public.is_connected and self.private.is_connected

    async def force_refresh(self):
        """Force refresh both public and private exchanges."""
        await asyncio.gather(self.public.refresh_exchange_data(), self.private.refresh_exchange_data())

    @property
    def balances(self) -> Dict[AssetName,AssetBalance]:
        return self.private.balances

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
        # symbol info is critical for position qty from contracts calculation

        symbols_info = await self.public.load_symbols_info()

        await asyncio.gather(*[self.public.initialize(symbols, public_channels),
                               self.private.initialize(symbols_info, private_channels)])



    async def subscribe_symbols(self, symbols: List) -> None:
        """Subscribe to symbols on both public and private exchanges."""
        await asyncio.gather(*[self.public.add_symbol(s) for s in symbols])

    async def unsubscribe_symbols(self, symbols: List) -> None:
        """Unsubscribe from symbols on both public and private exchanges."""
        await asyncio.gather(*[self.public.remove_symbol(s) for s in symbols])

    async def bind_handlers(self,
                            on_book_ticker: Optional[Callable[[BookTicker], Awaitable[None]]] = None,
                            on_order: Optional[Callable[[Order], Awaitable[None]]] = None,
                            on_balance: Optional[Callable[[AssetBalance], Awaitable[None]]] = None,
                            on_position: Optional[Callable[[Position], Awaitable[None]]] = None) -> None:
        """Add event handlers to both public and private exchanges."""
        on_book_ticker and self.adapter_public.bind(PublicWebsocketChannelType.BOOK_TICKER, on_book_ticker)
        on_order and self.adapter_private.bind(PrivateWebsocketChannelType.ORDER, on_order)
        on_balance and self.adapter_private.bind(PrivateWebsocketChannelType.BALANCE, on_balance)
        on_position and self.adapter_private.bind(PrivateWebsocketChannelType.POSITION, on_position)

    async def unbind_handlers(self,
                              on_book_ticker: Optional[Callable[[BookTicker], Awaitable[None]]] = None,
                              on_order: Optional[Callable[[Order], Awaitable[None]]] = None,
                              on_balance: Optional[Callable[[AssetBalance], Awaitable[None]]] = None,
                              on_position: Optional[Callable[[Position], Awaitable[None]]] = None) -> None:
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

    # def round_base_to_contracts(self, symbol: Symbol, base_quantity: float) -> float:
    #     """Convert base currency quantity to contract quantity."""
    #     if hasattr(self.private, 'round_base_to_contracts'):
    #         return self.private.round_base_to_contracts(symbol, base_quantity)
    #
    #     raise NotImplemented(f"Not implemented - round_base_to_contracts for {self.name}")
