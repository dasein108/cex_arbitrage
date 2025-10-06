"""
Test Data Factory for Trading Task Unit Tests

Central factory for creating all types of test data used in trading task tests.
Provides consistent, realistic test data with sensible defaults and easy customization.
"""

import time
from typing import Dict, Optional

from exchanges.structs import (
    Symbol, ExchangeEnum, Side, Order, OrderType, OrderStatus, 
    BookTicker, SymbolInfo, AssetBalance
)
from exchanges.structs.common import AssetName, TimeInForce
from trading.tasks.delta_neutral_task import DeltaNeutralTaskContext, Direction
from infrastructure.logging import HFTLoggerInterface


class TestDataFactory:
    """Factory for creating consistent test data across all trading task tests."""
    
    # Default test symbols
    DEFAULT_SYMBOL = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'))
    ALT_SYMBOL = Symbol(base=AssetName('ETH'), quote=AssetName('USDT'))
    
    # Default exchanges for dual exchange testing
    DEFAULT_BUY_EXCHANGE = ExchangeEnum.GATEIO
    DEFAULT_SELL_EXCHANGE = ExchangeEnum.MEXC
    
    # Default prices for realistic scenarios
    DEFAULT_BTC_PRICE = 50000.0
    DEFAULT_ETH_PRICE = 3000.0
    
    @classmethod
    def create_symbol(cls, base: str = 'BTC', quote: str = 'USDT') -> Symbol:
        """Create a symbol for testing."""
        return Symbol(base=AssetName(base), quote=AssetName(quote))
    
    @classmethod
    def create_symbol_info(cls, symbol: Optional[Symbol] = None, **kwargs) -> SymbolInfo:
        """Create symbol info with realistic defaults for testing."""
        if symbol is None:
            symbol = cls.DEFAULT_SYMBOL
        
        defaults = {
            'symbol': symbol,
            'base_precision': 8,
            'quote_precision': 2,
            'min_base_quantity': 0.001,
            'min_quote_quantity': 10.0,
            'maker_commission': 0.001,
            'taker_commission': 0.002,
            'tick': 0.01,
            'step': 0.001,
            'is_futures': False
        }
        
        # Override defaults with provided kwargs
        defaults.update(kwargs)
        
        return SymbolInfo(**defaults)
    
    @classmethod
    def create_book_ticker(cls, symbol: Optional[Symbol] = None, 
                          bid_price: Optional[float] = None,
                          ask_price: Optional[float] = None,
                          spread: float = 1.0, **kwargs) -> BookTicker:
        """Create book ticker with realistic bid/ask prices."""
        if symbol is None:
            symbol = cls.DEFAULT_SYMBOL
        
        if bid_price is None:
            base_price = cls.DEFAULT_BTC_PRICE if symbol.base == AssetName('BTC') else cls.DEFAULT_ETH_PRICE
            bid_price = base_price - spread/2
        
        if ask_price is None:
            ask_price = bid_price + spread
        
        defaults = {
            'symbol': symbol,
            'bid_price': bid_price,
            'bid_quantity': 1.0,
            'ask_price': ask_price,
            'ask_quantity': 1.0,
            'timestamp': int(time.time() * 1000)
        }
        
        defaults.update(kwargs)
        return BookTicker(**defaults)
    
    @classmethod
    def create_order(cls, symbol: Optional[Symbol] = None,
                    side: Side = Side.BUY,
                    quantity: float = 0.1,
                    price: Optional[float] = None,
                    order_id: Optional[str] = None,
                    **kwargs) -> Order:
        """Create an order with realistic defaults."""
        if symbol is None:
            symbol = cls.DEFAULT_SYMBOL
        
        if price is None:
            price = cls.DEFAULT_BTC_PRICE if symbol.base == AssetName('BTC') else cls.DEFAULT_ETH_PRICE
        
        if order_id is None:
            order_id = f"test_order_{int(time.time() * 1000)}"
        
        defaults = {
            'symbol': symbol,
            'order_id': order_id,
            'side': side,
            'order_type': OrderType.LIMIT,
            'quantity': quantity,
            'price': price,
            'filled_quantity': 0.0,
            'status': OrderStatus.NEW,
            'timestamp': int(time.time() * 1000),
            'time_in_force': TimeInForce.GTC
        }
        
        defaults.update(kwargs)
        return Order(**defaults)
    
    @classmethod
    def create_partial_filled_order(cls, symbol: Optional[Symbol] = None,
                                   side: Side = Side.BUY,
                                   quantity: float = 0.1,
                                   fill_ratio: float = 0.5,
                                   **kwargs) -> Order:
        """Create a partially filled order."""
        filled_quantity = quantity * fill_ratio
        
        return cls.create_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            filled_quantity=filled_quantity,
            status=OrderStatus.PARTIALLY_FILLED,
            **kwargs
        )
    
    @classmethod
    def create_filled_order(cls, symbol: Optional[Symbol] = None,
                           side: Side = Side.BUY,
                           quantity: float = 0.1,
                           **kwargs) -> Order:
        """Create a fully filled order."""
        return cls.create_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            filled_quantity=quantity,
            status=OrderStatus.FILLED,
            **kwargs
        )
    
    @classmethod
    def create_asset_balance(cls, asset: str = 'USDT', 
                            available: float = 10000.0,
                            locked: float = 0.0) -> AssetBalance:
        """Create asset balance for testing."""
        return AssetBalance(
            asset=AssetName(asset),
            available=available,
            locked=locked
        )
    
    @classmethod
    def create_delta_neutral_context(cls, 
                                   symbol: Optional[Symbol] = None,
                                   total_quantity: float = 1.0,
                                   order_quantity: float = 0.1,
                                   buy_exchange: ExchangeEnum = DEFAULT_BUY_EXCHANGE,
                                   sell_exchange: ExchangeEnum = DEFAULT_SELL_EXCHANGE,
                                   **kwargs) -> DeltaNeutralTaskContext:
        """Create delta neutral task context with realistic defaults."""
        if symbol is None:
            symbol = cls.DEFAULT_SYMBOL
        
        defaults = {
            'symbol': symbol,
            'total_quantity': total_quantity,
            'order_quantity': order_quantity,
            'exchange_names': {
                Side.BUY: buy_exchange,
                Side.SELL: sell_exchange
            },
            'direction': Direction.NONE,
            'filled_quantity': {Side.BUY: 0.0, Side.SELL: 0.0},
            'avg_price': {Side.BUY: 0.0, Side.SELL: 0.0},
            'offset_ticks': {Side.BUY: 1, Side.SELL: 1},
            'tick_tolerance': {Side.BUY: 5, Side.SELL: 5},
            'order_id': {Side.BUY: None, Side.SELL: None}
        }
        
        defaults.update(kwargs)
        return DeltaNeutralTaskContext(**defaults)
    
    @classmethod
    def create_arbitrage_scenario(cls, symbol: Optional[Symbol] = None,
                                 buy_price: float = 50000.0,
                                 sell_price: float = 50100.0,
                                 spread: float = 1.0) -> Dict:
        """Create market data for arbitrage scenario testing."""
        if symbol is None:
            symbol = cls.DEFAULT_SYMBOL
        
        return {
            'buy_side_ticker': cls.create_book_ticker(
                symbol=symbol,
                bid_price=buy_price - spread/2,
                ask_price=buy_price + spread/2
            ),
            'sell_side_ticker': cls.create_book_ticker(
                symbol=symbol,
                bid_price=sell_price - spread/2,
                ask_price=sell_price + spread/2
            ),
            'profit_potential': sell_price - buy_price - spread
        }
    
    @classmethod
    def create_imbalanced_fills_scenario(cls, symbol: Optional[Symbol] = None,
                                       buy_filled: float = 0.5,
                                       sell_filled: float = 0.3) -> Dict:
        """Create scenario with imbalanced fills between sides."""
        if symbol is None:
            symbol = cls.DEFAULT_SYMBOL
        
        return {
            'buy_order': cls.create_partial_filled_order(
                symbol=symbol,
                side=Side.BUY,
                quantity=1.0,
                fill_ratio=buy_filled
            ),
            'sell_order': cls.create_partial_filled_order(
                symbol=symbol,
                side=Side.SELL,
                quantity=1.0,
                fill_ratio=sell_filled
            ),
            'imbalance': buy_filled - sell_filled
        }