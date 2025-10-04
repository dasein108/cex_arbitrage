"""
Market Maker Bot - State Machine Architecture
==============================================
Simple, clean state machine implementation with single source of truth.
No reactive patterns - just straightforward async/await with clear state transitions.
"""

import asyncio
from enum import Enum, auto
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import time

from exchanges.interfaces.composite import BasePrivateComposite, BasePublicComposite
from exchanges.structs import (
    Side, TimeInForce, Symbol, Order,
    BookTicker, SymbolInfo
)
from infrastructure.logging import get_logger
from utils.exchange_utils import is_order_filled
from infrastructure.networking.websocket.structs import WebsocketChannelType


class MarketMakerState(Enum):
    """Clear, explicit state machine states."""
    IDLE = auto()
    BUYING = auto()
    PLACING_SELL = auto()
    MONITORING_SELL = auto()
    ADJUSTING_SELL = auto()
    COMPLETED = auto()
    ERROR = auto()


@dataclass
class MarketMakerContext:
    """Single source of truth for all bot state."""
    state: MarketMakerState = MarketMakerState.IDLE
    
    # Configuration
    symbol: Symbol = None
    symbol_info: SymbolInfo = None
    quantity_usdt: float = 0.0
    max_price_deviation_ticks: int = 2  # Replace order if price moves > 2 ticks
    
    # Current orders
    buy_order: Optional[Order] = None
    sell_order: Optional[Order] = None
    
    # Market data
    current_ask_price: float = 0.0
    last_sell_price: float = 0.0
    
    # Statistics
    cycles_completed: int = 0
    errors: list = field(default_factory=list)
    
    def reset_for_new_cycle(self):
        """Reset state for a new trading cycle."""
        self.state = MarketMakerState.IDLE
        self.buy_order = None
        self.sell_order = None
        self.last_sell_price = 0.0


