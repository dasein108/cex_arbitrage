"""
Unified REST API Demo

Combines public and private REST API demonstrations into a single script.
Eliminates code duplication between rest_public_demo.py and rest_private_demo.py.

Usage:
    python src/examples/demo/rest_api_demo.py mexc
    python src/examples/demo/rest_api_demo.py gateio --include-private
    python src/examples/demo/rest_api_demo.py mexc --include-private --timeout 60
"""

import asyncio
import argparse
import time
import sys
from typing import Dict, Any, List

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from exchanges.structs.enums import TimeInForce
from exchanges.structs import OrderType, Side

from ..base.demo_base import ExchangeDemoBase, RestDemoMixin
from ..utils.constants import DEFAULT_TEST_TIMEOUT


class RestApiDemo(ExchangeDemoBase, RestDemoMixin):
    """Unified REST API demo for both public and private endpoints."""
    
    def __init__(self, exchange_name: str):
        super().__init__(exchange_name)
        self.include_private = False
        self.timeout = DEFAULT_TEST_TIMEOUT
    
    async def run_public_tests(self) -> Dict[str, Any]:
        """Run all public API tests."""
        self.print_section("PUBLIC API TESTS")
        
        results = {}
        
        # Test ping
        results["ping"] = await self.test_ping()
        
        # Test server time
        results["server_time"] = await self.test_server_time()
        
        # Test exchange info
        results["exchange_info"] = await self.test_exchange_info()
        
        # Test orderbook
        results["orderbook"] = await self.test_orderbook()
        
        # Test recent trades
        results["recent_trades"] = await self.test_recent_trades()
        
        # Test historical trades
        results["historical_trades"] = await self.test_historical_trades()
        
        # Test ticker info
        results["ticker_info"] = await self.test_ticker_info()
        
        return results
    
    async def test_orderbook(self) -> Dict[str, Any]:
        """Test orderbook retrieval."""
        symbol = self.get_test_symbols()[0]  # Use first test symbol
        
        async def get_orderbook():
            result = await self.rest_client.get_orderbook(symbol, limit=5)
            
            # Structure the result
            bids_data = [{"price": bid.price, "size": bid.size} for bid in result.bids]
            asks_data = [{"price": ask.price, "size": ask.size} for ask in result.asks]
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "timestamp": result.timestamp,
                "bids_count": len(result.bids),
                "asks_count": len(result.asks),
                "bids": bids_data,
                "asks": asks_data
            }
        
        return await self.safe_execute("orderbook", get_orderbook)
    
    async def test_recent_trades(self) -> Dict[str, Any]:
        """Test recent trades retrieval."""
        symbol = self.get_test_symbols()[0]
        
        async def get_recent_trades():
            result = await self.rest_client.get_recent_trades(symbol, limit=5)
            
            # Structure the trade data
            trades_data = []
            for trade in result:
                trades_data.append({
                    "price": trade.price,
                    "quantity": trade.quantity,
                    "side": trade.side.name,
                    "timestamp": trade.timestamp,
                    "is_maker": trade.is_maker
                })
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "trades_count": len(result),
                "trades": trades_data
            }
        
        return await self.safe_execute("recent_trades", get_recent_trades)
    
    async def test_historical_trades(self) -> Dict[str, Any]:
        """Test historical trades retrieval."""
        symbol = self.get_test_symbols()[0]
        
        async def get_historical_trades():
            # Test with 24 hour time range
            now_ms = int(time.time() * 1000)
            from_ms = now_ms - (24 * 60 * 60 * 1000)
            
            result = await self.rest_client.get_historical_trades(
                symbol,
                limit=10,
                timestamp_from=from_ms,
                timestamp_to=now_ms
            )
            
            # Structure the trade data
            trades_data = []
            for trade in result[:5]:  # Show first 5 trades
                trades_data.append({
                    "price": trade.price,
                    "quantity": trade.quantity,
                    "side": trade.side.name,
                    "timestamp": trade.timestamp,
                    "trade_id": trade.trade_id,
                    "is_maker": trade.is_maker
                })
            
            # Check if exchange supports timestamp filtering
            supports_filtering = self.exchange_name.upper() != "MEXC"
            
            return {
                "symbol": f"{symbol.base}/{symbol.quote}",
                "trades_count": len(result),
                "timestamp_from": from_ms,
                "timestamp_to": now_ms,
                "supports_timestamp_filtering": supports_filtering,
                "sample_trades": trades_data
            }
        
        return await self.safe_execute("historical_trades", get_historical_trades)
    
    async def test_ticker_info(self) -> Dict[str, Any]:
        """Test ticker info retrieval."""
        symbol = self.get_test_symbols()[0]
        
        async def get_ticker_info():
            # Test single symbol ticker
            single_result = await self.rest_client.get_ticker_info(symbol)
            
            # Test all symbols ticker (limit for performance)
            all_result = await self.rest_client.get_ticker_info()
            
            # Extract single symbol data
            ticker = single_result.get(symbol)
            single_ticker_data = {}
            if ticker:
                single_ticker_data = {
                    "symbol": f"{ticker.symbol.base}/{ticker.symbol.quote}",
                    "last_price": ticker.last_price,
                    "price_change": ticker.price_change,
                    "price_change_percent": ticker.price_change_percent,
                    "high_price": ticker.high_price,
                    "low_price": ticker.low_price,
                    "volume": ticker.volume,
                    "quote_volume": ticker.quote_volume,
                    "bid_price": ticker.bid_price,
                    "ask_price": ticker.ask_price,
                    "open_time": ticker.open_time,
                    "close_time": ticker.close_time
                }
            
            # Sample from all symbols
            sample_tickers = []
            for i, (sym, tick) in enumerate(all_result.items()):
                if i >= 5:
                    break
                sample_tickers.append({
                    "symbol": f"{sym.base}/{sym.quote}",
                    "last_price": tick.last_price,
                    "price_change_percent": tick.price_change_percent,
                    "volume": tick.volume
                })
            
            return {
                "test_symbol": f"{symbol.base}/{symbol.quote}",
                "single_ticker_found": symbol in single_result,
                "single_ticker_data": single_ticker_data,
                "all_symbols_count": len(all_result),
                "sample_all_tickers": sample_tickers
            }
        
        return await self.safe_execute("ticker_info", get_ticker_info)
    
    async def run_private_tests(self) -> Dict[str, Any]:
        """Run all private API tests (requires credentials)."""
        self.print_section("PRIVATE API TESTS")
        
        results = {}
        
        # Test account balance
        results["account_balance"] = await self.test_account_balance()
        
        # Test asset balance
        results["asset_balance"] = await self.test_asset_balance()
        
        # Test open orders
        results["open_orders"] = await self.test_open_orders()
        
        # Test order lookup
        results["order_lookup"] = await self.test_order_lookup()
        
        # Test place order (small test order)
        results["place_order"] = await self.test_place_order()
        
        # Test cancel order
        results["cancel_order"] = await self.test_cancel_order()
        
        # Test cancel all orders
        results["cancel_all_orders"] = await self.test_cancel_all_orders()
        
        return results
    
    async def test_account_balance(self) -> Dict[str, Any]:
        """Test account balance retrieval."""
        async def get_account_balance():
            result = await self.rest_client.get_account_balance()
            
            # Show first 5 non-zero balances
            sample_balances = []
            for i, balance in enumerate(result[:5]):
                sample_balances.append({
                    "asset": balance.asset,
                    "free": balance.available,
                    "locked": balance.locked,
                    "total": balance.total
                })
            
            return {
                "total_balances": len(result),
                "sample_balances": sample_balances
            }
        
        return await self.safe_execute("account_balance", get_account_balance)
    
    async def test_asset_balance(self) -> Dict[str, Any]:
        """Test specific asset balance retrieval."""
        asset = AssetName('USDT')
        
        async def get_asset_balance():
            result = await self.rest_client.get_asset_balance(asset)
            
            if result:
                return {
                    "asset": asset,
                    "free": result.available,
                    "locked": result.locked,
                    "total": result.total,
                    "found": True
                }
            else:
                return {
                    "asset": asset,
                    "found": False
                }
        
        return await self.safe_execute("asset_balance", get_asset_balance)
    
    async def test_open_orders(self) -> Dict[str, Any]:
        """Test open orders retrieval."""
        async def get_open_orders():
            result = await self.rest_client.get_open_orders()
            
            # Show first 3 open orders
            sample_orders = []
            for i, order in enumerate(result[:3]):
                sample_orders.append({
                    "order_id": order.order_id,
                    "symbol": f"{order.symbol.base}/{order.symbol.quote}",
                    "side": order.side.name,
                    "order_type": order.order_type.name,
                    "quantity": order.quantity,
                    "price": order.price,
                    "status": order.status.name,
                    "filled": order.filled_quantity
                })
            
            return {
                "open_orders_count": len(result),
                "sample_orders": sample_orders
            }
        
        return await self.safe_execute("open_orders", get_open_orders)
    
    async def test_order_lookup(self) -> Dict[str, Any]:
        """Test order lookup (will likely fail with non-existent order)."""
        symbol = self.get_test_symbols()[0]
        order_id = "123456789"  # Non-existent order for testing
        
        async def get_order():
            try:
                result = await self.rest_client.get_order(symbol, order_id)
                return {
                    "order_found": True,
                    "order_id": result.order_id,
                    "symbol": f"{result.symbol.base}/{result.symbol.quote}",
                    "status": result.status.name
                }
            except Exception as e:
                return {
                    "order_found": False,
                    "error_message": str(e)
                }
        
        return await self.safe_execute("order_lookup", get_order)
    
    async def test_place_order(self) -> Dict[str, Any]:
        """Test order placement (small test order, likely to fail due to price/funds)."""
        symbol = Symbol(base=AssetName('ADA'), quote=AssetName('USDT'), is_futures=False)
        
        async def place_order():
            try:
                result = await self.rest_client.place_order(
                    symbol=symbol,
                    side=Side.BUY,
                    order_type=OrderType.LIMIT,
                    amount=0.01,
                    price=3000.0,  # Unrealistic price to avoid accidental execution
                    time_in_force=TimeInForce.GTC
                )
                
                return {
                    "order_placed": True,
                    "order_id": result.order_id,
                    "symbol": f"{result.symbol.base}/{result.symbol.quote}",
                    "side": result.side.name,
                    "amount": result.amount,
                    "price": result.price,
                    "status": result.status.name
                }
            except Exception as e:
                return {
                    "order_placed": False,
                    "error_message": str(e),
                    "note": "This is expected behavior for test orders"
                }
        
        return await self.safe_execute("place_order", place_order)
    
    async def test_cancel_order(self) -> Dict[str, Any]:
        """Test order cancellation (will likely fail with non-existent order)."""
        symbol = self.get_test_symbols()[0]
        order_id = "123456789"  # Non-existent order
        
        async def cancel_order():
            try:
                result = await self.rest_client.cancel_order(symbol, order_id)
                return {
                    "order_cancelled": True,
                    "order_id": result.order_id,
                    "status": result.status.name
                }
            except Exception as e:
                return {
                    "order_cancelled": False,
                    "error_message": str(e),
                    "note": "This is expected behavior for non-existent orders"
                }
        
        return await self.safe_execute("cancel_order", cancel_order)
    
    async def test_cancel_all_orders(self) -> Dict[str, Any]:
        """Test cancel all orders."""
        symbol = self.get_test_symbols()[0]
        
        async def cancel_all_orders():
            result = await self.rest_client.cancel_all_orders(symbol)
            
            cancelled_orders = []
            for order in result:
                cancelled_orders.append({
                    "order_id": order.order_id,
                    "symbol": f"{order.symbol.base}/{order.symbol.quote}",
                    "status": order.status.name
                })
            
            return {
                "cancelled_orders_count": len(result),
                "cancelled_orders": cancelled_orders
            }
        
        return await self.safe_execute("cancel_all_orders", cancel_all_orders)
    
    async def run_demo(self, **kwargs) -> Dict[str, Any]:
        """Run the complete REST API demo."""
        args = kwargs.get("args", [])
        
        # Parse arguments
        parser = argparse.ArgumentParser(description="Unified REST API Demo")
        parser.add_argument("exchange", nargs="?", default=self.exchange_name.lower(),
                          help="Exchange name (mexc, gateio)")
        parser.add_argument("--include-private", action="store_true",
                          help="Include private API tests (requires credentials)")
        parser.add_argument("--timeout", type=int, default=DEFAULT_TEST_TIMEOUT,
                          help="Timeout for operations in seconds")
        
        parsed_args = parser.parse_args(args)
        
        self.exchange_name = parsed_args.exchange.upper()
        self.include_private = parsed_args.include_private
        self.timeout = parsed_args.timeout
        
        # Print demo header
        demo_type = "PUBLIC + PRIVATE" if self.include_private else "PUBLIC"
        self.print_header(f"{self.exchange_name} REST API DEMO ({demo_type})")
        
        try:
            # Setup exchange (determine if private setup needed)
            await self.setup(
                need_rest=True,
                need_websocket=False,
                is_private=self.include_private
            )
            
            # Run public tests
            public_results = await self.run_public_tests()
            
            # Run private tests if requested
            private_results = {}
            if self.include_private:
                private_results = await self.run_private_tests()
            
            # Calculate success statistics
            all_results = {**public_results, **private_results}
            total_tests = len(all_results)
            successful_tests = len([r for r in all_results.values() if r.get("status") == "success"])
            
            self.logger.info(f"📊 Test Results Summary",
                           exchange=self.exchange_name,
                           total_tests=total_tests,
                           successful_tests=successful_tests,
                           success_rate=f"{(successful_tests/total_tests)*100:.1f}%")
            
            # Print demo footer
            self.print_footer(f"{self.exchange_name} REST API DEMO")
            
            return {
                "status": "success",
                "exchange": self.exchange_name,
                "demo_type": demo_type,
                "public_results": public_results,
                "private_results": private_results,
                "total_tests": total_tests,
                "successful_tests": successful_tests
            }
            
        except Exception as e:
            self.logger.error("Demo failed",
                            exchange=self.exchange_name,
                            error_message=str(e))
            return {
                "status": "error",
                "exchange": self.exchange_name,
                "error": str(e)
            }


if __name__ == "__main__":
    demo = RestApiDemo("mexc")  # Default, will be overridden by args
    sys.exit(asyncio.run(demo.main()))