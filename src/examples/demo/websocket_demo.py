"""
Unified WebSocket Demo

Combines public and private WebSocket demonstrations into a single script.
Eliminates code duplication between websocket_public_demo.py and websocket_private_demo.py.

Usage:
    python src/examples/demo/websocket_demo.py mexc
    python src/examples/demo/websocket_demo.py gateio --include-private
    python src/examples/demo/websocket_demo.py mexc --include-private --duration 60
"""

import asyncio
import argparse
import sys
from typing import Dict, Any, List

from exchanges.structs.common import Symbol
from exchanges.factory import create_websocket_client, create_public_handlers, create_private_handlers
from exchanges.utils.exchange_utils import get_exchange_enum

from ..base.demo_base import ExchangeDemoBase, WebSocketDemoMixin
from ..utils.constants import DEFAULT_MONITOR_DURATION


class WebSocketDemo(ExchangeDemoBase, WebSocketDemoMixin):
    """Unified WebSocket demo for both public and private channels."""
    
    def __init__(self, exchange_name: str):
        super().__init__(exchange_name)
        WebSocketDemoMixin.__init__(self)
        self.include_private = False
        self.duration = DEFAULT_MONITOR_DURATION
        self.symbols = []
    
    async def run_public_demo(self, symbols: List[Symbol]) -> Dict[str, Any]:
        """Run public WebSocket demo."""
        self.print_section("PUBLIC WEBSOCKET DEMO")
        
        try:
            # Setup data manager
            self.setup_data_manager()
            
            # Create public WebSocket client
            exchange_enum = get_exchange_enum(self.exchange_name)
            handlers = create_public_handlers(
                orderbook_diff_handler=self.data_manager.handle_orderbook_update,
                trades_handler=self.data_manager.handle_trade_update,
                book_ticker_handler=self.data_manager.handle_book_ticker_update
            )
            
            self.websocket_client = create_websocket_client(
                exchange=exchange_enum,
                is_private=False,
                config=self.config,
                handlers=handlers
            )
            
            self.logger.info("Public WebSocket client initialized",
                           exchange=self.exchange_name,
                           websocket_class=type(self.websocket_client).__name__)
            
            # Initialize connection with symbols
            self.logger.info("🔌 Testing WebSocket factory architecture",
                           exchange=self.exchange_name)
            await self.websocket_client.initialize(symbols)
            
            # Monitor for market data
            self.logger.info("⏳ Monitoring WebSocket connection",
                           exchange=self.exchange_name,
                           duration_seconds=self.duration)
            self.logger.info("💡 Expecting market data updates",
                           symbol_count=len(symbols))
            await asyncio.sleep(self.duration)
            
            # Get performance metrics
            performance_summary = self.get_websocket_performance_summary()
            connection_metrics = performance_summary.get("connection_metrics", {})
            data_summary = performance_summary.get("data_summary", {})
            
            self.logger.info("📊 WebSocket Performance Metrics",
                           connection_state=connection_metrics.get('connection_state', 'Unknown'),
                           messages_processed=connection_metrics.get('messages_processed', 0),
                           error_count=connection_metrics.get('error_count', 0),
                           uptime_seconds=connection_metrics.get('connection_uptime_seconds', 0))
            
            self.logger.info("📈 Data Summary",
                           **data_summary)
            
            # Show sample data
            self._show_sample_public_data(symbols, data_summary)
            
            # Determine success
            total_updates = (data_summary.get('total_orderbook_updates', 0) + 
                           data_summary.get('total_trade_updates', 0) + 
                           data_summary.get('total_book_ticker_updates', 0))
            
            if total_updates > 0:
                self.logger.info("✅ Public WebSocket demo successful!",
                               exchange=self.exchange_name)
                self.logger.info("🎉 Received real-time market data")
            else:
                self.logger.info("ℹ️  No market data received",
                               exchange=self.exchange_name)
                self.logger.info("✅ WebSocket connection and subscription working correctly")
                self.logger.info("💡 This may be normal if markets are quiet or symbols are inactive")
            
            return {
                "status": "success",
                "type": "public",
                "symbols_monitored": len(symbols),
                "monitor_duration": self.duration,
                "connection_metrics": connection_metrics,
                "data_summary": data_summary,
                "data_received": total_updates > 0
            }
            
        except Exception as e:
            self.logger.error("Public WebSocket demo failed",
                            exchange=self.exchange_name,
                            error_message=str(e))
            return {
                "status": "error",
                "type": "public",
                "error": str(e)
            }
        finally:
            if self.websocket_client:
                await self.websocket_client.close()
                self.websocket_client = None
    
    async def run_private_demo(self) -> Dict[str, Any]:
        """Run private WebSocket demo (requires credentials)."""
        self.print_section("PRIVATE WEBSOCKET DEMO")
        
        try:
            # Setup data manager
            self.setup_data_manager()
            
            # Create private WebSocket client
            exchange_enum = get_exchange_enum(self.exchange_name)
            handlers = create_private_handlers(
                order_handler=self._handle_order_update,
                balance_handler=self.data_manager.handle_balance_update,
                trade_handler=self._handle_private_trade_update
            )
            
            self.websocket_client = create_websocket_client(
                exchange=exchange_enum,
                is_private=True,
                config=self.config,
                handlers=handlers
            )
            
            self.logger.info("Private WebSocket client initialized",
                           exchange=self.exchange_name,
                           websocket_class=type(self.websocket_client).__name__)
            
            # Initialize connection (empty symbols list for private)
            self.logger.info("🔌 Testing private WebSocket factory architecture",
                           exchange=self.exchange_name)
            await self.websocket_client.initialize([])
            
            # Monitor for private data
            self.logger.info("⏳ Monitoring private WebSocket connection",
                           exchange=self.exchange_name,
                           duration_seconds=self.duration)
            self.logger.info("💡 Note: Private WebSocket only sends data during account activity")
            self.logger.info("   (trades, balance changes, order updates, deposits, withdrawals, etc.)")
            await asyncio.sleep(self.duration)
            
            # Get performance metrics
            performance_summary = self.get_websocket_performance_summary()
            connection_metrics = performance_summary.get("connection_metrics", {})
            data_summary = performance_summary.get("data_summary", {})
            
            self.logger.info("📊 WebSocket Performance Metrics",
                           connection_state=connection_metrics.get('connection_state', 'Unknown'),
                           messages_processed=connection_metrics.get('messages_processed', 0),
                           error_count=connection_metrics.get('error_count', 0),
                           uptime_seconds=connection_metrics.get('connection_uptime_seconds', 0))
            
            self.logger.info("📈 Private Data Summary",
                           **data_summary)
            
            # Show sample private data
            self._show_sample_private_data(data_summary)
            
            # Determine success
            total_updates = (data_summary.get('total_balance_updates', 0) + 
                           data_summary.get('error_count', 0))  # Include connection events
            
            if total_updates > 0:
                self.logger.info("✅ Private WebSocket demo successful!",
                               exchange=self.exchange_name)
                self.logger.info("🎉 Received private account data - your account has activity!")
            else:
                self.logger.info(f"ℹ️  No private messages received from {self.exchange_name} - this is NORMAL behavior",
                               exchange=self.exchange_name)
                self.logger.info("✅ Private WebSocket connection and authentication working correctly")
                self.logger.info(f"💡 To see private messages, perform trading activity in your {self.exchange_name} account")
                self.logger.info("   (place orders, make trades, deposits, withdrawals, etc.)")
            
            return {
                "status": "success",
                "type": "private",
                "monitor_duration": self.duration,
                "connection_metrics": connection_metrics,
                "data_summary": data_summary,
                "data_received": total_updates > 0
            }
            
        except Exception as e:
            self.logger.error("Private WebSocket demo failed",
                            exchange=self.exchange_name,
                            error_message=str(e))
            return {
                "status": "error",
                "type": "private",
                "error": str(e)
            }
        finally:
            if self.websocket_client:
                await self.websocket_client.close()
                self.websocket_client = None
    
    def _show_sample_public_data(self, symbols: List[Symbol], data_summary: Dict[str, Any]) -> None:
        """Show sample public market data."""
        if not symbols or not self.data_manager:
            return
        
        symbol = symbols[0]
        
        # Show latest orderbook
        orderbook = self.data_manager.get_orderbook(symbol)
        if orderbook and orderbook.bids and orderbook.asks:
            best_bid = orderbook.bids[0].price
            best_ask = orderbook.asks[0].price
            spread = best_ask - best_bid
            
            self.logger.info("💰 Latest orderbook",
                           symbol=f"{symbol.base}/{symbol.quote}",
                           best_bid=best_bid,
                           best_ask=best_ask,
                           spread=spread)
        
        # Show recent trades
        recent_trades = self.data_manager.get_trades(symbol, limit=3)
        if recent_trades:
            self.logger.info("🔄 Recent trades",
                           symbol=f"{symbol.base}/{symbol.quote}",
                           trade_count=len(recent_trades))
            for i, trade in enumerate(recent_trades, 1):
                self.logger.info("Recent trade",
                                 trade_number=i,
                                 side=trade.side.name,
                                 quantity=trade.quantity,
                                 price=trade.price)
        
        # Show latest book ticker
        book_ticker = self.data_manager.get_book_ticker(symbol)
        if book_ticker:
            spread = book_ticker.ask_price - book_ticker.bid_price
            spread_percentage = (spread / book_ticker.bid_price) * 100 if book_ticker.bid_price else 0
            
            self.logger.info("📊 Latest book ticker",
                           symbol=f"{symbol.base}/{symbol.quote}",
                           bid_price=book_ticker.bid_price,
                           bid_quantity=book_ticker.bid_quantity,
                           ask_price=book_ticker.ask_price,
                           ask_quantity=book_ticker.ask_quantity,
                           spread=spread,
                           spread_percentage=spread_percentage)
    
    def _show_sample_private_data(self, data_summary: Dict[str, Any]) -> None:
        """Show sample private account data."""
        if not self.data_manager:
            return
        
        # Show non-zero balances
        balances = self.data_manager.get_non_zero_balances()
        if balances:
            self.logger.info(f"💰 Current Balances ({len(balances)} assets)")
            for asset, balance in list(balances.items())[:5]:  # Show first 5
                self.logger.info("Asset balance",
                                 asset=asset,
                                 free=balance.available,
                                 locked=balance.locked,
                                 total=balance.total)
    
    async def _handle_order_update(self, order) -> None:
        """Handle private order updates."""
        self.logger.info("📋 Order update",
                       exchange=self.exchange_name,
                       order_id=getattr(order, 'order_id', 'Unknown'),
                       status=getattr(order, 'status', 'Unknown'))
        
        # Track in data manager
        self.data_manager.handle_connection_event("order_update", {
            "order_id": getattr(order, 'order_id', 'Unknown'),
            "status": getattr(order, 'status', 'Unknown')
        })
    
    async def _handle_private_trade_update(self, trade) -> None:
        """Handle private trade updates."""
        self.logger.info("💹 Private trade update",
                       exchange=self.exchange_name,
                       trade_data=str(trade))
        
        # Track in data manager
        self.data_manager.handle_connection_event("trade_update", trade)
    
    async def run_demo(self, **kwargs) -> Dict[str, Any]:
        """Run the complete WebSocket demo."""
        args = kwargs.get("args", [])
        
        # Parse arguments
        parser = argparse.ArgumentParser(description="Unified WebSocket Demo")
        parser.add_argument("exchange", nargs="?", default=self.exchange_name.lower(),
                          help="Exchange name (mexc, gateio)")
        parser.add_argument("--include-private", action="store_true",
                          help="Include private WebSocket demo (requires credentials)")
        parser.add_argument("--duration", type=int, default=DEFAULT_MONITOR_DURATION,
                          help="Monitor duration in seconds")
        parser.add_argument("--extended-symbols", action="store_true",
                          help="Use extended symbol list for testing")
        
        parsed_args = parser.parse_args(args)
        
        self.exchange_name = parsed_args.exchange.upper()
        self.include_private = parsed_args.include_private
        self.duration = parsed_args.duration
        self.symbols = self.get_test_symbols(extended=parsed_args.extended_symbols)
        
        # Print demo header
        demo_type = "PUBLIC + PRIVATE" if self.include_private else "PUBLIC"
        self.print_header(f"{self.exchange_name} WEBSOCKET DEMO ({demo_type})")
        
        try:
            # Setup exchange (determine if private setup needed)
            await self.setup(
                need_rest=False,
                need_websocket=False,  # We'll create WebSocket clients manually
                is_private=self.include_private
            )
            
            # Run public demo
            public_results = await self.run_public_demo(self.symbols)
            
            # Run private demo if requested
            private_results = {}
            if self.include_private:
                private_results = await self.run_private_demo()
            
            # Print demo footer
            self.print_footer(f"{self.exchange_name} WEBSOCKET DEMO")
            
            return {
                "status": "success",
                "exchange": self.exchange_name,
                "demo_type": demo_type,
                "public_results": public_results,
                "private_results": private_results,
                "symbols_tested": len(self.symbols),
                "monitor_duration": self.duration
            }
            
        except Exception as e:
            self.logger.error("WebSocket demo failed",
                            exchange=self.exchange_name,
                            error_message=str(e))
            return {
                "status": "error",
                "exchange": self.exchange_name,
                "error": str(e)
            }


if __name__ == "__main__":
    demo = WebSocketDemo("mexc")  # Default, will be overridden by args
    sys.exit(asyncio.run(demo.main()))