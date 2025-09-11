#!/usr/bin/env python3
"""
Example of using MEXC WebSocket with the public exchange interface
"""

import asyncio
import logging
from typing import Dict, Any

from exchanges.mexc.mexc_ws_public import MexcWebSocketPublicStream
from exchanges.mexc.mexc_public import MexcPublicExchange
from structs.exchange import Symbol, AssetName, ExchangeName, StreamType
from exchanges.interface.websocket.base_ws import WebSocketConfig
from common.config import config

logging.basicConfig(level=logging.DEBUG)


class MexcStreamManager:
    """High-level manager combining public exchange and WebSocket streams"""
    
    def __init__(self, api_key: str = None, secret_key: str = None):
        # Use centralized configuration for timeout and WebSocket settings
        self.public_exchange = MexcPublicExchange()
        self.websocket: MexcWebSocketPublicStream = None
        self.symbols: Dict[str, Symbol] = {}
        
        # Log configuration info
        logging.getLogger(__name__).info(f"Environment: {config.ENVIRONMENT.value}")
        logging.getLogger(__name__).info(f"WebSocket timeout: {config.WS_CONNECT_TIMEOUT}s")
        
    async def init(self, symbols: list[Symbol]):
        """Initialize with symbols of interest"""
        await self.public_exchange.init(symbols)
        
        # Store symbol mapping
        for symbol in symbols:
            symbol_str = await self.public_exchange.symbol_to_pair(symbol)
            self.symbols[symbol_str.lower()] = symbol
            
        # Create WebSocket with performance-optimized configuration
        ws_config = WebSocketConfig(
            url="wss://wbs.mexc.com/ws",
            timeout=30.0,
            ping_interval=15.0,
            ping_timeout=5.0,
            close_timeout=3.0,
            max_reconnect_attempts=20,
            reconnect_delay=0.5,
            reconnect_backoff=1.5,
            max_reconnect_delay=30.0,
            max_message_size=2 * 1024 * 1024,
            max_queue_size=5000,
            heartbeat_interval=20.0,
            enable_compression=True
        )
        
        self.websocket = MexcWebSocketPublicStream(
            message_handler=self._handle_stream_message,
            error_handler=self._handle_stream_error,
            config=ws_config
        )
        
    async def _handle_stream_message(self, message: Dict[str, Any]):
        """Handle incoming stream messages"""
        if not message:
            return
            
        msg_type = message.get('type')
        symbol = message.get('symbol')
        data = message.get('data')
        
        if msg_type == 'trades':
            await self._handle_trades(symbol, data)
        elif msg_type == 'depth':
            await self._handle_orderbook(symbol, data)
        elif msg_type == 'ticker':
            await self._handle_ticker(symbol, data)
        else:
            logging.debug(f"Unhandled message type: {msg_type}")
    
    async def _handle_stream_error(self, error: Exception):
        """Handle WebSocket errors"""
        logging.error(f"WebSocket error: {error}")
        # Could implement custom error handling logic here
            
    async def _handle_trades(self, symbol: Symbol, trades: list):
        """Process trade updates"""
        if not trades:
            return
        logging.info(f"[{symbol.base}/{symbol.quote}] Received {len(trades)} trades")
        for trade in trades:
            logging.debug(f"  Trade: {trade.price} @ {trade.amount} ({trade.side.value})")
            
    async def _handle_orderbook(self, symbol: Symbol, orderbook):
        """Process orderbook updates"""
        if not orderbook:
            return
        logging.info(f"[{symbol.base}/{symbol.quote}] Orderbook update - "
                    f"Bids: {len(orderbook.bids)}, Asks: {len(orderbook.asks)}")
        
        if orderbook.bids:
            best_bid = max(orderbook.bids, key=lambda x: x.price)
            logging.debug(f"  Best bid: {best_bid.price} @ {best_bid.size}")
            
        if orderbook.asks:
            best_ask = min(orderbook.asks, key=lambda x: x.price)
            logging.debug(f"  Best ask: {best_ask.price} @ {best_ask.size}")
    
    async def _handle_ticker(self, symbol: Symbol, ticker_data):
        """Process ticker updates"""
        if not ticker_data:
            return
        logging.info(f"[{symbol.base}/{symbol.quote}] Ticker update - "
                    f"Best bid: {ticker_data.get('best_bid_price', 'N/A')} @ {ticker_data.get('best_bid_qty', 'N/A')}, "
                    f"Best ask: {ticker_data.get('best_ask_price', 'N/A')} @ {ticker_data.get('best_ask_qty', 'N/A')}")
        
    async def start_streaming(self):
        """Start streaming data"""
        logging.info("Starting stream manager...")
        
        try:
            # Start the WebSocket connection
            await self.websocket.start()
            
            # Subscribe to streams for all symbols
            await self._subscribe_to_symbols()
            
            # Keep running and monitor health
            self._last_health_log = asyncio.get_event_loop().time()
            
            while True:
                await asyncio.sleep(1)
                
                # Log health status every 30 seconds and check for blocking
                current_time = asyncio.get_event_loop().time()
                if current_time - self._last_health_log > 30:
                    health = await self.websocket.get_health_check()
                    metrics = self.websocket.get_performance_metrics()
                    mexc_health = health.get('mexc_health', {})
                    
                    is_blocked = mexc_health.get('subscription_blocked', False)
                    messages_parsed = metrics.get('mexc_performance', {}).get('messages_parsed', 0)
                    
                    logging.info(f"Health: Connected={health.get('is_connected', False)}, "
                               f"Messages parsed: {messages_parsed}, Blocked: {is_blocked}")
                    
                    # If blocked, log additional info and suggest fallback
                    if is_blocked:
                        logging.warning("MEXC WebSocket subscriptions appear to be blocked!")
                        logging.warning("This is a server-side restriction. Consider:")
                        logging.warning("1. Using REST API fallback")
                        logging.warning("2. Trying from a different IP/region")
                        logging.warning("3. Using a VPN service")
                        break  # Exit the monitoring loop
                    
                    self._last_health_log = current_time
                    
        except KeyboardInterrupt:
            logging.info("Stopping stream manager...")
        finally:
            if self.websocket:
                await self.websocket.stop()
                
                # Print final diagnosis
                try:
                    final_health = await self.websocket.get_health_check()
                    final_metrics = self.websocket.get_performance_metrics()
                    mexc_health = final_health.get('mexc_health', {})
                    
                    if mexc_health.get('subscription_blocked', False):
                        logging.error("\n=== MEXC BLOCKING DETECTED ===")
                        logging.error("MEXC is blocking WebSocket subscriptions from this IP/region.")
                        logging.error("The WebSocket connection works, but subscriptions are ignored.")
                        logging.error("Solution: Use REST API fallback or try from different location.")
                        logging.error("===============================\n")
                except Exception:
                    pass  # Ignore errors during cleanup diagnosis
    
    async def _subscribe_to_symbols(self):
        """Subscribe to WebSocket streams for all configured symbols"""
        streams = []
        
        for symbol_str in self.symbols.keys():
            symbol_upper = symbol_str.upper()
            # Use MEXC stream format
            streams.extend([
                # f"spot@public.depth.v3.api.pb@{symbol_upper}",      # Orderbook
                f"spot@public.aggre.deals.v3.api.pb@10ms@{symbol_upper}",      # Trades
                # f"spot@public.bookTicker.v3.api.pb@{symbol_upper}", # Ticker
            ])
        
        if streams:
            logging.info(f"Subscribing to {len(streams)} streams")
            await self.websocket.subscribe(streams)
        else:
            logging.warning("No streams to subscribe to")


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