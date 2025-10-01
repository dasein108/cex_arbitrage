

import asyncio
import sys
import os
from typing import Optional, List
from dataclasses import dataclass, field
import reactivex as rx
from reactivex import operators as ops
from reactivex.disposable import Disposable

from config.structs import ExchangeConfig
from exchanges.interfaces.composite import BasePrivateComposite, BasePublicComposite

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config import get_exchange_config
from exchanges.utils.exchange_utils import  is_order_filled
from exchanges.structs import (
    Side, TimeInForce, AssetName, Symbol, Order,
    AssetBalance, BookTicker, SymbolInfo
)
from infrastructure.logging import get_logger
from infrastructure.networking.websocket.structs import WebsocketChannelType
from exchanges.exchange_factory import get_composite_implementation


async def execute_market_buy(
    private_exchange: BasePrivateComposite,
    symbol: Symbol,
    quantity_usdt: float,
    current_ask_price: float,
    logger
) -> Order:
    """
    Execute a single market buy order.
    Simple async function - no reactive patterns needed for one-time operation.
    
    Returns:
        Executed order
    """
    try:
        print(f"\n🛒 Executing LIVE market buy order at ask price {current_ask_price}...")
        
        order = await private_exchange.place_market_order(
            symbol=symbol,
            side=Side.BUY,
            quote_quantity=quantity_usdt,
            ensure=True
        )
        
        print(f"   ✅ Market buy order placed: {order}")
        return order
        
    except Exception as e:
        logger.error("Failed to execute market buy", error=str(e))
        print(f"   ❌ Market buy failed: {e}")
        raise


async def place_sell_order(
    private_exchange: BasePrivateComposite,
    symbol: Symbol,
    symbol_info: SymbolInfo,
    quantity: float,
    ask_price: float,
    logger
) -> Order:
    """Place initial limit sell order on top of the book."""
    try:
        sell_price = ask_price - symbol_info.tick
        
        order = await private_exchange.place_limit_order(
            symbol=symbol,
            side=Side.SELL,
            quantity=quantity,
            price=sell_price,
            time_in_force=TimeInForce.GTC
        )
        
        print(f"   ✅ Limit sell order placed: {order} at price {sell_price}")
        return order
        
    except Exception as e:
        logger.error("Failed to place limit sell", error=str(e))
        print(f"   ❌ Limit sell placement failed: {e}")
        raise


async def cancel_and_replace_order(
    private_exchange: BasePrivateComposite,
    current_order: Order,
    new_ask_price: float,
    symbol_info: SymbolInfo,
    reason: str,
    logger
) -> Order:
    """Cancel current order and place new one at better price."""
    try:
        print(f"   ⚠️  {reason}, cancelling order {current_order.order_id}")
        cancelled_order = await private_exchange.cancel_order(
            current_order.symbol, 
            current_order.order_id
        )
        
        # Check if order was filled during cancellation
        if is_order_filled(cancelled_order):
            print(f"   ✅✅✅ Limit sell filled during cancel: {cancelled_order}")
            return cancelled_order
        
        # Place new order at new price
        await asyncio.sleep(0.1)
        return await place_sell_order(
            private_exchange=private_exchange,
            symbol=current_order.symbol,
            symbol_info=symbol_info,
            quantity=current_order.quantity,
            ask_price=new_ask_price,
            logger=logger
        )
        
    except Exception as e:
        logger.error("Failed to cancel/replace order", error=str(e))
        print(f"   ❌ Cancel/replace failed: {e}")
        raise


