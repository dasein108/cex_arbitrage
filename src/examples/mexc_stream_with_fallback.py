#!/usr/bin/env python3
"""
MEXC WebSocket streaming with fallback to REST API when blocked.

This example demonstrates proper handling of MEXC WebSocket blocking and provides
fallback mechanisms for continued operation.
"""

import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from exchanges.mexc.mexc_ws_public import MexcWebSocketPublicStream
from exchanges.mexc.mexc_public import MexcPublicExchange
from structs.exchange import Symbol, AssetName, ExchangeName, StreamType
from exchanges.interface.websocket.base_ws import WebSocketConfig
from common.exceptions import ExchangeAPIError
from common.config import config

logging.basicConfig(level=logging.INFO)

class MexcStreamManagerWithFallback:
    """MEXC stream manager with REST API fallback when WebSocket is blocked"""
    
    def __init__(self):
        self.public_exchange = MexcPublicExchange()
        self.websocket: MexcWebSocketPublicStream = None
        self.symbols: Dict[str, Symbol] = {}
        self.use_websocket = True
        self.fallback_interval = 5.0  # Seconds between REST API polls
        
        self.logger = logging.getLogger(__name__)
        
    async def init(self, symbols: list[Symbol]):
        """Initialize with symbols of interest"""
        await self.public_exchange.init(symbols)
        
        # Store symbol mapping
        for symbol in symbols:
            symbol_str = await self.public_exchange.symbol_to_pair(symbol)
            self.symbols[symbol_str.lower()] = symbol
        
        # Try to initialize WebSocket
        await self._try_websocket_init()
    
    async def _try_websocket_init(self):
        """Try to initialize WebSocket, handle blocking gracefully"""
        try:
            ws_config = WebSocketConfig(
                url="wss://wbs.mexc.com/ws",
                timeout=10.0,  # Shorter timeout for faster failure detection
                ping_interval=15.0,
                ping_timeout=5.0,
                close_timeout=3.0,
                max_reconnect_attempts=3,  # Fewer attempts since blocking is persistent
                reconnect_delay=2.0,
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
            
            await self.websocket.start()
            
            # Try to subscribe to test if we're blocked
            test_streams = [f"spot@public.depth.v3.api.pb@{next(iter(self.symbols.keys())).upper()}"]
            await self.websocket.subscribe(test_streams)
            
            # Wait a moment to see if we get blocked
            await asyncio.sleep(2.0)
            
            self.logger.info("WebSocket initialized successfully")
            self.use_websocket = True
            
        except ExchangeAPIError as e:
            if "blocked" in str(e).lower():
                self.logger.warning(f"MEXC WebSocket blocked: {e}")
                self.logger.info("Falling back to REST API polling")
                self.use_websocket = False
                if self.websocket:
                    await self.websocket.stop()
                    self.websocket = None
            else:
                raise
        except Exception as e:
            self.logger.error(f"WebSocket initialization failed: {e}")
            self.logger.info("Falling back to REST API polling")
            self.use_websocket = False
            if self.websocket:
                await self.websocket.stop()
                self.websocket = None
    
    async def _handle_stream_message(self, message: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        if not message:
            return
            
        msg_type = message.get('type')
        symbol = message.get('symbol')
        data = message.get('data')
        timestamp = message.get('timestamp', datetime.now().timestamp())
        
        self.logger.info(f"[WebSocket] {msg_type} update for {symbol.base}/{symbol.quote if symbol else 'Unknown'}")
        
        if msg_type == 'depth' and data:
            self.logger.info(f"  Orderbook: {len(data.bids)} bids, {len(data.asks)} asks")
        elif msg_type == 'trades' and data:
            self.logger.info(f"  Trades: {len(data)} recent trades")
        elif msg_type == 'ticker' and data:
            self.logger.info(f"  Ticker: Best bid/ask {data.get('best_bid_price', 'N/A')}/{data.get('best_ask_price', 'N/A')}")
    
    async def _handle_stream_error(self, error: Exception):
        """Handle WebSocket errors"""
        self.logger.error(f"WebSocket error: {error}")
        
        # If we get blocked, switch to REST API fallback
        if "blocked" in str(error).lower():
            self.logger.warning("WebSocket blocked, switching to REST API fallback")
            self.use_websocket = False
            if self.websocket:
                await self.websocket.stop()
                self.websocket = None
    
    async def _rest_api_polling_loop(self):
        """Fallback REST API polling when WebSocket is blocked"""
        self.logger.info(f"Starting REST API polling every {self.fallback_interval}s")
        
        while not self.use_websocket:
            try:
                for symbol_str, symbol in self.symbols.items():
                    # Get orderbook via REST API
                    try:
                        orderbook = await self.public_exchange.get_orderbook(symbol, limit=10)
                        if orderbook:
                            self.logger.info(f"[REST API] Orderbook for {symbol.base}/{symbol.quote}: "
                                           f"{len(orderbook.bids)} bids, {len(orderbook.asks)} asks")
                            if orderbook.bids and orderbook.asks:
                                best_bid = max(orderbook.bids, key=lambda x: x.price)
                                best_ask = min(orderbook.asks, key=lambda x: x.price)
                                self.logger.info(f"  Best: {best_bid.price} / {best_ask.price}")
                    except Exception as e:
                        self.logger.error(f"REST API error for {symbol}: {e}")
                
                await asyncio.sleep(self.fallback_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"REST API polling error: {e}")
                await asyncio.sleep(self.fallback_interval)
    
    async def start_streaming(self):
        """Start streaming with WebSocket or REST fallback"""
        self.logger.info("Starting MEXC stream manager with fallback...")
        
        try:
            if self.use_websocket and self.websocket:
                # Subscribe to all streams
                streams = []
                for symbol_str in self.symbols.keys():
                    symbol_upper = symbol_str.upper()
                    streams.extend([
                        f"spot@public.depth.v3.api.pb@{symbol_upper}",
                        f"spot@public.deals.v3.api.pb@{symbol_upper}",
                        f"spot@public.bookTicker.v3.api.pb@{symbol_upper}",
                    ])
                
                if streams:
                    self.logger.info(f"Subscribing to {len(streams)} WebSocket streams")
                    await self.websocket.subscribe(streams)
                
                # Monitor WebSocket health
                last_health_log = asyncio.get_event_loop().time()
                
                while self.use_websocket:
                    await asyncio.sleep(1)
                    
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_health_log > 30:
                        if self.websocket:
                            health = await self.websocket.get_health_check()
                            metrics = self.websocket.get_performance_metrics()
                            self.logger.info(f"WebSocket health: Connected={health.get('is_connected', False)}, "
                                           f"Messages: {metrics.get('mexc_performance', {}).get('messages_parsed', 0)}")
                        last_health_log = current_time
            
            # If WebSocket not available, use REST API fallback
            if not self.use_websocket:
                await self._rest_api_polling_loop()
                
        except KeyboardInterrupt:
            self.logger.info("Stopping stream manager...")
        finally:
            if self.websocket:
                await self.websocket.stop()


async def main():
    """Example usage with blocking handling"""
    symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
    ]
    
    manager = MexcStreamManagerWithFallback()
    await manager.init(symbols)
    await manager.start_streaming()


if __name__ == "__main__":
    asyncio.run(main())