class SimpleMarketMaker:
    """
    Clean market maker implementation using state machine pattern.
    Single class owns all state - no distributed state management.
    """
    
    def __init__(
        self,
        private_exchange: BasePrivateComposite,
        public_exchange: BasePublicComposite,
        symbol: Symbol,
        symbol_info: SymbolInfo,
        quantity_usdt: float,
        logger=None
    ):
        self.private_exchange = private_exchange
        self.public_exchange = public_exchange
        self.logger = logger or get_logger(self.__class__.__name__)
        
        # Single context holds all state
        self.context = MarketMakerContext(
            symbol=symbol,
            symbol_info=symbol_info,
            quantity_usdt=quantity_usdt
        )
        
        # Control flags
        self._running = False
        self._stop_requested = False
        
        # State transition handlers
        self.state_handlers: Dict[MarketMakerState, Any] = {
            MarketMakerState.IDLE: self._handle_idle,
            MarketMakerState.BUYING: self._handle_buying,
            MarketMakerState.PLACING_SELL: self._handle_placing_sell,
            MarketMakerState.MONITORING_SELL: self._handle_monitoring_sell,
            MarketMakerState.ADJUSTING_SELL: self._handle_adjusting_sell,
            MarketMakerState.COMPLETED: self._handle_completed,
            MarketMakerState.ERROR: self._handle_error,
        }
    
    async def run_cycle(self) -> tuple[Order, Order]:
        """
        Run one complete market making cycle.
        Returns (buy_order, sell_order) when completed.
        """
        self.context.reset_for_new_cycle()
        self._running = True
        
        try:
            while self._running and self.context.state != MarketMakerState.COMPLETED:
                # Get handler for current state
                handler = self.state_handlers.get(self.context.state)
                if not handler:
                    raise ValueError(f"No handler for state {self.context.state}")
                
                # Execute state handler - it will transition to next state
                await handler()
                
                # Small delay to prevent tight loops
                await asyncio.sleep(0.1)
            
            if self.context.state == MarketMakerState.COMPLETED:
                self.context.cycles_completed += 1
                return self.context.buy_order, self.context.sell_order
            else:
                raise RuntimeError(f"Cycle ended in unexpected state: {self.context.state}")
                
        except Exception as e:
            self.logger.error(f"Market maker cycle failed: {e}")
            self.context.errors.append(str(e))
            self.context.state = MarketMakerState.ERROR
            raise
    
    async def _handle_idle(self):
        """Initial state - prepare for market buy."""
        self.logger.info("Starting new market making cycle")
        
        # Get current market price
        book_ticker = await self._get_current_book_ticker()
        self.context.current_ask_price = book_ticker.ask_price
        
        # Transition to buying
        self._transition_to(MarketMakerState.BUYING)
    
    async def _handle_buying(self):
        """Execute market buy order."""
        try:
            self.logger.info(f"Executing market buy at {self.context.current_ask_price}")
            
            self.context.buy_order = await self.private_exchange.place_market_order(
                symbol=self.context.symbol,
                side=Side.BUY,
                quote_quantity=self.context.quantity_usdt,
                ensure=True
            )
            
            self.logger.info(f"Market buy completed: {self.context.buy_order}")
            
            # Transition to placing sell
            self._transition_to(MarketMakerState.PLACING_SELL)
            
        except Exception as e:
            self.logger.error(f"Market buy failed: {e}")
            self.context.errors.append(f"Buy failed: {e}")
            self._transition_to(MarketMakerState.ERROR)
    
    async def _handle_placing_sell(self):
        """Place initial limit sell order."""
        try:
            # Get latest ask price
            book_ticker = await self._get_current_book_ticker()
            self.context.current_ask_price = book_ticker.ask_price
            
            # Calculate sell price (top of book)
            sell_price = self.context.current_ask_price - self.context.symbol_info.tick
            self.context.last_sell_price = sell_price
            
            self.logger.info(f"Placing limit sell at {sell_price}")
            
            self.context.sell_order = await self.private_exchange.place_limit_order(
                symbol=self.context.symbol,
                side=Side.SELL,
                quantity=self.context.buy_order.filled_quantity,
                price=sell_price,
                time_in_force=TimeInForce.GTC
            )
            
            self.logger.info(f"Limit sell placed: {self.context.sell_order}")
            
            # Transition to monitoring
            self._transition_to(MarketMakerState.MONITORING_SELL)
            
        except Exception as e:
            self.logger.error(f"Failed to place sell order: {e}")
            self.context.errors.append(f"Sell placement failed: {e}")
            self._transition_to(MarketMakerState.ERROR)
    
    async def _handle_monitoring_sell(self):
        """Monitor sell order and market conditions."""
        try:
            # Check order status
            order_status = await self.private_exchange.fetch_order(
                self.context.symbol,
                self.context.sell_order.order_id
            )
            
            # Check if filled
            if is_order_filled(order_status):
                self.context.sell_order = order_status
                self.logger.info(f"Sell order filled: {order_status}")
                self._transition_to(MarketMakerState.COMPLETED)
                return
            
            # Check if we need to adjust price
            book_ticker = await self._get_current_book_ticker()
            self.context.current_ask_price = book_ticker.ask_price
            
            expected_sell_price = self.context.current_ask_price - self.context.symbol_info.tick
            price_difference_ticks = abs(self.context.last_sell_price - expected_sell_price) / self.context.symbol_info.tick
            
            if price_difference_ticks > self.context.max_price_deviation_ticks:
                self.logger.info(f"Price moved {price_difference_ticks:.1f} ticks, adjusting order")
                self._transition_to(MarketMakerState.ADJUSTING_SELL)
            else:
                # Continue monitoring
                await asyncio.sleep(0.5)  # Poll every 500ms
                
        except Exception as e:
            self.logger.error(f"Error monitoring sell order: {e}")
            # Don't transition to error state for transient monitoring issues
            await asyncio.sleep(1)
    
    async def _handle_adjusting_sell(self):
        """Cancel and replace sell order at better price."""
        try:
            # Cancel existing order
            self.logger.info(f"Cancelling order {self.context.sell_order.order_id}")
            cancelled = await self.private_exchange.cancel_order(
                self.context.symbol,
                self.context.sell_order.order_id
            )
            
            # Check if it filled during cancel
            if is_order_filled(cancelled):
                self.context.sell_order = cancelled
                self.logger.info("Order filled during cancel")
                self._transition_to(MarketMakerState.COMPLETED)
                return
            
            # Place new order at current top of book
            await asyncio.sleep(0.1)  # Brief delay after cancel
            self._transition_to(MarketMakerState.PLACING_SELL)
            
        except Exception as e:
            self.logger.error(f"Failed to adjust sell order: {e}")
            # Try to continue monitoring existing order
            self._transition_to(MarketMakerState.MONITORING_SELL)
    
    async def _handle_completed(self):
        """Cycle completed successfully."""
        self.logger.info("Market making cycle completed successfully")
        self._running = False
    
    async def _handle_error(self):
        """Handle error state."""
        self.logger.error(f"Market maker in error state. Errors: {self.context.errors}")
        self._running = False
        raise RuntimeError(f"Market maker failed with errors: {self.context.errors}")
    
    async def _get_current_book_ticker(self) -> BookTicker:
        """Get current book ticker from exchange."""
        # In production, this would get from WebSocket stream
        # For simplicity, using REST call here
        orderbook = await self.public_exchange.get_orderbook(self.context.symbol, limit=5)
        return BookTicker(
            symbol=self.context.symbol,
            bid_price=orderbook.bids[0].price if orderbook.bids else 0,
            bid_quantity=orderbook.bids[0].quantity if orderbook.bids else 0,
            ask_price=orderbook.asks[0].price if orderbook.asks else 0,
            ask_quantity=orderbook.asks[0].quantity if orderbook.asks else 0,
            timestamp=time.time()
        )
    
    def _transition_to(self, new_state: MarketMakerState):
        """Transition to new state with logging."""
        old_state = self.context.state
        self.context.state = new_state
        self.logger.info(f"State transition: {old_state.name} -> {new_state.name}")
    
    def stop(self):
        """Request graceful stop."""
        self._stop_requested = True
        self._running = False


