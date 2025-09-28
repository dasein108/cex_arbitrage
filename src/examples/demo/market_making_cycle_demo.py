#!/usr/bin/env python3
"""
Unified Exchange Market Making single cycle Demo - LIVE TRADING

"""

import asyncio
import argparse
import sys
import os
import time
from typing import Optional, Dict, List

from config import get_exchange_config
from exchanges.utils.exchange_utils import get_exchange_enum, is_order_done, is_order_filled

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicSpotExchange
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.structs import (Side, TimeInForce, OrderStatus, AssetName, OrderId, Symbol, Order,
                               AssetBalance, OrderBook, BookTicker, SymbolInfo, ExchangeEnum)
from infrastructure.logging import get_logger, LoggingTimer
from exchanges.factory import create_exchange_component, get_symbol_mapper
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers, PrivateWebsocketHandlers


class UnifiedArbitrageDemo:
    """
    Simple arbitrage demo using unified exchange architecture.
    
    Strategy:
    1. Buy market order to acquire base currency
    2. Sell limit order at premium above current bid
    3. Monitor execution and balance changes via WebSocket events
    """

    def __init__(self,
                 exchange_name: str,
                 symbol_str: str,
                 quantity_usdt: float):
        """
        Initialize arbitrage demo for LIVE TRADING.
        
        Args:
            exchange_name: Exchange to use (mexc, gateio)
            symbol_str: Trading pair (e.g., BTCUSDT)
            quantity_usdt: Base quantity to trade in USDT
        """
        self.exchange_name = exchange_name
        self.quantity_usdt = quantity_usdt

        config = get_exchange_config(exchange_name)
        exchange_enum = get_exchange_enum(exchange_name)
        # since BTCUSDT is mexc native format, lil hack
        mexc_symbol = get_symbol_mapper(ExchangeEnum.MEXC).to_symbol(symbol_str)

        symbol = Symbol(base=mexc_symbol.base, quote=mexc_symbol.quote,
                        is_futures='_futures'in exchange_name.lower())
        self.symbol = symbol

        # Exchange
        private_handlers = PrivateWebsocketHandlers(
            order_handler=self._handle_order_update,
            balance_handler=self._handle_balance_update,
            execution_handler=self._handle_trade,
        )
        # public_handlers = PublicWebsocketHandlers
        private_exchange = create_exchange_component(exchange_enum,
                                                     config=config,
                                                     is_private=True,
                                                     component_type='composite',
                                                     handlers=private_handlers)

        public_handlers = PublicWebsocketHandlers(
            book_ticker_handler=self._handle_orderbook_update,
            trade_handler=self._handle_trade)

        public_exchange = create_exchange_component(exchange_enum,
                                                    config=config,
                                                    is_private=False,
                                                    component_type='composite',
                                                    handlers=public_handlers)

        self.public_exchange: Optional[CompositePublicSpotExchange] = public_exchange
        self.private_exchange: Optional[CompositePrivateSpotExchange] = private_exchange

        self.symbol_info: Optional[SymbolInfo] = None
        # Order tracking
        self.market_buy_order: Optional[Order] = None
        self.limit_sell_order: Optional[Order] = None
        self.orders: Dict[OrderId, Order] = {}
        self.book_ticker: BookTicker = BookTicker(symbol=self.symbol, bid_price=0.0, bid_quantity=0.0,
                                                    ask_price=0.0, ask_quantity=0.0, timestamp=0.0)

        # Balance tracking
        self.initial_balances: Dict[str, AssetBalance] = {}
        self.current_balances: Dict[str, AssetBalance] = {}

        # Performance metrics
        self.start_time = 0.0
        self.order_update_count = 0

        # Setup logging
        self.logger = get_logger('arbitrage.demo')

        self.logger.info("MM Cycle Demo initialized",
                         exchange=exchange_name,
                         symbol=str(symbol_str),
                         quantity=quantity_usdt,
                         mode="LIVE_TRADING")

    async def run_demo(self) -> None:
        """Run the complete arbitrage demo."""
        try:
            self.start_time = time.time()

            print(f"🚀 Starting MM Cycle Demo "
                  f": {self.exchange_name} | Symbol: {self.symbol} | Quantity: {self.quantity_usdt}")
            print("=" * 60)

            # Step 1: Initialize exchange
            await self._initialize_exchange()

            # Step 2: Get initial balances and market data
            await self._capture_initial_state()

            # Step 3: Execute market buy order
            await self._execute_market_buy()

            # Step 4: Wait for market buy execution
            await self._wait_for_market_buy_execution()

            # Step 5: Place limit sell order
            await self._handle_limit_sell_on_top()

            # Step 7: Show final results
            await self._show_results()

        except Exception as e:
            self.logger.error("Demo failed", error=str(e))
            print(f"❌ Demo failed: {e}")
            raise
        finally:
            # Cleanup
            await self._cleanup()

    async def _initialize_exchange(self) -> None:
        """Initialize the unified exchange with event handlers."""
        print("\n📡 Initializing exchange connection...")

        # Create exchange using config_manager pattern

        await self.public_exchange.initialize([self.symbol])
        await self.private_exchange.initialize(self.public_exchange.symbols_info)
        self.symbol_info = self.public_exchange.symbols_info.get(self.symbol)

    async def _capture_initial_state(self) -> None:
        """Capture initial balances and market data."""
        print("\n💰 Capturing initial state...")

        try:
            # Get initial balances
            self.initial_balances = self.private_exchange.balances
            self.current_balances = self.initial_balances.copy()

            base_asset = self.symbol.base
            quote_asset = self.symbol.quote

            base_balance = await self.private_exchange.get_asset_balance(self.symbol.base)
            quote_balance = await self.private_exchange.get_asset_balance(self.symbol.quote)
            self.book_ticker = await self.public_exchange.get_book_ticker(self.symbol)

            print(f"📊 Initial Balances: {base_balance}, {quote_balance}. Orderbook: {self.book_ticker}")

            # Check if we have enough quote balance for market buy
            if quote_balance.available < self.quantity_usdt:
                print(f"⚠️  Warning: Insufficient {quote_asset} balance for market buy")
                print(f"   - Required: ~{self.quantity_usdt:.8f}")
                print(f"   - Available: {quote_balance.available:.8f}")

        except Exception as e:
            self.logger.error("Failed to capture initial state", error=str(e))
            raise

    async def _execute_market_buy(self) -> None:
        """Execute market buy order to acquire base currency."""
        print(f"\n🛒 Executing LIVE market buy order...")

        try:
            quantity = self.quantity_usdt / self.book_ticker.ask_price
            order = await self.private_exchange.place_market_order(
                symbol=self.symbol,
                side=Side.BUY,
                quote_quantity=quantity
            )

            self.market_buy_order = order

            print(f"   ✅ Market buy order placed {order}")

        except Exception as e:
            self.logger.error("Failed to execute market buy", error=str(e))
            print(f"   ❌ Market buy failed: {e}")
            raise

    async def _wait_for_market_buy_execution(self) -> None:
        """Wait for market buy order to be executed."""
        print(f"\n⏱️  Waiting for market buy execution confirmation in async...")
        start_time = time.perf_counter()
        while not is_order_done(self.market_buy_order):
            o = self.market_buy_order

            executed_order = await self.private_exchange.get_active_order(o.symbol, o.order_id)
            if executed_order and is_order_done(executed_order):
                self.market_buy_order = executed_order

                elapsed = time.perf_counter() - start_time
                print(f"   ✅ Market buy executed successfully {o} vs {executed_order} TIME: {elapsed:.2f}s")
                break

    async def _handle_limit_sell_on_top(self) -> None:
        """Place limit sell order at premium above current bid."""
        print(f"\n📈 Start limit order sell on top...")

        while True:
            try:
                self.book_ticker = await self.public_exchange.get_book_ticker(self.symbol)
                if not self.limit_sell_order:
                    quantity = self.market_buy_order.filled_quantity
                    sell_price = self.book_ticker.ask_price - self.symbol_info.tick

                    order = await self.private_exchange.place_limit_order(
                        symbol=self.symbol,
                        side=Side.SELL,
                        quantity=quantity,
                        price=sell_price,
                        time_in_force=TimeInForce.GTC
                    )
                    print(f"   ✅ Limit sell order placed: {order}")
                    self.limit_sell_order = order
                else:
                    o = self.limit_sell_order
                    if is_order_filled(o):
                        print(f"   ✅✅✅ Limit sell executed: {o}")
                        break
                    if o.price >  self.book_ticker.ask_price:
                        o = await self.private_exchange.cancel_order(o.symbol, o.order_id)
                        self.limit_sell_order = o
                        print(f"   ⚠️  Limit sell price not on top, cancelled: {o}"'')
                        if is_order_filled(o):
                            print(f"   ✅ Limit sell executed during cancel: {o}")
                            break
                        else:
                            # trigger, replace at new top price
                            self.limit_sell_order = None

            except Exception as e:
                print(f"   ❌ Limit sell failed: {e}")
            finally:
                await asyncio.sleep(0.1)


    async def _show_results(self) -> None:
        """Show final demo results and statistics."""
        total_time = time.time() - self.start_time

        print(f"\n" + "=" * 60)
        print(f"🎉 Demo Results (Total time: {total_time:.2f}s)")
        # Order execution summary
        print(f"\n📋 Order Execution Summary:")
        print(f"   - Order updates: {self.order_update_count}")
        print(f"   - Market buy order: {self.market_buy_order}")
        print(f"   - Limit sell order: {self.limit_sell_order}")
        print(f"   - Orders tracked: {len(self.orders)}")
        print(f"   - Total time: {total_time:.2f}s")


    async def _cleanup(self) -> None:
        """Clean up orders and connections."""
        print(f"\n🧹 Cleaning up...")

        try:
            # Cancel any open orders
            open_orders = await self.private_exchange.get_open_orders(self.symbol, force=True)
            for order in open_orders:
                try:
                    await self.private_exchange.cancel_order(self.symbol, order.order_id)
                except Exception as e:
                    self.logger.warning("Failed to cancel order", order_id=order.order_id, error=str(e))

            # Close exchange connection
            await self.private_exchange.close()
            await self.public_exchange.close()
            print(f"   ✅ Exchange connection closed")

        except Exception as e:
            self.logger.error("Error during cleanup", error=str(e))
            print(f"   ⚠️  Cleanup error: {e}")

    # Event Handlers

    async def _handle_private_trade(self, trade) -> None:
        """Handle trade execution events from WebSocket."""
        if trade.symbol == self.symbol:
            return
        print(f"📢 Private Trade: {trade}")

    async def _handle_order_update(self, order: Order) -> None:
        """Handle order update events from WebSocket."""
        self.order_update_count += 1
        if order.symbol != self.symbol:
            return
        print(f"📢 Order Update Event: {order}")
        if self.market_buy_order and order.order_id == self.market_buy_order.order_id:
            self.market_buy_order = order
            print('Found market buy order update {self.market_buy_order} => {order}')
            if is_order_done(order):
                print(f"   ✅ Market buy executed: {order}")

        if self.limit_sell_order and order.order_id == self.limit_sell_order.order_id:
            self.limit_sell_order = order
            print('Found limit sell order update {self.market_buy_order} => {order}')
            if is_order_filled(self.limit_sell_order):
                print(f"   ✅✅ Websocket Limit buy executed: {order}")

    async def _handle_balance_update(self, balance: AssetBalance) -> None:
        """Handle balance update events from WebSocket."""
        if balance.asset not in [self.symbol.base, self.symbol.quote]:
            return
        # Update current balances
        old_balance = self.current_balances.get(balance.asset,
                                                AssetBalance(asset=balance.asset, available=0.0, locked=0.0))
        self.current_balances[balance.asset] = balance
        available_change = old_balance.available - balance.available

        print(f" 💰 Balance Update Event:: {balance.asset} change: {available_change:+.8f} = {balance}")

    async def _handle_orderbook_update(self, book_ticker: BookTicker) -> None:
        """Handle orderbook update events from WebSocket."""
        # Only log significant orderbook updates to avoid spam
        if book_ticker.symbol != self.symbol:
            return
        if self.book_ticker.ask_price != book_ticker.ask_price or self.book_ticker.bid_price != book_ticker.bid_price:
            self.book_ticker = book_ticker
            print(f"    - orderbook update {book_ticker}")

    async def _handle_trade(self, trade) -> None:
        """Handle trade execution events from WebSocket."""
        if trade.symbol != self.symbol:
            return
        print(f"    - public trade: {trade}")

async def main():
    """Main entry point for the demo."""
    parser = argparse.ArgumentParser(description="Unified Exchange Arbitrage Demo - LIVE TRADING")
    parser.add_argument("--exchange", default="gateio_futures", choices=["mexc_spot", "gateio_futures", "gateio_futures"],
                        help="Exchange to use (default: mexc_spot)")
    parser.add_argument("--symbol", default="ADAUSDT",
                        help="Trading pair symbol (default: ADAUSDT)")
    parser.add_argument("--quantity", type=float, default=3,
                        help="Quantity to trade in USDT (default: 1.5)")

    args = parser.parse_args()


    # Create and run demo
    demo = UnifiedArbitrageDemo(
        exchange_name=args.exchange,
        symbol_str=args.symbol,
        quantity_usdt=args.quantity
    )

    try:
        await demo.run_demo()
    except KeyboardInterrupt:
        print(f"\n\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
