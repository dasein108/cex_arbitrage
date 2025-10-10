"""
Simple Arbitrage PoC - MEXC Spot vs Gate.io Futures

Simplified proof-of-concept implementation to validate arbitrage opportunities
between MEXC spot and Gate.io futures markets.

Key Features:
- Direct REST API calls (no complex WebSocket/event architecture)
- Simple spread calculation using percentages (not basis points)
- Basic entry/exit threshold logic (0.06% entry, 0.03% exit)
- Minimal configuration and dependencies
- Self-contained implementation for easy testing

Usage:
    python src/simple_arbitrage_poc.py
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Tuple
import aiohttp
import logging
from simple_config import load_simple_config, ArbitrageConfig, ExchangeEndpoints

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class BookTicker:
    """Simple book ticker data structure"""
    symbol: str
    bid_price: float
    ask_price: float
    bid_qty: float
    ask_qty: float
    timestamp: float


@dataclass
class ArbitrageOpportunity:
    """Simple arbitrage opportunity data structure"""
    direction: str  # 'spot_to_futures' or 'futures_to_spot'
    spread_pct: float
    entry_price_spot: float
    entry_price_futures: float
    quantity: float
    estimated_profit: float
    timestamp: float


class SimpleArbitragePoC:
    """
    Simplified arbitrage detector for MEXC spot vs Gate.io futures
    
    This PoC implementation focuses on core arbitrage logic without
    complex architecture patterns or extensive error handling.
    """
    
    def __init__(self, 
                 config: ArbitrageConfig = None,
                 endpoints: ExchangeEndpoints = None):
        # Load configuration if not provided
        if config is None or endpoints is None:
            config, endpoints = load_simple_config()
        
        self.symbol = config.symbol
        self.entry_threshold_pct = config.entry_threshold_pct
        self.exit_threshold_pct = config.exit_threshold_pct
        self.position_size = config.position_size
        self.check_interval_seconds = config.check_interval_seconds
        self.monitoring_duration_minutes = config.monitoring_duration_minutes
        
        # API endpoints
        self.mexc_url = endpoints.mexc_url
        self.gateio_url = endpoints.gateio_url
        self.mexc_symbol_format = endpoints.mexc_symbol_format
        self.gateio_symbol_format = endpoints.gateio_symbol_format
        
        # Simple state tracking
        self.current_position: Optional[ArbitrageOpportunity] = None
        self.total_opportunities = 0
        self.total_profit = 0.0
        
    async def get_mexc_book_ticker(self) -> Optional[BookTicker]:
        """Fetch MEXC spot book ticker"""
        try:
            async with aiohttp.ClientSession() as session:
                params = {"symbol": self.mexc_symbol_format}
                async with session.get(self.mexc_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return BookTicker(
                            symbol=data["symbol"],
                            bid_price=float(data["bidPrice"]),
                            ask_price=float(data["askPrice"]),
                            bid_qty=float(data["bidQty"]),
                            ask_qty=float(data["askQty"]),
                            timestamp=time.time()
                        )
        except Exception as e:
            logger.warning(f"MEXC API error: {e}")
            return None
    
    async def get_gateio_book_ticker(self) -> Optional[BookTicker]:
        """Fetch Gate.io futures book ticker"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.gateio_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Find our symbol in the list
                        for ticker in data:
                            if ticker["contract"] == self.gateio_symbol_format:
                                return BookTicker(
                                    symbol=ticker["contract"],
                                    bid_price=float(ticker["bid_price"]),
                                    ask_price=float(ticker["ask_price"]),
                                    bid_qty=float(ticker["bid_size"]),
                                    ask_qty=float(ticker["ask_size"]),
                                    timestamp=time.time()
                                )
        except Exception as e:
            logger.warning(f"Gate.io API error: {e}")
            return None
    
    def calculate_arbitrage_spreads(self, mexc_ticker: BookTicker, gateio_ticker: BookTicker) -> Tuple[float, float]:
        """
        Calculate arbitrage spreads in both directions
        
        Returns:
            (spot_to_futures_spread_pct, futures_to_spot_spread_pct)
        """
        # Direction 1: Buy MEXC spot, Sell Gate.io futures
        spot_buy_price = mexc_ticker.ask_price  # Buy at ask
        futures_sell_price = gateio_ticker.bid_price  # Sell at bid
        spot_to_futures_spread_pct = (futures_sell_price - spot_buy_price) / spot_buy_price * 100
        
        # Direction 2: Buy Gate.io futures, Sell MEXC spot
        futures_buy_price = gateio_ticker.ask_price  # Buy at ask
        spot_sell_price = mexc_ticker.bid_price  # Sell at bid
        futures_to_spot_spread_pct = (spot_sell_price - futures_buy_price) / futures_buy_price * 100
        
        return spot_to_futures_spread_pct, futures_to_spot_spread_pct
    
    def check_entry_opportunity(self, mexc_ticker: BookTicker, gateio_ticker: BookTicker) -> Optional[ArbitrageOpportunity]:
        """Check for arbitrage entry opportunity"""
        if self.current_position is not None:
            return None  # Already in position
        
        spread_spot_to_futures, spread_futures_to_spot = self.calculate_arbitrage_spreads(mexc_ticker, gateio_ticker)
        
        # Check if either direction exceeds entry threshold
        if spread_spot_to_futures >= self.entry_threshold_pct:
            estimated_profit = spread_spot_to_futures / 100 * self.position_size * mexc_ticker.ask_price
            return ArbitrageOpportunity(
                direction="spot_to_futures",
                spread_pct=spread_spot_to_futures,
                entry_price_spot=mexc_ticker.ask_price,
                entry_price_futures=gateio_ticker.bid_price,
                quantity=self.position_size,
                estimated_profit=estimated_profit,
                timestamp=time.time()
            )
        
        elif spread_futures_to_spot >= self.entry_threshold_pct:
            estimated_profit = spread_futures_to_spot / 100 * self.position_size * gateio_ticker.ask_price
            return ArbitrageOpportunity(
                direction="futures_to_spot",
                spread_pct=spread_futures_to_spot,
                entry_price_spot=mexc_ticker.bid_price,
                entry_price_futures=gateio_ticker.ask_price,
                quantity=self.position_size,
                estimated_profit=estimated_profit,
                timestamp=time.time()
            )
        
        return None
    
    def check_exit_opportunity(self, mexc_ticker: BookTicker, gateio_ticker: BookTicker) -> bool:
        """Check if current position should be closed"""
        if self.current_position is None:
            return False
        
        spread_spot_to_futures, spread_futures_to_spot = self.calculate_arbitrage_spreads(mexc_ticker, gateio_ticker)
        
        # Check if spread has narrowed below exit threshold
        if self.current_position.direction == "spot_to_futures":
            return spread_spot_to_futures <= self.exit_threshold_pct
        else:
            return spread_futures_to_spot <= self.exit_threshold_pct
    
    async def run_single_check(self) -> None:
        """Run a single arbitrage opportunity check"""
        # Fetch market data
        mexc_ticker = await self.get_mexc_book_ticker()
        gateio_ticker = await self.get_gateio_book_ticker()
        
        if mexc_ticker is None or gateio_ticker is None:
            logger.warning("Failed to fetch market data")
            return
        
        # Check for exit opportunity first
        if self.check_exit_opportunity(mexc_ticker, gateio_ticker):
            logger.info(f"EXIT SIGNAL: Closing {self.current_position.direction} position")
            logger.info(f"Original spread: {self.current_position.spread_pct:.4f}%")
            self.total_profit += self.current_position.estimated_profit
            self.current_position = None
            return
        
        # Check for entry opportunity
        opportunity = self.check_entry_opportunity(mexc_ticker, gateio_ticker)
        if opportunity:
            self.current_position = opportunity
            self.total_opportunities += 1
            logger.info(f"ENTRY SIGNAL: {opportunity.direction}")
            logger.info(f"Spread: {opportunity.spread_pct:.4f}% | Estimated profit: ${opportunity.estimated_profit:.2f}")
            logger.info(f"MEXC: {mexc_ticker.bid_price:.4f}/{mexc_ticker.ask_price:.4f}")
            logger.info(f"Gate.io: {gateio_ticker.bid_price:.4f}/{gateio_ticker.ask_price:.4f}")
        
        # Log current spreads
        spread_spot_to_futures, spread_futures_to_spot = self.calculate_arbitrage_spreads(mexc_ticker, gateio_ticker)
        logger.debug(f"Spreads: spot->futures {spread_spot_to_futures:.4f}%, futures->spot {spread_futures_to_spot:.4f}%")
    
    async def run_monitoring_loop(self, duration_minutes: int = None, check_interval_seconds: int = None) -> None:
        """Run continuous arbitrage monitoring"""
        # Use configured defaults if not specified
        if duration_minutes is None:
            duration_minutes = self.monitoring_duration_minutes
        if check_interval_seconds is None:
            check_interval_seconds = self.check_interval_seconds
            
        logger.info(f"Starting arbitrage monitoring for {duration_minutes} minutes...")
        logger.info(f"Symbol: {self.symbol} | Entry: {self.entry_threshold_pct}% | Exit: {self.exit_threshold_pct}%")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        while time.time() < end_time:
            await self.run_single_check()
            await asyncio.sleep(check_interval_seconds)
        
        # Final summary
        logger.info("=== MONITORING SUMMARY ===")
        logger.info(f"Total opportunities found: {self.total_opportunities}")
        logger.info(f"Total estimated profit: ${self.total_profit:.2f}")
        logger.info(f"Current position: {self.current_position.direction if self.current_position else 'None'}")


async def main():
    """Main execution function"""
    logger.info("Loading configuration...")
    
    # Load configuration
    config, endpoints = load_simple_config()
    
    # Initialize PoC with loaded configuration
    arbitrage = SimpleArbitragePoC(config=config, endpoints=endpoints)
    
    logger.info(f"Configuration loaded: {config.symbol} | "
                f"Entry: {config.entry_threshold_pct}% | "
                f"Exit: {config.exit_threshold_pct}%")
    
    # Run monitoring loop with configured parameters
    await arbitrage.run_monitoring_loop(
        duration_minutes=config.monitoring_duration_minutes, 
        check_interval_seconds=config.check_interval_seconds
    )


if __name__ == "__main__":
    asyncio.run(main())