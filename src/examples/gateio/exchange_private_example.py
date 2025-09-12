#!/usr/bin/env python3
"""
Gate.io Exchange Interface Example (Private Trading Operations)

Demonstrates usage of the main GateioExchange class with full trading capabilities.
This example shows the high-level interface for both market data and trading operations.

Features demonstrated:
1. Exchange initialization with API credentials
2. Real-time balance monitoring
3. Order placement and management
4. Combined REST and WebSocket operations
5. Risk management and position tracking
6. Performance monitoring for trading operations

⚠️ REQUIRES API CREDENTIALS: You need valid Gate.io API key and secret.
Set credentials in config.yaml or provide them when initializing.

Usage:
    python -m src.examples.gateio.exchange_private_example
"""

import asyncio
import logging
from typing import Dict, List, Optional

from exchanges.gateio import GateioExchange
from exchanges.interface.structs import Symbol, AssetName, Side, OrderType, TimeInForce
from common.config import config


class TradingExample:
    """Example trading system using Gate.io exchange interface."""
    
    def __init__(self, api_key: str, secret_key: str):
        self.logger = logging.getLogger(__name__)
        self.exchange = GateioExchange(api_key=api_key, secret_key=secret_key)
        self.active_orders: Dict[str, dict] = {}
        
    async def demonstrate_full_trading_interface(self):
        """Demonstrate the complete trading interface."""
        
        # Define trading symbols
        trading_symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
        ]
        
        self.logger.info("Initializing Gate.io exchange with trading capabilities...")
        
        async with self.exchange.session(symbols=trading_symbols) as session:
            self.logger.info(f"Exchange session started: {session}")
            
            # Step 1: Check account balances
            await self._check_account_status(session)
            
            # Step 2: Monitor market data
            await self._monitor_market_data(session)
            
            # Step 3: Demonstrate order management
            await self._demonstrate_order_management(session)
            
            # Step 4: Risk management example
            await self._demonstrate_risk_management(session)
            
            # Step 5: Performance monitoring
            await self._show_performance_metrics(session)
    
    async def _check_account_status(self, exchange):
        """Check account balances and trading status."""
        
        self.logger.info("\n=== Account Status Check ===")
        
        try:
            # Get fresh balance data
            fresh_balances = await exchange.get_fresh_balances()
            
            # Show significant balances
            significant_balances = [
                (asset, balance) for asset, balance in fresh_balances.items() 
                if balance.total > 0.001
            ]
            
            self.logger.info(f"Account has {len(significant_balances)} assets with balance:")
            for asset, balance in significant_balances[:10]:
                self.logger.info(
                    f"  {asset}: {balance.total:.6f} "
                    f"(Available: {balance.available:.6f}, Locked: {balance.locked:.6f})"
                )
            
            # Check specific trading balances
            usdt_balance = exchange.get_asset_balance(AssetName("USDT"))
            btc_balance = exchange.get_asset_balance(AssetName("BTC"))
            
            if usdt_balance:
                self.logger.info(f"\nUSDT Balance: {usdt_balance.total:.2f} USDT")
                can_trade = usdt_balance.available >= 20  # Need at least $20
                self.logger.info(f"Can place test trades: {can_trade}")
            
            if btc_balance:
                self.logger.info(f"BTC Balance: {btc_balance.total:.6f} BTC")
            
        except Exception as e:
            self.logger.error(f"Failed to check account status: {e}")
    
    async def _monitor_market_data(self, exchange):
        """Monitor real-time market data."""
        
        self.logger.info("\n=== Market Data Monitoring ===")
        
        # Wait for initial market data
        self.logger.info("Collecting initial market data...")
        await asyncio.sleep(5)
        
        # Show current market prices
        all_orderbooks = exchange.get_all_orderbooks()
        
        market_data = {}
        for symbol, orderbook in all_orderbooks.items():
            if orderbook.bids and orderbook.asks:
                bid = orderbook.bids[0].price
                ask = orderbook.asks[0].price
                mid = (bid + ask) / 2
                spread = ask - bid
                spread_pct = (spread / mid) * 100
                
                market_data[symbol] = {
                    'bid': bid,
                    'ask': ask,
                    'mid': mid,
                    'spread': spread,
                    'spread_pct': spread_pct
                }
                
                self.logger.info(
                    f"{symbol.base}/{symbol.quote}: ${mid:,.2f} "
                    f"(Spread: ${spread:.2f} / {spread_pct:.3f}%)"
                )
        
        return market_data
    
    async def _demonstrate_order_management(self, exchange):
        """Demonstrate order placement and management."""
        
        self.logger.info("\n=== Order Management Demo ===")
        
        # Check if we have sufficient balance
        usdt_balance = exchange.get_asset_balance(AssetName("USDT"))
        
        if not usdt_balance or usdt_balance.available < 20:
            self.logger.info("Insufficient USDT balance for order demo (need $20+)")
            return
        
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        try:
            # Get current market price
            current_orderbook = exchange.get_orderbook(btc_usdt)
            if not current_orderbook or not current_orderbook.bids:
                self.logger.warning("No BTC/USDT market data available")
                return
            
            current_price = current_orderbook.bids[0].price
            self.logger.info(f"Current BTC price: ${current_price:,.2f}")
            
            # Place a limit buy order well below market (won't fill)
            safe_price = current_price * 0.8  # 20% below market
            order_amount = 0.0001  # Very small amount
            
            self.logger.info(f"Placing test limit buy order at ${safe_price:,.2f}...")
            
            # Example 1: Limit order
            limit_order = await exchange.place_limit_order(
                symbol=btc_usdt,
                side=Side.BUY,
                amount=order_amount,
                price=safe_price,
                time_in_force=TimeInForce.GTC
            )
            
            self.logger.info(f"✅ Limit order placed: {limit_order.order_id}")
            self.active_orders[limit_order.order_id] = {
                'order': limit_order,
                'type': 'limit_buy'
            }
            
            # Check order status
            await asyncio.sleep(2)
            
            order_status = await exchange.get_order_status(btc_usdt, limit_order.order_id)
            self.logger.info(f"Order status: {order_status.status.name}")
            
            # Modify order example (cancels and replaces)
            self.logger.info("Demonstrating order modification...")
            new_price = safe_price * 0.95  # Even lower price
            
            modified_order = await exchange.modify_order(
                symbol=btc_usdt,
                order_id=limit_order.order_id,
                new_price=new_price
            )
            
            self.logger.info(f"✅ Order modified: {modified_order.order_id}")
            self.active_orders[modified_order.order_id] = {
                'order': modified_order,
                'type': 'modified_limit_buy'
            }
            
            # Clean up test orders
            self.logger.info("Cleaning up test orders...")
            cancelled_order = await exchange.cancel_order(btc_usdt, modified_order.order_id)
            self.logger.info(f"✅ Order cancelled: {cancelled_order.order_id}")
            
        except Exception as e:
            self.logger.error(f"Order management demo failed: {e}")
    
    async def _demonstrate_risk_management(self, exchange):
        """Demonstrate risk management practices."""
        
        self.logger.info("\n=== Risk Management Demo ===")
        
        # Check all open orders
        open_orders = await exchange.get_open_orders()
        self.logger.info(f"Current open orders: {len(open_orders)}")
        
        if open_orders:
            total_exposure = 0
            for order in open_orders:
                if order.side == Side.BUY:
                    exposure = order.amount * order.price
                    total_exposure += exposure
                    
                    self.logger.info(
                        f"  Buy Order: {order.amount} {order.symbol.base} @ "
                        f"${order.price:.2f} = ${exposure:.2f} exposure"
                    )
            
            self.logger.info(f"Total buy exposure: ${total_exposure:.2f}")
        
        # Balance allocation check
        usdt_balance = exchange.get_asset_balance(AssetName("USDT"))
        if usdt_balance:
            total_usdt = usdt_balance.total
            available_usdt = usdt_balance.available
            locked_usdt = usdt_balance.locked
            
            if total_usdt > 0:
                utilization = (locked_usdt / total_usdt) * 100
                self.logger.info(f"USDT Utilization: {utilization:.1f}% locked in orders")
        
        # Example risk limits (educational)
        self.logger.info("Example risk limits:")
        self.logger.info("  - Maximum 10% of portfolio per trade")
        self.logger.info("  - Maximum 50% total position exposure")
        self.logger.info("  - Stop loss at -5% per position")
        self.logger.info("  - Daily loss limit: -2% of portfolio")
    
    async def _show_performance_metrics(self, exchange):
        """Show performance metrics and statistics."""
        
        self.logger.info("\n=== Performance Metrics ===")
        
        # Exchange performance metrics
        metrics = exchange.get_performance_metrics()
        
        self.logger.info("Exchange Performance:")
        for key, value in metrics.items():
            self.logger.info(f"  {key}: {value}")
        
        # Trading session summary
        self.logger.info(f"\nTrading Session Summary:")
        self.logger.info(f"  Active symbols: {len(exchange.active_symbols)}")
        self.logger.info(f"  Orders placed: {len(self.active_orders)}")
        self.logger.info(f"  WebSocket status: Connected")
        
        # Real-time data freshness
        latest_orderbook = exchange.orderbook
        if latest_orderbook.timestamp:
            import time
            age = time.time() - latest_orderbook.timestamp
            self.logger.info(f"  Latest orderbook age: {age:.2f} seconds")


