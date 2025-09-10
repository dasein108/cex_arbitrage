#!/usr/bin/env python3
"""
Arbitrage monitoring example using PublicExchangeInterface
Demonstrates real-time orderbook monitoring for arbitrage opportunities
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from exchanges.mexc.mexc_public import MexcPublicExchange
from structs.exchange import Symbol, AssetName, OrderBook, ExchangeName

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("arbitrage_monitor")


@dataclass
class ArbitrageOpportunity:
    """Represents a potential arbitrage opportunity"""
    symbol: Symbol
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    spread: float
    spread_percent: float
    potential_profit: float
    timestamp: float


class ArbitrageMonitor:
    """
    High-frequency arbitrage opportunity monitor
    Uses WebSocket streams for real-time orderbook monitoring
    """
    
    def __init__(self, min_spread_percent: float = 0.1, min_volume_usdt: float = 100):
        """
        Initialize arbitrage monitor
        
        Args:
            min_spread_percent: Minimum spread percentage to consider
            min_volume_usdt: Minimum volume in USDT to consider
        """
        self.exchange = MexcPublicExchange()
        self.min_spread_percent = min_spread_percent
        self.min_volume_usdt = min_volume_usdt
        self.opportunities: List[ArbitrageOpportunity] = []
        self.is_monitoring = False
        
    async def initialize(self, symbols: List[Symbol]):
        """Initialize exchange with symbols to monitor"""
        logger.info(f"Initializing arbitrage monitor with {len(symbols)} symbols")
        
        # Initialize exchange - starts WebSocket streams automatically
        await self.exchange.init(symbols)
        
        # Wait for initial data
        logger.info("Waiting for initial orderbook data...")
        await asyncio.sleep(3)
        
        # Verify WebSocket connection
        health = self.exchange.get_websocket_health()
        if not health['is_connected']:
            raise ConnectionError("WebSocket connection failed")
            
        logger.info(f"Monitor initialized - Tracking {health['streams']} streams")
        
    def calculate_arbitrage_opportunity(
        self, 
        symbol: Symbol, 
        orderbook: OrderBook
    ) -> Optional[ArbitrageOpportunity]:
        """
        Calculate arbitrage opportunity from orderbook
        
        Returns:
            ArbitrageOpportunity if profitable, None otherwise
        """
        if not orderbook.bids or not orderbook.asks:
            return None
            
        # Get best bid and ask
        best_bid = orderbook.bids[0]
        best_ask = orderbook.asks[0]
        
        # Calculate spread
        spread = best_ask.price - best_bid.price
        spread_percent = (spread / best_ask.price) * 100
        
        # Check minimum spread requirement
        if spread_percent < self.min_spread_percent:
            return None
            
        # Calculate potential profit (simplified)
        # In reality, would need to account for fees, slippage, etc.
        trade_size = min(best_bid.size, best_ask.size)
        volume_usdt = trade_size * best_bid.price
        
        # Check minimum volume requirement
        if volume_usdt < self.min_volume_usdt:
            return None
            
        # Calculate potential profit (before fees)
        potential_profit = trade_size * spread
        
        return ArbitrageOpportunity(
            symbol=symbol,
            bid_price=best_bid.price,
            bid_size=best_bid.size,
            ask_price=best_ask.price,
            ask_size=best_ask.size,
            spread=spread,
            spread_percent=spread_percent,
            potential_profit=potential_profit,
            timestamp=orderbook.timestamp
        )
        
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan all active symbols for arbitrage opportunities"""
        opportunities = []
        
        for symbol in self.exchange.get_active_symbols():
            # Get real-time orderbook from WebSocket
            orderbook = self.exchange.get_realtime_orderbook(symbol)
            
            if orderbook:
                opportunity = self.calculate_arbitrage_opportunity(symbol, orderbook)
                if opportunity:
                    opportunities.append(opportunity)
                    
        # Sort by potential profit
        opportunities.sort(key=lambda x: x.potential_profit, reverse=True)
        
        return opportunities
        
    async def monitor_spreads(self, interval: float = 0.1):
        """
        Continuously monitor spreads for arbitrage opportunities
        
        Args:
            interval: Scan interval in seconds
        """
        self.is_monitoring = True
        logger.info(f"Starting arbitrage monitoring (interval: {interval}s)")
        
        opportunity_count = 0
        total_scans = 0
        
        while self.is_monitoring:
            try:
                # Scan for opportunities
                opportunities = await self.scan_opportunities()
                total_scans += 1
                
                # Report new opportunities
                for opp in opportunities:
                    if opp not in self.opportunities:  # New opportunity
                        opportunity_count += 1
                        logger.info(
                            f"🎯 OPPORTUNITY #{opportunity_count}: "
                            f"{opp.symbol.base}/{opp.symbol.quote} | "
                            f"Spread: {opp.spread_percent:.3f}% | "
                            f"Profit: ${opp.potential_profit:.2f} | "
                            f"Volume: ${opp.bid_size * opp.bid_price:.0f}"
                        )
                        
                # Update tracked opportunities
                self.opportunities = opportunities
                
                # Brief sleep for high-frequency monitoring
                await asyncio.sleep(interval)
                
                # Periodic statistics
                if total_scans % 100 == 0:
                    active_symbols = len(self.exchange.get_active_symbols())
                    logger.info(
                        f"📊 Stats: Scans={total_scans}, "
                        f"Opportunities={opportunity_count}, "
                        f"Active={len(self.opportunities)}, "
                        f"Symbols={active_symbols}"
                    )
                    
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(1)
                
    async def analyze_market_depth(self, symbol: Symbol) -> Dict:
        """
        Analyze market depth for a symbol
        
        Returns:
            Dictionary with depth analysis metrics
        """
        orderbook = self.exchange.get_realtime_orderbook(symbol)
        
        if not orderbook:
            return {}
            
        # Calculate depth metrics
        bid_depth = sum(entry.size * entry.price for entry in orderbook.bids[:10])
        ask_depth = sum(entry.size * entry.price for entry in orderbook.asks[:10])
        
        # Calculate weighted average prices
        bid_wavg = sum(e.price * e.size for e in orderbook.bids[:5]) / sum(e.size for e in orderbook.bids[:5]) if orderbook.bids else 0
        ask_wavg = sum(e.price * e.size for e in orderbook.asks[:5]) / sum(e.size for e in orderbook.asks[:5]) if orderbook.asks else 0
        
        return {
            'symbol': f"{symbol.base}/{symbol.quote}",
            'bid_depth_usdt': bid_depth,
            'ask_depth_usdt': ask_depth,
            'depth_imbalance': (bid_depth - ask_depth) / (bid_depth + ask_depth) * 100 if (bid_depth + ask_depth) > 0 else 0,
            'bid_wavg': bid_wavg,
            'ask_wavg': ask_wavg,
            'wavg_spread': ask_wavg - bid_wavg,
            'levels': {
                'bids': len(orderbook.bids),
                'asks': len(orderbook.asks)
            }
        }
        
    async def track_spread_changes(self, symbol: Symbol, duration: int = 10):
        """
        Track spread changes over time for a symbol
        
        Args:
            symbol: Symbol to track
            duration: Duration in seconds
        """
        logger.info(f"Tracking spread changes for {symbol.base}/{symbol.quote} for {duration}s")
        
        spreads = []
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < duration:
            orderbook = self.exchange.get_realtime_orderbook(symbol)
            
            if orderbook and orderbook.bids and orderbook.asks:
                spread = orderbook.asks[0].price - orderbook.bids[0].price
                spread_percent = (spread / orderbook.asks[0].price) * 100
                spreads.append({
                    'time': asyncio.get_event_loop().time() - start_time,
                    'spread': spread,
                    'spread_percent': spread_percent,
                    'bid': orderbook.bids[0].price,
                    'ask': orderbook.asks[0].price
                })
                
            await asyncio.sleep(0.1)  # 100ms intervals
            
        # Analyze spread statistics
        if spreads:
            avg_spread = sum(s['spread'] for s in spreads) / len(spreads)
            min_spread = min(s['spread'] for s in spreads)
            max_spread = max(s['spread'] for s in spreads)
            
            logger.info(f"Spread analysis for {symbol.base}/{symbol.quote}:")
            logger.info(f"  Samples: {len(spreads)}")
            logger.info(f"  Average: ${avg_spread:.4f}")
            logger.info(f"  Range: ${min_spread:.4f} - ${max_spread:.4f}")
            logger.info(f"  Volatility: ${max_spread - min_spread:.4f}")
            
        return spreads
        
    async def stop(self):
        """Stop monitoring and cleanup"""
        self.is_monitoring = False
        await self.exchange.stop_all()
        logger.info("Arbitrage monitor stopped")


