

import asyncio
import sys
import os
from typing import Optional
from dataclasses import dataclass
import reactivex as rx
from reactivex import operators as ops

from config.structs import ExchangeConfig
from exchanges.interfaces.composite import BasePrivateComposite

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


def create_market_buy_stream(
    private_exchange: BasePrivateComposite,
    symbol: Symbol,
    quantity_usdt: float,
    ask_price_stream: rx.Observable[BookTicker],
    logger
) -> rx.Observable[Order]:
    """
    Create a stream that executes market buy order once.
    Fires only on the first ask price and completes after successful execution.
    
    Returns:
        Observable stream of executed order (emits once)
    """
    def execute_order(book_ticker: BookTicker):
        async def _execute():
            try:
                print(f"\n🛒 Executing LIVE market buy order at ask price {book_ticker.ask_price}...")
                
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
        
        return rx.from_future(asyncio.ensure_future(_execute()))
    
    return ask_price_stream.pipe(
        ops.take(1),  # Only take the first ask price
        ops.flat_map(execute_order)
    )


def create_limit_sell_on_top_stream(
    market_buy_stream: rx.Observable[Order],
    ask_price_stream: rx.Observable[BookTicker],
    orders_stream: rx.Observable[Order],
    private_exchange: BasePrivateComposite,
    symbol: Symbol,
    symbol_info: SymbolInfo,
    logger
) -> rx.Observable[Order]:
    """
    Create a stream that places/cancels limit sell orders until filled.
    Triggered when market buy order is executed.
    
    Places limit sell at ask_price - tick to be on top of the book.
    Cancels and replaces if price moves above our order.
    
    Returns:
        Observable stream of filled sell orders
    """
    
    def create_sell_cycle(market_buy_order: Order):
        """Create a sell cycle for a single market buy order."""
        print(f"\n📈 Starting limit sell cycle for quantity: {market_buy_order.filled_quantity}")
        
        # Local state for this sell cycle
        current_sell_order: Optional[Order] = None
        
        async def place_sell_order(ask_price: float):
            """Place a new limit sell order on top of the book."""
            nonlocal current_sell_order
            
            try:
                quantity = market_buy_order.filled_quantity
                sell_price = ask_price - symbol_info.tick
                
                order = await private_exchange.place_limit_order(
                    symbol=symbol,
                    side=Side.SELL,
                    quantity=quantity,
                    price=sell_price,
                    time_in_force=TimeInForce.GTC
                )
                
                print(f"   ✅ Limit sell order placed: {order} at price {sell_price}")
                current_sell_order = order
                return order
                
            except Exception as e:
                logger.error("Failed to place limit sell", error=str(e))
                print(f"   ❌ Limit sell placement failed: {e}")
                raise
        
        async def cancel_and_replace(ask_price: float, reason: str):
            """Cancel current order and place new one."""
            nonlocal current_sell_order
            
            if not current_sell_order:
                return await place_sell_order(ask_price)
            
            try:
                print(f"   ⚠️  {reason}, cancelling order {current_sell_order.order_id}")
                cancelled_order = await private_exchange.cancel_order(
                    current_sell_order.symbol, 
                    current_sell_order.order_id
                )
                
                # Check if order was filled during cancellation
                if is_order_filled(cancelled_order):
                    print(f"   ✅✅✅ Limit sell filled during cancel: {cancelled_order}")
                    current_sell_order = cancelled_order
                    return cancelled_order
                else:
                    # Place new order at new price
                    await asyncio.sleep(0.1)
                    return await place_sell_order(ask_price)
                    
            except Exception as e:
                logger.error("Failed to cancel/replace order", error=str(e))
                print(f"   ❌ Cancel/replace failed: {e}")
                raise
        
        def handle_sell_logic(combined_data):
            """Handle the sell order logic based on price and order updates."""
            ask_price, order_update = combined_data
            
            async def _handle():
                nonlocal current_sell_order
                
                # If we have an order update for our current sell order
                if order_update and current_sell_order and order_update.order_id == current_sell_order.order_id:
                    current_sell_order = order_update
                    
                    if is_order_filled(order_update):
                        print(f"   ✅✅✅ Limit sell order FILLED: {order_update}")
                        return ("filled", order_update)
                
                # If no order exists yet, place initial order
                if not current_sell_order:
                    order = await place_sell_order(ask_price.ask_price)
                    return ("placed", order)
                
                # If our price is not on top anymore, cancel and replace
                if current_sell_order.price > ask_price.ask_price:
                    order = await cancel_and_replace(
                        ask_price.ask_price, 
                        "Price moved above us"
                    )
                    if is_order_filled(order):
                        return ("filled", order)
                    return ("replaced", order)
                
                # Otherwise, just keep monitoring
                return ("monitoring", current_sell_order)
            
            return rx.from_future(asyncio.ensure_future(_handle()))
        
        # Combine ask price stream and order updates
        # Start with None to ensure we get initial ask price even without order updates
        orders_with_initial: rx.Observable[Optional[Order]] = orders_stream.pipe(
            ops.start_with(None)  # type: ignore
        )
        combined_stream = rx.combine_latest(
            ask_price_stream,
            orders_with_initial
        )
        
        # Process the combined stream until filled
        sell_cycle_stream = combined_stream.pipe(
            ops.flat_map(handle_sell_logic),  # Returns (state, order) tuples
            ops.take_while(lambda result: result[0] != "filled", inclusive=True),  # Continue until filled
            ops.filter(lambda result: result[0] == "filled"),  # Only emit the filled result
            ops.map(lambda result: result[1])  # Extract the order
        )
        
        return sell_cycle_stream
    
    # Create a new sell cycle for each market buy order
    return market_buy_stream.pipe(
        ops.map(create_sell_cycle),
        ops.switch_latest()
    )