async def main():
    """Example usage of the state machine market maker."""
    from config import get_exchange_config
    from exchanges.exchange_factory import get_composite_implementation
    from exchanges.structs import AssetName
    
    logger = get_logger("mm_state_machine")
    
    # Configuration
    exchange_name = "mexc_spot"
    config = get_exchange_config(exchange_name)
    symbol = Symbol(base=AssetName("HIFI"), quote=AssetName("USDT"), is_futures=False)
    quantity_usdt = 2.1
    
    # Setup exchanges
    private_exchange = get_composite_implementation(config, is_private=True)
    public_exchange = get_composite_implementation(config, is_private=False)
    
    try:
        # Initialize
        await public_exchange.initialize([symbol], [WebsocketChannelType.BOOK_TICKER])
        await private_exchange.initialize(
            public_exchange.symbols_info,
            [WebsocketChannelType.ORDER, WebsocketChannelType.BALANCE]
        )
        
        await public_exchange.wait_until_connected()
        await private_exchange.wait_until_connected()
        await asyncio.sleep(1)
        
        symbol_info = public_exchange.symbols_info.get(symbol)
        
        # Create market maker
        market_maker = SimpleMarketMaker(
            private_exchange=private_exchange,
            public_exchange=public_exchange,
            symbol=symbol,
            symbol_info=symbol_info,
            quantity_usdt=quantity_usdt,
            logger=logger
        )
        
        # Run one cycle
        print("\n🚀 Starting market making cycle...")
        buy_order, sell_order = await market_maker.run_cycle()
        
        print(f"\n✅ Cycle completed!")
        print(f"  Buy: {buy_order}")
        print(f"  Sell: {sell_order}")
        
    finally:
        # Cleanup
        await private_exchange.close()
        await public_exchange.close()


if __name__ == "__main__":
    asyncio.run(main())