async def demonstrate_error_recovery():
    """Demonstrate error handling and recovery mechanisms."""
    
    logger = logging.getLogger(__name__)
    
    logger.info("\n=== Error Recovery Demo ===")
    
    # Test with invalid credentials
    logger.info("Testing invalid credentials handling...")
    
    invalid_exchange = GateioExchange(api_key="invalid", secret_key="invalid")
    
    try:
        async with invalid_exchange.session() as session:
            # This should fail gracefully
            await session.get_fresh_balances()
    except Exception as e:
        logger.info(f"Expected error for invalid credentials: {type(e).__name__}")
    
    logger.info("Error recovery demo completed")


def main():
    """Main entry point."""
    print("Gate.io Exchange Interface Example (Private Trading)")
    print("=" * 60)
    print("This example demonstrates full trading capabilities with Gate.io.")
    print("⚠️  REQUIRES API CREDENTIALS - Set in config.yaml")
    print()
    
    # Check for credentials
    if not config.has_gateio_credentials():
        print("❌ Gate.io API credentials not found!")
        print()
        print("Please configure your API credentials:")
        print("1. Edit config.yaml and add your Gate.io API key and secret")
        print("2. Or set environment variables GATEIO_API_KEY and GATEIO_SECRET_KEY")
        print()
        print("API Key Requirements:")
        print("  - Spot Trading permission enabled")
        print("  - Sufficient account balance for test trades")
        print("  - API key restrictions configured appropriately")
        return
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Create trading example instance
        trading_system = TradingExample(
            api_key=config.GATEIO_API_KEY,
            secret_key=config.GATEIO_SECRET_KEY
        )
        
        # Run full demonstration
        asyncio.run(trading_system.demonstrate_full_trading_interface())
        
        # Run error recovery demo
        asyncio.run(demonstrate_error_recovery())
        
        print("\n✅ All private exchange examples completed successfully!")
        
        print("\nKey Trading Features Demonstrated:")
        print("  - Real-time balance monitoring")
        print("  - Limit order placement and modification")
        print("  - Order status tracking")
        print("  - Risk management practices")
        print("  - Error handling and recovery")
        print("  - Performance metrics monitoring")
        
        print("\n⚠️  Trading Reminders:")
        print("  - Always test with small amounts first")
        print("  - Implement proper risk management")
        print("  - Monitor API rate limits")
        print("  - Keep API credentials secure")
        print("  - Use testnet for development when available")
        
    except KeyboardInterrupt:
        print("\n⚠️ Examples interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Examples failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()