async def main():
    """Main demonstration"""
    
    # Configure symbols to monitor
    symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
        Symbol(base=AssetName("BNB"), quote=AssetName("USDT")),
        Symbol(base=AssetName("XRP"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ADA"), quote=AssetName("USDT")),
    ]
    
    # Create monitor with configuration
    monitor = ArbitrageMonitor(
        min_spread_percent=0.05,  # 0.05% minimum spread
        min_volume_usdt=100        # $100 minimum volume
    )
    
    try:
        # Initialize
        await monitor.initialize(symbols)
        
        # Analyze market depth for each symbol
        logger.info("\n📊 Market Depth Analysis:")
        for symbol in symbols[:3]:
            depth = await monitor.analyze_market_depth(symbol)
            if depth:
                logger.info(
                    f"  {depth['symbol']}: "
                    f"Bid=${depth['bid_depth_usdt']:.0f}, "
                    f"Ask=${depth['ask_depth_usdt']:.0f}, "
                    f"Imbalance={depth['depth_imbalance']:.1f}%"
                )
                
        # Track spread changes for BTC
        logger.info("\n📈 Spread Tracking:")
        await monitor.track_spread_changes(symbols[0], duration=5)
        
        # Start continuous monitoring
        logger.info("\n🔍 Starting continuous arbitrage monitoring...")
        logger.info("Press Ctrl+C to stop\n")
        
        await monitor.monitor_spreads(interval=0.1)  # 100ms scan interval
        
    except KeyboardInterrupt:
        logger.info("\nStopping monitor...")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await monitor.stop()


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║           Arbitrage Opportunity Monitor                  ║
    ║                                                          ║
    ║  Real-time monitoring using WebSocket streams for:       ║
    ║  • Spread detection                                      ║
    ║  • Market depth analysis                                 ║
    ║  • Opportunity identification                            ║
    ║  • High-frequency scanning (100ms intervals)             ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    asyncio.run(main())