def create_sell_monitoring_stream(
    market_buy_order: Order,
    ask_price_stream: rx.Observable[BookTicker],
    orders_stream: rx.Observable[Order],
    private_exchange: BasePrivateComposite,
    symbol: Symbol,
    symbol_info: SymbolInfo,
    logger
) -> rx.Observable[Order]:
    """
    Monitor and manage limit sell order until filled.
    Uses RxPY where it adds value: combining price updates with order status.
    """
    print(f"\n📈 Starting limit sell cycle for quantity: {market_buy_order.filled_quantity}")
    
    # Track current sell order state
    current_sell_order: Optional[Order] = None
    
    def handle_price_and_order_update(combined_data):
        """Process price changes and order updates."""
        ask_price, order_update = combined_data
        
        async def _process_update():
            nonlocal current_sell_order
            
            # Update order state if we received an update for our order
            if order_update and current_sell_order and order_update.order_id == current_sell_order.order_id:
                current_sell_order = order_update
                if is_order_filled(order_update):
                    print(f"   ✅✅✅ Limit sell order FILLED: {order_update}")
                    return ("filled", order_update)
            
            # Place initial order if none exists
            if not current_sell_order:
                order = await place_sell_order(
                    private_exchange, symbol, symbol_info,
                    market_buy_order.filled_quantity, ask_price.ask_price, logger
                )
                current_sell_order = order
                return ("placed", order)
            
            # Replace order if price moved above us
            if current_sell_order.price > ask_price.ask_price:
                order = await cancel_and_replace_order(
                    private_exchange, current_sell_order, ask_price.ask_price,
                    symbol_info, "Price moved above us", logger
                )
                current_sell_order = order
                if is_order_filled(order):
                    return ("filled", order)
                return ("replaced", order)
            
            # Continue monitoring
            return ("monitoring", current_sell_order)
        
        return rx.from_future(asyncio.ensure_future(_process_update()))
    
    # Combine price stream with order updates (start with None for initial price)
    combined_stream = rx.combine_latest(
        ask_price_stream,
        orders_stream.pipe(ops.start_with(None))
    )
    
    # Process until order is filled
    return combined_stream.pipe(
        ops.flat_map(handle_price_and_order_update),
        ops.take_while(lambda result: result[0] != "filled", inclusive=True),
        ops.filter(lambda result: result[0] == "filled"),
        ops.map(lambda result: result[1])
    )


@dataclass
class SubscriptionTracker:
    """Track and cleanup ReactiveX subscriptions."""
    subscriptions: List[Disposable] = field(default_factory=list)
    
    def add(self, subscription: Disposable) -> None:
        """Add subscription for tracking."""
        self.subscriptions.append(subscription)
    
    def dispose_all(self) -> None:
        """Dispose all tracked subscriptions."""
        for sub in self.subscriptions:
            if sub and not sub.is_disposed:
                sub.dispose()
        self.subscriptions.clear()

@dataclass
class DemoStrategySetup:
    symbol: Symbol
    private_exchange: BasePrivateComposite
    public_exchange: BasePublicComposite  # Add for cleanup
    symbol_info: SymbolInfo
    orders_stream: rx.Observable[Order]
    balance_stream: rx.Observable[AssetBalance]
    ask_price_stream: rx.Observable[BookTicker]
    quantity_usdt: float = 3  # Default quantity for buys
    subscription_tracker: SubscriptionTracker = field(default_factory=SubscriptionTracker)

async def create_strategy_setup(exchange_config: ExchangeConfig, symbol: Symbol,
                                quantity_usdt: float) -> DemoStrategySetup:
    private_exchange: BasePrivateComposite = get_composite_implementation(exchange_config, is_private=True)
    public_exchange = get_composite_implementation(exchange_config, is_private=False)

    await public_exchange.initialize([symbol], [WebsocketChannelType.BOOK_TICKER])
    await private_exchange.initialize(public_exchange.symbols_info, [WebsocketChannelType.ORDER,
                                                                     WebsocketChannelType.BALANCE])

    await public_exchange.wait_until_connected()
    await private_exchange.wait_until_connected()
    await asyncio.sleep(1)

    symbol_info = public_exchange.symbols_info.get(symbol)

    # Setup reactive streams
    orders_stream = private_exchange.orders_stream.pipe(
        ops.filter(lambda o: o is not None and o.symbol == symbol)
    )
    balance_stream = private_exchange.balances_stream.pipe(
        ops.filter(lambda b: b is not None and b.asset in [symbol.base, symbol.quote])
    )

    # stream of top ask price changes for our symbol
    ask_price_stream = public_exchange.book_tickers_stream.pipe(
        ops.filter(lambda bt: bt.symbol == symbol),
        ops.distinct_until_changed(lambda bt: bt.ask_price)
    )
    return DemoStrategySetup(
        symbol=symbol,
        private_exchange=private_exchange,
        public_exchange=public_exchange,  # Include for cleanup
        symbol_info=symbol_info,
        orders_stream=orders_stream,
        balance_stream=balance_stream,
        ask_price_stream=ask_price_stream,
        quantity_usdt=quantity_usdt
    )


