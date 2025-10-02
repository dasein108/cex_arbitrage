

import asyncio
import sys
import os
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from config.structs import ExchangeConfig
from exchanges.interfaces.composite import BasePrivateComposite, BasePublicComposite

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config import get_exchange_config
from exchanges.utils.exchange_utils import is_order_filled
from exchanges.structs import (
    Side, TimeInForce, AssetName, Symbol, Order,
    AssetBalance, BookTicker, SymbolInfo
)
from infrastructure.logging import get_logger
from infrastructure.networking.websocket.structs import WebsocketChannelType, PublicWebsocketChannelType, \
    PrivateWebsocketChannelType
from exchanges.exchange_factory import get_composite_implementation


class MarketMakerState(Enum):
    """States for the market maker state machine."""
    IDLE = "idle"
    BUYING = "buying"
    PLACING_SELL = "placing_sell"
    MONITORING_SELL = "monitoring_sell"
    ADJUSTING_SELL = "adjusting_sell"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class MarketMakerContext:
    """Single source of truth for all market maker state."""
    # Configuration
    symbol: Symbol
    symbol_info: SymbolInfo
    quantity_usdt: float
    private_exchange: BasePrivateComposite
    public_exchange: BasePublicComposite
    logger: any
    
    # State
    current_state: MarketMakerState = MarketMakerState.IDLE
    
    # Orders
    market_buy_order: Optional[Order] = None
    limit_sell_order: Optional[Order] = None
    
    # Market data
    current_ask_price: Optional[float] = None
    
    # Error tracking
    error: Optional[Exception] = None
    
    # Performance tracking
    adjustment_count: int = 0