@dataclass
class DemoStrategySetup:
    symbol: Symbol
    private_exchange: BasePrivateComposite
    symbol_info: SymbolInfo
    orders_stream: rx.Observable[Order]
    balance_stream: rx.Observable[AssetBalance]
    ask_price_stream: rx.Observable[BookTicker]
    quantity_usdt: float = 3  # Default quantity for buys

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
    return DemoStrategySetup(symbol,
                             private_exchange,
                             symbol_info,
                             orders_stream,
                             balance_stream,
                             ask_price_stream,
                             quantity_usdt)


async def run_market_making_cycle(
    demo_setup: DemoStrategySetup,
    logger
) -> tuple[Order, Order]:
    """
    Execute a complete market making cycle: buy -> sell.
    Returns when both orders are executed or raises exception on error.
    
    Returns:
        tuple of (market_buy_order, limit_sell_order)
    """
    # Create events to track completion
    cycle_complete = asyncio.Event()
    cycle_error: Optional[Exception] = None
    completed_orders = {}
    
    # Create market buy stream and share it to avoid multiple executions
    market_buy_stream = create_market_buy_stream(
        private_exchange=demo_setup.private_exchange,
        symbol=demo_setup.symbol,
        quantity_usdt=demo_setup.quantity_usdt,
        ask_price_stream=demo_setup.ask_price_stream,
        logger=logger
    ).pipe(
        ops.share()  # Share the stream so multiple subscriptions don't cause multiple executions
    )
    
    # Create limit sell stream that triggers when market buy completes
    limit_sell_stream = create_limit_sell_on_top_stream(
        market_buy_stream=market_buy_stream,
        ask_price_stream=demo_setup.ask_price_stream,
        orders_stream=demo_setup.orders_stream,
        private_exchange=demo_setup.private_exchange,
        symbol=demo_setup.symbol,
        symbol_info=demo_setup.symbol_info,
        logger=logger
    )
    
    # Merge both streams into a single pipeline
    # Note: We don't need to include market_buy_stream in merge since
    # it's already being consumed by limit_sell_stream
    complete_cycle_stream = rx.merge(
        market_buy_stream.pipe(
            ops.map(lambda order: ("buy", order))
        ),
        limit_sell_stream.pipe(
            ops.map(lambda order: ("sell", order))
        )
    )
    
    def on_next(event):
        order_type, order = event
        if order_type == "buy":
            print(f"📦 Market buy completed: {order}")
            completed_orders["buy"] = order
        elif order_type == "sell":
            print(f"💰 Limit sell completed: {order}")
            completed_orders["sell"] = order
            # Sell completes the cycle
            cycle_complete.set()
    
    def on_error(error):
        nonlocal cycle_error
        print(f"❌ Error in market making cycle: {error}")
        cycle_error = error
        cycle_complete.set()
    
    def on_completed():
        print("✅ Market making cycle stream completed")
        cycle_complete.set()
    
    # Subscribe to merged pipeline
    complete_cycle_stream.subscribe(
        on_next=on_next,
        on_error=on_error,
        on_completed=on_completed
    )
    
    # Wait for cycle to complete or error
    await cycle_complete.wait()
    
    # Check for errors
    if cycle_error:
        raise cycle_error
    
    # Return completed orders
    buy_order = completed_orders.get("buy")
    sell_order = completed_orders.get("sell")
    
    if not buy_order or not sell_order:
        raise RuntimeError(f"Cycle incomplete: buy={buy_order is not None}, sell={sell_order is not None}")
    
    return buy_order, sell_order


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
        # Cleanup connections if needed


        await asyncio.sleep(0.5)


if __name__ == "__main__":

    exchange = "mexc_spot"
    config = get_exchange_config(exchange)
    quantity_usdt = 2.1
    # hack to get right symbol
    trading_symbol = Symbol(base=AssetName("HIFI"), quote=AssetName("USDT"), is_futures=config.is_futures)

    asyncio.run(main(trading_symbol, config, quantity_usdt))