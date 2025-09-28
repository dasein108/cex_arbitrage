#!/usr/bin/env python3
"""
Simple Order Placement Demo

Demonstrates basic order placement using the factory pattern:
- Limit orders with IOC and GTC time-in-force
- Market orders
- Minimal order quantities from symbol info
- Orderbook-based pricing (top bid - 10%)

Usage:
    PYTHONPATH=src python src/examples/demo/simple_order_placement_demo.py
"""

import asyncio
from typing import Optional, Literal, List

from config import get_exchange_config
from exchanges.utils import get_exchange_enum
from exchanges.factory import create_exchange_component
from exchanges.structs.common import Symbol, AssetName
from exchanges.structs import Side, TimeInForce, OrderType
from infrastructure.logging import get_logger

TestCase = Literal["limit_ioc", "limit_gtc", "market_quote_qty"]

async def main():
    """Simple order placement demonstration."""
    logger = get_logger("order_demo")

    # Configuration
    exchange_name = "gateio_spot"  # Change to desired exchange
    test_cases: List[TestCase] = ["limit_ioc", "limit_gtc", "market_quote_qty"] #
    try:
        # Get exchange configuration and enum
        config = get_exchange_config(exchange_name)
        exchange_enum = get_exchange_enum(exchange_name)
        symbol = Symbol(base=AssetName("ADA"), quote=AssetName("USDT"),
                        is_futures='_futures' in exchange_name.lower())

        logger.info("Starting order placement demo",
                   exchange=exchange_name, 
                   symbol=f"{symbol.base}/{symbol.quote}")
        
        # Create public REST component for market data
        public_rest = create_exchange_component(
            exchange_enum,
            config=config,
            is_private=False,
            component_type='rest'
        )
        
        # Create private REST component for trading
        private_rest = create_exchange_component(
            exchange_enum,
            config=config,
            is_private=True,
            component_type='rest'
        )
        
        # Get symbol information for minimum quantities
        logger.info("Fetching symbol information...")
        symbols_info = await public_rest.get_symbols_info()
        symbol_info = symbols_info.get(symbol)
        
        if not symbol_info:
            logger.error("Failed to get symbol info")
            return
            
        logger.info("Symbol info retrieved",
                   min_base_qty=symbol_info.min_base_quantity,
                   min_quote_qty=symbol_info.min_quote_quantity,
                   price_precision=symbol_info.quote_precision,
                   qty_precision=symbol_info.base_precision)
        
        # Get current orderbook for pricing
        logger.info("Fetching orderbook for pricing...")
        orderbook = await public_rest.get_orderbook(symbol)
        
        if not orderbook or not orderbook.bids:
            logger.error("Failed to get orderbook or no bids available")
            return
            
        top_bid = orderbook.bids[0].price
        # Calculate limit price: top bid - 10%
        limit_price = float(top_bid) * 0.9
        
        # Round to exchange precision
        # limit_price = round(limit_price, symbol_info.quote_precision)
        
        logger.info("Pricing calculated",
                   top_bid=top_bid,
                   limit_price=limit_price,
                   discount_pct="10%")
        
        # Use minimum base quantity for orders
        order_quantity = max(symbol_info.min_base_quantity, symbol_info.min_quote_quantity / limit_price + 0.01)
        
        # Round to exchange precision
        # order_quantity = round(order_quantity, symbol_info.base_precision)
        
        logger.info("Order quantity calculated", quantity=order_quantity)


        if 'limit_ioc'  in test_cases:
            # Demo 1: Limit order with IOC (Immediate or Cancel)
            logger.info("=== Demo 1: Limit Order with IOC ===")
            try:
                ioc_order = await private_rest.place_order(
                    symbol=symbol,
                    side=Side.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=order_quantity,
                    price=limit_price,
                    time_in_force=TimeInForce.IOC
                )
                logger.info("IOC limit order placed", order_id=ioc_order.order_id)
            except Exception as e:
                logger.error("IOC limit order failed", error=str(e))

            await asyncio.sleep(0.1)  # Brief pause between orders

        # Demo 2: Limit order with GTC (Good Till Cancelled)

        if 'limit_gtc' in test_cases:
            logger.info("=== Demo 2: Limit Order with GTC ===")
            try:
                gtc_order = await private_rest.place_order(
                    symbol=symbol,
                    side=Side.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=order_quantity,
                    price=limit_price,
                    time_in_force=TimeInForce.GTC
                )
                logger.info("GTC limit order placed", order_id=gtc_order.order_id)
            except Exception as e:
                logger.error("GTC limit order failed", error=str(e))

            await asyncio.sleep(0.1)  # Brief pause between orders
        
        # Demo 3: Market order using quantity (contracts)
        if 'market_quote_qty' in test_cases:
            logger.info("=== Demo 3: Market Order (Contracts) ===")
            try:
                # For futures market orders, use quantity (number of contracts) directly
                # This is more straightforward than converting from quote quantity
                market_quantity = max(symbol_info.min_base_quantity, 1.0)

                market_order = await private_rest.place_order(
                    symbol=symbol,
                    side=Side.BUY,
                    order_type=OrderType.MARKET,
                    quantity=market_quantity  # Use quantity for futures market orders
                )
                logger.info("Market order placed", order_id=market_order.order_id)
            except Exception as e:
                logger.error("Market order failed", error=str(e))

            await asyncio.sleep(0.1)  # Brief pause
        
    except Exception as e:
        logger.error("Demo failed", error=str(e))
        raise
    finally:
        # Cleanup connections
        try:
            if 'public_rest' in locals():
                await public_rest.close()
            if 'private_rest' in locals():
                await private_rest.close()
        except Exception as e:
            logger.error("Cleanup failed", error=str(e))


if __name__ == "__main__":
    asyncio.run(main())