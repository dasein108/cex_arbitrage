"""
Market Maker Bot - Event-Driven Architecture
=============================================
Clean event-driven implementation using asyncio queues and message passing.
No complex reactive patterns - just simple async message processing.
"""

import asyncio
from enum import Enum, auto
from typing import Optional, Any
from dataclasses import dataclass
import time

from exchanges.interfaces.composite import BasePrivateComposite, BasePublicComposite
from exchanges.structs import (
    Side, TimeInForce, Symbol, Order,
    BookTicker, SymbolInfo
)
from infrastructure.logging import get_logger
from utils.exchange_utils import is_order_filled
from infrastructure.networking.websocket.structs import WebsocketChannelType


class EventType(Enum):
    """All possible event types in the system."""
    # Market events
    PRICE_UPDATE = auto()
    
    # Order events
    ORDER_UPDATE = auto()
    ORDER_FILLED = auto()
    
    # Commands
    START_CYCLE = auto()
    EXECUTE_BUY = auto()
    PLACE_SELL = auto()
    ADJUST_SELL = auto()
    CANCEL_ORDER = auto()
    
    # System events
    CYCLE_COMPLETE = auto()
    ERROR = auto()
    SHUTDOWN = auto()


@dataclass
class Event:
    """Base event class with type and optional data."""
    type: EventType
    data: Any = None
    error: Optional[Exception] = None


@dataclass
class MarketMakerState:
    """Centralized state for the market maker."""
    # Configuration
    symbol: Symbol
    symbol_info: SymbolInfo
    quantity_usdt: float
    max_price_deviation_ticks: int = 2
    
    # Current orders
    buy_order: Optional[Order] = None
    sell_order: Optional[Order] = None
    pending_order_id: Optional[str] = None  # Track order we're waiting for
    
    # Market data
    current_ask_price: float = 0.0
    last_sell_price: float = 0.0
    
    # Flags
    is_buying: bool = False
    is_adjusting: bool = False
    cycle_active: bool = False


