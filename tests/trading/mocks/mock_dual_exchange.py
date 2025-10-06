"""
Mock Dual Exchange for Testing

Provides a mock implementation of DualExchange that combines public and private
exchange functionality for comprehensive trading task testing.
"""

import asyncio
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from exchanges.dual_exchange import DualExchange
from config.structs import ExchangeConfig
from exchanges.structs import Symbol, ExchangeEnum
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

from .mock_public_exchange import MockPublicExchange
from .mock_private_exchange import MockPrivateExchange


class MockDualExchange:
    """Mock implementation of DualExchange for testing.
    
    Combines mock public and private exchanges to provide a complete
    testing environment for dual exchange trading tasks.
    """
    
    def __init__(self, config: ExchangeConfig, logger: HFTLoggerInterface = None):
        """Initialize mock dual exchange."""
        self.config = config
        self.logger = logger
        self.name = config.name if hasattr(config, 'name') else str(config.exchange_enum)
        self.is_futures = getattr(config, 'is_futures', False)
        self.exchange_enum = config.exchange_enum
        
        # Create mock public and private exchanges
        self.public = MockPublicExchange(config.exchange_enum)
        self.private = MockPrivateExchange(config.exchange_enum)
        
        # Mock adapters (not used in testing but expected by interface)
        self.adapter_private = MagicMock()
        self.adapter_public = MagicMock()
        
        # Track initialization
        self._is_initialized = False
    
    @staticmethod
    def get_instance(config: ExchangeConfig, logger: HFTLoggerInterface = None) -> 'MockDualExchange':
        """Get or create a mock instance (matches DualExchange interface)."""
        return MockDualExchange(config, logger)
    
    async def initialize(self, symbols: List[Symbol] = None, 
                        public_channels: List[PublicWebsocketChannelType] = None,
                        private_channels: List[PrivateWebsocketChannelType] = None) -> None:
        """Initialize both public and private mock exchanges."""
        if symbols is None:
            symbols = []
        
        # Initialize both exchanges
        await self.public.initialize(symbols, public_channels)
        await self.private.initialize(symbols, private_channels)
        
        self._is_initialized = True
    
    async def close(self):
        """Close both exchanges."""
        await self.public.close()
        await self.private.close()
        self._is_initialized = False
    
    def is_connected(self) -> bool:
        """Check if both exchanges are connected."""
        return self.public.is_connected() and self.private.is_connected()
    
    def was_initialized(self) -> bool:
        """Check if the dual exchange was initialized."""
        return self._is_initialized
    
    # Convenience methods for test control
    def set_book_ticker(self, symbol: Symbol, bid_price: float, ask_price: float,
                       bid_quantity: float = 1.0, ask_quantity: float = 1.0):
        """Set book ticker for testing price movements."""
        self.public.set_book_ticker(symbol, bid_price, ask_price, bid_quantity, ask_quantity)
    
    def update_price(self, symbol: Symbol, new_price: float, spread: float = 1.0):
        """Update prices for testing price movement scenarios."""
        self.public.update_price(symbol, new_price, spread)
    
    def set_symbol_info(self, symbol: Symbol, **kwargs):
        """Update symbol info for testing different exchange parameters."""
        self.public.set_symbol_info(symbol, **kwargs)
    
    def set_order_fill_behavior(self, order_id: str, fill_quantity: float):
        """Set how much an order should be filled (for testing partial fills)."""
        self.private.set_order_fill_behavior(order_id, fill_quantity)
    
    def set_should_fail_orders(self, should_fail: bool):
        """Control whether order placement should fail (for error testing)."""
        self.private.set_should_fail_orders(should_fail)
    
    def set_should_fail_cancellation(self, should_fail: bool):
        """Control whether order cancellation should fail (for error testing)."""
        self.private.set_should_fail_cancellation(should_fail)
    
    def simulate_order_fill(self, order_id: str, fill_quantity: float):
        """Simulate an order getting filled during execution."""
        self.private.simulate_order_fill(order_id, fill_quantity)
    
    def set_futures_mode(self, is_futures: bool):
        """Set whether this exchange operates in futures mode."""
        self.is_futures = is_futures
        self.private.set_futures_mode(is_futures)
    
    # Verification methods for tests
    def get_placed_orders(self):
        """Get all orders that were placed."""
        return self.private.get_placed_orders()
    
    def get_cancelled_orders(self):
        """Get all order IDs that were cancelled."""
        return self.private.get_cancelled_orders()
    
    def get_order_count(self) -> int:
        """Get total number of orders placed."""
        return self.private.get_order_count()
    
    def get_order_by_id(self, order_id: str):
        """Get order by ID."""
        return self.private.get_order_by_id(order_id)
    
    def reset_tracking(self):
        """Reset tracking for new test."""
        self.private.reset_tracking()
    
    def round_base_to_contracts(self, symbol: Symbol, quantity: float) -> float:
        """Round quantity to contract size (for futures testing)."""
        return self.private.round_base_to_contracts(symbol, quantity)


# Global registry for mock dual exchanges (matches DualExchange pattern)
_MOCK_DUAL_CLIENTS: Dict[ExchangeEnum, MockDualExchange] = {}


def get_mock_dual_exchange_instance(config: ExchangeConfig, logger: HFTLoggerInterface = None) -> MockDualExchange:
    """Get or create a singleton MockDualExchange instance per exchange enum."""
    if config.exchange not in _MOCK_DUAL_CLIENTS:
        _MOCK_DUAL_CLIENTS[config.exchange] = MockDualExchange(config, logger)
    return _MOCK_DUAL_CLIENTS[config.exchange]


def clear_mock_dual_exchange_registry():
    """Clear the mock registry (for test cleanup)."""
    global _MOCK_DUAL_CLIENTS
    _MOCK_DUAL_CLIENTS.clear()