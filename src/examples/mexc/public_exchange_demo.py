"""
MEXC Public Exchange Basic Demo

Simple demonstration of the refactored MexcPublicExchange showing
the hybrid architecture integration and basic functionality.

This demo focuses on:
- Exchange instantiation with hybrid architecture  
- Base class method availability
- Configuration and setup
- Basic API exploration

Safe for testing without network connectivity or real credentials.
"""

import asyncio
import logging
from typing import Dict, Any

from core.config.structs import ExchangeConfig, ExchangeCredentials, NetworkConfig, WebSocketConfig
from structs.exchange import Symbol, AssetName
from core.config import get_exchange_config
from cex.mexc.public_exchange import MexcPublicExchange



async def main():
    """Run the basic demo."""
    symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
               Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))]
    exchange = MexcPublicExchange(get_exchange_config("mexc"))
    await exchange.initialize(symbols)
    await asyncio.sleep(30)  # Wait for potential messages (if connected)
    await exchange.close()

if __name__ == "__main__":
    """
    Run the basic demo:
    
    PYTHONPATH=src python src/examples/mexc/public_exchange_demo.py
    
    This demo is safe to run without network connectivity or real API credentials.
    """
    asyncio.run(main())