class EventDrivenMarketMaker:
    """
    Event-driven market maker using message passing.
    All components communicate through a central event queue.
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
        
        # Central event queue
        self.event_queue: asyncio.Queue = asyncio.Queue()
        
        # State management
        self.state = MarketMakerState(
            symbol=symbol,
            symbol_info=symbol_info,
            quantity_usdt=quantity_usdt
        )
        
        # Background tasks
        self.tasks = []
        self._running = False
    
    async def start(self):
        """Start all background tasks."""
        self._running = True
        
        # Start event processor
        self.tasks.append(
            asyncio.create_task(self._event_processor())
        )
        
        # Start market data monitor
        self.tasks.append(
            asyncio.create_task(self._market_data_monitor())
        )
        
        # Start order monitor
        self.tasks.append(
            asyncio.create_task(self._order_monitor())
        )
        
        self.logger.info("Event-driven market maker started")
    
    async def stop(self):
        """Gracefully stop all tasks."""
        self._running = False
        
        # Send shutdown event
        await self.event_queue.put(Event(EventType.SHUTDOWN))
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        self.logger.info("Event-driven market maker stopped")
    
    async def run_cycle(self) -> tuple[Order, Order]:
        """
        Run one complete market making cycle.
        Returns (buy_order, sell_order) when completed.
        """
        # Reset state
        self.state.buy_order = None
        self.state.sell_order = None
        self.state.cycle_active = True
        
        # Create completion future
        cycle_complete = asyncio.Future()
        
        # Setup completion handler
        async def wait_for_completion():
            while self.state.cycle_active:
                # Check if cycle is complete
                if self.state.sell_order and is_order_filled(self.state.sell_order):
                    cycle_complete.set_result((self.state.buy_order, self.state.sell_order))
                    self.state.cycle_active = False
                    break
                await asyncio.sleep(0.1)
        
        # Start completion watcher
        completion_task = asyncio.create_task(wait_for_completion())
        
        # Start the cycle
        await self.event_queue.put(Event(EventType.START_CYCLE))
        
        try:
            # Wait for completion
            return await cycle_complete
        finally:
            completion_task.cancel()
    
    async def _event_processor(self):
        """Main event processing loop."""
        while self._running:
            try:
                # Get next event with timeout
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=1.0
                )
                
                # Process event
                await self._handle_event(event)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Error processing event: {e}")
    
    async def _handle_event(self, event: Event):
        """Route events to appropriate handlers."""
        handlers = {
            EventType.START_CYCLE: self._handle_start_cycle,
            EventType.PRICE_UPDATE: self._handle_price_update,
            EventType.ORDER_UPDATE: self._handle_order_update,
            EventType.ORDER_FILLED: self._handle_order_filled,
            EventType.EXECUTE_BUY: self._handle_execute_buy,
            EventType.PLACE_SELL: self._handle_place_sell,
            EventType.ADJUST_SELL: self._handle_adjust_sell,
            EventType.ERROR: self._handle_error,
            EventType.SHUTDOWN: self._handle_shutdown,
        }
        
        handler = handlers.get(event.type)
        if handler:
            await handler(event)
        else:
            self.logger.warning(f"No handler for event type: {event.type}")
    
    async def _handle_start_cycle(self, event: Event):
        """Start a new trading cycle."""
        self.logger.info("Starting new market making cycle")
        
        # Trigger buy order
        await self.event_queue.put(Event(EventType.EXECUTE_BUY))
    
    async def _handle_execute_buy(self, event: Event):
        """Execute market buy order."""
        if self.state.is_buying:
            return  # Already buying
        
        self.state.is_buying = True
        
        try:
            # Get current price
            book_ticker = await self._get_current_book_ticker()
            self.state.current_ask_price = book_ticker.ask_price
            
            self.logger.info(f"Executing market buy at {self.state.current_ask_price}")
            
            # Execute buy
            self.state.buy_order = await self.private_exchange.place_market_order(
                symbol=self.state.symbol,
                side=Side.BUY,
                quote_quantity=self.state.quantity_usdt,
                ensure=True
            )
            
            self.logger.info(f"Market buy completed: {self.state.buy_order}")
            
            # Trigger sell order placement
            await self.event_queue.put(Event(EventType.PLACE_SELL))
            
        except Exception as e:
            self.logger.error(f"Market buy failed: {e}")
            await self.event_queue.put(Event(EventType.ERROR, error=e))
        finally:
            self.state.is_buying = False
    
    async def _handle_place_sell(self, event: Event):
        """Place limit sell order."""
        if not self.state.buy_order:
            self.logger.error("Cannot place sell without buy order")
            return
        
        try:
            # Get latest price
            book_ticker = await self._get_current_book_ticker()
            self.state.current_ask_price = book_ticker.ask_price
            
            # Calculate sell price
            sell_price = self.state.current_ask_price - self.state.symbol_info.tick
            self.state.last_sell_price = sell_price
            
            self.logger.info(f"Placing limit sell at {sell_price}")
            
            # Place order
            self.state.sell_order = await self.private_exchange.place_limit_order(
                symbol=self.state.symbol,
                side=Side.SELL,
                quantity=self.state.buy_order.filled_quantity,
                price=sell_price,
                time_in_force=TimeInForce.GTC
            )
            
            self.state.pending_order_id = self.state.sell_order.order_id
            self.logger.info(f"Limit sell placed: {self.state.sell_order}")
            
        except Exception as e:
            self.logger.error(f"Failed to place sell order: {e}")
            await self.event_queue.put(Event(EventType.ERROR, error=e))
    
    async def _handle_price_update(self, event: Event):
        """Handle price updates and check if we need to adjust orders."""
        if not self.state.sell_order or self.state.is_adjusting:
            return
        
        book_ticker: BookTicker = event.data
        self.state.current_ask_price = book_ticker.ask_price
        
        # Check if we need to adjust
        expected_price = self.state.current_ask_price - self.state.symbol_info.tick
        price_diff_ticks = abs(self.state.last_sell_price - expected_price) / self.state.symbol_info.tick
        
        if price_diff_ticks > self.state.max_price_deviation_ticks:
            self.logger.info(f"Price moved {price_diff_ticks:.1f} ticks, adjusting order")
            await self.event_queue.put(Event(EventType.ADJUST_SELL))
    
    async def _handle_order_update(self, event: Event):
        """Handle order status updates."""
        order: Order = event.data
        
        # Check if this is our sell order
        if order.order_id == self.state.pending_order_id:
            self.state.sell_order = order
            
            if is_order_filled(order):
                await self.event_queue.put(Event(EventType.ORDER_FILLED, data=order))
    
    async def _handle_order_filled(self, event: Event):
        """Handle order fill completion."""
        order: Order = event.data
        
        if order.side == Side.SELL:
            self.logger.info(f"Sell order filled: {order}")
            self.state.sell_order = order
            self.state.cycle_active = False
            await self.event_queue.put(Event(EventType.CYCLE_COMPLETE))
    
    async def _handle_adjust_sell(self, event: Event):
        """Adjust sell order price."""
        if self.state.is_adjusting or not self.state.sell_order:
            return
        
        self.state.is_adjusting = True
        
        try:
            # Cancel existing order
            self.logger.info(f"Cancelling order {self.state.sell_order.order_id}")
            cancelled = await self.private_exchange.cancel_order(
                self.state.symbol,
                self.state.sell_order.order_id
            )
            
            # Check if filled during cancel
            if is_order_filled(cancelled):
                self.state.sell_order = cancelled
                await self.event_queue.put(Event(EventType.ORDER_FILLED, data=cancelled))
                return
            
            # Place new order
            await asyncio.sleep(0.1)
            await self.event_queue.put(Event(EventType.PLACE_SELL))
            
        except Exception as e:
            self.logger.error(f"Failed to adjust order: {e}")
        finally:
            self.state.is_adjusting = False
    
    async def _handle_error(self, event: Event):
        """Handle errors."""
        self.logger.error(f"Error in market maker: {event.error}")
        self.state.cycle_active = False
    
    async def _handle_shutdown(self, event: Event):
        """Handle shutdown request."""
        self.logger.info("Shutting down market maker")
        self._running = False
    
    async def _market_data_monitor(self):
        """Monitor market data and emit price update events."""
        while self._running:
            try:
                if self.state.cycle_active and self.state.sell_order:
                    # Get current market data
                    book_ticker = await self._get_current_book_ticker()
                    
                    # Emit price update event
                    await self.event_queue.put(
                        Event(EventType.PRICE_UPDATE, data=book_ticker)
                    )
                
                await asyncio.sleep(1.0)  # Check every second
                
            except Exception as e:
                self.logger.error(f"Market data monitor error: {e}")
                await asyncio.sleep(1.0)
    
    async def _order_monitor(self):
        """Monitor order status and emit order update events."""
        while self._running:
            try:
                if self.state.pending_order_id:
                    # Check order status
                    order = await self.private_exchange.fetch_order(
                        self.state.symbol,
                        self.state.pending_order_id
                    )
                    
                    # Emit order update event
                    await self.event_queue.put(
                        Event(EventType.ORDER_UPDATE, data=order)
                    )
                
                await asyncio.sleep(0.5)  # Check every 500ms
                
            except Exception as e:
                self.logger.error(f"Order monitor error: {e}")
                await asyncio.sleep(1.0)
    
    async def _get_current_book_ticker(self) -> BookTicker:
        """Get current book ticker from exchange."""
        orderbook = await self.public_exchange.get_orderbook(self.state.symbol, limit=5)
        return BookTicker(
            symbol=self.state.symbol,
            bid_price=orderbook.bids[0].price if orderbook.bids else 0,
            bid_quantity=orderbook.bids[0].quantity if orderbook.bids else 0,
            ask_price=orderbook.asks[0].price if orderbook.asks else 0,
            ask_quantity=orderbook.asks[0].quantity if orderbook.asks else 0,
            timestamp=time.time()
        )


async def main():
    """Example usage of the event-driven market maker."""
    from config import get_exchange_config
    from exchanges.exchange_factory import get_composite_implementation
    from exchanges.structs import AssetName
    
    logger = get_logger("mm_event_driven")
    
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
        market_maker = EventDrivenMarketMaker(
            private_exchange=private_exchange,
            public_exchange=public_exchange,
            symbol=symbol,
            symbol_info=symbol_info,
            quantity_usdt=quantity_usdt,
            logger=logger
        )
        
        # Start background tasks
        await market_maker.start()
        
        # Run one cycle
        print("\n🚀 Starting market making cycle...")
        buy_order, sell_order = await market_maker.run_cycle()
        
        print(f"\n✅ Cycle completed!")
        print(f"  Buy: {buy_order}")
        print(f"  Sell: {sell_order}")
        
        # Stop background tasks
        await market_maker.stop()
        
    finally:
        # Cleanup
        await private_exchange.close()
        await public_exchange.close()


if __name__ == "__main__":
    asyncio.run(main())