async def run_market_making_cycle(
    demo_setup: DemoStrategySetup,
    logger
) -> tuple[Order, Order]:
    """
    Execute a complete market making cycle: buy -> sell.
    Simplified sequential logic with RxPY only for ongoing monitoring.
    
    Returns:
        tuple of (market_buy_order, limit_sell_order)
    """
    # Step 1: Get current ask price and execute market buy
    current_ask_price = await get_current_ask_price(demo_setup.ask_price_stream)
    
    market_buy_order = await execute_market_buy(
        private_exchange=demo_setup.private_exchange,
        symbol=demo_setup.symbol,
        quantity_usdt=demo_setup.quantity_usdt,
        current_ask_price=current_ask_price,
        logger=logger
    )
    
    print(f"📦 Market buy completed: {market_buy_order}")
    
    # Step 2: Monitor sell order until filled using reactive patterns
    # This is where RxPY adds value - ongoing monitoring of price + order state
    sell_complete_event = asyncio.Event()
    sell_error: Optional[Exception] = None
    filled_sell_order: Optional[Order] = None
    
    def on_sell_filled(order: Order):
        nonlocal filled_sell_order
        print(f"💰 Limit sell completed: {order}")
        filled_sell_order = order
        sell_complete_event.set()
    
    def on_sell_error(error: Exception):
        nonlocal sell_error
        print(f"❌ Error in sell monitoring: {error}")
        sell_error = error
        sell_complete_event.set()
    
    # Start sell monitoring stream
    sell_stream = create_sell_monitoring_stream(
        market_buy_order=market_buy_order,
        ask_price_stream=demo_setup.ask_price_stream,
        orders_stream=demo_setup.orders_stream,
        private_exchange=demo_setup.private_exchange,
        symbol=demo_setup.symbol,
        symbol_info=demo_setup.symbol_info,
        logger=logger
    )
    
    subscription = sell_stream.subscribe(
        on_next=on_sell_filled,
        on_error=on_sell_error
    )
    
    demo_setup.subscription_tracker.add(subscription)
    
    try:
        # Wait for sell order to complete
        await sell_complete_event.wait()
        
        if sell_error:
            raise sell_error
        
        if not filled_sell_order:
            raise RuntimeError("Sell order monitoring completed without result")
        
        return market_buy_order, filled_sell_order
    
    finally:
        if subscription and not subscription.is_disposed:
            subscription.dispose()


async def get_current_ask_price(ask_price_stream: rx.Observable[BookTicker]) -> float:
    """Get the current ask price from the stream."""
    price_future = asyncio.Future()
    
    def on_price(book_ticker: BookTicker):
        if not price_future.done():
            price_future.set_result(book_ticker.ask_price)
    
    def on_error(error):
        if not price_future.done():
            price_future.set_exception(error)
    
    subscription = ask_price_stream.pipe(ops.take(1)).subscribe(
        on_next=on_price,
        on_error=on_error
    )
    
    try:
        return await price_future
    finally:
        if subscription and not subscription.is_disposed:
            subscription.dispose()


async def cleanup_resources(demo_setup: Optional[DemoStrategySetup], logger) -> None:
    """Properly cleanup all resources to ensure program termination."""
    if not demo_setup:
        logger.info("No demo setup to cleanup")
        return
        
    try:
        logger.info("Starting resource cleanup...")
        
        # Dispose all ReactiveX subscriptions first
        demo_setup.subscription_tracker.dispose_all()
        logger.info("Disposed all ReactiveX subscriptions")
        
        # Close exchange connections with timeout
        cleanup_tasks = []
        
        if demo_setup.private_exchange:
            cleanup_tasks.append(demo_setup.private_exchange.close())
            logger.info("Closing private exchange...")
        
        if demo_setup.public_exchange:
            cleanup_tasks.append(demo_setup.public_exchange.close())
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
    
    try:
        # Setup exchanges and streams
        demo_setup = await create_strategy_setup(exchange_config, symbol, quantity_usdt)
        
        # Run complete market making cycle
        print("🚀 Starting market making cycle...")
        buy_order, sell_order = await run_market_making_cycle(demo_setup, logger)
        
        print(f"\n✅✅✅ Cycle completed successfully!")
        print(f"  Buy order: {buy_order}")
        print(f"  Sell order: {sell_order}")
        
    except Exception as e:
        logger.error("Market making cycle failed", error=str(e))
        print(f"\n❌❌❌ Cycle failed: {e}")
        raise
    
    finally:
        print("\n🏁 Finalizing program...")
        await cleanup_resources(demo_setup if 'demo_setup' in locals() else None, logger)


if __name__ == "__main__":

    exchange = "mexc_spot"
    config = get_exchange_config(exchange)
    quantity_usdt = 2.1
    # hack to get right symbol
    trading_symbol = Symbol(base=AssetName("HIFI"), quote=AssetName("USDT"), is_futures=config.is_futures)

    asyncio.run(main(trading_symbol, config, quantity_usdt))