"""
Dual Exchange Mock System for Testing Trading Tasks

Provides a complete dual exchange mock system that simulates realistic trading
scenarios across two exchanges. Designed for testing delta neutral and other
dual exchange trading strategies.
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from unittest.mock import patch, MagicMock

from exchanges.structs import Symbol, ExchangeEnum, Side
from exchanges.structs.common import AssetName
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig

from .mock_public_exchange import MockPublicExchange
from .mock_private_exchange import MockPrivateExchange
from .mock_dual_exchange import MockDualExchange, get_mock_dual_exchange_instance, clear_mock_dual_exchange_registry


class DualExchangeMockSystem:
    """Complete dual exchange mock system for testing trading tasks.
    
    Provides realistic simulation of trading across two exchanges with controllable
    market conditions, order behavior, and error scenarios. Designed specifically
    for testing delta neutral and arbitrage strategies.
    """
    
    def __init__(self, 
                 buy_exchange: ExchangeEnum = ExchangeEnum.GATEIO,
                 sell_exchange: ExchangeEnum = ExchangeEnum.MEXC):
        """Initialize dual exchange mock system.
        
        Args:
            buy_exchange: Exchange enum for buy side
            sell_exchange: Exchange enum for sell side
        """
        self.buy_exchange_enum = buy_exchange
        self.sell_exchange_enum = sell_exchange
        
        # Mock exchanges for each side - support both architectures
        self.public_exchanges = {
            Side.BUY: MockPublicExchange(buy_exchange),
            Side.SELL: MockPublicExchange(sell_exchange)
        }
        
        self.private_exchanges = {
            Side.BUY: MockPrivateExchange(buy_exchange),
            Side.SELL: MockPrivateExchange(sell_exchange)
        }
        
        # Mock dual exchanges for unified architecture
        self.dual_exchanges = {
            Side.BUY: None,
            Side.SELL: None
        }
        
        # Tracking for test verification
        self._active_patches: List = []
        self._is_setup = False
        
    async def setup(self, symbols: List[Symbol]):
        """Setup mock exchanges with given symbols."""
        if self._is_setup:
            return
        
        # Initialize all exchanges
        init_tasks = []
        
        for side in [Side.BUY, Side.SELL]:
            init_tasks.append(self.public_exchanges[side].initialize(symbols))
            init_tasks.append(self.private_exchanges[side].initialize(symbols))
        
        await asyncio.gather(*init_tasks)
        
        # Create dual exchanges for unified architecture  
        from config.structs import ExchangeConfig, ExchangeCredentials
        from exchanges.structs.types import ExchangeName
        from unittest.mock import MagicMock
        
        for side, exchange_enum in [(Side.BUY, self.buy_exchange_enum), (Side.SELL, self.sell_exchange_enum)]:
            config = ExchangeConfig(
                name=ExchangeName(exchange_enum.value),
                credentials=ExchangeCredentials(api_key="mock", secret_key="mock"),
                base_url="https://mock.exchange.com",
                websocket_url="wss://mock.exchange.com"
            )
            dual_exchange = MockDualExchange(config)
            dual_exchange.public = self.public_exchanges[side]
            dual_exchange.private = self.private_exchanges[side]
            self.dual_exchanges[side] = dual_exchange
        
        self._is_setup = True
    
    async def teardown(self):
        """Teardown mock exchanges and clean up patches."""
        if not self._is_setup:
            return
        
        # Close all exchanges
        close_tasks = []
        
        for side in [Side.BUY, Side.SELL]:
            close_tasks.append(self.public_exchanges[side].close())
            close_tasks.append(self.private_exchanges[side].close())
        
        await asyncio.gather(*close_tasks)
        
        # Clear dual exchange registry
        clear_mock_dual_exchange_registry()
        
        # Stop all patches
        for patch_obj in self._active_patches:
            patch_obj.stop()
        self._active_patches.clear()
        
        self._is_setup = False
    
    def patch_exchange_factory(self):
        """Patch the exchange factory and DualExchange to return mock exchanges.
        
        Returns patch objects that should be used as context managers or
        stopped manually after testing.
        """
        def mock_get_composite_implementation(config: ExchangeConfig, is_private: bool):
            """Mock factory function that returns appropriate mock exchange."""
            # Handle both ExchangeName object and string
            exchange_name = config.name.value if hasattr(config.name, 'value') else config.name
            
            # Determine which side this exchange is for
            side = None
            if exchange_name == self.buy_exchange_enum.value:
                side = Side.BUY
            elif exchange_name == self.sell_exchange_enum.value:
                side = Side.SELL
            else:
                # Default to BUY side for unknown exchanges
                side = Side.BUY
            
            if is_private:
                return self.private_exchanges[side]
            else:
                return self.public_exchanges[side]
        
        def mock_dual_exchange_get_instance(config: ExchangeConfig, logger: HFTLoggerInterface = None):
            """Mock DualExchange.get_instance that returns appropriate mock."""
            # Handle both ExchangeName object and string
            exchange_name = config.name.value if hasattr(config.name, 'value') else config.name
            
            # Determine which side this exchange is for
            side = None
            if exchange_name == self.buy_exchange_enum.value:
                side = Side.BUY
            elif exchange_name == self.sell_exchange_enum.value:
                side = Side.SELL
            else:
                # Default to BUY side for unknown exchanges
                side = Side.BUY
            
            return self.dual_exchanges[side]
        
        # Patch the factory function
        factory_patch = patch('exchanges.exchange_factory.get_composite_implementation', 
                             side_effect=mock_get_composite_implementation)
        
        # Patch DualExchange.get_instance for unified architecture
        dual_exchange_patch = patch('exchanges.dual_exchange.DualExchange.get_instance',
                                   side_effect=mock_dual_exchange_get_instance)
        
        # Patch config manager to return mock configs
        def mock_get_exchange_config(exchange_enum_or_name):
            """Handle both ExchangeEnum and string inputs."""
            if isinstance(exchange_enum_or_name, str):
                # Convert string to enum if needed
                exchange_enum = getattr(ExchangeEnum, exchange_enum_or_name.upper(), None)
                if exchange_enum is None:
                    # Fallback - create a simple mock enum
                    exchange_enum = self.buy_exchange_enum
            else:
                exchange_enum = exchange_enum_or_name
            
            from config.structs import ExchangeConfig, ExchangeCredentials
            from exchanges.structs.types import ExchangeName
            return ExchangeConfig(
                name=ExchangeName(exchange_enum.value),
                credentials=ExchangeCredentials(api_key="mock", secret_key="mock"),
                base_url="https://mock.exchange.com",
                websocket_url="wss://mock.exchange.com"
            )
        
        config_patch = patch('config.config_manager.get_exchange_config',
                           side_effect=mock_get_exchange_config)
        
        # Start patches
        factory_patch.start()
        dual_exchange_patch.start()
        config_patch.start()
        
        self._active_patches.extend([factory_patch, dual_exchange_patch, config_patch])
        
        return factory_patch, dual_exchange_patch, config_patch
    
    # Market data control methods
    def set_prices(self, symbol: Symbol, 
                   buy_side_bid: float, buy_side_ask: float,
                   sell_side_bid: float, sell_side_ask: float):
        """Set prices on both exchanges for arbitrage scenarios."""
        self.public_exchanges[Side.BUY].set_book_ticker(
            symbol, buy_side_bid, buy_side_ask
        )
        self.public_exchanges[Side.SELL].set_book_ticker(
            symbol, sell_side_bid, sell_side_ask
        )
    
    def set_spread_scenario(self, symbol: Symbol, 
                           buy_exchange_price: float, sell_exchange_price: float,
                           spread: float = 1.0):
        """Set up a spread scenario for arbitrage testing."""
        self.public_exchanges[Side.BUY].update_price(symbol, buy_exchange_price, spread)
        self.public_exchanges[Side.SELL].update_price(symbol, sell_exchange_price, spread)
    
    def move_prices(self, symbol: Symbol, price_change: float):
        """Move prices on both exchanges by the same amount."""
        for side in [Side.BUY, Side.SELL]:
            current_ticker = self.public_exchanges[side]._book_ticker[symbol]
            new_price = (current_ticker.bid_price + current_ticker.ask_price) / 2 + price_change
            self.public_exchanges[side].update_price(symbol, new_price)
    
    # Order behavior control
    def set_order_fill_behavior(self, side: Side, order_id: str, fill_quantity: float):
        """Set fill behavior for specific orders."""
        self.private_exchanges[side].set_order_fill_behavior(order_id, fill_quantity)
    
    def set_order_failure_behavior(self, side: Side, should_fail_orders: bool = False,
                                  should_fail_cancellation: bool = False):
        """Set failure behavior for orders on specific side."""
        self.private_exchanges[side].set_should_fail_orders(should_fail_orders)
        self.private_exchanges[side].set_should_fail_cancellation(should_fail_cancellation)
    
    def simulate_partial_fills(self, symbol: Symbol, 
                              buy_fill_ratio: float = 0.5, 
                              sell_fill_ratio: float = 0.3):
        """Simulate partial fills at different rates on each side."""
        # This will be applied to new orders as they come in
        # For existing orders, use simulate_order_fill_during_execution
        pass
    
    def simulate_order_fill_during_execution(self, side: Side, order_id: str, fill_quantity: float):
        """Simulate order getting filled during task execution."""
        self.private_exchanges[side].simulate_order_fill(order_id, fill_quantity)
    
    # Test verification methods
    def get_order_history(self, side: Side) -> List:
        """Get order history for specific side."""
        return self.private_exchanges[side].get_placed_orders()
    
    def get_total_orders_placed(self) -> int:
        """Get total orders placed across both sides."""
        buy_orders = len(self.private_exchanges[Side.BUY].get_placed_orders())
        sell_orders = len(self.private_exchanges[Side.SELL].get_placed_orders())
        return buy_orders + sell_orders
    
    def get_cancelled_orders(self, side: Side) -> List[str]:
        """Get cancelled order IDs for specific side."""
        return self.private_exchanges[side].get_cancelled_orders()
    
    def verify_initialization(self) -> Tuple[bool, bool, bool, bool]:
        """Verify all exchanges were properly initialized."""
        return (
            self.public_exchanges[Side.BUY].was_initialized(),
            self.public_exchanges[Side.SELL].was_initialized(),
            self.private_exchanges[Side.BUY].was_initialized(),
            self.private_exchanges[Side.SELL].was_initialized()
        )
    
    def reset_for_new_test(self):
        """Reset all tracking for a new test."""
        for side in [Side.BUY, Side.SELL]:
            self.private_exchanges[side].reset_tracking()
    
    # Convenience methods for common test scenarios
    def setup_profitable_arbitrage(self, symbol: Symbol, 
                                  buy_price: float = 50000.0, 
                                  sell_price: float = 50100.0):
        """Setup profitable arbitrage scenario (sell price > buy price)."""
        self.set_spread_scenario(symbol, buy_price, sell_price)
    
    def setup_losing_arbitrage(self, symbol: Symbol,
                              buy_price: float = 50100.0,
                              sell_price: float = 50000.0):
        """Setup losing arbitrage scenario (buy price > sell price)."""
        self.set_spread_scenario(symbol, buy_price, sell_price)
    
    def setup_fast_moving_market(self, symbol: Symbol, 
                                initial_price: float = 50000.0,
                                price_volatility: float = 100.0):
        """Setup market with high volatility for testing price movement tolerance."""
        self.set_spread_scenario(symbol, initial_price, initial_price)
        # Test can then call move_prices repeatedly to simulate volatility