class MarketMakerStateMachine:
    """
    Simple state machine for market making cycle.
    States: IDLE → BUYING → PLACING_SELL → MONITORING_SELL → [ADJUSTING_SELL] → COMPLETED
    """
    
    def __init__(self, context: MarketMakerContext):
        self.context = context
        
    async def run_cycle(self) -> tuple[Order, Order]:
        """Execute complete market making cycle."""
        print("🚀 Starting market making cycle...")
        
        try:
            while self.context.current_state != MarketMakerState.COMPLETED:
                self.context.logger.info(f"State: {self.context.current_state.value}")
                
                if self.context.current_state == MarketMakerState.IDLE:
                    await self._handle_idle()
                elif self.context.current_state == MarketMakerState.BUYING:
                    await self._handle_buying()
                elif self.context.current_state == MarketMakerState.PLACING_SELL:
                    await self._handle_placing_sell()
                elif self.context.current_state == MarketMakerState.MONITORING_SELL:
                    await self._handle_monitoring_sell()
                elif self.context.current_state == MarketMakerState.ADJUSTING_SELL:
                    await self._handle_adjusting_sell()
                elif self.context.current_state == MarketMakerState.ERROR:
                    raise self.context.error or RuntimeError("Unknown error occurred")
                
                # Small delay to prevent busy loop
                await asyncio.sleep(0.1)
            
            print("✅✅✅ Market making cycle completed successfully!")
            return self.context.market_buy_order, self.context.limit_sell_order
            
        except Exception as e:
            self.context.error = e
            self.context.current_state = MarketMakerState.ERROR
            self.context.logger.error("Market making cycle failed", error=str(e))
            print(f"❌❌❌ Cycle failed: {e}")
            raise
    
    async def _handle_idle(self):
        """Get current market price and transition to buying."""
        print("📊 Getting current market price...")
        self.context.current_ask_price = await self._get_current_ask_price()
        self.context.current_state = MarketMakerState.BUYING
    
    async def _handle_buying(self):
        """Execute market buy order."""
        print(f"🛒 Executing market buy at ask price {self.context.current_ask_price}...")
        
        try:
            order = await self.context.private_exchange.place_market_order(
                symbol=self.context.symbol,
                side=Side.BUY,
                quote_quantity=self.context.quantity_usdt,
                ensure=True
            )
            
            self.context.market_buy_order = order
            print(f"📦 Market buy completed: {order}")
            self.context.current_state = MarketMakerState.PLACING_SELL
            
        except Exception as e:
            self.context.error = e
            self.context.current_state = MarketMakerState.ERROR
    
    async def _handle_placing_sell(self):
        """Place initial limit sell order."""
        print(f"📈 Placing limit sell order for quantity: {self.context.market_buy_order.filled_quantity}")
        
        try:
            # Get fresh price for sell order
            current_ask = await self._get_current_ask_price()
            sell_price = current_ask - self.context.symbol_info.tick
            
            order = await self.context.private_exchange.place_limit_order(
                symbol=self.context.symbol,
                side=Side.SELL,
                quantity=self.context.market_buy_order.filled_quantity,
                price=sell_price,
                time_in_force=TimeInForce.GTC
            )
            
            self.context.limit_sell_order = order
            print(f"✅ Limit sell order placed: {order} at price {sell_price}")
            self.context.current_state = MarketMakerState.MONITORING_SELL
            
        except Exception as e:
            self.context.error = e
            self.context.current_state = MarketMakerState.ERROR
    
    async def _handle_monitoring_sell(self):
        """Monitor sell order and market conditions."""
        try:
            # Check if order is filled
            order_status = await self._get_order_status(self.context.limit_sell_order)
            
            if is_order_filled(order_status):
                self.context.limit_sell_order = order_status
                print(f"💰 Limit sell order FILLED: {order_status}")
                self.context.current_state = MarketMakerState.COMPLETED
                return
            
            # Check if we need to adjust position
            current_ask = await self._get_current_ask_price()
            expected_sell_price = current_ask - self.context.symbol_info.tick
            
            # Only adjust if significantly out of position (more than 2 ticks)
            price_difference = abs(self.context.limit_sell_order.price - expected_sell_price)
            
            if price_difference > self.context.symbol_info.tick * 2:
                print(f"⚠️ Price moved significantly. Current ask: {current_ask}, Our price: {self.context.limit_sell_order.price}")
                self.context.current_ask_price = current_ask
                self.context.current_state = MarketMakerState.ADJUSTING_SELL
            
            # Wait before next check
            await asyncio.sleep(1.0)
            
        except Exception as e:
            self.context.error = e
            self.context.current_state = MarketMakerState.ERROR
    
    async def _handle_adjusting_sell(self):
        """Cancel current order and place new one at better price."""
        try:
            print(f"🔄 Adjusting sell order position (adjustment #{self.context.adjustment_count + 1})")
            
            # Cancel existing order
            cancelled_order = await self.context.private_exchange.cancel_order(
                self.context.limit_sell_order.symbol,
                self.context.limit_sell_order.order_id
            )
            
            # Check if filled during cancellation
            if is_order_filled(cancelled_order):
                self.context.limit_sell_order = cancelled_order
                print(f"✅✅✅ Order filled during cancellation: {cancelled_order}")
                self.context.current_state = MarketMakerState.COMPLETED
                return
            
            # Place new order at current market price
            new_sell_price = self.context.current_ask_price - self.context.symbol_info.tick
            
            new_order = await self.context.private_exchange.place_limit_order(
                symbol=self.context.symbol,
                side=Side.SELL,
                quantity=self.context.limit_sell_order.quantity,
                price=new_sell_price,
                time_in_force=TimeInForce.GTC
            )
            
            self.context.limit_sell_order = new_order
            self.context.adjustment_count += 1
            
            print(f"✅ New limit sell order placed: {new_order} at price {new_sell_price}")
            self.context.current_state = MarketMakerState.MONITORING_SELL
            
        except Exception as e:
            self.context.error = e
            self.context.current_state = MarketMakerState.ERROR
    
    async def _get_current_ask_price(self) -> float:
        """Get current ask price from public exchange."""
        book_ticker = await self.context.public_exchange.get_book_ticker(self.context.symbol)
        return book_ticker.ask_price
    
    async def _get_order_status(self, order: Order) -> Order:
        """Get current status of an order."""
        return await self.context.private_exchange.get_order(order.symbol, order.order_id)


