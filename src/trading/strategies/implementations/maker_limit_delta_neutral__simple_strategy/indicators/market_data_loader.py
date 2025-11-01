"""
Market Data Loader for Maker Limit Strategy

Handles initial DB data loading with fallback to real-time only mode.
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple
import pandas as pd

from exchanges.structs import ExchangeEnum, Symbol
from exchanges.structs.enums import KlineInterval
from infrastructure.logging import get_logger


class SimpleMarketDataLoader:
    """Loads initial historical data from DB, falls back to real-time only mode."""
    
    def __init__(self):
        self.logger = get_logger("SimpleMarketDataLoader")
        self.historical_loaded = False
        self.book_ticker_source = None
        
    async def load_initial_data(self, exchanges: List[ExchangeEnum], symbol: Symbol, hours: int = 12) -> Dict:
        """Load initial historical data from DB, fallback to real-time only."""
        
        try:
            # Import here to avoid circular dependencies
            from trading.research.cross_arbitrage.arbitrage_analyzer import BookTickerDbSource
            self.book_ticker_source = BookTickerDbSource()
            
            self.logger.info(f"Loading {hours}h historical data for {symbol} from exchanges: {exchanges}")
            
            df = await self.book_ticker_source.get_multi_exchange_data(
                exchanges=exchanges,
                symbol=symbol,
                hours=hours,
                timeframe=KlineInterval.MINUTE_1 # 1-minute timeframe
            )
            
            if df is not None and not df.empty:
                processed_data = self._process_initial_data(df)
                self.historical_loaded = True
                self.logger.info(f"✅ Loaded {len(df)} historical data points")
                return processed_data
            else:
                self.logger.warning("📊 No historical data found, using real-time only")
                return self._create_empty_history()
                
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to load historical data: {e}. Using real-time only mode.")
            self.historical_loaded = False
            return self._create_empty_history()
    
    def _process_initial_data(self, df: pd.DataFrame) -> Dict:
        """Extract price history and spread history from DB data."""
        
        processed = {
            'spot_prices': [],
            'futures_prices': [],
            'spot_spreads': [],
            'futures_spreads': [],
            'timestamps': []
        }
        
        try:
            # Find exchange columns by pattern matching
            spot_bid_col = None
            spot_ask_col = None
            futures_bid_col = None
            futures_ask_col = None
            
            for col in df.columns:
                if 'FUTURES' in col.upper():
                    if 'bid_price' in col:
                        futures_bid_col = col
                    elif 'ask_price' in col:
                        futures_ask_col = col
                else:
                    # Assume non-futures is spot
                    if 'bid_price' in col:
                        spot_bid_col = col
                    elif 'ask_price' in col:
                        spot_ask_col = col
            
            if not all([spot_bid_col, spot_ask_col, futures_bid_col, futures_ask_col]):
                self.logger.error(f"Missing required columns. Found: {list(df.columns)}")
                return self._create_empty_history()
            
            self.logger.info(f"Using columns: spot=({spot_bid_col}, {spot_ask_col}), "
                           f"futures=({futures_bid_col}, {futures_ask_col})")
            
            # Process each row
            for _, row in df.iterrows():
                try:
                    # Extract prices
                    spot_bid = float(row[spot_bid_col])
                    spot_ask = float(row[spot_ask_col])
                    futures_bid = float(row[futures_bid_col])
                    futures_ask = float(row[futures_ask_col])
                    
                    # Skip rows with invalid data
                    if any(price <= 0 for price in [spot_bid, spot_ask, futures_bid, futures_ask]):
                        continue
                    
                    # Calculate mid prices
                    spot_mid = (spot_bid + spot_ask) / 2
                    futures_mid = (futures_bid + futures_ask) / 2
                    
                    # Calculate spread percentages
                    spot_spread_pct = ((spot_ask - spot_bid) / spot_mid) * 100
                    futures_spread_pct = ((futures_ask - futures_bid) / futures_mid) * 100
                    
                    # Store processed data
                    processed['spot_prices'].append(spot_mid)
                    processed['futures_prices'].append(futures_mid)
                    processed['spot_spreads'].append(spot_spread_pct)
                    processed['futures_spreads'].append(futures_spread_pct)
                    processed['timestamps'].append(row.name)  # Index is timestamp
                    
                except (ValueError, KeyError) as e:
                    # Skip invalid rows
                    continue
            
            self.logger.info(f"Processed {len(processed['spot_prices'])} valid data points")
            
        except Exception as e:
            self.logger.error(f"Error processing historical data: {e}")
            return self._create_empty_history()
        
        return processed
    
    def _create_empty_history(self) -> Dict:
        """Create empty history structure for real-time only mode."""
        return {
            'spot_prices': [],
            'futures_prices': [],
            'spot_spreads': [],
            'futures_spreads': [],
            'timestamps': []
        }
    
    @property
    def has_historical_data(self) -> bool:
        """Check if historical data was successfully loaded."""
        return self.historical_loaded