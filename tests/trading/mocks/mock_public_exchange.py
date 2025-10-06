"""
Mock Public Exchange for Testing Delta Neutral Tasks

Provides a realistic but controllable mock implementation of BasePublicComposite
for testing trading task state machines without actual exchange connections.
"""

import asyncio
from typing import Dict, List, Optional
from unittest.mock import AsyncMock

from exchanges.interfaces.composite.base_public_composite import BasePublicComposite
from exchanges.structs import Symbol, BookTicker, SymbolInfo, ExchangeEnum
from exchanges.structs.common import AssetName
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType


class MockPublicExchange(BasePublicComposite):
    """Mock public exchange for testing trading tasks.
    
    Provides controllable market data simulation for testing state machine logic
    without real exchange dependencies. Supports realistic trading scenarios.
    """
    
    def __init__(self, exchange_enum: ExchangeEnum):
        # Initialize without calling super().__init__ to avoid real exchange setup
        self.exchange = exchange_enum
        self._book_ticker: Dict[Symbol, BookTicker] = {}
        self._symbols_info: Dict[Symbol, SymbolInfo] = {}
        self._is_connected = False
        
        # Mock implementation tracking
        self._initialize_called = False
        self._close_called = False
    
    @property
    def symbols_info(self) -> Dict[Symbol, SymbolInfo]:
        """Get symbols info (property to match interface)."""
        return self._symbols_info
        
    async def initialize(self, symbols: List[Symbol], 
                        public_channels: Optional[List[PublicWebsocketChannelType]] = None):
        """Initialize mock with provided symbols."""
        self._initialize_called = True
        self._is_connected = True
        
        # Set up default symbol info for each symbol
        for symbol in symbols:
            self._symbols_info[symbol] = SymbolInfo(
                symbol=symbol,
                base_precision=8,
                quote_precision=2,
                min_base_quantity=0.001,
                min_quote_quantity=10.0,
                maker_commission=0.001,
                taker_commission=0.002,
                tick=0.01,
                step=0.001,
                is_futures=False
            )
            
            # Set up default book ticker
            self._book_ticker[symbol] = BookTicker(
                symbol=symbol,
                bid_price=50000.0,
                bid_quantity=1.0,
                ask_price=50001.0,
                ask_quantity=1.0,
                timestamp=1640995200000  # Fixed timestamp for testing
            )
    
    async def close(self):
        """Close mock exchange."""
        self._close_called = True
        self._is_connected = False
    
    def is_connected(self) -> bool:
        """Check if mock exchange is connected."""
        return self._is_connected
    
    # Methods for test control
    def set_book_ticker(self, symbol: Symbol, bid_price: float, ask_price: float,
                       bid_quantity: float = 1.0, ask_quantity: float = 1.0):
        """Set book ticker for testing price movements."""
        self._book_ticker[symbol] = BookTicker(
            symbol=symbol,
            bid_price=bid_price,
            bid_quantity=bid_quantity,
            ask_price=ask_price,
            ask_quantity=ask_quantity,
            timestamp=1640995200000
        )
    
    def update_price(self, symbol: Symbol, new_price: float, spread: float = 1.0):
        """Update prices for testing price movement scenarios."""
        bid_price = new_price - spread/2
        ask_price = new_price + spread/2
        self.set_book_ticker(symbol, bid_price, ask_price)
    
    def set_symbol_info(self, symbol: Symbol, **kwargs):
        """Update symbol info for testing different exchange parameters."""
        current_info = self._symbols_info.get(symbol)
        if current_info:
            # Create new SymbolInfo with updated fields
            info_dict = {
                'symbol': symbol,
                'base_precision': kwargs.get('base_precision', current_info.base_precision),
                'quote_precision': kwargs.get('quote_precision', current_info.quote_precision),
                'min_base_quantity': kwargs.get('min_base_quantity', current_info.min_base_quantity),
                'min_quote_quantity': kwargs.get('min_quote_quantity', current_info.min_quote_quantity),
                'maker_commission': kwargs.get('maker_commission', current_info.maker_commission),
                'taker_commission': kwargs.get('taker_commission', current_info.taker_commission),
                'tick': kwargs.get('tick', current_info.tick),
                'step': kwargs.get('step', current_info.step),
                'is_futures': kwargs.get('is_futures', current_info.is_futures)
            }
            self._symbols_info[symbol] = SymbolInfo(**info_dict)
    
    # Verification methods for tests
    def was_initialized(self) -> bool:
        """Check if initialize was called (for test verification)."""
        return self._initialize_called
    
    def was_closed(self) -> bool:
        """Check if close was called (for test verification)."""
        return self._close_called