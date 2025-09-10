#!/usr/bin/env python3
"""
Example of using MEXC WebSocket with the public exchange interface
"""

import asyncio
import logging
from typing import Dict, Any

from exchanges.mexc.websocket import MexcWebSocketPublicStream
from exchanges.mexc.mexc_public import MexcPublicExchange
from structs.exchange import Symbol, AssetName, ExchangeName, StreamType

logging.basicConfig(level=logging.INFO)


class MexcStreamManager:
    """High-level manager combining public exchange and WebSocket streams"""
    
    def __init__(self, api_key: str = None, secret_key: str = None):
        self.public_exchange = MexcPublicExchange()
        self.websocket: MexcWebSocketPublicStream = None
        self.symbols: Dict[str, Symbol] = {}
        
    async def init(self, symbols: list[Symbol]):
        """Initialize with symbols of interest"""
        await self.public_exchange.init(symbols)
        
        # Store symbol mapping
        for symbol in symbols:
            symbol_str = await self.public_exchange.symbol_to_pair(symbol)
            self.symbols[symbol_str.lower()] = symbol
            
        # Create WebSocket
        self.websocket = MexcWebSocketPublicStream(
            exchange_name=ExchangeName("MEXC"),
            on_message=self._handle_stream_message,
            on_connected=self._on_connected,
            timeout=30.0
        )
        
    async def _handle_stream_message(self, message: Dict[str, Any]):
        """Handle incoming stream messages"""
        stream_type = message.get('stream_type')
        symbol = message.get('symbol')
        
        if stream_type == StreamType.TRADES.value:
            await self._handle_trades(symbol, message['data'])
        elif stream_type == StreamType.ORDERBOOK.value:
            await self._handle_orderbook(symbol, message['data'])
        else:
            logging.info(f"Unknown message type: {message}")
            
    async def _handle_trades(self, symbol: Symbol, trades: list):
        """Process trade updates"""
        logging.info(f"[{symbol.base}/{symbol.quote}] Received {len(trades)} trades")
        for trade in trades:
            logging.debug(f"  Trade: {trade.price} @ {trade.amount} ({trade.side.value})")
            
    async def _handle_orderbook(self, symbol: Symbol, orderbook):
        """Process orderbook updates"""
        logging.info(f"[{symbol.base}/{symbol.quote}] Orderbook update - "
                    f"Bids: {len(orderbook.bids)}, Asks: {len(orderbook.asks)}")
        
        if orderbook.bids:
            best_bid = max(orderbook.bids, key=lambda x: x.price)
            logging.debug(f"  Best bid: {best_bid.price} @ {best_bid.size}")
            
        if orderbook.asks:
            best_ask = min(orderbook.asks, key=lambda x: x.price)
            logging.debug(f"  Best ask: {best_ask.price} @ {best_ask.size}")
            
    async def _on_connected(self):
        """Called when WebSocket connects"""
        logging.info("WebSocket connected - subscribing to streams")
        
        # Subscribe to all symbols
        streams = []
        for symbol_str in self.symbols.keys():
            streams.extend([
                f"{symbol_str}@deal",   # Trades
                f"{symbol_str}@depth"   # Orderbook
            ])
            
        await self.websocket.subscribe(streams)
        
    async def start_streaming(self):
        """Start streaming data"""
        logging.info("Starting stream manager...")
        
        try:
            # Keep running
            while True:
                await asyncio.sleep(1)
                
                # Log health status every 30 seconds
                if hasattr(self, '_last_health_log'):
                    if asyncio.get_event_loop().time() - self._last_health_log > 30:
                        health = self.websocket.get_health_status()
                        logging.info(f"Health: {health}")
                        self._last_health_log = asyncio.get_event_loop().time()
                else:
                    self._last_health_log = asyncio.get_event_loop().time()
                    
        except KeyboardInterrupt:
            logging.info("Stopping stream manager...")
        finally:
            if self.websocket:
                await self.websocket.stop()


async def main():
    """Example usage"""
    # Define symbols to track
    symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
        Symbol(base=AssetName("BNB"), quote=AssetName("USDT"))
    ]
    
    # Create and initialize manager
    manager = MexcStreamManager()
    await manager.init(symbols)
    
    # Start streaming
    await manager.start_streaming()


if __name__ == "__main__":
    asyncio.run(main())