async def create_market_maker_context(
    exchange_config: ExchangeConfig, 
    symbol: Symbol,
    quantity_usdt: float,
    logger
) -> MarketMakerContext:
    """Create and initialize market maker context."""
    
    # Create exchange connections
    private_exchange = get_composite_implementation(exchange_config, is_private=True)
    public_exchange = get_composite_implementation(exchange_config, is_private=False)

    # Initialize exchanges (minimal setup - no WebSocket streams needed)
    await public_exchange.initialize([symbol], [PublicWebsocketChannelType.BOOK_TICKER])  # No WebSocket channels needed
    await private_exchange.initialize(public_exchange.symbols_info, [PrivateWebsocketChannelType.ORDER,
                                                                     PrivateWebsocketChannelType.BALANCE])

    # Get symbol info
    symbol_info = public_exchange.symbols_info.get(symbol)
    
    return MarketMakerContext(
        symbol=symbol,
        symbol_info=symbol_info,
        quantity_usdt=quantity_usdt,
        private_exchange=private_exchange,
        public_exchange=public_exchange,
        logger=logger
    )


async def run_market_making_cycle(
    exchange_config: ExchangeConfig,
    symbol: Symbol,
    quantity_usdt: float,
    logger
) -> tuple[Order, Order]:
    """
    Execute a complete market making cycle using state machine.
    Simple, straightforward implementation with clear state transitions.
    
    Returns:
        tuple of (market_buy_order, limit_sell_order)
    """
    # Create context and state machine
    context = await create_market_maker_context(exchange_config, symbol, quantity_usdt, logger)
    state_machine = MarketMakerStateMachine(context)
    
    # Run the cycle
    return await state_machine.run_cycle()


async def cleanup_resources(context: Optional[MarketMakerContext], logger) -> None:
    """Properly cleanup all resources to ensure program termination."""
    if not context:
        logger.info("No context to cleanup")
        return
        
    try:
        logger.info("Starting resource cleanup...")
        
        # Close exchange connections with timeout
        cleanup_tasks = []
        
        if context.private_exchange:
            cleanup_tasks.append(context.private_exchange.close())
            logger.info("Closing private exchange...")
        
        if context.public_exchange:
            cleanup_tasks.append(context.public_exchange.close())
            logger.info("Closing public exchange...")
        
        # Wait for cleanup with timeout
        if cleanup_tasks:
            await asyncio.wait_for(
                asyncio.gather(*cleanup_tasks, return_exceptions=True),
                timeout=5.0
            )
            logger.info("All exchanges closed successfully")
        
        # Cancel any remaining background tasks
        tasks = [t for t in asyncio.all_tasks() if t != asyncio.current_task()]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} remaining tasks...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Small delay for final cleanup
        await asyncio.sleep(0.1)
        logger.info("Resource cleanup completed")
        
    except asyncio.TimeoutError:
        logger.warning("Resource cleanup timed out after 5 seconds")
    except Exception as e:
        logger.error(f"Error during resource cleanup: {e}")


async def main(symbol: Symbol, exchange_config: ExchangeConfig, quantity_usdt: float):
    logger = get_logger("rx_mm_demo")
    context = None
    
    try:
        # Run complete market making cycle with state machine
        buy_order, sell_order = await run_market_making_cycle(exchange_config, symbol, quantity_usdt, logger)
        
        print(f"\n✅✅✅ Cycle completed successfully!")
        print(f"  Buy order: {buy_order}")
        print(f"  Sell order: {sell_order}")
        
    except Exception as e:
        logger.error("Market making cycle failed", error=str(e))
        print(f"\n❌❌❌ Cycle failed: {e}")
        raise
    
    finally:
        print("\n🏁 Finalizing program...")
        await cleanup_resources(context, logger)


if __name__ == "__main__":

    exchange = "mexc_spot"
    config = get_exchange_config(exchange)
    quantity_usdt = 2.1
    # hack to get right symbol
    trading_symbol = Symbol(base=AssetName("HIFI"), quote=AssetName("USDT"), is_futures=config.is_futures)

    asyncio.run(main(trading_symbol, config, quantity_usdt))